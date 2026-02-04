#!/usr/bin/env python3
"""
实体同义词归一化

根据同义词库，将三元组中的实体统一归一化为规范名称。

问题背景：
- Gold: (人为因素, has_hazard_factor, 洪水)
- Pred: (洪水, has_hazard_factor, 人类活动)
- 问题：即使语义相同，因为表述不同导致不匹配

解决方案：
1. 加载同义词库
2. 将三元组中的 subject 和 object 归一化为规范名称
3. 输出归一化后的文件

使用方式：
    python scripts/p5/normalize_entities.py \
        --input data/p5_eval_pool/gold.jsonl \
        --synonyms configs/entity_synonyms.json \
        --output data/p5_eval_pool/gold_entity_normalized.jsonl

    # 同时归一化 Gold 和 Pred
    python scripts/p5/normalize_entities.py \
        --gold data/p5_eval_pool/gold.jsonl \
        --pred outputs/eval_models/xxx/predictions.jsonl \
        --synonyms configs/entity_synonyms.json \
        --gold-out data/p5_eval_pool/gold_entity_normalized.jsonl \
        --pred-out outputs/eval_models/xxx/predictions_entity_normalized.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional


def load_synonyms(synonyms_path: Path) -> Dict[str, str]:
    """
    加载同义词库，构建 synonym -> canonical 映射

    Returns:
        Dict[synonym, canonical_name]
    """
    data = json.loads(synonyms_path.read_text(encoding="utf-8"))

    mapping = {}
    for key, entry in data.items():
        if key.startswith("_"):
            continue  # 跳过描述字段

        canonical = entry.get("canonical", "")
        synonyms = entry.get("synonyms", [])

        if canonical:
            # 规范名映射到自己
            mapping[canonical.lower()] = canonical
            # 同义词映射到规范名
            for syn in synonyms:
                mapping[syn.lower()] = canonical

    return mapping


def normalize_entity(entity: str, synonym_map: Dict[str, str]) -> str:
    """
    归一化单个实体

    Args:
        entity: 原始实体名
        synonym_map: 同义词映射表

    Returns:
        归一化后的实体名（如果没找到映射则返回原名）
    """
    if entity is None:
        return ""
    entity_text = str(entity)
    entity_lower = entity_text.lower().strip()

    # 1. 精确匹配
    if entity_lower in synonym_map:
        return synonym_map[entity_lower]

    # 2. 包含匹配（检查实体是否包含某个同义词）
    for syn, canonical in synonym_map.items():
        if syn in entity_lower or entity_lower in syn:
            # 只有当长度相近时才认为是匹配
            if abs(len(syn) - len(entity_lower)) <= 3:
                return canonical

    return entity_text


def normalize_triple(triple: Dict[str, Any], synonym_map: Dict[str, str]) -> Dict[str, Any]:
    """
    归一化单个三元组中的实体
    """
    normalized = dict(triple)

    subject = triple.get("subject", "")
    obj = triple.get("object", "")

    new_subject = normalize_entity(subject, synonym_map)
    new_object = normalize_entity(obj, synonym_map)

    # 记录变更
    changes = []
    if new_subject != subject:
        normalized["subject"] = new_subject
        normalized["_original_subject"] = subject
        changes.append(f"subject: {subject} -> {new_subject}")

    if new_object != obj:
        normalized["object"] = new_object
        normalized["_original_object"] = obj
        changes.append(f"object: {obj} -> {new_object}")

    if changes:
        normalized["_entity_normalized"] = True

    return normalized


def normalize_file(
    input_path: Path,
    output_path: Path,
    synonym_map: Dict[str, str]
) -> Dict[str, int]:
    """
    归一化文件中所有三元组的实体

    Returns:
        统计信息
    """
    stats = {
        "total_records": 0,
        "total_triples": 0,
        "normalized_triples": 0,
        "subject_changes": 0,
        "object_changes": 0,
    }

    with open(input_path, encoding="utf-8") as f_in, \
         open(output_path, "w", encoding="utf-8") as f_out:
        for line in f_in:
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                f_out.write(line + "\n")
                continue

            stats["total_records"] += 1

            # 归一化三元组
            triples = record.get("triples", [])
            normalized_triples = []

            for triple in triples:
                stats["total_triples"] += 1
                normalized = normalize_triple(triple, synonym_map)
                normalized_triples.append(normalized)

                if normalized.get("_entity_normalized"):
                    stats["normalized_triples"] += 1
                if normalized.get("_original_subject"):
                    stats["subject_changes"] += 1
                if normalized.get("_original_object"):
                    stats["object_changes"] += 1

            record["triples"] = normalized_triples
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="实体同义词归一化")

    # 单文件模式
    parser.add_argument("--input", "-i", default=None, help="输入文件（单文件模式）")
    parser.add_argument("--output", "-o", default=None, help="输出文件（单文件模式）")

    # 双文件模式
    parser.add_argument("--gold", "-g", default=None, help="Gold 文件")
    parser.add_argument("--pred", "-p", default=None, help="Pred 文件")
    parser.add_argument("--gold-out", "-go", default=None, help="归一化后的 Gold 文件")
    parser.add_argument("--pred-out", "-po", default=None, help="归一化后的 Pred 文件")

    # 同义词库
    parser.add_argument("--synonyms", "-s", required=True, help="同义词库文件路径")

    args = parser.parse_args()

    # 检查参数
    if args.input and args.output:
        files_to_process = [(Path(args.input), Path(args.output))]
    elif args.gold and args.gold_out:
        files_to_process = [(Path(args.gold), Path(args.gold_out))]
        if args.pred and args.pred_out:
            files_to_process.append((Path(args.pred), Path(args.pred_out)))
    else:
        print("错误：请指定 --input/--output 或 --gold/--gold-out", file=sys.stderr)
        sys.exit(1)

    # 加载同义词库
    synonyms_path = Path(args.synonyms)
    if not synonyms_path.exists():
        print(f"错误：同义词库文件不存在: {synonyms_path}", file=sys.stderr)
        sys.exit(1)

    print(f"加载同义词库: {synonyms_path}")
    synonym_map = load_synonyms(synonyms_path)
    print(f"  同义词条目数: {len(synonym_map)}")

    # 处理文件
    total_stats = {
        "total_records": 0,
        "total_triples": 0,
        "normalized_triples": 0,
        "subject_changes": 0,
        "object_changes": 0,
    }

    for input_path, output_path in files_to_process:
        if not input_path.exists():
            print(f"警告：文件不存在: {input_path}")
            continue

        output_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"\n处理: {input_path}")
        stats = normalize_file(input_path, output_path, synonym_map)

        print(f"  记录数: {stats['total_records']}")
        print(f"  三元组数: {stats['total_triples']}")
        print(f"  归一化三元组: {stats['normalized_triples']} ({stats['normalized_triples']/max(1, stats['total_triples'])*100:.1f}%)")
        print(f"  主语变更: {stats['subject_changes']}")
        print(f"  宾语变更: {stats['object_changes']}")
        print(f"  输出: {output_path}")

        for key in total_stats:
            total_stats[key] += stats[key]

    # 总结
    print("\n" + "=" * 50)
    print("实体归一化完成")
    print("=" * 50)
    print(f"总记录数: {total_stats['total_records']}")
    print(f"总三元组数: {total_stats['total_triples']}")
    print(f"总归一化数: {total_stats['normalized_triples']} ({total_stats['normalized_triples']/max(1, total_stats['total_triples'])*100:.1f}%)")


if __name__ == "__main__":
    main()
