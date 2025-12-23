#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CQ 覆盖度评估（命令行版）。

用途：把“CQ 测试集（hold-out）用于评估本体覆盖度”的做法落地成可复现实验。
支持：
- 传入单个/多个 TBox（逗号分隔、glob、目录）
- 选择不同表示方式以对齐论文对比：label / definition / label+definition / full
- 输出 CSV 与 Markdown 表格（用于论文直接引用）

示例：
  # 对多个版本 TBox 评估 test CQ 覆盖度（默认 full 表示）
  python3 scripts/run_cq_coverage.py \
    --tboxes "outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_*.json" \
    --cqs outputs/cq_pipeline/final/p1_cqs_test.json \
    --out-csv outputs/cq_coverage/coverage.csv \
    --out-md outputs/cq_coverage/coverage.md

  # 仅用 label（更贴近论文 Type-1：CQ vs labels）
  python3 scripts/run_cq_coverage.py \
    --tboxes "outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_*.json" \
    --cqs outputs/cq_pipeline/final/p1_cqs_test.json \
    --text-mode label \
    --out-csv outputs/cq_coverage/coverage_label.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.cq_coverage import CQCoverageEvaluator


def _expand_tbox_paths(spec: str) -> List[Path]:
    """
    支持三种输入：
    1) 逗号分隔文件列表
    2) glob（含 * ? []）
    3) 目录（读取目录下所有 .json）
    """
    parts = [p.strip() for p in (spec or "").split(",") if p.strip()]
    paths: List[Path] = []
    for p in parts:
        candidate = Path(p)
        if candidate.exists() and candidate.is_dir():
            paths.extend(sorted(candidate.glob("*.json")))
            continue
        if any(ch in p for ch in ["*", "?", "["]):
            paths.extend(sorted(Path().glob(p)))
            continue
        paths.append(candidate)
    # 去重保持顺序
    seen = set()
    out: List[Path] = []
    for p in paths:
        rp = str(p)
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_thresholds(raw: Optional[str]) -> List[float]:
    if not raw:
        return [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    out: List[float] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(float(part))
    return out


@dataclass
class CoverageRow:
    model_name: str
    text_mode: str
    total_count: int
    avg_max_similarity: float
    coverage_by_threshold: Dict[float, float]


def _row_to_flat_dict(row: CoverageRow, thresholds: List[float]) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "model_name": row.model_name,
        "text_mode": row.text_mode,
        "total_count": row.total_count,
        "avg_max_similarity": round(row.avg_max_similarity, 4),
    }
    for t in thresholds:
        d[f"coverage@{t:g}"] = round(row.coverage_by_threshold.get(t, 0.0), 4)
    return d


def _to_markdown(rows: List[CoverageRow], thresholds: List[float]) -> str:
    headers = ["Model", "Mode", "N", "AvgSim"] + [f"Cov@{t:g}" for t in thresholds]
    sep = ["---"] * len(headers)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(sep) + " |"]
    for r in rows:
        cols = [
            r.model_name,
            r.text_mode,
            str(r.total_count),
            f"{r.avg_max_similarity:.4f}",
        ] + [f"{r.coverage_by_threshold.get(t, 0.0):.4f}" for t in thresholds]
        lines.append("| " + " | ".join(cols) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="CQ 覆盖度评估（批量 TBox）")
    parser.add_argument("--tboxes", required=True, help="TBox 文件列表/Glob/目录（可逗号分隔）")
    parser.add_argument("--cqs", required=True, help="CQ 测试集 JSON（含 cqs 字段或数组）")
    parser.add_argument("--text-mode", default="full", help="label|definition|label+definition|full")
    parser.add_argument("--thresholds", default=None, help="阈值列表，逗号分隔，如 0.4,0.5,0.6")
    parser.add_argument("--embedding-model", default="BAAI/bge-base-zh-v1.5", help="SentenceTransformer 模型名/路径")
    parser.add_argument("--device", default="cpu", help="cpu/cuda")
    parser.add_argument("--include-relations", action="store_true", help="纳入关系文本（默认：full 模式下开启）")
    parser.add_argument("--include-attributes", action="store_true", help="纳入属性文本（默认：full 模式下开启）")
    parser.add_argument("--out-csv", default=None, help="输出 CSV 路径")
    parser.add_argument("--out-md", default=None, help="输出 Markdown 路径")
    args = parser.parse_args()

    tbox_paths = _expand_tbox_paths(args.tboxes)
    if not tbox_paths:
        raise FileNotFoundError(f"未找到任何 TBox：{args.tboxes}")
    cqs_path = Path(args.cqs)
    if not cqs_path.exists():
        raise FileNotFoundError(f"CQ 文件不存在：{cqs_path}")

    thresholds = _parse_thresholds(args.thresholds)

    # full 模式默认把 classes/relations/attributes 都纳入；非 full 则只按 text_mode 控制表示
    text_mode = (args.text_mode or "full").strip()
    include_relations = bool(args.include_relations) if text_mode != "full" else True
    include_attributes = bool(args.include_attributes) if text_mode != "full" else True

    evaluator = CQCoverageEvaluator(model_name=args.embedding_model, device=args.device)
    test_cqs = _load_json(cqs_path)

    rows: List[CoverageRow] = []
    for tbox_path in tbox_paths:
        if not tbox_path.exists():
            continue
        tbox = _load_json(tbox_path)
        result = evaluator.evaluate(
            test_cqs,
            tbox,
            thresholds=thresholds,
            text_mode=text_mode,
            include_relations=include_relations,
            include_attributes=include_attributes,
        )
        # result: {threshold -> {cq_coverage, avg_max_similarity, covered_count, total_count, ...}}
        any_key = thresholds[0] if thresholds else next(iter(result.keys()))
        total_count = int(result[any_key].get("total_count", 0))
        avg_max_similarity = float(result[any_key].get("avg_max_similarity", 0.0))
        coverage_by_threshold = {float(k): float(v.get("cq_coverage", 0.0)) for k, v in result.items()}
        rows.append(
            CoverageRow(
                model_name=tbox_path.stem,
                text_mode=text_mode,
                total_count=total_count,
                avg_max_similarity=avg_max_similarity,
                coverage_by_threshold=coverage_by_threshold,
            )
        )

    # 输出
    if args.out_csv:
        out_csv = Path(args.out_csv)
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        with out_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=list(_row_to_flat_dict(rows[0], thresholds).keys()) if rows else [],
            )
            writer.writeheader()
            for r in rows:
                writer.writerow(_row_to_flat_dict(r, thresholds))
        print(f"[CQ-COVERAGE] CSV 已保存：{out_csv}")

    if args.out_md:
        out_md = Path(args.out_md)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(_to_markdown(rows, thresholds), encoding="utf-8")
        print(f"[CQ-COVERAGE] Markdown 已保存：{out_md}")

    if not args.out_csv and not args.out_md:
        print(_to_markdown(rows, thresholds))


if __name__ == "__main__":
    main()

