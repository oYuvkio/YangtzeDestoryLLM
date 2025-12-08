#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 _corpus_index.json 重建 .corpus_cleaner_cache.jsonl 缓存文件。

当缓存文件丢失但输出文件仍存在时，可以用此脚本恢复缓存，
避免重新处理已完成的文件。

用法：
    python tools/rebuild_cache.py --output-dir ./data/corpus_for_kg/handle_all_new

功能：
1. 读取 _corpus_index.json 中的成功记录
2. 验证输出文件是否实际存在
3. 生成 .corpus_cleaner_cache.jsonl 缓存文件
"""
import argparse
import json
import time
from pathlib import Path
from typing import Dict, Any, List


def rebuild_cache_from_index(
    output_dir: Path,
    verify_files: bool = True,
) -> Dict[str, Any]:
    """
    从 _corpus_index.json 重建缓存文件。
    
    Args:
        output_dir: 输出目录（包含 _corpus_index.json）
        verify_files: 是否验证输出文件存在
        
    Returns:
        统计信息字典
    """
    index_path = output_dir / "_corpus_index.json"
    cache_path = output_dir / ".corpus_cleaner_cache.jsonl"
    
    if not index_path.exists():
        raise FileNotFoundError(f"索引文件不存在: {index_path}")
    
    # 读取索引
    print(f"📖 读取索引文件: {index_path}")
    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    
    success_records = index_data.get("success", [])
    skipped_records = index_data.get("skipped", [])
    failed_records = index_data.get("failed", [])
    
    print(f"   成功记录: {len(success_records)}")
    print(f"   跳过记录: {len(skipped_records)}")
    print(f"   失败记录: {len(failed_records)}")
    
    # 构建缓存条目
    cache_entries: List[Dict[str, Any]] = []
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    
    verified_count = 0
    missing_count = 0
    
    # 处理成功记录
    for record in success_records:
        path = record.get("path", "")
        parts_count = record.get("parts_count", 0)
        output_paths = record.get("output_paths", [])
        
        # 验证输出文件存在
        if verify_files and output_paths:
            existing_paths = []
            for out_path in output_paths:
                full_path = output_dir / out_path
                if full_path.exists():
                    existing_paths.append(out_path)
            
            if len(existing_paths) == len(output_paths):
                verified_count += 1
            elif len(existing_paths) > 0:
                # 部分存在
                print(f"   ⚠️  部分文件缺失: {path} ({len(existing_paths)}/{len(output_paths)})")
                parts_count = len(existing_paths)
                output_paths = existing_paths
                verified_count += 1
            else:
                # 全部缺失
                print(f"   ❌ 文件不存在: {path}")
                missing_count += 1
                continue
        
        cache_entries.append({
            "path": path,
            "status": "success",
            "parts": parts_count,
            "output_paths": output_paths,  # 新增：记录已完成的输出路径
            "error": "",
            "timestamp": timestamp,
        })
    
    # 处理跳过记录
    for record in skipped_records:
        cache_entries.append({
            "path": record.get("path", ""),
            "status": "skipped",
            "parts": 0,
            "output_paths": [],
            "error": record.get("message", ""),
            "timestamp": timestamp,
        })
    
    # 处理失败记录（可选：是否保留失败记录以便下次重试）
    # 这里不写入失败记录，让下次运行时重新尝试
    
    # 写入缓存文件
    print(f"\n📝 写入缓存文件: {cache_path}")
    with cache_path.open("w", encoding="utf-8") as f:
        for entry in cache_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    stats = {
        "cache_path": str(cache_path),
        "total_entries": len(cache_entries),
        "success_entries": sum(1 for e in cache_entries if e["status"] == "success"),
        "skipped_entries": sum(1 for e in cache_entries if e["status"] == "skipped"),
        "verified_count": verified_count,
        "missing_count": missing_count,
    }
    
    print(f"\n✅ 缓存重建完成!")
    print(f"   写入条目: {stats['total_entries']}")
    print(f"   成功条目: {stats['success_entries']}")
    print(f"   跳过条目: {stats['skipped_entries']}")
    if verify_files:
        print(f"   验证通过: {stats['verified_count']}")
        print(f"   文件缺失: {stats['missing_count']}")
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="从 _corpus_index.json 重建缓存文件"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="输出目录路径（包含 _corpus_index.json）",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="跳过文件存在性验证",
    )
    
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    
    if not output_dir.exists():
        print(f"❌ 目录不存在: {output_dir}")
        return 1
    
    try:
        rebuild_cache_from_index(
            output_dir=output_dir,
            verify_files=not args.no_verify,
        )
        return 0
    except Exception as e:
        print(f"❌ 错误: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
