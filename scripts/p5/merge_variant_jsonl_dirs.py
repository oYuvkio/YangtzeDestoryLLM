#!/usr/bin/env python3
"""
合并两个输出目录下的各 variant 子目录中的 JSONL 文件（按 doc_id 去重）。

示例：
  python scripts/p5/merge_variant_jsonl_dirs.py \
    --src-a outputs/eval_models_hybrid/qwen/qwen3-8b_0 \
    --src-b outputs/eval_models_hybrid/qwen/qwen3-8b_1 \
    --out outputs/eval_models_hybrid/qwen/qwen3-8b_merged
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


def parse_list(value: str) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def pick_doc_id(record: Dict[str, object]) -> str:
    for key in ("doc_id", "docid", "id", "document_id"):
        value = record.get(key)
        if value not in [None, ""]:
            return str(value)
    meta = record.get("meta") or record.get("_meta") or {}
    if isinstance(meta, dict):
        for key in ("doc_id", "docid", "id", "document_id"):
            value = meta.get(key)
            if value not in [None, ""]:
                return str(value)
    return ""


def load_jsonl(path: Path) -> Tuple[Dict[str, dict], List[str], int, int]:
    records: Dict[str, dict] = {}
    order: List[str] = []
    total = 0
    skipped = 0
    if not path.exists():
        return records, order, total, skipped
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(record, dict):
                skipped += 1
                continue
            doc_id = pick_doc_id(record)
            if not doc_id:
                skipped += 1
                continue
            if doc_id not in records:
                order.append(doc_id)
            records[doc_id] = record
    return records, order, total, skipped


def merge_jsonl(a_path: Path, b_path: Path, out_path: Path, prefer: str) -> Dict[str, int]:
    a_records, a_order, a_total, a_skipped = load_jsonl(a_path)
    b_records, b_order, b_total, b_skipped = load_jsonl(b_path)

    merged: Dict[str, dict] = {}
    order: List[str] = []

    def add_records(records: Dict[str, dict], record_order: List[str], allow_overwrite: bool) -> None:
        for doc_id in record_order:
            if doc_id in merged and not allow_overwrite:
                continue
            if doc_id not in merged:
                order.append(doc_id)
            merged[doc_id] = records[doc_id]

    if prefer == "a":
        add_records(a_records, a_order, allow_overwrite=True)
        add_records(b_records, b_order, allow_overwrite=False)
    else:
        add_records(b_records, b_order, allow_overwrite=True)
        add_records(a_records, a_order, allow_overwrite=False)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for doc_id in order:
            f.write(json.dumps(merged[doc_id], ensure_ascii=False) + "\n")

    return {
        "a_total": a_total,
        "b_total": b_total,
        "a_skipped": a_skipped,
        "b_skipped": b_skipped,
        "merged_count": len(merged),
        "out_path": str(out_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="合并两个目录下的 JSONL 文件（按 doc_id 去重）")
    parser.add_argument("--src-a", required=True, help="来源目录 A")
    parser.add_argument("--src-b", required=True, help="来源目录 B")
    parser.add_argument("--out", required=True, help="输出目录")
    parser.add_argument(
        "--variants",
        default="full,wo_cot,wo_graph,wo_verify",
        help="需要合并的子目录（逗号分隔）",
    )
    parser.add_argument(
        "--prefer",
        choices=["a", "b"],
        default="a",
        help="doc_id 冲突时优先保留哪个目录（默认 a）",
    )
    args = parser.parse_args()

    src_a = Path(args.src_a)
    src_b = Path(args.src_b)
    out_dir = Path(args.out)
    variants = parse_list(args.variants)

    if not variants:
        raise SystemExit("错误: 未指定任何 variant")

    meta = {
        "timestamp": datetime.now().isoformat(),
        "src_a": str(src_a),
        "src_b": str(src_b),
        "out": str(out_dir),
        "variants": variants,
        "prefer": args.prefer,
        "details": {},
    }

    for variant in variants:
        a_variant = src_a / variant
        b_variant = src_b / variant
        out_variant = out_dir / variant
        out_variant.mkdir(parents=True, exist_ok=True)

        jsonl_names = set()
        if a_variant.exists():
            jsonl_names.update([p.name for p in a_variant.glob("*.jsonl")])
        if b_variant.exists():
            jsonl_names.update([p.name for p in b_variant.glob("*.jsonl")])

        detail = {"files": {}}
        for name in sorted(jsonl_names):
            a_path = a_variant / name
            b_path = b_variant / name
            out_path = out_variant / name
            detail["files"][name] = merge_jsonl(a_path, b_path, out_path, args.prefer)

        meta["details"][variant] = detail

    meta_path = out_dir / "merge_variants.meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"合并完成，元数据: {meta_path}")


if __name__ == "__main__":
    main()
