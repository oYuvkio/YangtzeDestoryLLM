#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""\
基于 Embedding 的 TBox 去重工具（P2 阶段）。

目标：
- 落地论文中的“Embedding 去重（相似度阈值 0.7）”要求；
- 仅做**自动去重**，不再要求人工标注和二次 apply-review；
- 可生成 review.csv 作为人工审阅参考，但流水线本身不依赖人工步骤。

当前版本特性：
- 支持类（classes）和关系（relations）的向量去重；
- 属性（attributes）按 (owner, name) 规则去重合并；
- 默认使用 `BAAI/bge-base-zh-v1.5` + 余弦相似度阈值 0.7；
- 可通过 configs/cfg.yaml 的 `tbox_dedup` 配置覆盖阈值和模型名称。

使用示例：

    # 仅基于 P2 初始 TBox 去重
    python tools/tbox_dedup.py dedup \
        --in-tbox outputs/cq_pipeline/final/p2_tbox_init.json \
        --out-tbox outputs/cq_pipeline/final/p3_tbox_dedup.json \
        --review "outputs/cq_pipeline/final/p3_tbox_review.csv" \
        --log-file logs/kg_tbox/dedup_p2.log

    # 基于已规范化的 P3 TBox 作为基准进行增量去重
    python tools/tbox_dedup.py dedup \
        --in-tbox outputs/cq_pipeline/final/p2_tbox_init.json \
        --base-tbox outputs/cq_pipeline/final/p3_tbox_normalized.json \
        --out-tbox outputs/cq_pipeline/final/p3_tbox_dedup.json \
        --review "outputs/cq_pipeline/final/p3_tbox_review.csv" \
        --log-file logs/kg_tbox/dedup_p2.log

说明：
- 本工具只实现“自动过滤 + 合并”，不依赖人工标注；
- review.csv 仅用于人工抽查和论文分析，不参与后续自动合并逻辑。
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:  # pragma: no cover - 运行环境保证已安装
    yaml = None  # type: ignore
    YAML_AVAILABLE = False

try:
    from kg.utils.deduplication import EmbeddingDeduplicator, DeduplicationResult
    DEDUP_MODULE_AVAILABLE = True
except ImportError:  # pragma: no cover
    EmbeddingDeduplicator = None  # type: ignore
    DeduplicationResult = None  # type: ignore
    DEDUP_MODULE_AVAILABLE = False


# =============================================================================
# 日志配置
# =============================================================================


def setup_logger(name: str = "tbox_dedup", level: int = logging.INFO, log_file: Optional[Path] = None) -> logging.Logger:
    """配置并返回 logger。"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8", mode="a")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


logger = setup_logger()


# =============================================================================
# 配置加载
# =============================================================================


@dataclass
class TBoxDedupConfig:
    model: str = "BAAI/bge-base-zh-v1.5"
    sim_th: float = 0.7
    dedup_base: bool = False
    review_csv_encoding: str = "utf-8"


@dataclass
class DedupStats:
    """去重统计"""

    classes_input: int = 0
    classes_kept: int = 0
    classes_merged: int = 0
    relations_input: int = 0
    relations_kept: int = 0
    relations_merged: int = 0
    attributes_input: int = 0
    attributes_kept: int = 0
    attributes_merged: int = 0

    similarity_distribution: Dict[str, int] = field(
        default_factory=lambda: {
            "0.9-1.0": 0,
            "0.8-0.9": 0,
            "0.7-0.8": 0,
            "0.6-0.7": 0,
            "<0.6": 0,
        }
    )

    def add_similarity(self, sim: float) -> None:
        if sim >= 0.9:
            self.similarity_distribution["0.9-1.0"] += 1
        elif sim >= 0.8:
            self.similarity_distribution["0.8-0.9"] += 1
        elif sim >= 0.7:
            self.similarity_distribution["0.7-0.8"] += 1
        elif sim >= 0.6:
            self.similarity_distribution["0.6-0.7"] += 1
        else:
            self.similarity_distribution["<0.6"] += 1

    def print_report(self, logger: logging.Logger) -> None:
        logger.info("=" * 60)
        logger.info("TBox 去重统计报告")
        logger.info("=" * 60)
        logger.info("类 (Classes):")
        logger.info("  输入: %d", self.classes_input)
        logger.info("  保留: %d", self.classes_kept)
        logger.info("  合并: %d", self.classes_merged)
        logger.info(
            "  去重率: %.1f%%",
            self.classes_merged / max(self.classes_input, 1) * 100.0,
        )
        logger.info("关系 (Relations):")
        logger.info("  输入: %d", self.relations_input)
        logger.info("  保留: %d", self.relations_kept)
        logger.info("  合并: %d", self.relations_merged)
        logger.info(
            "  去重率: %.1f%%",
            self.relations_merged / max(self.relations_input, 1) * 100.0,
        )
        logger.info("属性 (Attributes):")
        logger.info("  输入: %d", self.attributes_input)
        logger.info("  保留: %d", self.attributes_kept)
        logger.info("  合并: %d", self.attributes_merged)
        logger.info("-" * 40)
        logger.info("相似度分布（被合并项）:")
        for band, count in self.similarity_distribution.items():
            if count > 0:
                logger.info("  %s: %d", band, count)
        logger.info("=" * 60)


def load_config() -> TBoxDedupConfig:
    """从 configs/cfg.yaml 加载 tbox_dedup 配置。"""
    cfg_path = PROJECT_ROOT / "configs" / "cfg.yaml"
    if not (cfg_path.exists() and YAML_AVAILABLE):
        logger.warning("未找到 cfg.yaml 或未安装 PyYAML，使用默认去重配置")
        return TBoxDedupConfig()

    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    block = cfg.get("tbox_dedup", {}) or {}
    model = block.get("model") or "BAAI/bge-base-zh-v1.5"
    sim_th = float(block.get("sim_th", 0.7))
    output_cfg = block.get("output", {}) or {}
    review_csv_encoding = output_cfg.get("review_csv_encoding", "utf-8")
    dedup_base = bool(block.get("dedup_base", False))
    return TBoxDedupConfig(
        model=model,
        sim_th=sim_th,
        dedup_base=dedup_base,
        review_csv_encoding=review_csv_encoding,
    )


# =============================================================================
# 核心逻辑
# =============================================================================


def load_tbox(path: Path) -> Dict[str, Any]:
    """加载 TBox JSON 文件为字典。"""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_tbox(tbox: Dict[str, Any], path: Path) -> None:
    """以 UTF-8 保存 TBox JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(tbox, f, ensure_ascii=False, indent=2)


def dedup_tbox_once(
    in_tbox: Dict[str, Any],
    base_tbox: Optional[Dict[str, Any]],
    model_name: str,
    sim_th: float,
    *,
    dedup_base: bool = False,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], DedupStats]:
    """对 TBox 执行一次自动去重。

    返回：
        merged_tbox: 去重后的 TBox
        review_rows: 用于写入 review.csv 的行（可选，用于人工审阅）
        stats: 去重统计信息
    """
    if not DEDUP_MODULE_AVAILABLE:
        raise RuntimeError(
            "kg.utils.deduplication 模块不可用，无法执行 TBox 去重。请确认依赖已安装。"
        )

    classes = in_tbox.get("classes", []) or []
    relations = in_tbox.get("relations", []) or []
    attributes = in_tbox.get("attributes", []) or []

    base_classes = (base_tbox or {}).get("classes", []) or []
    base_relations = (base_tbox or {}).get("relations", []) or []
    base_attributes = (base_tbox or {}).get("attributes", []) or []

    stats = DedupStats(
        classes_input=len(classes),
        relations_input=len(relations),
        attributes_input=len(attributes) + len(base_attributes),
    )

    logger.info(
        "TBox 去重输入规模: classes=%d, relations=%d, attributes(base+new)=%d",
        len(classes),
        len(relations),
        stats.attributes_input,
    )

    dedup = EmbeddingDeduplicator(model_name=model_name, threshold=sim_th)

    # 可选：对基准 TBox 内部也做一次去重
    if dedup_base and base_tbox:
        logger.info("对 base_tbox 内部进行去重（一次性预处理）...")
        base_tbox_clean, base_review_rows, base_stats = dedup_tbox_once(
            in_tbox=base_tbox,
            base_tbox=None,
            model_name=model_name,
            sim_th=sim_th,
            dedup_base=False,
        )
        base_classes = base_tbox_clean.get("classes", []) or []
        base_relations = base_tbox_clean.get("relations", []) or []
        base_attributes = base_tbox_clean.get("attributes", []) or []
        stats.classes_input += base_stats.classes_input
        stats.classes_kept += base_stats.classes_kept
        stats.classes_merged += base_stats.classes_merged
        stats.relations_input += base_stats.relations_input
        stats.relations_kept += base_stats.relations_kept
        stats.relations_merged += base_stats.relations_merged
        stats.attributes_input += base_stats.attributes_input
        stats.attributes_kept += base_stats.attributes_kept
        stats.attributes_merged += base_stats.attributes_merged
        for band, count in base_stats.similarity_distribution.items():
            stats.similarity_distribution[band] = (
                stats.similarity_distribution.get(band, 0) + count
            )
        review_rows: List[Dict[str, Any]] = list(base_review_rows)
    else:
        review_rows = []

    # ---- 类去重 ----
    class_res: DeduplicationResult = dedup.deduplicate_classes(base_classes, classes)
    merged_classes: List[Dict[str, Any]] = list(base_classes) + class_res.accepted
    stats.classes_kept += len(class_res.accepted)
    stats.classes_merged += len(class_res.rejected)

    # ---- 关系去重 ----
    rel_res: DeduplicationResult = dedup.deduplicate_relations(base_relations, relations)
    merged_relations: List[Dict[str, Any]] = list(base_relations) + rel_res.accepted
    stats.relations_kept += len(rel_res.accepted)
    stats.relations_merged += len(rel_res.rejected)

    # ---- 属性去重（按 owner+name 去重，带冲突提示） ----
    merged_attributes: List[Dict[str, Any]] = []
    seen_attr_keys: set = set()
    attr_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def _add_attrs(items: List[Dict[str, Any]], source: str = "base") -> None:
        for a in items:
            owner = a.get("owner")
            name = a.get("name")
            key = (owner, name)
            if not owner or not name:
                logger.warning("属性缺少 owner 或 name (%s): %s", source, a)
                continue
            if key in seen_attr_keys:
                existing = attr_map.get(key)
                if existing and existing.get("value_type") != a.get("value_type"):
                    logger.warning(
                        "属性类型冲突: %s.%s, 已有=%s, 新=%s",
                        owner,
                        name,
                        existing.get("value_type"),
                        a.get("value_type"),
                    )
                continue
            seen_attr_keys.add(key)
            attr_map[key] = a
            merged_attributes.append(a)

    _add_attrs(base_attributes, source="base")
    _add_attrs(attributes, source="new")

    stats.attributes_kept = len(merged_attributes)
    stats.attributes_merged = stats.attributes_input - stats.attributes_kept

    # ---- 构造 review 记录（仅记录被判定为重复的项） ----
    def _find_best_match(
        name: str, collection: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not name:
            return None
        for item in collection:
            if item.get("name") == name:
                return item
        return None

    def _build_review_row(
        elem_type: str,
        candidate: Dict[str, Any],
        best_match: Optional[Dict[str, Any]],
        similarity: float,
    ) -> Dict[str, Any]:
        """构建 review.csv 行。"""
        stats.add_similarity(similarity)
        if similarity >= 0.9:
            merge_rec = "强烈建议合并（高度相似）"
        elif similarity >= 0.8:
            merge_rec = "建议合并（较相似）"
        elif similarity >= 0.7:
            merge_rec = "可考虑合并（边界相似）"
        elif similarity >= 0.6:
            merge_rec = "建议保留（相似度较低）"
        else:
            merge_rec = "建议保留（相似度很低）"

        examples = candidate.get("examples") or []
        if not isinstance(examples, list):
            examples = []

        return {
            "type": elem_type,
            "name": candidate.get("name", ""),
            "cn_name": candidate.get("cn_name", ""),
            "definition": (candidate.get("definition", "") or "")[:200],
            "examples": ",".join(examples[:3]),
            "candidate_id": candidate.get("name", ""),
            "best_match_name": best_match.get("name", "") if best_match else "",
            "best_match_cn_name": best_match.get("cn_name", "") if best_match else "",
            "best_match_definition": (
                (best_match.get("definition", "") or "")[:200]
                if best_match
                else ""
            ),
            "best_match_id": best_match.get("name", "") if best_match else "",
            "similarity": f"{similarity:.4f}",
            "action": "AUTO_MERGE",
            "suggestion": f"auto_merge@{similarity:.2f}",
            "merge_recommendation": merge_rec,
        }

    for c in class_res.rejected:
        sim = float(c.get("_similarity", 0.0))
        best_name = c.get("_similar_to", "")
        best_match = _find_best_match(best_name, base_classes + classes)
        review_rows.append(
            _build_review_row("class", c, best_match=best_match, similarity=sim)
        )

    for r in rel_res.rejected:
        sim = float(r.get("_similarity", 0.0))
        best_name = r.get("_similar_to", "")
        best_match = _find_best_match(best_name, base_relations + relations)
        review_rows.append(
            _build_review_row("relation", r, best_match=best_match, similarity=sim)
        )

    logger.info(
        "TBox 去重完成: classes(keep=%d, dup=%d), relations(keep=%d, dup=%d), attributes(merged=%d)",
        stats.classes_kept,
        stats.classes_merged,
        stats.relations_kept,
        stats.relations_merged,
        stats.attributes_kept,
    )

    merged_tbox = {
        "classes": merged_classes,
        "relations": merged_relations,
        "attributes": merged_attributes,
    }

    return merged_tbox, review_rows, stats


def write_review_csv(rows: List[Dict[str, Any]], path: Path, *, encoding: str = "utf-8") -> None:
    """将去重结果写入 review.csv（供人工审阅/论文使用）。"""
    if not rows:
        logger.info("无重复项，无需生成 review.csv")
        return

    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "type",
        "name",
        "cn_name",
        "definition",
        "examples",
        "candidate_id",
        "best_match_name",
        "best_match_cn_name",
        "best_match_definition",
        "best_match_id",
        "similarity",
        "action",
        "suggestion",
        "merge_recommendation",
    ]

    with path.open("w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    logger.info("review.csv 已写入: %s (共 %d 条)", path, len(rows))


# =============================================================================
# CLI
# =============================================================================


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TBox Embedding 去重工具（P2 阶段）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  # 仅基于 P2 初始 TBox 去重
  python tools/tbox_dedup.py dedup \
      --in-tbox outputs/cq_pipeline/final/p2_tbox_init.json \
      --out-tbox outputs/cq_pipeline/final/p3_tbox_dedup.json \
      --review outputs/cq_pipeline/final/p3_tbox_review.csv \
      --log-file logs/kg_tbox/dedup_p2.log

  # 基于 P3 规范化 TBox 作为基准进行增量去重
  python tools/tbox_dedup.py dedup \
      --in-tbox outputs/cq_pipeline/final/p2_tbox_init.json \
      --base-tbox outputs/cq_pipeline/final/p3_tbox_normalized.json \
      --out-tbox outputs/cq_pipeline/final/p3_tbox_dedup.json \
      --review outputs/cq_pipeline/final/p3_tbox_review.csv \
      --log-file logs/kg_tbox/dedup_p2.log
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    dedup_parser = subparsers.add_parser("dedup", help="执行一次自动 TBox 去重")
    dedup_parser.add_argument("--in-tbox", type=Path, required=True, help="输入 TBox JSON 路径（P2 初始 TBox）")
    dedup_parser.add_argument("--base-tbox", type=Path, default=None, help="基准 TBox JSON 路径（可选，如 P3 规范化 TBox）")
    dedup_parser.add_argument("--out-tbox", type=Path, required=True, help="去重后的 TBox 输出路径")
    dedup_parser.add_argument("--review", type=Path, default=None, help="可选：输出 review.csv 供人工审阅")
    dedup_parser.add_argument("--model", type=str, default=None, help="覆盖配置文件中的 SentenceTransformer 模型名称")
    dedup_parser.add_argument("--sim-th", type=float, default=None, help="覆盖配置中的相似度阈值（默认 0.7）")
    dedup_parser.add_argument("--log-file", type=Path, default=None, help="日志文件路径")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # 重新配置 logger
    global logger
    logger = setup_logger(log_file=args.log_file)

    # 加载配置
    cfg = load_config()
    model_name = args.model or cfg.model
    sim_th = float(args.sim_th if args.sim_th is not None else cfg.sim_th)

    if args.command == "dedup":
        in_path: Path = args.in_tbox
        base_path: Optional[Path] = args.base_tbox
        out_path: Path = args.out_tbox
        review_path: Optional[Path] = args.review

        if not in_path.exists():
            logger.error("输入 TBox 不存在: %s", in_path)
            return 1
        if base_path is not None and not base_path.exists():
            logger.error("基准 TBox 不存在: %s", base_path)
            return 1

        logger.info("=== TBox Embedding 去重（自动模式）===")
        logger.info("in_tbox   = %s", in_path)
        if base_path is not None:
            logger.info("base_tbox = %s", base_path)
        logger.info("out_tbox  = %s", out_path)
        logger.info("model     = %s", model_name)
        logger.info("sim_th    = %.3f", sim_th)

        in_tbox = load_tbox(in_path)
        base_tbox = load_tbox(base_path) if base_path is not None else None

        merged_tbox, review_rows, stats = dedup_tbox_once(
            in_tbox=in_tbox,
            base_tbox=base_tbox,
            model_name=model_name,
            sim_th=sim_th,
            dedup_base=cfg.dedup_base,
        )

        save_tbox(merged_tbox, out_path)
        logger.info("去重后的 TBox 已保存: %s", out_path)

        if review_path is not None:
            write_review_csv(review_rows, review_path, encoding=cfg.review_csv_encoding)

        stats.print_report(logger)
        logger.info("TBox 去重流程完成")
        return 0

    logger.error("未知命令: %s", args.command)
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
