#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将新华网爬虫输出的 JSONL 转换为 filter_corpus_light 需要的格式。

输入: xinhua_news.jsonl（每行一个 JSON 对象，包含 content, pubtime, title 等）
输出: 每条新闻生成一个 .txt 文件和对应的 .meta.json 文件

使用示例:
    python tools/convert_news_to_corpus.py \
        --input data/corpus_for_kg/used_kg_corpus/科普\ \&\ 新闻/新闻/xinhua_news.jsonl \
        --output data/corpus_for_kg/handled_all_kg_corpus/新闻/xinhua
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def extract_year(pubtime: str) -> str:
    """从发布时间中提取年份"""
    if not pubtime:
        return ""
    # 尝试多种格式
    match = re.match(r"(\d{4})", pubtime)
    if match:
        return match.group(1)
    return ""


def generate_safe_filename(news_id: str, title: str) -> str:
    """生成安全的文件名"""
    # 使用 ID 的前 16 位 + 标题的前 20 个字符
    safe_title = re.sub(r'[^\u4e00-\u9fff\w]', '', title)[:20]
    safe_id = news_id.replace("/", "_").replace("\\", "_")[:32]
    return f"{safe_id}_{safe_title}" if safe_title else safe_id


def convert_news_to_corpus(
    input_path: Path,
    output_dir: Path,
    min_content_chars: int = 50,
    skip_existing: bool = True,
) -> Dict[str, int]:
    """
    将新闻 JSONL 转换为语料格式。
    
    Args:
        input_path: 输入 JSONL 文件路径
        output_dir: 输出目录
        min_content_chars: 最小正文字符数（过滤太短的新闻）
        skip_existing: 是否跳过已存在的文件
    
    Returns:
        统计信息字典
    """
    stats = {
        "total": 0,
        "converted": 0,
        "skipped_existing": 0,
        "skipped_short": 0,
        "skipped_empty": 0,
        "errors": 0,
    }
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with input_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            stats["total"] += 1
            
            try:
                news = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[WARN] 第 {line_num} 行 JSON 解析失败: {e}")
                stats["errors"] += 1
                continue
            
            # 提取字段
            news_id = news.get("id", "")
            content = news.get("content", "").strip()
            title = news.get("title", "").strip()
            pubtime = news.get("pubtime", "")
            url = news.get("url", "")
            keyword = news.get("keyword", "")
            source = news.get("source", "新华网")
            
            # 跳过空内容
            if not content:
                stats["skipped_empty"] += 1
                continue
            
            # 跳过过短内容
            if len(content) < min_content_chars:
                stats["skipped_short"] += 1
                continue
            
            # 生成文件名
            if not news_id:
                news_id = hashlib.md5(f"{title}:{content[:100]}".encode()).hexdigest()[:16]
            
            filename = generate_safe_filename(news_id, title)
            txt_path = output_dir / f"{filename}.txt"
            meta_path = output_dir / f"{filename}.meta.json"
            
            # 跳过已存在
            if skip_existing and txt_path.exists():
                stats["skipped_existing"] += 1
                continue
            
            # 写入 TXT 文件
            txt_path.write_text(content, encoding="utf-8")
            
            # 构建元数据
            year = extract_year(pubtime)
            meta = {
                "md5_hash": news_id,
                "source_file": f"xinhua_news_{news_id}.json",
                "title": title,
                "year": year,
                "pubtime": pubtime,
                "url": url,
                "source_type": "news",
                "source": source,
                "keyword": keyword,
                # 以下字段保持与 corpus_cleaner 输出格式兼容
                "province": "",  # 新闻可能涉及多省，暂不提取
                "river": "",     # 可后续用 NER 提取
                "prev_part_id": "",
                "next_part_id": "",
                "group_id": f"xinhua_{year}" if year else "xinhua",
                "converted_at": datetime.now().isoformat(),
            }
            
            # 写入 meta.json
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            
            stats["converted"] += 1
            
            if stats["converted"] % 10 == 0:
                print(f"\r已转换: {stats['converted']}", end="", flush=True)
    
    print()  # 换行
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="将新华网新闻 JSONL 转换为语料格式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="输入 JSONL 文件路径"
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="输出目录路径"
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=50,
        help="最小正文字符数（默认: 50）"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制覆盖已存在的文件"
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_dir = Path(args.output)
    
    if not input_path.exists():
        print(f"错误: 输入文件不存在: {input_path}")
        return 1
    
    print("=" * 60)
    print("新闻语料转换工具")
    print("=" * 60)
    print(f"输入: {input_path}")
    print(f"输出: {output_dir}")
    print(f"最小字符数: {args.min_chars}")
    print(f"跳过已存在: {not args.force}")
    print("=" * 60)
    
    stats = convert_news_to_corpus(
        input_path,
        output_dir,
        min_content_chars=args.min_chars,
        skip_existing=not args.force,
    )
    
    print("=" * 60)
    print("转换完成！")
    print(f"  - 总计: {stats['total']} 条")
    print(f"  - 转换: {stats['converted']} 条")
    print(f"  - 跳过（已存在）: {stats['skipped_existing']} 条")
    print(f"  - 跳过（内容太短）: {stats['skipped_short']} 条")
    print(f"  - 跳过（无内容）: {stats['skipped_empty']} 条")
    print(f"  - 错误: {stats['errors']} 条")
    print(f"  - 输出目录: {output_dir}")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
