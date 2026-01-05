#!/usr/bin/env python3
"""
三元组匹配诊断脚本

对比 Pred 和 Gold 的关系分布，生成智能映射建议。

使用方式：
    python scripts/p5/diagnose_triple_mismatch.py \
        --pred outputs/eval_models/Qwen_Qwen3-8B/predictions.jsonl \
        --gold data/p5_eval_pool/final/test_final.jsonl \
        --tbox outputs/cq_pipeline/final/p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json \
        --output-mapping configs/relation_mapping.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
from difflib import SequenceMatcher


# ============================================================
# 归一化函数
# ============================================================
_NORMALIZE_RE = re.compile(r"[\s\-_./:]+")


def normalize_label(name: str) -> str:
    """对关系名做轻量归一化。"""
    if not name:
        return ""
    return _NORMALIZE_RE.sub("", name.strip().lower())


# ============================================================
# 数据加载
# ============================================================
def load_relations_from_jsonl(path: Path) -> Counter:
    """从 JSONL 文件加载关系频次。"""
    counter: Counter = Counter()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                for triple in data.get("triples", []):
                    predicate = triple.get("predicate", "")
                    if predicate:
                        counter[predicate] += 1
            except json.JSONDecodeError:
                continue
    return counter


def load_tbox_relations(tbox_path: Path) -> Dict[str, Dict[str, str]]:
    """加载 TBox 关系定义，返回 {name: {cn_name, domain, range}}。"""
    tbox = json.loads(tbox_path.read_text(encoding="utf-8"))
    relations = {}
    for r in tbox.get("relations", []):
        name = r.get("name", "")
        if name:
            relations[name] = {
                "cn_name": r.get("cn_name", ""),
                "domain": r.get("domain", ""),
                "range": r.get("range", ""),
            }
    return relations


# ============================================================
# 智能映射建议
# ============================================================
# 预定义的语义映射规则（Gold 关系 -> TBox 关系）
SEMANTIC_MAPPING_RULES = {
    # 影响类
    "affects": "affects_region",
    "affected_by": "affects_region",  # 需要 swap
    "has_impact": "causes_impact",
    "causes": "causes_impact",
    "has_cause": "has_hazard_factor",

    # 位置类
    "located_in": "located_in",
    "occurs_at": "located_in",
    "located_at": "located_in",

    # 组成类
    "part_of": "belongs_to_basin",  # 可能需要根据上下文
    "composed_of": "belongs_to_basin",
    "consists_of": "belongs_to_basin",

    # 触发/响应类
    "triggers": "triggers_response",
    "implements": "implements_measure",
    "executes": "executes_operation",

    # 水系类
    "flows_into": "flows_into",
    "flows_through": "flows_into",
    "connects_to": "connects_lake",

    # 保护类
    "protects": "protects_region",
    "mitigates": "implements_measure",

    # 属性类（建议忽略，因为这些是属性值而非关系）
    "has_value": "IGNORE",
    "has_attribute": "IGNORE",
    "has_property": "IGNORE",
}

# 需要交换主宾的关系
INVERSE_RELATIONS = {
    "affected_by": {"standard": "affects_region", "swap_direction": True},
    "caused_by": {"standard": "causes_impact", "swap_direction": True},
    "protected_by": {"standard": "protects_region", "swap_direction": True},
}


def compute_similarity(s1: str, s2: str) -> float:
    """计算两个字符串的相似度。"""
    return SequenceMatcher(None, normalize_label(s1), normalize_label(s2)).ratio()


def suggest_mapping(
    gold_rel: str,
    tbox_relations: Dict[str, Dict[str, str]],
    threshold: float = 0.6,
) -> Tuple[str, float, str]:
    """
    为 Gold 关系建议 TBox 映射。

    返回: (建议的 TBox 关系, 相似度, 映射原因)
    """
    gold_norm = normalize_label(gold_rel)

    # 1. 检查预定义规则
    if gold_rel in SEMANTIC_MAPPING_RULES:
        target = SEMANTIC_MAPPING_RULES[gold_rel]
        if target == "IGNORE":
            return "IGNORE", 1.0, "预定义规则（属性值）"
        if target in tbox_relations:
            return target, 1.0, "预定义语义映射"

    # 2. 精确匹配（归一化后）
    for tbox_rel in tbox_relations:
        if normalize_label(tbox_rel) == gold_norm:
            return tbox_rel, 1.0, "精确匹配"

    # 3. 中文名匹配
    for tbox_rel, info in tbox_relations.items():
        cn_name = info.get("cn_name", "")
        if cn_name and normalize_label(cn_name) == gold_norm:
            return tbox_rel, 1.0, "中文名匹配"

    # 4. 模糊匹配
    best_match = None
    best_score = 0.0
    for tbox_rel in tbox_relations:
        score = compute_similarity(gold_rel, tbox_rel)
        if score > best_score:
            best_score = score
            best_match = tbox_rel

    if best_match and best_score >= threshold:
        return best_match, best_score, f"模糊匹配 ({best_score:.2f})"

    # 5. 无法映射
    return "IGNORE", 0.0, "无匹配"


def generate_mapping_config(
    gold_relations: Counter,
    tbox_relations: Dict[str, Dict[str, str]],
    min_freq: int = 3,
) -> Dict[str, Any]:
    """
    生成完整的映射配置。

    Args:
        gold_relations: Gold 关系频次
        tbox_relations: TBox 关系定义
        min_freq: 最小频次阈值（低于此频次的关系直接忽略）
    """
    relation_mapping = {}
    inverse_relations = {}
    ignore_relations = []
    mapping_report = []

    tbox_rel_set = set(tbox_relations.keys())

    for gold_rel, count in sorted(gold_relations.items(), key=lambda x: -x[1]):
        # 已在 TBox 中的关系不需要映射
        if gold_rel in tbox_rel_set or normalize_label(gold_rel) in {normalize_label(r) for r in tbox_rel_set}:
            mapping_report.append({
                "gold_relation": gold_rel,
                "frequency": count,
                "mapping": gold_rel,
                "reason": "TBox 原生关系",
                "action": "保留",
            })
            continue

        # 低频关系直接忽略
        if count < min_freq:
            ignore_relations.append(gold_rel)
            mapping_report.append({
                "gold_relation": gold_rel,
                "frequency": count,
                "mapping": "IGNORE",
                "reason": f"低频关系 (freq={count} < {min_freq})",
                "action": "忽略",
            })
            continue

        # 检查是否需要逆向映射
        if gold_rel in INVERSE_RELATIONS:
            inv_config = INVERSE_RELATIONS[gold_rel]
            inverse_relations[gold_rel] = inv_config
            mapping_report.append({
                "gold_relation": gold_rel,
                "frequency": count,
                "mapping": inv_config["standard"],
                "reason": "逆向关系（交换主宾）",
                "action": "逆向映射",
            })
            continue

        # 智能建议映射
        suggested, score, reason = suggest_mapping(gold_rel, tbox_relations)

        if suggested != "IGNORE":
            relation_mapping[gold_rel] = suggested
            mapping_report.append({
                "gold_relation": gold_rel,
                "frequency": count,
                "mapping": suggested,
                "similarity": score,
                "reason": reason,
                "action": "映射",
            })
        else:
            relation_mapping[gold_rel] = "IGNORE"
            mapping_report.append({
                "gold_relation": gold_rel,
                "frequency": count,
                "mapping": "IGNORE",
                "reason": reason,
                "action": "忽略",
            })

    return {
        "relation_mapping": relation_mapping,
        "inverse_relations": inverse_relations,
        "ignore_relations": ignore_relations,
        "_mapping_report": mapping_report,
    }


# ============================================================
# 诊断报告
# ============================================================
def print_comparison_report(
    pred_relations: Counter,
    gold_relations: Counter,
    tbox_relations: Dict[str, Dict[str, str]],
) -> None:
    """打印 Pred vs Gold 关系分布对比报告。"""

    tbox_rel_set = set(tbox_relations.keys())
    tbox_rel_norm = {normalize_label(r) for r in tbox_rel_set}

    print("=" * 80)
    print("三元组关系分布诊断报告")
    print("=" * 80)
    print()

    # 统计
    pred_total = sum(pred_relations.values())
    gold_total = sum(gold_relations.values())

    pred_in_tbox = sum(c for r, c in pred_relations.items() if normalize_label(r) in tbox_rel_norm)
    gold_in_tbox = sum(c for r, c in gold_relations.items() if normalize_label(r) in tbox_rel_norm)

    print(f"{'指标':<25} {'Pred':<15} {'Gold':<15}")
    print("-" * 55)
    print(f"{'关系种类':<25} {len(pred_relations):<15} {len(gold_relations):<15}")
    print(f"{'三元组总数':<25} {pred_total:<15} {gold_total:<15}")
    print(f"{'TBox 关系三元组':<25} {pred_in_tbox:<15} {gold_in_tbox:<15}")
    print(f"{'TBox 覆盖率':<25} {pred_in_tbox/pred_total*100:.1f}%{'':<10} {gold_in_tbox/gold_total*100:.1f}%")
    print()

    # 关系对比
    all_relations = set(pred_relations.keys()) | set(gold_relations.keys())

    print("-" * 80)
    print("关系分布对比 (按 Gold 频次排序)")
    print("-" * 80)
    print(f"{'关系名':<35} {'Pred':<10} {'Gold':<10} {'TBox':<8} {'状态'}")
    print("-" * 80)

    for rel in sorted(all_relations, key=lambda r: -gold_relations.get(r, 0)):
        pred_count = pred_relations.get(rel, 0)
        gold_count = gold_relations.get(rel, 0)
        in_tbox = "✅" if normalize_label(rel) in tbox_rel_norm else "❌"

        if pred_count > 0 and gold_count > 0:
            status = "双方都有"
        elif pred_count > 0:
            status = "仅 Pred"
        else:
            status = "仅 Gold"

        print(f"{rel:<35} {pred_count:<10} {gold_count:<10} {in_tbox:<8} {status}")

    print()

    # 问题诊断
    print("=" * 80)
    print("问题诊断")
    print("=" * 80)

    # Gold 高频但不在 TBox 的关系
    gold_not_in_tbox = [(r, c) for r, c in gold_relations.most_common()
                        if normalize_label(r) not in tbox_rel_norm]
    if gold_not_in_tbox:
        print()
        print("【问题 1】Gold 高频关系不在 TBox 中（需要映射）:")
        for rel, count in gold_not_in_tbox[:10]:
            suggested, score, reason = suggest_mapping(rel, tbox_relations)
            print(f"  {rel:<30} freq={count:<6} -> {suggested:<25} ({reason})")

    # Pred 有但 Gold 没有的关系
    pred_only = [(r, c) for r, c in pred_relations.most_common()
                 if gold_relations.get(r, 0) == 0]
    if pred_only:
        print()
        print("【问题 2】Pred 预测了但 Gold 中没有的关系（可能是模型偏见）:")
        for rel, count in pred_only[:10]:
            print(f"  {rel:<30} freq={count}")

    # Gold 有但 Pred 没有的关系
    gold_only = [(r, c) for r, c in gold_relations.most_common()
                 if pred_relations.get(r, 0) == 0 and c >= 10]
    if gold_only:
        print()
        print("【问题 3】Gold 中有但 Pred 未预测的高频关系（模型召回不足）:")
        for rel, count in gold_only[:10]:
            print(f"  {rel:<30} freq={count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="三元组匹配诊断")
    parser.add_argument("--pred", required=True, help="Pred 预测文件（jsonl）")
    parser.add_argument("--gold", required=True, help="Gold 标注文件（jsonl）")
    parser.add_argument("--tbox", required=True, help="TBox 文件（json）")
    parser.add_argument("--output-mapping", default=None, help="输出映射配置路径")
    parser.add_argument("--min-freq", type=int, default=3, help="最小频次阈值")

    args = parser.parse_args()

    pred_path = Path(args.pred)
    gold_path = Path(args.gold)
    tbox_path = Path(args.tbox)

    # 加载数据
    pred_relations = load_relations_from_jsonl(pred_path)
    gold_relations = load_relations_from_jsonl(gold_path)
    tbox_relations = load_tbox_relations(tbox_path)

    # 打印诊断报告
    print_comparison_report(pred_relations, gold_relations, tbox_relations)

    # 生成映射配置
    config = generate_mapping_config(gold_relations, tbox_relations, args.min_freq)

    # 打印映射建议
    print()
    print("=" * 80)
    print("映射配置建议")
    print("=" * 80)

    mapped_count = sum(1 for v in config["relation_mapping"].values() if v != "IGNORE")
    ignored_count = sum(1 for v in config["relation_mapping"].values() if v == "IGNORE")
    inverse_count = len(config["inverse_relations"])

    print(f"  映射关系数: {mapped_count}")
    print(f"  忽略关系数: {ignored_count}")
    print(f"  逆向关系数: {inverse_count}")
    print()

    print("【映射详情】")
    for item in config["_mapping_report"]:
        if item["action"] == "映射":
            print(f"  {item['gold_relation']:<30} -> {item['mapping']:<25} ({item['reason']})")

    print()
    print("【忽略详情】")
    for item in config["_mapping_report"]:
        if item["action"] == "忽略" and item["frequency"] >= 10:
            print(f"  {item['gold_relation']:<30} freq={item['frequency']:<6} ({item['reason']})")

    # 保存配置
    if args.output_mapping:
        output_path = Path(args.output_mapping)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 移除内部报告字段
        save_config = {
            "relation_mapping": config["relation_mapping"],
            "inverse_relations": config["inverse_relations"],
            "ignore_relations": config["ignore_relations"],
        }

        output_path.write_text(
            json.dumps(save_config, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print()
        print(f"映射配置已保存: {output_path}")


if __name__ == "__main__":
    main()
