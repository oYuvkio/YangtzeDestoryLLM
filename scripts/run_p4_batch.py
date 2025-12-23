#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P4 文献驱动 TBox 增强批处理脚本。

该脚本从指定语料目录读取文献，调用 LLM 生成模式增强建议，
并根据支持度聚合建议，生成增强后的 TBox。

用法示例:
    # 基础用法（从 TXT 目录）
    python scripts/run_p4_batch.py \
        --base-tbox outputs/cq_pipeline/final/p3_tbox_dedup.json \
        --corpus-dir data/enhancing_onto_corpus_docs
    
    # 从 JSONL 语料文件
    python scripts/run_p4_batch.py \
        --base-tbox outputs/cq_pipeline/final/p3_tbox_dedup.json \
        --corpus-jsonl data/corpus_for_onto/p4_only.jsonl
    
    # 仅合并（跳过 LLM 调用）
    python scripts/run_p4_batch.py --merge-only \
        --agg-file outputs/cq_pipeline/process/p4_corpus_suggestions_agg.json
    
    # 多配置生成
    python scripts/run_p4_batch.py \
        --base-tbox outputs/p3_tbox.json \
        --corpus-dir data/p4_corpus \
        --extra-supports 1,3 \
        --allow-new-classes
    
    # 生成冲突报告
    python scripts/run_p4_batch.py \
        --base-tbox outputs/cq_pipeline/final/p3_tbox_dedup.json \
        --corpus-jsonl data/corpus_for_onto/p4_only.jsonl \
        --conflict-report outputs/ontoqa/p4_conflicts.json
"""
import json
import argparse
import hashlib
import logging
import sys
import random
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import yaml
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()
from kg.cq_pipeline import (
    CQLLMPipeline,
    TBoxSchema,
    ClassDef,
    RelationDef,
    AttributeDef,
)
from kg.utils.schema_alignment import SchemaAligner
from kg.utils.deduplication import EmbeddingDeduplicator
from kg.llm_core import set_logger as set_llm_logger


# ==============================================================================
# 数据结构（整合自 apply_p4.py）
# ==============================================================================
@dataclass
class Conflict:
    """冲突记录"""
    type: str  # signature_conflict, parent_conflict, domain_range_conflict
    element_type: str  # class, relation, attribute
    name: str
    existing_value: str
    new_value: str
    suggestion_doc_id: str = ""
    suggestion_evidence: str = ""
    resolution: str = "pending"  # pending, keep_existing, use_new, manual
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "element_type": self.element_type,
            "name": self.name,
            "existing_value": self.existing_value,
            "new_value": self.new_value,
            "suggestion_doc_id": self.suggestion_doc_id,
            "suggestion_evidence": self.suggestion_evidence,
            "resolution": self.resolution,
        }


@dataclass
class ApplyStats:
    """应用统计"""
    suggestions_total: int = 0
    classes_added: int = 0
    classes_merged: int = 0
    relations_added: int = 0
    relations_merged: int = 0
    attributes_added: int = 0
    attributes_merged: int = 0
    conflicts_total: int = 0
    conflicts_signature: int = 0
    conflicts_parent: int = 0
    conflicts_domain_range: int = 0


class P4Applier:
    """P4 建议应用器（用于冲突检测）"""
    
    def __init__(self, tbox: Dict[str, Any]):
        self.tbox = tbox
        self.stats = ApplyStats()
        self.conflicts: List[Conflict] = []
        
        # 构建索引
        self._class_index: Dict[str, Dict[str, Any]] = {}
        self._relation_index: Dict[str, Dict[str, Any]] = {}
        self._attribute_index: Dict[tuple, Dict[str, Any]] = {}
        
        self._build_indices()
    
    def _build_indices(self) -> None:
        """构建元素索引"""
        for c in self.tbox.get("classes", []):
            name = c.get("name", "")
            if name:
                self._class_index[name] = c
        
        for r in self.tbox.get("relations", []):
            name = r.get("name", "")
            if name:
                self._relation_index[name] = r
        
        for a in self.tbox.get("attributes", []):
            owner = a.get("owner", "")
            name = a.get("name", "")
            if owner and name:
                self._attribute_index[(owner, name)] = a
    
    def apply_suggestion(self, suggestion: Dict[str, Any]) -> None:
        """应用单个建议（检测冲突）"""
        self.stats.suggestions_total += 1
        stype = suggestion.get("type", "").lower()
        name = suggestion.get("name", "")
        
        if not stype or not name:
            return
        
        if stype == "class":
            self._check_class_conflict(suggestion)
        elif stype == "relation":
            self._check_relation_conflict(suggestion)
        elif stype == "attribute":
            self._check_attribute_conflict(suggestion)
    
    def _check_class_conflict(self, suggestion: Dict[str, Any]) -> None:
        """检查类冲突"""
        name = suggestion.get("name", "")
        if name not in self._class_index:
            return
        
        existing = self._class_index[name]
        existing_parent = existing.get("parent", "")
        new_parent = suggestion.get("parent", "")
        
        if new_parent and existing_parent and new_parent != existing_parent:
            self.conflicts.append(Conflict(
                type="parent_conflict",
                element_type="class",
                name=name,
                existing_value=existing_parent,
                new_value=new_parent,
                suggestion_doc_id=suggestion.get("doc_id", ""),
                suggestion_evidence=suggestion.get("evidence_span", ""),
            ))
            self.stats.conflicts_total += 1
            self.stats.conflicts_parent += 1
    
    def _check_relation_conflict(self, suggestion: Dict[str, Any]) -> None:
        """检查关系冲突"""
        name = suggestion.get("name", "")
        if name not in self._relation_index:
            return
        
        existing = self._relation_index[name]
        
        # 解析 domain 和 range
        domain = suggestion.get("domain", "")
        range_ = suggestion.get("range", "")
        if not domain or not range_:
            extra = suggestion.get("parent_or_domain_range_or_owner", "")
            if "->" in extra:
                parts = [p.strip() for p in extra.split("->", 1)]
                if len(parts) == 2:
                    domain = domain or parts[0]
                    range_ = range_ or parts[1]
        
        existing_domain = existing.get("domain", "")
        existing_range = existing.get("range", "")
        
        has_conflict = False
        if domain and existing_domain and domain != existing_domain:
            self.conflicts.append(Conflict(
                type="domain_range_conflict",
                element_type="relation",
                name=f"{name}.domain",
                existing_value=existing_domain,
                new_value=domain,
                suggestion_doc_id=suggestion.get("doc_id", ""),
                suggestion_evidence=suggestion.get("evidence_span", ""),
            ))
            has_conflict = True
        
        if range_ and existing_range and range_ != existing_range:
            self.conflicts.append(Conflict(
                type="domain_range_conflict",
                element_type="relation",
                name=f"{name}.range",
                existing_value=existing_range,
                new_value=range_,
                suggestion_doc_id=suggestion.get("doc_id", ""),
                suggestion_evidence=suggestion.get("evidence_span", ""),
            ))
            has_conflict = True
        
        if has_conflict:
            self.stats.conflicts_total += 1
            self.stats.conflicts_domain_range += 1
    
    def _check_attribute_conflict(self, suggestion: Dict[str, Any]) -> None:
        """检查属性冲突"""
        owner = suggestion.get("owner", "") or suggestion.get("parent_or_domain_range_or_owner", "")
        name = suggestion.get("name", "")
        
        if not owner or not name:
            return
        
        key = (owner, name)
        if key not in self._attribute_index:
            return
        
        existing = self._attribute_index[key]
        existing_type = existing.get("value_type", existing.get("type", ""))
        new_type = suggestion.get("value_type", "")
        
        if new_type and new_type.lower() == "null":
            new_type = ""
        
        if new_type and existing_type and new_type != existing_type:
            self.conflicts.append(Conflict(
                type="signature_conflict",
                element_type="attribute",
                name=f"{owner}.{name}",
                existing_value=existing_type,
                new_value=new_type,
                suggestion_doc_id=suggestion.get("doc_id", ""),
                suggestion_evidence=suggestion.get("evidence_span", ""),
            ))
            self.stats.conflicts_total += 1
            self.stats.conflicts_signature += 1


# ==============================================================================
# 日志配置
# ==============================================================================
def setup_logger(
    name: str = "run_p4_batch",
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    """设置日志器"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()
    
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)
    
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8", mode="a")
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    
    return logger


logger = setup_logger()


def build_tbox(path: Path) -> TBoxSchema:
    """从 JSON 文件构建 TBoxSchema"""
    data = json.loads(path.read_text(encoding="utf-8"))
    return TBoxSchema(
        classes=[ClassDef(**c) for c in data.get("classes", [])],
        relations=[RelationDef(**r) for r in data.get("relations", [])],
        attributes=[AttributeDef(**a) for a in data.get("attributes", [])],
    )


def load_tbox_dict(path: Path) -> Dict[str, Any]:
    """加载 TBox 为字典格式"""
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl_corpus(jsonl_path: Path) -> List[Dict[str, Any]]:
    """加载 JSONL 格式的语料文件"""
    docs = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    docs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return docs


def write_json_with_backup(path: Path, data: dict, version_tag: str) -> None:
    """
    落盘时自动生成带时间戳的备份文件，避免多轮实验覆盖历史产物。
    例：p4_tbox_augmented_supp1_20250310_1530.json
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False,
                    indent=2), encoding="utf-8")
    backup = path.with_name(f"{path.stem}_{version_tag}{path.suffix}")
    backup.write_text(json.dumps(data, ensure_ascii=False,
                      indent=2), encoding="utf-8")
    print(f"[SAVE] 主文件: {path.name}，备份: {backup.name}")


def compute_file_md5(path: Path) -> str:
    """计算文件 MD5"""
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()


def save_run_metadata(
    path: Path,
    args: argparse.Namespace,
    base_tbox_path: Path,
    corpus_path: Optional[Path],
    cfg: Dict[str, Any],
    llm_config: Dict[str, Any],
) -> None:
    """保存实验元数据，确保可复现"""
    meta = {
        "generated_at": datetime.now().isoformat(),
        "base_tbox_path": str(base_tbox_path),
        "base_tbox_md5": compute_file_md5(base_tbox_path),
        "corpus_path": str(corpus_path) if corpus_path else None,
        "corpus_md5": compute_file_md5(corpus_path) if corpus_path else None,
        "args": {
            "min_support": args.min_support,
            "allow_new_classes": args.allow_new_classes,
            "no_auto_allow1": args.no_auto_allow1,
            "align_names": args.align_names,
            "dedup_new": args.dedup_new,
            "dedup_threshold": args.dedup_threshold,
            "conflict_policy": args.conflict_policy,
            "seed": args.seed,
            "max_docs": args.max_docs,
        },
        "llm_config": {
            "provider": llm_config.get("provider"),
            "model_name": llm_config.get("model_name"),
            "temperature": llm_config.get("temperature"),
        },
        "cfg_digest": hashlib.md5(json.dumps(cfg, sort_keys=True).encode()).hexdigest() if cfg else None,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"[元数据] 已保存: {path}")


def merge_suggestions(
    base: TBoxSchema,
    suggestions: List[Dict],
    *,
    allow_new_classes: bool = False,
    min_support: int = 2,
    align_names: bool = False,
    dedup_new: bool = False,
    dedup_threshold: float = 0.8,
    conflict_policy: str = "keep_existing",
    conflict_actions: Optional[List[Dict]] = None,
) -> TBoxSchema:
    """
    根据聚合建议生成增强 TBox。

    规则：
    - 默认不新增类；允许时也需满足 support 阈值；
    - 关系必须有 domain/range 且存在于类集合；
    - 属性必须挂在现有 owner 上。
    
    冲突策略：
    - keep_existing: 保留现有定义，忽略建议
    - use_new: 采用新建议，覆盖旧定义
    - skip_conflicts: 跳过有冲突的建议
    """
    # 名称对齐
    if align_names:
        aligner = SchemaAligner()
        for s in suggestions:
            if s.get("type") == "class":
                s["name"] = aligner.align_class_name(s.get("name", ""))
            elif s.get("type") == "relation":
                s["name"] = aligner.align_relation_name(s.get("name", ""))

    # 构建现有元素索引（用于冲突检测和 use_new 策略）
    class_index = {c.name: i for i, c in enumerate(base.classes)}
    rel_index = {(r.name, r.domain, r.range): i for i, r in enumerate(base.relations)}
    attr_index = {(a.owner, a.name): i for i, a in enumerate(base.attributes)}
    
    class_names = set(class_index.keys())
    rel_keys = set(rel_index.keys())
    attr_keys = set(attr_index.keys())

    new_classes = list(base.classes)
    new_relations = list(base.relations)
    new_attrs = list(base.attributes)
    
    if conflict_actions is None:
        conflict_actions = []

    # 可选：对 class/relation 做 embedding 去重，减少重复
    if dedup_new:
        dedup = EmbeddingDeduplicator(threshold=dedup_threshold)
        base_dict = base.to_dict()
        cand_classes = [s for s in suggestions if s.get("type") == "class"]
        cand_rels = [s for s in suggestions if s.get("type") == "relation"]
        class_res = dedup.deduplicate_classes(base_dict.get("classes", []), cand_classes)
        rel_res = dedup.deduplicate_relations(base_dict.get("relations", []), cand_rels)
        suggestions = class_res.accepted + rel_res.accepted + [s for s in suggestions if s.get("type") == "attribute"]

    for s in suggestions:
        s_type = s.get("type")
        name = s.get("name")
        cn_name = s.get("cn_name", "")
        definition = s.get("definition", "")
        support = int(s.get("_support", 1))
        if not name or support < min_support:
            continue

        if s_type == "class":
            if name in class_names:
                # 冲突检测
                if conflict_policy == "skip_conflicts":
                    conflict_actions.append({"action": "skip", "type": "class", "name": name, "reason": "already_exists"})
                    continue
                elif conflict_policy == "use_new":
                    # 替换现有类
                    idx = class_index[name]
                    old_class = new_classes[idx]
                    new_classes[idx] = ClassDef(
                        name=name, cn_name=cn_name or old_class.cn_name,
                        definition=definition or old_class.definition,
                        parent=s.get("parent", "") or old_class.parent,
                        examples=old_class.examples,
                    )
                    conflict_actions.append({"action": "replaced", "type": "class", "name": name})
                # keep_existing: 不做任何操作
                continue
            
            if not allow_new_classes:
                continue
            new_classes.append(
                ClassDef(name=name, cn_name=cn_name, definition=definition, examples=[]))
            class_names.add(name)
            class_index[name] = len(new_classes) - 1
            
        elif s_type == "relation":
            domain = s.get("parent_or_domain_range_or_owner") or s.get("domain") or ""
            range_ = s.get("range") or ""
            if not domain or not range_ or domain not in class_names or range_ not in class_names:
                continue
            key = (name, domain, range_)
            
            if key in rel_keys:
                if conflict_policy == "skip_conflicts":
                    conflict_actions.append({"action": "skip", "type": "relation", "name": name, "key": str(key)})
                    continue
                elif conflict_policy == "use_new":
                    idx = rel_index[key]
                    old_rel = new_relations[idx]
                    new_relations[idx] = RelationDef(
                        name=name, cn_name=cn_name or old_rel.cn_name,
                        domain=domain, range=range_,
                        definition=definition or old_rel.definition,
                        functional=s.get("functional", old_rel.functional),
                    )
                    conflict_actions.append({"action": "replaced", "type": "relation", "name": name})
                continue
            
            new_relations.append(
                RelationDef(
                    name=name, cn_name=cn_name, domain=domain, range=range_,
                    definition=definition, functional=s.get("functional"),
                )
            )
            rel_keys.add(key)
            rel_index[key] = len(new_relations) - 1
            
        elif s_type == "attribute":
            owner = s.get("parent_or_domain_range_or_owner") or s.get("owner") or ""
            if not owner or owner not in class_names:
                continue
            key = (owner, name)
            
            if key in attr_keys:
                if conflict_policy == "skip_conflicts":
                    conflict_actions.append({"action": "skip", "type": "attribute", "name": f"{owner}.{name}"})
                    continue
                elif conflict_policy == "use_new":
                    idx = attr_index[key]
                    old_attr = new_attrs[idx]
                    new_attrs[idx] = AttributeDef(
                        owner=owner, name=name,
                        cn_name=cn_name or old_attr.cn_name,
                        value_type=s.get("value_type", old_attr.value_type),
                    )
                    conflict_actions.append({"action": "replaced", "type": "attribute", "name": f"{owner}.{name}"})
                continue
            
            new_attrs.append(AttributeDef(
                owner=owner, name=name, cn_name=cn_name, value_type=s.get("value_type", "string")))
            attr_keys.add(key)
            attr_index[key] = len(new_attrs) - 1

    return TBoxSchema(classes=new_classes, relations=new_relations, attributes=new_attrs)


def main():
    """
    P4 批处理：
    - process_dir：存放按文献拆分的 suggestions 以及聚合建议
    - final_dir  ：存放最终/基线 TBox（带时间戳备份）
    """
    parser = argparse.ArgumentParser(description="P4 文献增强 TBox 批处理")
    parser.add_argument("--cfg", default="configs/cfg.yaml", help="默认配置文件，命令行优先级更高")
    parser.add_argument("--base-tbox", default=None,
                        help="基线 TBox 路径（默认 cfg.paths.output_dir/p3_tbox_dedup.json）")
    parser.add_argument("--corpus-dir", default=None,
                        help="增强语料目录（TXT 文件，默认 cfg.paths.p4_corpus_dir）")
    parser.add_argument("--corpus-jsonl", default=None,
                        help="增强语料 JSONL 文件（优先于 --corpus-dir）")
    parser.add_argument("--process-dir", default=None,
                        help="中间结果输出目录（默认 cfg.paths.p4_process_dir）")
    parser.add_argument("--final-dir", default=None,
                        help="最终 TBox 输出目录（默认 cfg.paths.p4_final_dir）")
    parser.add_argument("--min-support", type=int, default=None,
                        help="建议合并的最小支持度，默认读 cfg.p4.min_support 或 2")
    parser.add_argument("--overwrite", action="store_true",
                        help="覆盖已存在的 per-file 建议（默认跳过已完成文件）")
    parser.add_argument("--rerun-empty", action="store_true",
                        help="对已存在但建议为空或包含 error 的文件重跑（不全量覆盖）")
    parser.add_argument("--allow-new-classes", action="store_true",
                        help="合并阶段是否允许新增类（默认读 cfg.p4.allow_new_classes）")
    parser.add_argument("--no-auto-allow1", action="store_true",
                        help="关闭默认的 allow1 额外实验（未开启 allow-new-classes 时默认会自动再跑 allow1）")
    parser.add_argument("--extra-supports", default="",
                        help="额外的 min_support 列表，用逗号分隔，如 1,3")
    parser.add_argument("--agg-file", default=None,
                        help="直接指定聚合建议文件（默认 process_dir/p4_corpus_suggestions_agg.json）")
    parser.add_argument("--merge-only", action="store_true",
                        help="仅基于已有聚合文件做合并，不重新调用 LLM 生成建议")
    parser.add_argument("--align-names", action="store_true",
                        help="合并前对建议做同义归一（SchemaAligner），默认读 cfg.p4.align_synonyms")
    parser.add_argument("--dedup-new", action="store_true",
                        help="对新增类/关系做 embedding 去重，减少重复（阈值见 --dedup-threshold），默认读 cfg.p4.dedup_with_embeddings")
    parser.add_argument("--dedup-threshold", type=float, default=None,
                        help="去重相似度阈值，默认读 cfg.p4.dedup_threshold 或 0.8")
    parser.add_argument("--conflict-report", default=None,
                        help="冲突报告输出路径（可选）")
    parser.add_argument("--out-suggestions", default=None,
                        help="建议 JSONL 输出路径（可选，用于兼容新模块）")
    parser.add_argument("--max-docs", type=int, default=None,
                        help="最大处理文档数（用于测试）")
    parser.add_argument("--seed", type=int, default=42,
                        help="随机种子（默认 42）")
    parser.add_argument("--log-file", type=Path, default=None,
                        help="日志文件路径")
    parser.add_argument("--conflict-policy", default="keep_existing",
                        choices=["keep_existing", "use_new", "skip_conflicts"],
                        help="冲突处理策略: keep_existing(保留旧), use_new(采用新), skip_conflicts(跳过)")
    args = parser.parse_args()
    
    # 设置日志
    global logger
    if args.log_file:
        logger = setup_logger(log_file=args.log_file)
    # 让 llm_core 模块复用当前 logger，方便统一输出详细调试信息
    try:
        set_llm_logger(logger)
    except Exception:
        pass

    cfg: Dict[str, any] = {}
    # 默认加载 configs/cfg.yaml
    cfg_path = Path(args.cfg) if args.cfg else Path("configs/cfg.yaml")
    if cfg_path.exists():
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            logger.info(f"加载配置文件: {cfg_path}")
        except Exception as e:
            logger.warning(f"配置文件加载失败: {e}")
            cfg = {}
    else:
        logger.warning(f"未找到配置文件: {cfg_path}")

    def pick(*vals, default=None):
        for v in vals:
            if v not in [None, ""]:
                return v
        return default

    cfg_paths = cfg.get("paths", {}) if isinstance(cfg, dict) else {}
    cfg_p4 = cfg.get("p4", {}) if isinstance(cfg, dict) else {}

    version_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_dir = Path(pick(args.final_dir, cfg_paths.get("p4_final_dir"), "outputs/cq_pipeline/final"))
    process_dir = Path(pick(args.process_dir, cfg_paths.get("p4_process_dir"), "outputs/cq_pipeline/process"))
    final_dir.mkdir(parents=True, exist_ok=True)
    process_dir.mkdir(parents=True, exist_ok=True)

    base_dir = pick(args.base_tbox, cfg_paths.get("output_dir"), "outputs/cq_pipeline/final")
    base_path = Path(base_dir) if args.base_tbox else Path(base_dir) / "p3_tbox_dedup.json"
    if not base_path.exists():
        # 回退到旧名称
        base_path_alt = base_path.parent / "p3_tbox_normalized.json"
        if base_path_alt.exists():
            base_path = base_path_alt
        else:
            logger.error(f"未找到基线 TBox：{base_path}，请先完成 P1-P3。")
            return
    base = build_tbox(base_path)
    base_dict = load_tbox_dict(base_path)
    logger.info(f"加载基线 TBox: {base_path}")
    logger.info(f"  - 类: {len(base.classes)}, 关系: {len(base.relations)}, 属性: {len(base.attributes)}")

    agg_path = Path(args.agg_file) if args.agg_file else process_dir / "p4_corpus_suggestions_agg.json"

    # 支持 JSONL 格式语料（优先）或 TXT 目录
    # merge-only 模式下不强制要求语料存在
    corpus_jsonl = Path(args.corpus_jsonl) if args.corpus_jsonl else None
    corpus_dir = Path(pick(args.corpus_dir, cfg_paths.get("p4_corpus_dir"), "data/enhancing_onto_corpus_docs"))
    use_jsonl = False

    if args.merge_only:
        if not agg_path.exists():
            logger.error(f"[P4] merge-only 模式未找到聚合文件：{agg_path}")
            return
    else:
        if corpus_jsonl and corpus_jsonl.exists():
            use_jsonl = True
            logger.info(f"使用 JSONL 语料: {corpus_jsonl}")
        elif not corpus_dir.exists():
            logger.error(f"未找到语料目录：{corpus_dir}")
            return
        else:
            logger.info(f"使用 TXT 语料目录: {corpus_dir}")

    # 从 cfg.yaml 加载 LLM 配置（merge-only 时无需初始化）
    cfg_llm = cfg.get("llm", {})
    pipeline = None
    if not args.merge_only:
        pipeline = CQLLMPipeline(llm_config=cfg_llm)
        if cfg_llm:
            logger.info(f"[LLM][P4] model={cfg_llm.get('model_name')}, temperature={cfg_llm.get('temperature')}")

    aggregated: List[Dict] = []
    processed, skipped_existing, failed = [], [], []
    processed_src, skipped_src = [], []
    quota_exhausted = False
    sleep_between_calls = bool(cfg_p4.get("sleep_between_calls", True))
    sleep_min_sec_raw = cfg_p4.get("sleep_min_sec", 2)
    sleep_max_sec_raw = cfg_p4.get("sleep_max_sec", 5)
    try:
        sleep_min_sec = float(sleep_min_sec_raw)
    except Exception:
        sleep_min_sec = 2.0
    try:
        sleep_max_sec = float(sleep_max_sec_raw)
    except Exception:
        sleep_max_sec = 5.0
    if sleep_min_sec < 0:
        sleep_min_sec = 0.0
    if sleep_max_sec < sleep_min_sec:
        logger.warning(
            f"[P4] sleep_max_sec({sleep_max_sec}) < sleep_min_sec({sleep_min_sec})，"
            "已自动对齐为相同值。"
        )
        sleep_max_sec = sleep_min_sec
    if sleep_between_calls:
        logger.info(
            f"[P4] 已启用调用间隔随机休眠（{sleep_min_sec}-{sleep_max_sec}s）以避免限流。"
        )
    else:
        logger.info("[P4] 已关闭调用间隔休眠。")

    def is_quota_error(msg: str) -> bool:
        lower = msg.lower()
        return ("quota" in lower) or ("insufficient" in lower) or ("429" in lower)

    def truncate_text_for_log(text: str, max_chars: int = 800) -> str:
        """截断文本用于日志打印，避免过长。"""
        clean_text = text.replace("\n", " ").strip()
        if max_chars <= 0:
            return clean_text
        if len(clean_text) <= max_chars:
            return clean_text
        return clean_text[:max_chars] + f"...(截断，原长 {len(clean_text)} 字)"

    def flush_log_handlers() -> None:
        """刷新日志 handlers，确保每次调用及时落盘。"""
        for handler in logger.handlers:
            try:
                handler.flush()
            except Exception:
                continue

    # 初始化 raw_suggestions（所有路径共用）
    raw_suggestions = []
    files = []
    jsonl_docs = []
    
    if args.merge_only and agg_path.exists():
        logger.info(f"[P4] merge-only 模式，读取已有聚合文件：{agg_path}")
        aggregated = json.loads(agg_path.read_text(
            encoding="utf-8")).get("suggestions", [])
    elif use_jsonl:
        # 使用 JSONL 格式语料
        jsonl_docs = load_jsonl_corpus(corpus_jsonl)
        if args.max_docs and len(jsonl_docs) > args.max_docs:
            random.seed(args.seed)
            random.shuffle(jsonl_docs)
            jsonl_docs = jsonl_docs[:args.max_docs]
        logger.info(f"[P4] 加载 JSONL 语料 {len(jsonl_docs)} 条")
        
        # 处理 JSONL 格式语料（支持断点续跑）
        suggestions_jsonl_path = Path(args.out_suggestions) if args.out_suggestions else process_dir / "p4_suggestions.jsonl"
        suggestions_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 断点续跑：读取已处理的 doc_id
        processed_doc_ids: set = set()
        if suggestions_jsonl_path.exists() and not args.overwrite:
            logger.info(f"[P4] 检测到已有建议文件，启用断点续跑模式...")
            with suggestions_jsonl_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            s = json.loads(line)
                            doc_id = s.get("doc_id", s.get("_source", ""))
                            if doc_id:
                                processed_doc_ids.add(doc_id)
                            raw_suggestions.append(s)  # 加载已有建议
                        except json.JSONDecodeError:
                            continue
            logger.info(f"[P4] 已处理文档: {len(processed_doc_ids)} 个，已有建议: {len(raw_suggestions)} 条")
            skipped_src.extend(list(processed_doc_ids))
        
        # 筛选待处理文档
        docs_to_process = []
        for i, doc in enumerate(jsonl_docs):
            doc_id = doc.get("id", doc.get("doc_id", f"doc_{i}"))
            if doc_id not in processed_doc_ids:
                docs_to_process.append((i, doc, doc_id))
        
        if not docs_to_process:
            logger.info("[P4] 所有文档已处理完成，无需重新生成。")
        else:
            logger.info(f"[P4] 待处理文档: {len(docs_to_process)} 个，开始生成 suggestions...")
            
            # 使用追加模式写入
            write_mode = "a" if processed_doc_ids else "w"
            with suggestions_jsonl_path.open(write_mode, encoding="utf-8") as out_f:
                for idx, (i, doc, doc_id) in enumerate(docs_to_process):
                    if quota_exhausted:
                        break
                    
                    doc_text = doc.get("text", "")
                    doc_title = doc.get("title", doc.get("doc_title", ""))
                    
                    if not doc_text.strip():
                        continue
                    
                    if (idx + 1) % 50 == 0 or (idx + 1) == len(docs_to_process):
                        logger.info(f"[P4] 进度: {idx+1}/{len(docs_to_process)} (总: {len(processed_doc_ids) + idx + 1}/{len(jsonl_docs)})")
                    
                    doc_index = idx + 1
                    total_docs = len(docs_to_process)
                    logger.info("=" * 80)
                    logger.info(
                        f"[P4][LLM] 准备调用 enhance_schema: idx={doc_index}/{total_docs}, "
                        f"doc_id={doc_id}, title={doc_title}, text_len={len(doc_text)}"
                    )
                    logger.info(f"[P4][LLM] 输入预览: {truncate_text_for_log(doc_text)}")
                    flush_log_handlers()

                    try:
                        res = pipeline.enhance_schema(base, doc_text)
                        suggestions = res.get("suggestions", []) or []
                        for suggestion in suggestions:
                            suggestion["_source"] = doc_id
                            suggestion["doc_id"] = doc_id
                            suggestion["doc_title"] = doc_title
                            out_f.write(json.dumps(suggestion, ensure_ascii=False) + "\n")
                        out_f.flush()
                        raw_suggestions.extend(suggestions)
                        processed_src.append(doc_id)
                        
                        res_preview = truncate_text_for_log(
                            json.dumps(res, ensure_ascii=False),
                            max_chars=2000,
                        )
                        logger.info(
                            f"[P4][LLM] 调用完成: doc_id={doc_id}, suggestions={len(suggestions)}"
                        )
                        logger.info(f"[P4][LLM] 输出预览: {res_preview}")
                        if suggestions:
                            for suggestion in suggestions:
                                sug_type = suggestion.get("type", "")
                                sug_name = suggestion.get("name", "")
                                sug_extra = (
                                    suggestion.get("parent_or_domain_range_or_owner", "")
                                    or suggestion.get("parent", "")
                                    or suggestion.get("domain", "")
                                    or suggestion.get("owner", "")
                                )
                                sug_range = suggestion.get("range", "")
                                logger.info(
                                    f"[P4][LLM] 建议: type={sug_type}, name={sug_name}, "
                                    f"extra={sug_extra}, range={sug_range}"
                        )
                        flush_log_handlers()
                    except Exception as exc:
                        msg = str(exc)
                        failed.append((doc_id, msg))
                        logger.warning(f"[P4][LLM] 调用失败: doc_id={doc_id}, error={msg}")
                        flush_log_handlers()
                        if is_quota_error(msg):
                            quota_exhausted = True
                            logger.error("[P4] 检测到配额/429错误，停止后续任务。")
                            break
                    finally:
                        if sleep_between_calls and doc_index < total_docs and not quota_exhausted:
                            sleep_seconds = random.uniform(sleep_min_sec, sleep_max_sec)
                            sleep_seconds_display = round(sleep_seconds, 2)
                            logger.info(
                                f"[P4][LLM] 休眠 {sleep_seconds_display}s 以避免限流..."
                            )
                            flush_log_handlers()
                            time.sleep(sleep_seconds)
        
        logger.info(f"[P4] 建议已保存到: {suggestions_jsonl_path}（共 {len(raw_suggestions)} 条）")
    else:
        # 使用 TXT 目录
        files = sorted(corpus_dir.rglob("*.txt"))
        if args.max_docs and len(files) > args.max_docs:
            files = files[:args.max_docs]
        if not files:
            logger.error(f"未找到语料文件，目录为空：{corpus_dir}")
            return
        logger.info(
            f"[P4] 发现语料 {len(files)} 篇，开始逐篇生成 suggestions（存储在 {process_dir}）...")
        
        # 处理 TXT 文件
        total_docs = len(files)
        for doc_index, fp in enumerate(files, start=1):
            if quota_exhausted:
                break
            doc_text = fp.read_text(encoding="utf-8")
            try:
                rel = fp.relative_to(corpus_dir).with_suffix("")
                rel_dir = rel.parent
                stem = rel.name
            except ValueError:
                rel_dir = None
                stem = fp.stem

            per_doc_dir = process_dir / rel_dir if rel_dir else process_dir
            per_doc_dir.mkdir(parents=True, exist_ok=True)
            per_doc_path = per_doc_dir / f"{stem}_suggestions.json"
            # 若文件已存在且不覆盖，判断是否需要重跑
            if per_doc_path.exists() and not args.overwrite:
                try:
                    existing_json = json.loads(
                        per_doc_path.read_text(encoding="utf-8"))
                    existing = existing_json.get("suggestions", [])
                    has_error = "error" in existing_json
                    need_rerun = False
                    if args.rerun_empty and (has_error or len(existing) == 0):
                        need_rerun = True
                    if not need_rerun:
                        raw_suggestions.extend(existing)
                        skipped_existing.append(str(per_doc_path))
                        skipped_src.append(str(fp))
                        print(
                            f"[P4] 跳过已存在: {per_doc_path} (建议 {len(existing)} 条，error={has_error})")
                        continue
                    else:
                        print(f"[P4] 重跑空/错误文件: {per_doc_path}")
                except Exception:
                    # 解析失败则继续重跑
                    pass

            logger.info("=" * 80)
            logger.info(
                f"[P4][LLM] 准备调用 enhance_schema: file={fp.name}, text_len={len(doc_text)}"
            )
            logger.info(f"[P4][LLM] 输入预览: {truncate_text_for_log(doc_text)}")
            flush_log_handlers()

            try:
                res = pipeline.enhance_schema(base, doc_text)
                suggestions = res.get("suggestions", []) or []
                for suggestion in suggestions:
                    suggestion["_source"] = fp.name
                raw_suggestions.extend(suggestions)
                per_doc_path.write_text(
                    json.dumps({"suggestions": suggestions},
                               ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                processed.append(str(per_doc_path))
                processed_src.append(str(fp))
                
                res_preview = truncate_text_for_log(
                    json.dumps(res, ensure_ascii=False),
                    max_chars=2000,
                )
                logger.info(
                    f"[P4][LLM] 调用完成: file={fp.name}, suggestions={len(suggestions)}"
                )
                logger.info(f"[P4][LLM] 输出预览: {res_preview}")
                if suggestions:
                    for suggestion in suggestions:
                        sug_type = suggestion.get("type", "")
                        sug_name = suggestion.get("name", "")
                        sug_extra = (
                            suggestion.get("parent_or_domain_range_or_owner", "")
                            or suggestion.get("parent", "")
                            or suggestion.get("domain", "")
                            or suggestion.get("owner", "")
                        )
                        sug_range = suggestion.get("range", "")
                        logger.info(
                            f"[P4][LLM] 建议: type={sug_type}, name={sug_name}, "
                            f"extra={sug_extra}, range={sug_range}"
                        )
                flush_log_handlers()
                logger.info(f"[P4] {fp.name} -> {per_doc_path}，共 {len(suggestions)} 条建议")
            except Exception as exc:
                msg = str(exc)
                failed.append((str(fp), msg))
                per_doc_path.write_text(
                    json.dumps({"suggestions": [], "error": msg},
                               ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                logger.warning(f"[P4][LLM] 调用失败: file={fp.name}, error={msg}")
                flush_log_handlers()
                if is_quota_error(msg):
                    quota_exhausted = True
                    logger.error("[P4] 检测到配额/429错误，停止后续任务。")
                    break
            finally:
                if sleep_between_calls and doc_index < total_docs and not quota_exhausted:
                    sleep_seconds = random.uniform(sleep_min_sec, sleep_max_sec)
                    sleep_seconds_display = round(sleep_seconds, 2)
                    logger.info(
                        f"[P4][LLM] 休眠 {sleep_seconds_display}s 以避免限流..."
                    )
                    flush_log_handlers()
                    time.sleep(sleep_seconds)

    # 聚合与频次统计（_support + _support_sources）
    # 只在非 merge-only 模式下执行
    if not (args.merge_only and agg_path.exists()):
        logger.info("[P4] 开始聚合建议并统计支持度...")
        
        # 可选：聚合前做名称规整/同义映射
        align_before_agg = bool(pick(args.align_names, cfg_p4.get("align_synonyms"), False))
        aligner = SchemaAligner() if align_before_agg else None
        
        def normalize_name(s: Dict[str, Any]) -> Dict[str, Any]:
            """规整名称：strip、同义对齐"""
            s = dict(s)  # 复制
            name = s.get("name", "").strip()
            s_type = s.get("type", "").lower()
            
            if aligner:
                if s_type == "class":
                    name = aligner.align_class_name(name)
                elif s_type == "relation":
                    name = aligner.align_relation_name(name)
            
            s["name"] = name
            
            # 规整 owner/domain/range
            for field in ["owner", "domain", "range", "parent"]:
                if s.get(field):
                    s[field] = s[field].strip()
            
            return s
        
        suggestion_buckets: Dict[tuple, Dict[str, Any]] = {}
        for s in raw_suggestions:
            s = normalize_name(s)
            s_type = s.get("type")
            name = s.get("name")
            if not s_type or not name:
                continue
            parent_or_owner = s.get("parent_or_domain_range_or_owner") or s.get(
                "owner") or s.get("domain") or ""
            range_ = s.get("range") or ""
            key = (s_type, name, parent_or_owner, range_)
            doc_id = s.get("doc_id", s.get("_source", ""))
            
            if key not in suggestion_buckets:
                s["_support"] = 1
                s["_support_sources"] = [doc_id] if doc_id else []
                suggestion_buckets[key] = s
            else:
                suggestion_buckets[key]["_support"] += 1
                # 记录来源（去重）
                if doc_id and doc_id not in suggestion_buckets[key].get("_support_sources", []):
                    suggestion_buckets[key].setdefault("_support_sources", []).append(doc_id)

        aggregated = list(suggestion_buckets.values())
        agg_path.write_text(
            json.dumps({"suggestions": aggregated},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"[P4] 聚合建议已写入：{agg_path}，总计 {len(aggregated)} 条")
        
        # 统计建议类型分布
        class_count = sum(1 for s in aggregated if s.get("type") == "class")
        rel_count = sum(1 for s in aggregated if s.get("type") == "relation")
        attr_count = sum(1 for s in aggregated if s.get("type") == "attribute")
        logger.info(f"  - 类建议: {class_count}, 关系建议: {rel_count}, 属性建议: {attr_count}")

    # 使用多组配置生成增强 TBox
    min_support_cfg = cfg_p4.get("min_support", 2)
    supports = {pick(args.min_support, min_support_cfg, 2)}
    if args.extra_supports:
        for s in args.extra_supports.split(","):
            s = s.strip()
            if s.isdigit():
                supports.add(int(s))

    configs = []
    for sup in sorted(supports):
        configs.append((sup, args.allow_new_classes,
                        f"s{sup}_allow{int(args.allow_new_classes)}"))
        if not args.allow_new_classes and not args.no_auto_allow1:
            configs.append((sup, True, f"s{sup}_allow1"))

    # 默认为 cfg 或参数的 allow_new_classes
    allow_new_default = pick(args.allow_new_classes, cfg_p4.get("allow_new_classes"), False)
    align_names = bool(pick(args.align_names, cfg_p4.get("align_synonyms"), False))
    dedup_new = bool(pick(args.dedup_new, cfg_p4.get("dedup_with_embeddings"), False))
    dedup_threshold = float(pick(args.dedup_threshold, cfg_p4.get("dedup_threshold"), 0.8))

    # 冲突收集与冲突动作记录
    all_conflicts: List[Dict] = []
    all_conflict_actions: List[Dict] = []
    
    for sup, allow_cls, suffix in configs:
        allow_flag = allow_cls if args.allow_new_classes else allow_new_default if allow_cls else allow_cls
        conflict_actions: List[Dict] = []
        tbox_aug = merge_suggestions(
            base,
            aggregated,
            allow_new_classes=allow_flag,
            min_support=sup,
            align_names=align_names,
            dedup_new=dedup_new,
            dedup_threshold=dedup_threshold,
            conflict_policy=args.conflict_policy,
            conflict_actions=conflict_actions,
        )
        out_path = final_dir / f"p4_tbox_augmented_{suffix}.json"
        write_json_with_backup(out_path, tbox_aug.to_dict(), version_tag)
        
        # 记录冲突动作
        if conflict_actions:
            all_conflict_actions.extend([
                {**ca, "config": suffix} for ca in conflict_actions
            ])
        
        # 统计增强结果
        added_classes = len(tbox_aug.classes) - len(base.classes)
        added_rels = len(tbox_aug.relations) - len(base.relations)
        added_attrs = len(tbox_aug.attributes) - len(base.attributes)
        logger.info(
            f"[P4] 已生成增强 TBox (allow_new_classes={allow_flag}, min_support={sup}, policy={args.conflict_policy}) -> {out_path.name}")
        logger.info(
            f"     新增: 类 +{added_classes}, 关系 +{added_rels}, 属性 +{added_attrs}")
    
    # 保存冲突动作日志
    if all_conflict_actions:
        conflict_actions_path = process_dir / "p4_conflict_actions.jsonl"
        with conflict_actions_path.open("w", encoding="utf-8") as f:
            for ca in all_conflict_actions:
                f.write(json.dumps(ca, ensure_ascii=False) + "\n")
        logger.info(f"[P4] 冲突动作日志已保存: {conflict_actions_path} ({len(all_conflict_actions)} 条)")
    
    # 生成冲突报告（如果指定）
    if args.conflict_report:
        conflict_path = Path(args.conflict_report)
        # 使用 P4Applier 检测冲突
        applier = P4Applier(dict(base_dict))  # 使用副本
        for s in aggregated:
            applier.apply_suggestion(s)
        
        if applier.conflicts:
            conflict_report = {
                "generated_at": datetime.now().isoformat(),
                "summary": {
                    "total_conflicts": applier.stats.conflicts_total,
                    "signature_conflicts": applier.stats.conflicts_signature,
                    "parent_conflicts": applier.stats.conflicts_parent,
                    "domain_range_conflicts": applier.stats.conflicts_domain_range,
                },
                "conflicts": [c.to_dict() for c in applier.conflicts],
            }
            conflict_path.parent.mkdir(parents=True, exist_ok=True)
            conflict_path.write_text(
                json.dumps(conflict_report, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.info(f"[P4] 冲突报告已保存: {conflict_path}")
            logger.info(f"     共 {applier.stats.conflicts_total} 条冲突")
        else:
            logger.info("[P4] 无冲突检测到")
    # 保存进度
    seen_src = set(processed_src) | set(skipped_src) | {p for p, _e in failed}
    not_processed = [str(f) for f in files if str(f) not in seen_src]
    progress = {
        "processed": processed,
        "skipped_existing": skipped_existing,
        "failed": failed,
        "total_files": len(files),
        "quota_exhausted": quota_exhausted,
        "not_processed": not_processed,
    }
    progress_path = process_dir / "_p4_progress.json"
    progress_path.write_text(json.dumps(
        progress, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"[P4] 处理完成。进度已保存：{progress_path}")
    
    # 最终统计
    logger.info("=" * 60)
    logger.info("P4 批处理完成")
    logger.info("=" * 60)
    logger.info(f"处理文档: {len(processed_src)} 成功, {len(failed)} 失败, {len(skipped_src)} 跳过")
    logger.info(f"聚合建议: {len(aggregated)} 条")
    if quota_exhausted:
        logger.warning("注意: 因配额限制提前终止")
    
    # 保存实验元数据
    meta_path = process_dir / "p4_run_meta.json"
    corpus_path_for_meta = corpus_jsonl if use_jsonl else corpus_dir
    save_run_metadata(
        path=meta_path,
        args=args,
        base_tbox_path=base_path,
        corpus_path=corpus_path_for_meta,
        cfg=cfg,
        llm_config=cfg_llm,
    )


if __name__ == "__main__":
    main()
