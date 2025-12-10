#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSONL 文件去重工具

支持多种去重策略：
1. content: 基于正文内容哈希（推荐，最严格）
2. title: 基于标题去重
3. title_time: 基于标题+发布时间去重
4. url: 基于 URL 去重

使用示例:
    # 基于内容去重（默认）
    python tools/deduplicate_jsonl.py \
        --input data/corpus_for_kg/used_kg_corpus/科普\ \&\ 新闻/新闻/xinhua_news.jsonl \
        --output data/corpus_for_kg/used_kg_corpus/科普\ \&\ 新闻/新闻/xinhua_news_dedup.jsonl

    # 基于标题+时间去重
    python tools/deduplicate_jsonl.py \
        --input xinhua_news.jsonl \
        --output xinhua_news_dedup.jsonl \
        --strategy title_time
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


def compute_content_hash(content: str) -> str:
    """计算内容哈希（忽略空白差异）"""
    # 规范化：去除首尾空白，压缩连续空白
    normalized = " ".join(content.split())
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def get_dedup_key(item: Dict[str, Any], strategy: str) -> str:
    """根据策略生成去重键"""
    if strategy == "content":
        content = item.get("content", "")
        return compute_content_hash(content) if content else ""
    
    elif strategy == "title":
        return item.get("title", "").strip()
    
    elif strategy == "title_time":
        title = item.get("title", "").strip()
        pubtime = item.get("pubtime", "").strip()
        return f"{title}|{pubtime}"
    
    elif strategy == "url":
        return item.get("url", "").strip()
    
    else:
        raise ValueError(f"未知策略: {strategy}")


def deduplicate_jsonl(
    input_path: Path,
    output_path: Path,
    strategy: str = "content",
    keep: str = "first",
) -> Dict[str, int]:
    """
    对 JSONL 文件进行去重。
    
    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径
        strategy: 去重策略 (content/title/title_time/url)
        keep: 保留策略 (first/last)
    
    Returns:
        统计信息字典
    """
    stats = {
        "total": 0,
        "kept": 0,
        "duplicates": 0,
        "empty_key": 0,
    }
    
    # 第一遍：收集所有记录和去重键
    records: List[Tuple[str, Dict[str, Any]]] = []
    
    with input_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                item = json.loads(line)
                stats["total"] += 1
                
                key = get_dedup_key(item, strategy)
                if not key:
                    stats["empty_key"] += 1
                    # 空键的记录也保留
                    records.append(("", item))
                else:
                    records.append((key, item))
                    
            except json.JSONDecodeError as e:
                print(f"[WARN] 第 {line_num} 行解析失败: {e}")
    
    # 第二遍：去重
    seen_keys: Set[str] = set()
    kept_records: List[Dict[str, Any]] = []
    
    if keep == "last":
        # 从后往前遍历
        records = list(reversed(records))
    
    for key, item in records:
        if not key:
            # 空键直接保留
            kept_records.append(item)
            stats["kept"] += 1
        elif key not in seen_keys:
            seen_keys.add(key)
            kept_records.append(item)
            stats["kept"] += 1
        else:
            stats["duplicates"] += 1
    
    if keep == "last":
        # 恢复顺序
        kept_records = list(reversed(kept_records))
    
    # 写入输出
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for item in kept_records:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="JSONL 文件去重工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
去重策略说明:
  content    - 基于正文内容哈希去重（最严格，推荐）
  title      - 仅基于标题去重
  title_time - 基于标题+发布时间去重
  url        - 基于 URL 去重

示例:
  python tools/deduplicate_jsonl.py -i news.jsonl -o news_dedup.jsonl
  python tools/deduplicate_jsonl.py -i news.jsonl -o news_dedup.jsonl --strategy title_time
        """
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="输入 JSONL 文件路径"
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="输出 JSONL 文件路径"
    )
    parser.add_argument(
        "--strategy", "-s",
        choices=["content", "title", "title_time", "url"],
        default="content",
        help="去重策略（默认: content）"
    )
    parser.add_argument(
        "--keep",
        choices=["first", "last"],
        default="first",
        help="保留第一个还是最后一个重复项（默认: first）"
    )
    parser.add_argument(
        "--inplace",
        action="store_true",
        help="原地去重（输出覆盖输入）"
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    if args.inplace:
        output_path = input_path
        # 先写到临时文件
        temp_path = input_path.with_suffix(".jsonl.tmp")
    else:
        output_path = Path(args.output)
        temp_path = output_path
    
    if not input_path.exists():
        print(f"错误: 输入文件不存在: {input_path}")
        return 1
    
    print("=" * 60)
    print("JSONL 去重工具")
    print("=" * 60)
    print(f"输入: {input_path}")
    print(f"输出: {output_path}")
    print(f"策略: {args.strategy}")
    print(f"保留: {args.keep}")
    print("=" * 60)
    
    stats = deduplicate_jsonl(
        input_path,
        temp_path,
        strategy=args.strategy,
        keep=args.keep,
    )
    
    # 如果是原地模式，替换原文件
    if args.inplace and temp_path != output_path:
        temp_path.replace(output_path)
    
    print("=" * 60)
    print("去重完成！")
    print(f"  - 总计: {stats['total']} 条")
    print(f"  - 保留: {stats['kept']} 条")
    print(f"  - 去除重复: {stats['duplicates']} 条")
    if stats['empty_key'] > 0:
        print(f"  - 空键（已保留）: {stats['empty_key']} 条")
    print(f"  - 去重率: {stats['duplicates'] / stats['total'] * 100:.1f}%")
    print(f"  - 输出: {output_path}")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
