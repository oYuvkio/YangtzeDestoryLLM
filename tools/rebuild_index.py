#!/usr/bin/env python3
"""从输出目录现有文件重建 _corpus_index.json"""
import json
from pathlib import Path
from collections import defaultdict
import time

def rebuild_index(output_dir: str):
    output_path = Path(output_dir)
    if not output_path.exists():
        print(f"❌ 目录不存在: {output_path}")
        return
    
    # 扫描所有 .txt 文件（排除索引文件）
    txt_files = [f for f in output_path.rglob("*.txt") if f.name != "_corpus_index.json"]
    
    # 按源文件分组
    source_map = defaultdict(list)
    for f in txt_files:
        # 从文件名提取源文件名（去除 _partXXX 后缀）
        name = f.stem
        parts = name.rsplit("_part", 1)
        source_name = parts[0] if len(parts) > 1 else name
        source_map[source_name].append(str(f.relative_to(output_path)))
    
    # 构建索引
    success_records = []
    for source, output_paths in sorted(source_map.items()):
        success_records.append({
            "path": f"(重建) {source}",
            "parts_count": len(output_paths),
            "output_paths": sorted(output_paths)
        })
    
    index_data = {
        "tool_name": "P4 语料批量清洗工具",
        "tool_version": "4.0.0 (索引重建)",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "note": "此索引从输出目录现有文件重建",
        "summary": {
            "total_files": len(success_records),
            "total_parts": len(txt_files),
            "success_count": len(success_records),
            "skipped_count": 0,
            "failed_count": 0,
            "duration_seconds": 0.0
        },
        "success": success_records,
        "skipped": [],
        "failed": []
    }
    
    index_path = output_path / "_corpus_index.json"
    index_path.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"✅ 索引重建完成!")
    print(f"   源文件数: {len(success_records)}")
    print(f"   输出分片: {len(txt_files)}")
    print(f"   索引路径: {index_path}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python rebuild_index.py <输出目录>")
        sys.exit(1)
    rebuild_index(sys.argv[1])
