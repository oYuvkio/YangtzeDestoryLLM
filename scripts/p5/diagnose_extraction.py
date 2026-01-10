#!/usr/bin/env python3
"""
抽取诊断脚本

分析 Gold 和 Pred 之间的差异，生成诊断报告，帮助理解低指标的原因。

功能：
1. 统计 events 不一致情况
2. 统计关系分布差异
3. 找出典型不匹配样本
4. 分析主宾颠倒情况
5. 输出诊断报告

使用方式：
    python scripts/p5/diagnose_extraction.py \
        --gold data/p5_eval_pool/gold.jsonl \
        --pred outputs/eval_models/xxx/predictions.jsonl \
        --tbox outputs/cq_pipeline/final/tbox_s2_optimized.json \
        --output outputs/eval_models/xxx/diagnosis_report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Any, List, Tuple, Set
from difflib import SequenceMatcher


def load_jsonl(path: Path) -> List[Dict]:
    """加载 JSONL 文件"""
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def load_tbox(path: Path) -> Dict[str, Any]:
    """加载 TBox"""
    return json.loads(path.read_text(encoding="utf-8"))


def analyze_events(gold_records: List[Dict], pred_records: List[Dict]) -> Dict[str, Any]:
    """
    分析事件不一致情况

    Returns:
        事件分析结果
    """
    stats = {
        "gold_event_count": 0,
        "pred_event_count": 0,
        "gold_has_pred_missing": 0,  # Gold有事件但Pred没有
        "pred_has_gold_missing": 0,  # Pred有事件但Gold没有
        "both_have_events": 0,
        "neither_has_events": 0,
        "event_type_distribution_gold": Counter(),
        "event_type_distribution_pred": Counter(),
        "mismatched_samples": [],
    }

    # 构建 doc_id -> record 映射
    gold_map = {r.get("doc_id", ""): r for r in gold_records}
    pred_map = {r.get("doc_id", ""): r for r in pred_records}

    all_doc_ids = set(gold_map.keys()) | set(pred_map.keys())

    for doc_id in all_doc_ids:
        gold_record = gold_map.get(doc_id, {})
        pred_record = pred_map.get(doc_id, {})

        gold_events = gold_record.get("events", [])
        pred_events = pred_record.get("events", [])

        stats["gold_event_count"] += len(gold_events)
        stats["pred_event_count"] += len(pred_events)

        # 统计事件类型分布
        for e in gold_events:
            etype = e.get("event_type", "Unknown")
            stats["event_type_distribution_gold"][etype] += 1

        for e in pred_events:
            etype = e.get("event_type", "Unknown")
            stats["event_type_distribution_pred"][etype] += 1

        # 统计不一致情况
        gold_has = len(gold_events) > 0
        pred_has = len(pred_events) > 0

        if gold_has and not pred_has:
            stats["gold_has_pred_missing"] += 1
            if len(stats["mismatched_samples"]) < 10:
                stats["mismatched_samples"].append({
                    "doc_id": doc_id,
                    "type": "gold_has_pred_missing",
                    "gold_events": [e.get("name", "") for e in gold_events],
                    "pred_events": [],
                })
        elif pred_has and not gold_has:
            stats["pred_has_gold_missing"] += 1
            if len(stats["mismatched_samples"]) < 10:
                stats["mismatched_samples"].append({
                    "doc_id": doc_id,
                    "type": "pred_has_gold_missing",
                    "gold_events": [],
                    "pred_events": [e.get("name", "") for e in pred_events],
                })
        elif gold_has and pred_has:
            stats["both_have_events"] += 1
        else:
            stats["neither_has_events"] += 1

    # 转换 Counter 为普通 dict
    stats["event_type_distribution_gold"] = dict(stats["event_type_distribution_gold"].most_common())
    stats["event_type_distribution_pred"] = dict(stats["event_type_distribution_pred"].most_common())

    return stats


def analyze_relations(gold_records: List[Dict], pred_records: List[Dict], tbox: Dict) -> Dict[str, Any]:
    """
    分析关系分布差异

    Returns:
        关系分析结果
    """
    stats = {
        "gold_triple_count": 0,
        "pred_triple_count": 0,
        "relation_distribution_gold": Counter(),
        "relation_distribution_pred": Counter(),
        "relations_only_in_gold": [],
        "relations_only_in_pred": [],
        "tbox_relations_unused_by_gold": [],
        "tbox_relations_unused_by_pred": [],
    }

    # 统计关系分布
    for r in gold_records:
        for t in r.get("triples", []):
            pred_name = t.get("predicate", "")
            stats["relation_distribution_gold"][pred_name] += 1
            stats["gold_triple_count"] += 1

    for r in pred_records:
        for t in r.get("triples", []):
            pred_name = t.get("predicate", "")
            stats["relation_distribution_pred"][pred_name] += 1
            stats["pred_triple_count"] += 1

    # 找出差异
    gold_relations = set(stats["relation_distribution_gold"].keys())
    pred_relations = set(stats["relation_distribution_pred"].keys())

    stats["relations_only_in_gold"] = sorted(gold_relations - pred_relations)
    stats["relations_only_in_pred"] = sorted(pred_relations - gold_relations)

    # TBox 关系使用情况
    tbox_relations = {r["name"] for r in tbox.get("relations", [])}
    stats["tbox_relations_unused_by_gold"] = sorted(tbox_relations - gold_relations)
    stats["tbox_relations_unused_by_pred"] = sorted(tbox_relations - pred_relations)

    # 转换 Counter 为普通 dict
    stats["relation_distribution_gold"] = dict(stats["relation_distribution_gold"].most_common())
    stats["relation_distribution_pred"] = dict(stats["relation_distribution_pred"].most_common())

    return stats


def analyze_subject_object_swap(gold_records: List[Dict], pred_records: List[Dict]) -> Dict[str, Any]:
    """
    分析主宾颠倒情况

    Returns:
        主宾颠倒分析结果
    """
    stats = {
        "potential_swaps": 0,
        "swap_examples": [],
    }

    # 构建 doc_id -> record 映射
    gold_map = {r.get("doc_id", ""): r for r in gold_records}
    pred_map = {r.get("doc_id", ""): r for r in pred_records}

    for doc_id, gold_record in gold_map.items():
        pred_record = pred_map.get(doc_id, {})
        gold_triples = gold_record.get("triples", [])
        pred_triples = pred_record.get("triples", [])

        for gt in gold_triples:
            g_subj = gt.get("subject", "")
            g_pred = gt.get("predicate", "")
            g_obj = gt.get("object", "")

            for pt in pred_triples:
                p_subj = pt.get("subject", "")
                p_pred = pt.get("predicate", "")
                p_obj = pt.get("object", "")

                # 检查是否主宾颠倒（关系相同，但主宾交换）
                if p_pred == g_pred:
                    # 主宾完全颠倒
                    if p_subj == g_obj and p_obj == g_subj:
                        stats["potential_swaps"] += 1
                        if len(stats["swap_examples"]) < 20:
                            stats["swap_examples"].append({
                                "doc_id": doc_id,
                                "gold": f"({g_subj}, {g_pred}, {g_obj})",
                                "pred": f"({p_subj}, {p_pred}, {p_obj})",
                                "type": "exact_swap",
                            })
                    # 模糊匹配主宾颠倒
                    elif (similarity(p_subj, g_obj) > 0.8 and similarity(p_obj, g_subj) > 0.8):
                        stats["potential_swaps"] += 1
                        if len(stats["swap_examples"]) < 20:
                            stats["swap_examples"].append({
                                "doc_id": doc_id,
                                "gold": f"({g_subj}, {g_pred}, {g_obj})",
                                "pred": f"({p_subj}, {p_pred}, {p_obj})",
                                "type": "fuzzy_swap",
                            })

    return stats


def similarity(a: str, b: str) -> float:
    """计算两个字符串的相似度"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def analyze_entity_alignment(gold_records: List[Dict], pred_records: List[Dict]) -> Dict[str, Any]:
    """
    分析实体对齐情况

    Returns:
        实体对齐分析结果
    """
    stats = {
        "gold_entity_count": 0,
        "pred_entity_count": 0,
        "exact_matches": 0,
        "fuzzy_matches": 0,
        "unmatched_gold": [],
        "unmatched_pred": [],
        "alignment_examples": [],
    }

    # 收集所有实体
    gold_entities = set()
    pred_entities = set()

    for r in gold_records:
        for t in r.get("triples", []):
            if t.get("subject"):
                gold_entities.add(t["subject"])
            if t.get("object"):
                gold_entities.add(t["object"])

    for r in pred_records:
        for t in r.get("triples", []):
            if t.get("subject"):
                pred_entities.add(t["subject"])
            if t.get("object"):
                pred_entities.add(t["object"])

    stats["gold_entity_count"] = len(gold_entities)
    stats["pred_entity_count"] = len(pred_entities)

    # 精确匹配
    exact_matches = gold_entities & pred_entities
    stats["exact_matches"] = len(exact_matches)

    # 模糊匹配
    unmatched_gold = gold_entities - exact_matches
    unmatched_pred = pred_entities - exact_matches

    fuzzy_matched_gold = set()
    fuzzy_matched_pred = set()

    for g in unmatched_gold:
        for p in unmatched_pred:
            if p in fuzzy_matched_pred:
                continue
            sim = similarity(g, p)
            if sim > 0.8:
                stats["fuzzy_matches"] += 1
                fuzzy_matched_gold.add(g)
                fuzzy_matched_pred.add(p)
                if len(stats["alignment_examples"]) < 20:
                    stats["alignment_examples"].append({
                        "gold": g,
                        "pred": p,
                        "similarity": round(sim, 3),
                    })
                break

    # 未匹配实体
    stats["unmatched_gold"] = sorted(unmatched_gold - fuzzy_matched_gold)[:50]
    stats["unmatched_pred"] = sorted(unmatched_pred - fuzzy_matched_pred)[:50]

    return stats


def analyze_mismatches(gold_records: List[Dict], pred_records: List[Dict]) -> Dict[str, Any]:
    """
    分析典型不匹配样本

    Returns:
        不匹配分析结果
    """
    stats = {
        "total_docs": 0,
        "docs_with_matches": 0,
        "docs_without_matches": 0,
        "worst_samples": [],  # Triple F1 最低的样本
    }

    gold_map = {r.get("doc_id", ""): r for r in gold_records}
    pred_map = {r.get("doc_id", ""): r for r in pred_records}

    all_doc_ids = set(gold_map.keys()) & set(pred_map.keys())
    stats["total_docs"] = len(all_doc_ids)

    sample_scores = []

    for doc_id in all_doc_ids:
        gold_record = gold_map.get(doc_id, {})
        pred_record = pred_map.get(doc_id, {})

        gold_triples = gold_record.get("triples", [])
        pred_triples = pred_record.get("triples", [])

        # 简单计算匹配数
        matches = 0
        gold_set = {(t.get("subject", ""), t.get("predicate", ""), t.get("object", ""))
                    for t in gold_triples}
        pred_set = {(t.get("subject", ""), t.get("predicate", ""), t.get("object", ""))
                    for t in pred_triples}

        matches = len(gold_set & pred_set)

        if matches > 0:
            stats["docs_with_matches"] += 1
        else:
            stats["docs_without_matches"] += 1

        # 计算 F1
        if len(gold_set) == 0 and len(pred_set) == 0:
            f1 = 1.0
        elif len(gold_set) == 0 or len(pred_set) == 0:
            f1 = 0.0
        else:
            p = matches / len(pred_set)
            r = matches / len(gold_set)
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0

        sample_scores.append({
            "doc_id": doc_id,
            "f1": f1,
            "gold_count": len(gold_set),
            "pred_count": len(pred_set),
            "matches": matches,
            "gold_triples": [f"({s}, {p}, {o})" for s, p, o in list(gold_set)[:5]],
            "pred_triples": [f"({s}, {p}, {o})" for s, p, o in list(pred_set)[:5]],
        })

    # 找出最差的样本
    sample_scores.sort(key=lambda x: x["f1"])
    stats["worst_samples"] = sample_scores[:10]

    return stats


def generate_report(
    gold_records: List[Dict],
    pred_records: List[Dict],
    tbox: Dict
) -> Dict[str, Any]:
    """
    生成完整诊断报告
    """
    report = {
        "summary": {
            "gold_record_count": len(gold_records),
            "pred_record_count": len(pred_records),
        },
        "event_analysis": analyze_events(gold_records, pred_records),
        "relation_analysis": analyze_relations(gold_records, pred_records, tbox),
        "subject_object_swap_analysis": analyze_subject_object_swap(gold_records, pred_records),
        "entity_alignment_analysis": analyze_entity_alignment(gold_records, pred_records),
        "mismatch_analysis": analyze_mismatches(gold_records, pred_records),
    }

    return report


def print_summary(report: Dict[str, Any]) -> None:
    """打印报告摘要"""
    print("\n" + "=" * 60)
    print("诊断报告摘要")
    print("=" * 60)

    # 基本统计
    print(f"\n📊 基本统计:")
    print(f"  Gold 记录数: {report['summary']['gold_record_count']}")
    print(f"  Pred 记录数: {report['summary']['pred_record_count']}")

    # 事件分析
    ea = report["event_analysis"]
    print(f"\n📋 事件分析:")
    print(f"  Gold 事件总数: {ea['gold_event_count']}")
    print(f"  Pred 事件总数: {ea['pred_event_count']}")
    print(f"  Gold有Pred无: {ea['gold_has_pred_missing']} 条")
    print(f"  Pred有Gold无: {ea['pred_has_gold_missing']} 条")

    # 关系分析
    ra = report["relation_analysis"]
    print(f"\n🔗 关系分析:")
    print(f"  Gold 三元组总数: {ra['gold_triple_count']}")
    print(f"  Pred 三元组总数: {ra['pred_triple_count']}")
    print(f"  仅在Gold中的关系: {len(ra['relations_only_in_gold'])} 种")
    print(f"  仅在Pred中的关系: {len(ra['relations_only_in_pred'])} 种")
    if ra["relations_only_in_gold"]:
        print(f"    Gold独有: {', '.join(ra['relations_only_in_gold'][:5])}...")
    if ra["relations_only_in_pred"]:
        print(f"    Pred独有: {', '.join(ra['relations_only_in_pred'][:5])}...")

    # 主宾颠倒分析
    sa = report["subject_object_swap_analysis"]
    print(f"\n🔄 主宾颠倒分析:")
    print(f"  潜在颠倒数: {sa['potential_swaps']}")
    if sa["swap_examples"]:
        print("  示例:")
        for ex in sa["swap_examples"][:3]:
            print(f"    Gold: {ex['gold']}")
            print(f"    Pred: {ex['pred']}")
            print()

    # 实体对齐分析
    eaa = report["entity_alignment_analysis"]
    print(f"\n🏷️ 实体对齐分析:")
    print(f"  Gold 实体数: {eaa['gold_entity_count']}")
    print(f"  Pred 实体数: {eaa['pred_entity_count']}")
    print(f"  精确匹配: {eaa['exact_matches']}")
    print(f"  模糊匹配: {eaa['fuzzy_matches']}")
    print(f"  未匹配Gold实体: {len(eaa['unmatched_gold'])}")
    print(f"  未匹配Pred实体: {len(eaa['unmatched_pred'])}")

    # 不匹配分析
    ma = report["mismatch_analysis"]
    print(f"\n❌ 不匹配分析:")
    print(f"  总文档数: {ma['total_docs']}")
    print(f"  有匹配的文档: {ma['docs_with_matches']}")
    print(f"  无匹配的文档: {ma['docs_without_matches']}")

    print("\n" + "=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="抽取诊断脚本")
    parser.add_argument("--gold", "-g", required=True, help="Gold 文件")
    parser.add_argument("--pred", "-p", required=True, help="Pred 文件")
    parser.add_argument("--tbox", "-t", required=True, help="TBox 文件")
    parser.add_argument("--output", "-o", required=True, help="诊断报告输出路径")

    args = parser.parse_args()

    gold_path = Path(args.gold)
    pred_path = Path(args.pred)
    tbox_path = Path(args.tbox)
    output_path = Path(args.output)

    # 检查文件
    for p, name in [(gold_path, "Gold"), (pred_path, "Pred"), (tbox_path, "TBox")]:
        if not p.exists():
            print(f"错误：{name} 文件不存在: {p}", file=sys.stderr)
            sys.exit(1)

    print(f"加载数据...")
    gold_records = load_jsonl(gold_path)
    pred_records = load_jsonl(pred_path)
    tbox = load_tbox(tbox_path)

    print(f"  Gold 记录: {len(gold_records)}")
    print(f"  Pred 记录: {len(pred_records)}")

    print(f"\n生成诊断报告...")
    report = generate_report(gold_records, pred_records, tbox)

    # 保存报告
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已保存: {output_path}")

    # 打印摘要
    print_summary(report)


if __name__ == "__main__":
    main()
