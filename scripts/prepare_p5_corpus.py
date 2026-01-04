#!/usr/bin/env python3
"""
从JSONL语料文件提取文本，准备P5抽取用的语料目录

使用方式：
    python scripts/prepare_p5_corpus.py --input data/corpus_for_onto/p4_only_v3.jsonl
    python scripts/prepare_p5_corpus.py --input data/corpus_for_onto/p4_only_v3.jsonl --output data/corpus_for_extraction --limit 100
"""

import argparse
import json
import hashlib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="准备P5抽取用的语料目录")
    parser.add_argument("--input", "-i", required=True, help="输入JSONL文件路径")
    parser.add_argument("--output", "-o", default="data/corpus_for_extraction", help="输出目录")
    parser.add_argument("--limit", type=int, default=0, help="最多处理的文档数（0=不限制）")
    parser.add_argument("--text-field", default="content", help="文本字段名")
    parser.add_argument("--id-field", default="doc_id", help="ID字段名")

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"[ERROR] 输入文件不存在: {input_path}")
        return

    count = 0
    skipped = 0

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if args.limit > 0 and count >= args.limit:
                break

            line = line.strip()
            if not line:
                continue

            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue

            # 获取文本内容
            text = doc.get(args.text_field, "")
            if not text:
                # 尝试其他常见字段名
                for field in ["text", "body", "paragraph", "source_text"]:
                    if doc.get(field):
                        text = doc.get(field)
                        break

            if not text or len(text.strip()) < 50:
                skipped += 1
                continue

            # 生成文件名
            doc_id = doc.get(args.id_field, "")
            if not doc_id:
                # 使用内容哈希作为ID
                doc_id = hashlib.md5(text.encode()).hexdigest()[:12]

            # 清理文件名中的非法字符
            safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(doc_id))
            output_file = output_dir / f"{safe_id}.txt"

            # 写入文本
            output_file.write_text(text.strip(), encoding="utf-8")
            count += 1

            if count % 100 == 0:
                print(f"[进度] 已处理 {count} 个文档...")

    print(f"\n完成！")
    print(f"  输入文件: {input_path}")
    print(f"  输出目录: {output_dir}")
    print(f"  成功提取: {count} 个文档")
    print(f"  跳过: {skipped} 个")
    print(f"\n可以使用以下命令运行P5抽取:")
    print(f"  bash scripts/run_p5_extraction.sh --corpus {output_dir}")


if __name__ == "__main__":
    main()
