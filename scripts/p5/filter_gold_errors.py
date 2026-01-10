#!/usr/bin/env python3
"""
过滤 Gold/Pred 中包含 error 的行

用途：
- 剔除 Gold 或 Pred 中存在 error 的样本
- 只保留双方都有效的样本用于评测

使用方式：
    # 只过滤 Gold
    python scripts/p5/filter_gold_errors.py \
        --gold data/p5_eval_pool/gold.jsonl \
        --gold-out data/p5_eval_pool/gold_filtered.jsonl

    # 同时过滤 Gold 和 Pred（任一方有 error 则跳过）
    python scripts/p5/filter_gold_errors.py \
        --gold data/p5_eval_pool/gold.jsonl \
        --pred outputs/eval_models/xxx/predictions.jsonl \
        --gold-out data/p5_eval_pool/gold_filtered.jsonl \
        --pred-out outputs/eval_models/xxx/predictions_filtered.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional


def load_jsonl(path: Path) -> Dict[str, Dict[str, Any]]:
    """加载 JSONL 文件，返回 doc_id -> record 映射"""
    records = {}
    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                doc_id = d.get("doc_id", f"line_{line_num}")
                records[doc_id] = d
            except json.JSONDecodeError as e:
                print(f"  [WARN] JSON 解析失败 ({path.name} 行 {line_num}): {e}")
    return records


def has_error(record: Dict[str, Any]) -> Optional[str]:
    """检查记录是否有 error，返回 error 信息或 None"""
    if record.get("error"):
        return str(record.get("error"))
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="过滤 Gold/Pred 中包含 error 的行")
    parser.add_argument("--gold", "-g", required=True, help="输入 Gold 文件")
    parser.add_argument("--pred", "-p", default=None, help="输入 Pred 文件（可选）")
    parser.add_argument("--gold-out", "-go", required=True, help="输出过滤后的 Gold 文件")
    parser.add_argument("--pred-out", "-po", default=None, help="输出过滤后的 Pred 文件")

    # 兼容旧参数
    parser.add_argument("--input", "-i", default=None, help="(旧参数) 等同于 --gold")
    parser.add_argument("--output", "-o", default=None, help="(旧参数) 等同于 --gold-out")

    args = parser.parse_args()

    # 兼容旧参数
    gold_path = Path(args.gold if args.gold else args.input)
    gold_out_path = Path(args.gold_out if args.gold_out else args.output)
    pred_path = Path(args.pred) if args.pred else None
    pred_out_path = Path(args.pred_out) if args.pred_out else None

    if not gold_path.exists():
        print(f"[ERROR] Gold 文件不存在: {gold_path}", file=sys.stderr)
        sys.exit(1)

    if pred_path and not pred_path.exists():
        print(f"[ERROR] Pred 文件不存在: {pred_path}", file=sys.stderr)
        sys.exit(1)

    gold_out_path.parent.mkdir(parents=True, exist_ok=True)
    if pred_out_path:
        pred_out_path.parent.mkdir(parents=True, exist_ok=True)

    # 加载数据
    print(f"加载 Gold: {gold_path}")
    gold_records = load_jsonl(gold_path)
    print(f"  共 {len(gold_records)} 条")

    pred_records = {}
    if pred_path:
        print(f"加载 Pred: {pred_path}")
        pred_records = load_jsonl(pred_path)
        print(f"  共 {len(pred_records)} 条")

    # 统计
    stats = {
        "valid": 0,
        "gold_error": 0,
        "pred_error": 0,
        "both_error": 0,
        "pred_missing": 0,
    }

    skipped_details = []  # 记录跳过的详情

    # 过滤
    valid_gold = {}
    valid_pred = {}

    for doc_id, gold_rec in gold_records.items():
        gold_err = has_error(gold_rec)

        if pred_path:
            # 同时检查 Gold 和 Pred
            pred_rec = pred_records.get(doc_id)

            if pred_rec is None:
                stats["pred_missing"] += 1
                skipped_details.append(f"  [SKIP] {doc_id}: Pred 缺失")
                continue

            pred_err = has_error(pred_rec)

            if gold_err and pred_err:
                stats["both_error"] += 1
                skipped_details.append(f"  [SKIP] {doc_id}: Gold error={gold_err[:50]}..., Pred error={pred_err[:50]}...")
                continue
            elif gold_err:
                stats["gold_error"] += 1
                skipped_details.append(f"  [SKIP] {doc_id}: Gold error={gold_err[:80]}")
                continue
            elif pred_err:
                stats["pred_error"] += 1
                skipped_details.append(f"  [SKIP] {doc_id}: Pred error={pred_err[:80]}")
                continue

            # 双方都有效
            stats["valid"] += 1
            valid_gold[doc_id] = gold_rec
            valid_pred[doc_id] = pred_rec
        else:
            # 只检查 Gold
            if gold_err:
                stats["gold_error"] += 1
                skipped_details.append(f"  [SKIP] {doc_id}: Gold error={gold_err[:80]}")
                continue

            stats["valid"] += 1
            valid_gold[doc_id] = gold_rec

    # 输出跳过详情
    if skipped_details:
        print(f"\n跳过的样本 ({len(skipped_details)} 条):")
        for detail in skipped_details:
            print(detail)

    # 写入过滤后的文件
    with open(gold_out_path, "w", encoding="utf-8") as f:
        for doc_id in valid_gold:
            f.write(json.dumps(valid_gold[doc_id], ensure_ascii=False) + "\n")

    if pred_out_path and valid_pred:
        with open(pred_out_path, "w", encoding="utf-8") as f:
            for doc_id in valid_pred:
                f.write(json.dumps(valid_pred[doc_id], ensure_ascii=False) + "\n")

    # 输出统计
    print(f"\n过滤完成:")
    print(f"  有效样本: {stats['valid']}")
    print(f"  Gold error: {stats['gold_error']}")
    if pred_path:
        print(f"  Pred error: {stats['pred_error']}")
        print(f"  双方都 error: {stats['both_error']}")
        print(f"  Pred 缺失: {stats['pred_missing']}")
    print(f"\n输出文件:")
    print(f"  Gold: {gold_out_path}")
    if pred_out_path:
        print(f"  Pred: {pred_out_path}")


if __name__ == "__main__":
    main()
