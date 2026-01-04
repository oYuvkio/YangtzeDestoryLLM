#!/usr/bin/env python3
"""
合并 dev 和 test 语料，为统一标注和审查做准备

流程：
1. 合并 dev.jsonl + test.jsonl → combined_pool.jsonl
2. 标注后进行二次审查
3. 过滤后重新按比例划分 dev/test

使用方式：
    # 步骤1: 合并语料
    python scripts/p5/prepare_combined_pool.py --merge

    # 步骤2: 标注（使用 run_gold_annotation.sh）

    # 步骤3: 审查（使用 review_gold_annotations.py）

    # 步骤4: 重新划分
    python scripts/p5/prepare_combined_pool.py --split \
        --input data/p5_eval_pool/gold_reviewed.jsonl \
        --dev-ratio 0.6
"""

import argparse
import json
import random
from pathlib import Path
from datetime import datetime


def merge_pools(dev_path: Path, test_path: Path, output_path: Path,
                existing_gold: Path = None) -> dict:
    """
    合并 dev 和 test 语料

    如果指定 existing_gold，会排除已标注的文档（用于增量标注）
    """
    # 加载已标注的doc_id（如果有）
    existing_ids = set()
    if existing_gold and existing_gold.exists():
        with open(existing_gold, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        doc = json.loads(line)
                        existing_ids.add(doc.get("doc_id", ""))
                    except:
                        pass
        print(f"已有标注: {len(existing_ids)} 条")

    combined = []
    sources = {"dev": 0, "test": 0, "skipped": 0}
    seen_ids = set()

    for source, path in [("dev", dev_path), ("test", test_path)]:
        if not path.exists():
            print(f"[WARN] 文件不存在: {path}")
            continue

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    doc = json.loads(line)
                    doc_id = doc.get("doc_id", "")

                    # 去重
                    if doc_id in seen_ids:
                        continue
                    seen_ids.add(doc_id)

                    # 排除已标注的
                    if doc_id in existing_ids:
                        sources["skipped"] += 1
                        continue

                    # 记录来源
                    doc["_source"] = source
                    combined.append(doc)
                    sources[source] += 1
                except json.JSONDecodeError:
                    continue

    # 保存合并结果
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for doc in combined:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    stats = {
        "dev_count": sources["dev"],
        "test_count": sources["test"],
        "skipped_existing": sources["skipped"],
        "total": len(combined),
        "output": str(output_path),
        "timestamp": datetime.now().isoformat()
    }

    # 保存配置
    config_path = output_path.with_suffix(".config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return stats


def split_by_ratio(input_path: Path, output_dir: Path,
                   dev_ratio: float = 0.6, seed: int = 42) -> dict:
    """
    按比例重新划分 dev/test
    """
    samples = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    samples.append(json.loads(line))
                except:
                    pass

    if not samples:
        print("[ERROR] 没有找到有效样本")
        return {}

    # 随机打乱
    random.seed(seed)
    random.shuffle(samples)

    # 划分
    split_idx = int(len(samples) * dev_ratio)
    dev_samples = samples[:split_idx]
    test_samples = samples[split_idx:]

    # 保存
    output_dir.mkdir(parents=True, exist_ok=True)

    dev_path = output_dir / "dev_final.jsonl"
    test_path = output_dir / "test_final.jsonl"

    with open(dev_path, "w", encoding="utf-8") as f:
        for doc in dev_samples:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    with open(test_path, "w", encoding="utf-8") as f:
        for doc in test_samples:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    stats = {
        "total": len(samples),
        "dev_count": len(dev_samples),
        "test_count": len(test_samples),
        "dev_ratio": dev_ratio,
        "seed": seed,
        "dev_path": str(dev_path),
        "test_path": str(test_path),
        "timestamp": datetime.now().isoformat()
    }

    # 保存配置
    config_path = output_dir / "split_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return stats


def main():
    parser = argparse.ArgumentParser(description="合并/划分评估语料")
    parser.add_argument("--merge", action="store_true", help="合并 dev 和 test")
    parser.add_argument("--split", action="store_true", help="按比例划分")

    # 合并参数
    parser.add_argument("--dev", default="data/p5_eval_pool/dev.jsonl", help="dev文件路径")
    parser.add_argument("--test", default="data/p5_eval_pool/test.jsonl", help="test文件路径")
    parser.add_argument("--output", "-o", default="data/p5_eval_pool/combined_pool.jsonl",
                        help="输出文件路径")
    parser.add_argument("--existing-gold", default=None,
                        help="已有标注文件（用于增量标注，跳过已标注的）")

    # 划分参数
    parser.add_argument("--input", "-i", help="待划分的文件（审查通过的）")
    parser.add_argument("--output-dir", default="data/p5_eval_pool/final",
                        help="划分后的输出目录")
    parser.add_argument("--dev-ratio", type=float, default=0.6, help="dev集比例")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")

    args = parser.parse_args()

    if args.merge:
        print("=" * 60)
        print("合并 dev + test 语料")
        print("=" * 60)

        stats = merge_pools(
            Path(args.dev),
            Path(args.test),
            Path(args.output),
            Path(args.existing_gold) if args.existing_gold else None
        )

        print(f"\n合并完成:")
        print(f"  dev 来源: {stats['dev_count']} 条")
        print(f"  test 来源: {stats['test_count']} 条")
        print(f"  跳过已标注: {stats['skipped_existing']} 条")
        print(f"  总计: {stats['total']} 条")
        print(f"  输出: {stats['output']}")

    elif args.split:
        if not args.input:
            print("[ERROR] 必须指定 --input 参数")
            return

        print("=" * 60)
        print("按比例划分 dev/test")
        print("=" * 60)

        stats = split_by_ratio(
            Path(args.input),
            Path(args.output_dir),
            args.dev_ratio,
            args.seed
        )

        if stats:
            print(f"\n划分完成:")
            print(f"  总样本: {stats['total']} 条")
            print(f"  dev: {stats['dev_count']} 条 ({stats['dev_ratio']*100:.0f}%)")
            print(f"  test: {stats['test_count']} 条 ({(1-stats['dev_ratio'])*100:.0f}%)")
            print(f"  dev 输出: {stats['dev_path']}")
            print(f"  test 输出: {stats['test_path']}")
    else:
        print("请指定 --merge 或 --split 操作")
        parser.print_help()


if __name__ == "__main__":
    main()
