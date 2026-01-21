#!/usr/bin/env python3
"""
合并多 worker 的消融输出结果（按 doc_id 去重）。
默认合并 *_<id> 目录下的 predictions.jsonl 到原输出目录。
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


def parse_list(value: str) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def load_jsonl(path: Path) -> Tuple[Dict[str, dict], List[str], int]:
    records: Dict[str, dict] = {}
    order: List[str] = []
    total = 0
    if not path.exists():
        return records, order, total
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            doc_id = record.get("doc_id")
            if not doc_id:
                continue
            if doc_id not in records:
                order.append(doc_id)
            records[doc_id] = record
    return records, order, total


def main() -> None:
    parser = argparse.ArgumentParser(description="合并多 worker 输出（按 doc_id 去重）")
    parser.add_argument("--output-base", required=True, help="基础输出目录（不带 _id 后缀）")
    parser.add_argument("--workers", type=int, default=1, help="worker 总数（默认 1）")
    parser.add_argument("--ids", default="", help="worker id 列表（逗号分隔，优先级高于 --workers）")
    parser.add_argument(
        "--variants",
        default="full,wo_cot,wo_graph,wo_verify",
        help="需要合并的实验类型（逗号分隔）",
    )
    args = parser.parse_args()

    output_base = Path(args.output_base)
    worker_ids = [int(x) for x in parse_list(args.ids)] if args.ids else list(range(args.workers))
    variants = parse_list(args.variants)

    if not worker_ids:
        raise SystemExit("错误: 未指定任何 worker id")
    if not variants:
        raise SystemExit("错误: 未指定任何 variant")

    meta = {
        "timestamp": datetime.now().isoformat(),
        "output_base": str(output_base),
        "worker_ids": worker_ids,
        "variants": variants,
        "details": {},
    }

    for variant in variants:
        merged: Dict[str, dict] = {}
        order: List[str] = []
        variant_detail = {"workers": {}, "merged_count": 0}

        for wid in worker_ids:
            worker_base = Path(f"{output_base}_{wid}")
            pred_path = worker_base / variant / "predictions.jsonl"
            records, rec_order, total = load_jsonl(pred_path)
            variant_detail["workers"][str(wid)] = {
                "path": str(pred_path),
                "read_lines": total,
                "unique_records": len(records),
            }
            for doc_id in rec_order:
                if doc_id not in merged:
                    order.append(doc_id)
                merged[doc_id] = records[doc_id]

        out_dir = output_base / variant
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "predictions.jsonl"
        with out_path.open("w", encoding="utf-8") as f:
            for doc_id in order:
                f.write(json.dumps(merged[doc_id], ensure_ascii=False) + "\n")

        variant_detail["merged_count"] = len(merged)
        variant_detail["output"] = str(out_path)
        meta["details"][variant] = variant_detail

    meta_path = output_base / "merge_workers.meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"合并完成，元数据: {meta_path}")


if __name__ == "__main__":
    main()
