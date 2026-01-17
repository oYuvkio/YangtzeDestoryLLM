#!/usr/bin/env python3
"""按 doc_id 频次过滤 JSONL，保留原始行输出。"""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable, List


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "遍历根目录下的 JSONL 文件，统计 doc_id 出现次数，"
            "保留出现指定次数的原始行并导出。"
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("data/filtered_gold"),
        help="包含各模型子目录的根路径，默认 data/filtered_gold。",
    )
    parser.add_argument(
        "--count",
        type=int,
        required=True,
        help="目标出现次数 N，仅保留出现次数等于 N 的 doc_id 对应行。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出 JSONL 路径，默认写到 root/merge_filted_<N>.jsonl。",
    )
    parser.add_argument(
        "--glob",
        default="*.jsonl",
        help="相对于 root 的文件匹配模式，默认 *.jsonl。",
    )
    return parser.parse_args()


def list_jsonl(root: Path, pattern: str) -> List[Path]:
    # 排序保证可重复结果。
    return sorted(root.rglob(pattern))


def build_counts(files: Iterable[Path]) -> Counter:
    counts: Counter = Counter()
    for path in files:
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        doc_id = json.loads(line).get("doc_id")
                    except json.JSONDecodeError:
                        continue
                    if doc_id:
                        counts[doc_id] += 1
        except FileNotFoundError:
            continue
    return counts


def write_filtered(files: Iterable[Path], counts: Counter, target: int, output: Path) -> int:
    kept = 0
    with output.open("w", encoding="utf-8") as out_f:
        for path in files:
            try:
                with path.open("r", encoding="utf-8") as f:
                    for line in f:
                        raw = line.rstrip("\n")
                        if not raw:
                            continue
                        try:
                            doc_id = json.loads(raw).get("doc_id")
                        except json.JSONDecodeError:
                            continue
                        if doc_id and counts.get(doc_id) == target:
                            out_f.write(raw + "\n")
                            kept += 1
            except FileNotFoundError:
                continue
    return kept


def main() -> None:
    args = parse_args()
    root = args.root
    target = args.count
    files = list_jsonl(root, args.glob)

    counts = build_counts(files)

    output = args.output or root / f"merge_filted_{target}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)

    kept = write_filtered(files, counts, target, output)

    print(
        f"扫描 {len(files)} 个文件，满足次数 {target} 的 doc_id 行数: {kept}，输出: {output}"
    )


if __name__ == "__main__":
    main()
