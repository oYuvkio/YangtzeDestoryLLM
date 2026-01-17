#!/usr/bin/env python3
"""按 doc_id 频次过滤 JSONL，保留原始行输出。

遍历根目录下的 JSONL 文件，统计 doc_id 出现次数，
保留出现至少 N 次的原始行并导出到 JSONL。
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "遍历根目录统计 doc_id 出现次数，并导出出现至少 N 次的原始 JSON 行。"
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
        help="目标出现次数 N，仅保留出现次数至少为 N 的 doc_id 对应行。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出路径：可为文件或目录。默认写到 root/merge_filted_<N>.jsonl。",
    )
    parser.add_argument(
        "--glob",
        default="*.jsonl",
        help="相对于 root 的文件匹配模式，默认 *.jsonl。",
    )
    return parser.parse_args()


def iter_jsonl_files(root: Path, pattern: str) -> Iterable[Path]:
    """Yield JSONL files under root matching pattern."""
    yield from root.rglob(pattern)


def collect_counts(paths: Iterable[Path]) -> Counter:
    counts: Counter = Counter()
    for path in paths:
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # 跳过无法解析的行
                    doc_id = data.get("doc_id")
                    if doc_id:
                        counts[doc_id] += 1
        except FileNotFoundError:
            continue
    return counts


def main() -> None:
    args = parse_args()
    root: Path = args.root
    n: int = args.count
    root.mkdir(parents=True, exist_ok=True)

    files = list(iter_jsonl_files(root, args.glob))
    counts = collect_counts(files)

    # 兼容目录输出：当 --output 为目录或无后缀时，写入目录下命名文件
    if args.output is None:
        output = root / f"merge_filted_{n}.jsonl"
    else:
        out = args.output
        if out.suffix.lower() == ".jsonl":
            output = out
        else:
            # 视为目录
            output = out / f"merge_filted_{n}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)

    kept = 0
    seen: Set[str] = set()
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
                        if doc_id and counts.get(doc_id, 0) >= n and doc_id not in seen:
                            out_f.write(raw + "\n")
                            kept += 1
                            seen.add(doc_id)
            except FileNotFoundError:
                continue

    print(
        f"扫描 {len(files)} 个文件，保留出现次数 >= {n} 的原始行共 {kept} 条。输出: {output}"
    )


if __name__ == "__main__":
    main()
