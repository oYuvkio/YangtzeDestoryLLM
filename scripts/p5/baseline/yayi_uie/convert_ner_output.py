#!/usr/bin/env python3
"""
Convert old YAYI-UIE NER outputs to fill parsed entities from raw_output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.p5.baseline.yayi_uie.parser import NEROutputParser


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert YAYI-UIE NER outputs")
    parser.add_argument("--input", required=True, help="Input JSONL file")
    parser.add_argument("--output", required=True, help="Output JSONL file")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite entities even if already present",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    parser = NEROutputParser()

    if not input_path.exists():
        print(f"[ERROR] input not found: {input_path}")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    updated = 0
    skipped = 0
    errors = 0

    with input_path.open("r", encoding="utf-8") as in_f, output_path.open("w", encoding="utf-8") as out_f:
        for line in in_f:
            raw = line.strip()
            if not raw:
                continue
            total += 1
            try:
                record: Dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                errors += 1
                continue

            entities = record.get("entities", [])
            has_entities = isinstance(entities, list) and len(entities) > 0
            if has_entities and not args.overwrite:
                skipped += 1
                out_f.write(raw + "\n")
                continue

            raw_output = record.get("raw_output", "")
            result = parser.parse(raw_output)
            if result.success and result.data.get("entities"):
                record["entities"] = result.data.get("entities", [])
                updated += 1
            else:
                skipped += 1

            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(
        f"Done. total={total} updated={updated} skipped={skipped} errors={errors} "
        f"output={output_path}"
    )


if __name__ == "__main__":
    main()
