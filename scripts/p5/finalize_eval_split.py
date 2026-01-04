#!/usr/bin/env python3
"""
评测数据集最终划分脚本

将 gold_reviewed.jsonl 作为 test 集，从 p5_only_v3.jsonl 随机抽样作为 dev 集。

使用方式：
    python scripts/p5/finalize_eval_split.py
    python scripts/p5/finalize_eval_split.py --dev-count 300
"""

import argparse
import json
import random
from pathlib import Path
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description="评测数据集最终划分")
    parser.add_argument("--gold-reviewed",
                        default="data/p5_eval_pool/gold_reviewed.jsonl",
                        help="审查通过的标注文件（作为 test）")
    parser.add_argument("--p5-corpus",
                        default="data/corpus_for_kg/p5_only_v3.jsonl",
                        help="P5 语料文件（作为 dev 抽样来源）")
    parser.add_argument("--output-dir",
                        default="data/p5_eval_pool/final",
                        help="输出目录")
    parser.add_argument("--dev-count", type=int, default=300,
                        help="dev 集抽样数量（默认 300）")
    parser.add_argument("--seed", type=int, default=42,
                        help="随机种子（默认 42）")

    args = parser.parse_args()

    gold_path = Path(args.gold_reviewed)
    p5_path = Path(args.p5_corpus)
    output_dir = Path(args.output_dir)

    # 检查输入文件
    if not gold_path.exists():
        print(f"[ERROR] 文件不存在: {gold_path}")
        return
    if not p5_path.exists():
        print(f"[ERROR] 文件不存在: {p5_path}")
        return

    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("评测数据集最终划分")
    print("=" * 60)

    # ========== Step 1: 复制 gold_reviewed 作为 test_final ==========
    print("\n[Step 1] 复制 gold_reviewed → test_final")

    test_samples = []
    with open(gold_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    test_samples.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    test_path = output_dir / "test_final.jsonl"
    with open(test_path, "w", encoding="utf-8") as f:
        for sample in test_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    print(f"  test_final: {len(test_samples)} 条")
    print(f"  输出: {test_path}")

    # ========== Step 2: 从 p5_only_v3 随机抽样作为 dev_final ==========
    print(f"\n[Step 2] 从 p5_only_v3 随机抽样 {args.dev_count} 条 → dev_final")

    p5_samples = []
    with open(p5_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    p5_samples.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    print(f"  P5 语料总量: {len(p5_samples)} 条")

    # 随机抽样
    random.seed(args.seed)
    random.shuffle(p5_samples)
    dev_samples = p5_samples[:args.dev_count]

    # 转换字段格式，保持与 test_final 一致
    for s in dev_samples:
        # id -> doc_id
        if "id" in s and "doc_id" not in s:
            s["doc_id"] = s.pop("id")
        # text -> source_text
        if "text" in s and "source_text" not in s:
            s["source_text"] = s.pop("text")
        # 标记为无标注
        s["has_annotations"] = False

    dev_path = output_dir / "dev_final.jsonl"
    with open(dev_path, "w", encoding="utf-8") as f:
        for sample in dev_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    print(f"  dev_final: {len(dev_samples)} 条")
    print(f"  输出: {dev_path}")

    # ========== Step 3: 生成划分配置报告 ==========
    print("\n[Step 3] 生成划分配置报告")

    config = {
        "timestamp": datetime.now().isoformat(),
        "seed": args.seed,
        "test": {
            "file": str(test_path),
            "count": len(test_samples),
            "source": str(gold_path),
            "source_description": "gold_reviewed.jsonl (经 LLM 标注 + 二次审查)",
            "has_annotations": True
        },
        "dev": {
            "file": str(dev_path),
            "count": len(dev_samples),
            "source": str(p5_path),
            "source_description": "p5_only_v3.jsonl (随机抽样)",
            "has_annotations": False
        },
        "summary": {
            "total_samples": len(test_samples) + len(dev_samples),
            "test_ratio": len(test_samples) / (len(test_samples) + len(dev_samples)),
            "dev_ratio": len(dev_samples) / (len(test_samples) + len(dev_samples))
        }
    }

    config_path = output_dir / "split_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"  配置: {config_path}")

    # ========== 汇总 ==========
    print("\n" + "=" * 60)
    print("划分完成！")
    print("=" * 60)
    print(f"\n最终数据集:")
    print(f"  test_final.jsonl: {len(test_samples)} 条 (有标注，用于评测)")
    print(f"  dev_final.jsonl:  {len(dev_samples)} 条 (无标注，用于展示)")
    print(f"\n输出目录: {output_dir}")


if __name__ == "__main__":
    main()
