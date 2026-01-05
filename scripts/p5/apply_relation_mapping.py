#!/usr/bin/env python3
"""
应用关系映射，处理 Schema 漂移问题。

对 Gold 和 Pred 中的三元组关系进行映射/忽略，
使评测在统一的 Schema 下进行。

使用方式：
    python scripts/p5/apply_relation_mapping.py \
        --pred outputs/eval_models/gpt4o_mini/predictions_aligned.jsonl \
        --gold data/p5_eval_pool/final/test_final.jsonl \
        --mapping configs/relation_mapping.json \
        --out-pred outputs/eval_models/gpt4o_mini/predictions_mapped.jsonl \
        --out-gold outputs/eval_models/gpt4o_mini/gold_mapped.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_mapping_config(config_path: Path) -> Dict[str, Any]:
    """加载映射配置。"""
    if not config_path.exists():
        return {"relation_mapping": {}, "inverse_relations": {}, "ignore_relations": []}

    config = json.loads(config_path.read_text(encoding="utf-8"))
    return {
        "relation_mapping": config.get("relation_mapping", {}),
        "inverse_relations": config.get("inverse_relations", {}),
        "ignore_relations": config.get("ignore_relations", []),
    }


def apply_mapping_to_triple(
    triple: Dict[str, Any],
    config: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    对单个三元组应用映射规则。

    返回:
        - 映射后的三元组
        - None 表示应该忽略
    """
    predicate = triple.get("predicate", "")
    relation_mapping = config.get("relation_mapping", {})
    inverse_relations = config.get("inverse_relations", {})
    ignore_relations = config.get("ignore_relations", [])

    # 检查是否需要忽略
    if predicate in ignore_relations:
        return None

    # 检查是否有映射
    if predicate in relation_mapping:
        mapped = relation_mapping[predicate]
        if mapped == "IGNORE":
            return None
        # 应用映射
        new_triple = dict(triple)
        new_triple["predicate"] = mapped
        new_triple["original_predicate"] = predicate  # 保留原始关系
        return new_triple

    # 检查是否是逆向关系
    if predicate in inverse_relations:
        inv_config = inverse_relations[predicate]
        if inv_config.get("swap_direction", False):
            # 交换主宾
            new_triple = dict(triple)
            new_triple["predicate"] = inv_config.get("standard", predicate)
            new_triple["subject"], new_triple["object"] = triple.get("object", ""), triple.get("subject", "")
            new_triple["original_predicate"] = predicate
            return new_triple
        else:
            # 只替换关系名
            new_triple = dict(triple)
            new_triple["predicate"] = inv_config.get("standard", predicate)
            new_triple["original_predicate"] = predicate
            return new_triple

    # 无需映射，原样返回
    return triple


def apply_mapping_to_record(
    record: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """对单条记录应用映射。"""
    new_record = dict(record)

    # 处理三元组
    original_triples = record.get("triples", [])
    mapped_triples = []
    ignored_count = 0

    for triple in original_triples:
        mapped = apply_mapping_to_triple(triple, config)
        if mapped is not None:
            mapped_triples.append(mapped)
        else:
            ignored_count += 1

    new_record["triples"] = mapped_triples
    new_record["_mapping_stats"] = {
        "original_count": len(original_triples),
        "mapped_count": len(mapped_triples),
        "ignored_count": ignored_count,
    }

    return new_record


def apply_mapping_to_file(
    input_path: Path,
    output_path: Path,
    config: Dict[str, Any],
) -> Dict[str, int]:
    """对整个文件应用映射。"""
    records = []
    total_original = 0
    total_mapped = 0
    total_ignored = 0

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                mapped_record = apply_mapping_to_record(record, config)
                records.append(mapped_record)

                stats = mapped_record.get("_mapping_stats", {})
                total_original += stats.get("original_count", 0)
                total_mapped += stats.get("mapped_count", 0)
                total_ignored += stats.get("ignored_count", 0)
            except json.JSONDecodeError:
                continue

    # 保存
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {
        "record_count": len(records),
        "total_original": total_original,
        "total_mapped": total_mapped,
        "total_ignored": total_ignored,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="应用关系映射")
    parser.add_argument("--pred", required=True, help="预测结果文件（jsonl）")
    parser.add_argument("--gold", required=True, help="Gold 标注文件（jsonl）")
    parser.add_argument("--mapping", required=True, help="映射配置文件（json）")
    parser.add_argument("--out-pred", required=True, help="映射后的预测结果输出路径")
    parser.add_argument("--out-gold", required=True, help="映射后的 Gold 输出路径")

    args = parser.parse_args()

    pred_path = Path(args.pred)
    gold_path = Path(args.gold)
    mapping_path = Path(args.mapping)
    out_pred_path = Path(args.out_pred)
    out_gold_path = Path(args.out_gold)

    # 检查文件
    if not pred_path.exists():
        print(f"[ERROR] 预测文件不存在: {pred_path}")
        return
    if not gold_path.exists():
        print(f"[ERROR] Gold 文件不存在: {gold_path}")
        return
    if not mapping_path.exists():
        print(f"[WARN] 映射配置不存在，将不做任何映射: {mapping_path}")

    # 加载配置
    config = load_mapping_config(mapping_path)

    print("=" * 60)
    print("应用关系映射")
    print("=" * 60)
    print(f"映射规则数: {len(config.get('relation_mapping', {}))}")
    print(f"逆向规则数: {len(config.get('inverse_relations', {}))}")
    print(f"忽略关系数: {len(config.get('ignore_relations', []))}")
    print()

    # 处理 Pred
    print("[处理预测结果]")
    pred_stats = apply_mapping_to_file(pred_path, out_pred_path, config)
    print(f"  记录数: {pred_stats['record_count']}")
    print(f"  三元组: {pred_stats['total_original']} → {pred_stats['total_mapped']} (忽略 {pred_stats['total_ignored']})")
    print(f"  输出: {out_pred_path}")
    print()

    # 处理 Gold
    print("[处理 Gold 标注]")
    gold_stats = apply_mapping_to_file(gold_path, out_gold_path, config)
    print(f"  记录数: {gold_stats['record_count']}")
    print(f"  三元组: {gold_stats['total_original']} → {gold_stats['total_mapped']} (忽略 {gold_stats['total_ignored']})")
    print(f"  输出: {out_gold_path}")
    print()

    print("=" * 60)
    print("映射完成")
    print("=" * 60)

    # 保存统计
    stats_path = out_pred_path.with_suffix(".mapping_stats.json")
    stats = {
        "pred": pred_stats,
        "gold": gold_stats,
        "config": config,
    }
    stats_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"统计信息: {stats_path}")


if __name__ == "__main__":
    main()
