#!/usr/bin/env python3
"""
JSONL 去重工具
支持多种去重策略：content(text字段)、title、title_time、url
"""
import argparse
import json
import hashlib
from pathlib import Path
from typing import Dict, Set


def compute_hash(text: str) -> str:
    """计算文本的MD5哈希值"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def get_dedup_key(item: Dict, strategy: str) -> str:
    """根据策略获取去重键"""
    if strategy == "content" or strategy == "text":
        text = item.get("text", "") or item.get("content", "")
        return compute_hash(text.strip())
    elif strategy == "title":
        return item.get("title", "").strip()
    elif strategy == "title_time":
        title = item.get("title", "").strip()
        pubtime = item.get("pubtime", "") or item.get("year", "")
        return f"{title}|{pubtime}"
    elif strategy == "url":
        return item.get("url", "").strip()
    else:
        raise ValueError(f"未知的去重策略: {strategy}")


def deduplicate_jsonl(
    input_path: str,
    output_path: str,
    strategy: str = "content",
    keep: str = "first"
) -> Dict:
    """
    对JSONL文件进行去重
    
    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径
        strategy: 去重策略 (content/text, title, title_time, url)
        keep: 保留哪个 (first/last)
    
    Returns:
        统计信息字典
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")
    
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 读取所有记录
    records = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                records.append(item)
            except json.JSONDecodeError as e:
                print(f"警告: 第 {line_num} 行 JSON 解析失败: {e}")
    
    total_count = len(records)
    print(f"读取记录数: {total_count}")
    
    # 去重
    seen_keys: Set[str] = set()
    unique_records = []
    duplicate_count = 0
    
    if keep == "last":
        records = list(reversed(records))
    
    for item in records:
        key = get_dedup_key(item, strategy)
        if key not in seen_keys:
            seen_keys.add(key)
            unique_records.append(item)
        else:
            duplicate_count += 1
    
    if keep == "last":
        unique_records = list(reversed(unique_records))
    
    # 写入输出文件
    with open(output_path, 'w', encoding='utf-8') as f:
        for item in unique_records:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    unique_count = len(unique_records)
    print(f"去重后记录数: {unique_count}")
    print(f"移除重复记录: {duplicate_count}")
    print(f"输出文件: {output_path}")
    
    return {
        "total": total_count,
        "unique": unique_count,
        "duplicates": duplicate_count,
        "strategy": strategy
    }


def main():
    parser = argparse.ArgumentParser(description="JSONL 文件去重工具")
    parser.add_argument("--input", "-i", required=True, help="输入 JSONL 文件路径")
    parser.add_argument("--output", "-o", required=True, help="输出 JSONL 文件路径")
    parser.add_argument(
        "--strategy", "-s",
        choices=["content", "text", "title", "title_time", "url"],
        default="content",
        help="去重策略 (默认: content)"
    )
    parser.add_argument(
        "--keep", "-k",
        choices=["first", "last"],
        default="first",
        help="保留首次还是最后一次出现 (默认: first)"
    )
    
    args = parser.parse_args()
    
    stats = deduplicate_jsonl(
        input_path=args.input,
        output_path=args.output,
        strategy=args.strategy,
        keep=args.keep
    )
    
    print(f"\n去重完成! 策略: {stats['strategy']}")
    print(f"  原始记录: {stats['total']}")
    print(f"  去重后: {stats['unique']}")
    print(f"  移除重复: {stats['duplicates']}")


if __name__ == "__main__":
    main()
