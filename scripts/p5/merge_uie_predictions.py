#!/usr/bin/env python3
"""
合并 UIE 的 NER/RE 预测结果为单一 JSONL。

使用 NER 的 entities + RE 的 events/triples，便于与 gold 统一评测。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def load_jsonl(path: Path) -> Dict[str, Dict[str, Any]]:
    data: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return data
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            doc_id = str(obj.get("doc_id", "")).strip()
            if doc_id:
                data[doc_id] = obj
    return data


def resolve_output_path(output: Path, name: str) -> Path:
    if output.suffix.lower() == ".jsonl":
        return output
    return output / name


def main() -> None:
    parser = argparse.ArgumentParser(description="合并 UIE NER/RE 预测结果")
    parser.add_argument("--ner", required=True, help="NER 预测文件 (jsonl)")
    parser.add_argument("--re", required=True, help="RE 预测文件 (jsonl)")
    parser.add_argument("--output", required=True, help="输出文件或目录")
    parser.add_argument(
        "--no-prefer-ner-entities",
        action="store_true",
        help="不使用 NER 的 entities，保留 RE 自带 entities",
    )
    parser.add_argument(
        "--include-ner-only",
        action="store_true",
        help="当 RE 缺失时，保留仅 NER 的记录",
    )
    args = parser.parse_args()

    ner_path = Path(args.ner)
    re_path = Path(args.re)
    output_path = resolve_output_path(Path(args.output), "predictions_merged.jsonl")

    ner_data = load_jsonl(ner_path)
    re_data = load_jsonl(re_path)

    doc_ids = set(re_data.keys())
    if args.include_ner_only:
        doc_ids.update(ner_data.keys())

    output_path.parent.mkdir(parents=True, exist_ok=True)

    merged = 0
    with output_path.open("w", encoding="utf-8") as out_f:
        for doc_id in doc_ids:
            base = re_data.get(doc_id) or ner_data.get(doc_id)
            if not base:
                continue
            record = dict(base)
            if not args.no_prefer_ner_entities:
                ner_record = ner_data.get(doc_id)
                if ner_record and "entities" in ner_record:
                    record["entities"] = ner_record.get("entities", [])
            record.setdefault("events", [])
            record.setdefault("triples", [])
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            merged += 1

    print(f"合并完成: {merged} 条 -> {output_path}")


if __name__ == "__main__":
    main()
