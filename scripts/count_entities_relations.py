#!/usr/bin/env python3
"""Count entities and relation triples in a JSONL file (no de-dup)."""

import argparse
import json
from pathlib import Path
from typing import Any


def _count_entities(entities: Any) -> int:
    """Count entity mentions from the 'entities' field without de-dup."""
    if entities is None:
        return 0
    # Common format: list of dicts like [{'Type': [..], ...}, ...]
    if isinstance(entities, list):
        total = 0
        for item in entities:
            if isinstance(item, dict):
                for v in item.values():
                    if isinstance(v, list):
                        total += len(v)
                    elif v is not None:
                        total += 1
            elif isinstance(item, list):
                total += len(item)
            elif item is not None:
                total += 1
        return total
    if isinstance(entities, dict):
        total = 0
        for v in entities.values():
            if isinstance(v, list):
                total += len(v)
            elif v is not None:
                total += 1
        return total
    return 1


def _count_triples(triples: Any) -> int:
    if triples is None:
        return 0
    if isinstance(triples, list):
        return len(triples)
    if isinstance(triples, dict):
        return 1
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Count entities and relation triples in a JSONL file (no de-dup)."
    )
    parser.add_argument(
        "jsonl",
        type=Path,
        help="Path to the JSONL file (each line is a JSON object).",
    )
    parser.add_argument(
        "--entities-key",
        default="entities",
        help="Field name that stores entities. Default: entities",
    )
    parser.add_argument(
        "--triples-key",
        default="triples",
        help="Field name that stores relation triples. Default: triples",
    )
    args = parser.parse_args()

    total_entities = 0
    total_triples = 0
    line_count = 0

    with args.jsonl.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            line_count += 1
            obj = json.loads(line)
            total_entities += _count_entities(obj.get(args.entities_key))
            total_triples += _count_triples(obj.get(args.triples_key))

    print(f"lines: {line_count}")
    print(f"entities_total: {total_entities}")
    print(f"triples_total: {total_triples}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
