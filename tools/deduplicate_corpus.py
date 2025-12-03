"""
按内容去重并保留第一份，输出到 data/new_all_kg_corpus（保留原目录结构）。

规则与策略：
- 全局去重：跨文件夹、跨文件名，内容相同视为重复，仅保留首次出现。
- 去重键：
  * txt：整体内容 MD5
  * jsonl：按行内容 MD5
  * .meta.json：不去重，直接复制
  * 其他文件：按字节 MD5
- 保留原相对目录结构到目标目录。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, Set


def md5_text(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def copy_txt(src: Path, dst: Path, seen: Set[str]) -> bool:
    content = src.read_text(encoding="utf-8", errors="ignore")
    h = md5_text(content)
    if h in seen:
        return False
    seen.add(h)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")
    return True


def copy_jsonl(src: Path, dst: Path, seen: Set[str]) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    out_lines = []
    kept = False
    for line in src.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        h = md5_text(line)
        if h in seen:
            continue
        seen.add(h)
        out_lines.append(line)
        kept = True
    if kept:
        dst.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return kept


def process_dir(src_root: Path, dst_root: Path) -> Dict[str, int]:
    """
    全局去重：跨目录/跨文件名，同内容只保留第一份。
    """
    seen: Set[str] = set()
    stats = {"copied": 0, "skipped": 0}

    for src in src_root.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(src_root)
        dst = dst_root / rel

        # 元数据直接复制
        if src.suffix == ".json" and src.name.endswith(".meta.json"):
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(src.read_text(encoding="utf-8",
                           errors="ignore"), encoding="utf-8")
            stats["copied"] += 1
            continue

        # 根据后缀处理
        try:
            ext = src.suffix.lower()
            if ext == ".txt":
                copied = copy_txt(src, dst, seen)
            elif ext in [".jsonl"]:
                copied = copy_jsonl(src, dst, seen)
            elif src.name.endswith(".meta.json"):
                # 元数据直接复制
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(src.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
                copied = True
            else:
                # 其他文件按字节哈希去重
                data = src.read_bytes()
                h = md5_bytes(data)
                if h in seen:
                    copied = False
                else:
                    seen.add(h)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(data)
                    copied = True
            stats["copied" if copied else "skipped"] += 1
        except Exception:
            stats["skipped"] += 1
    return stats


def main():
    parser = argparse.ArgumentParser(description="按内容+文件名去重，复制 corpus 到新目录。")
    parser.add_argument("--src", default="data/corpus_for_kg_all_kg_corpus",
                        help="源目录（递归遍历），默认 data/corpus_for_kg_all_kg_corpus")
    parser.add_argument("--dst", default="data/new_all_kg_corpus",
                        help="去重后的输出目录，默认 data/new_all_kg_corpus")
    args = parser.parse_args()

    src_root = Path(args.src)
    dst_root = Path(args.dst)
    if not src_root.exists():
        raise FileNotFoundError(f"源目录不存在：{src_root}")

    stats = process_dir(src_root, dst_root)
    print(
        f"完成：保留 {stats['copied']} 个文件/行，跳过 {stats['skipped']} 个重复或异常。输出目录：{dst_root}")


if __name__ == "__main__":
    main()
