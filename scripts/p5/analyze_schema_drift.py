#!/usr/bin/env python3
"""
Schema 漂移分析脚本

分析 Gold 标注中的关系是否在 TBox 中定义，
统计非标准关系的频次，生成映射建议。

使用方式：
    python scripts/p5/analyze_schema_drift.py \
        --gold data/p5_eval_pool/final/test_final.jsonl \
        --tbox outputs/cq_pipeline/final/p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json

    # 输出映射模板
    python scripts/p5/analyze_schema_drift.py \
        --gold data/p5_eval_pool/final/test_final.jsonl \
        --tbox outputs/cq_pipeline/final/p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json \
        --output-mapping configs/relation_mapping_template.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Set


def load_tbox_relations(tbox_path: Path) -> Set[str]:
    """加载 TBox 中定义的关系名称。"""
    tbox = json.loads(tbox_path.read_text(encoding="utf-8"))
    relations = set()
    for r in tbox.get("relations", []):
        relations.add(r.get("name", ""))
        # 也添加中文名
        if r.get("cn_name"):
            relations.add(r.get("cn_name"))
    return relations


_NORMALIZE_RE = re.compile(r"[\s\-_./:]+")


def normalize_label(name: str) -> str:
    """对关系/事件类型名做轻量归一化，减少大小写/空白/符号差异。"""
    if not name:
        return ""
    return _NORMALIZE_RE.sub("", name.strip().lower())


def load_gold_relations(gold_path: Path) -> Counter:
    """统计 Gold 中出现的所有关系及其频次。"""
    rel_counter: Counter = Counter()

    with open(gold_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                for triple in data.get("triples", []):
                    predicate = triple.get("predicate", "")
                    if predicate:
                        rel_counter[predicate] += 1
            except json.JSONDecodeError:
                continue

    return rel_counter


def load_gold_events(gold_path: Path) -> Counter:
    """统计 Gold 中出现的所有事件类型及其频次。"""
    event_counter: Counter = Counter()

    with open(gold_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                for event in data.get("events", []):
                    event_type = event.get("event_type", "")
                    if event_type:
                        event_counter[event_type] += 1
            except json.JSONDecodeError:
                continue

    return event_counter


def load_tbox_classes(tbox_path: Path) -> Set[str]:
    """加载 TBox 中定义的类名称。"""
    tbox = json.loads(tbox_path.read_text(encoding="utf-8"))
    classes = set()
    for c in tbox.get("classes", []):
        classes.add(c.get("name", ""))
        if c.get("cn_name"):
            classes.add(c.get("cn_name"))
    return classes


def analyze_drift(
    gold_path: Path,
    tbox_path: Path,
    output_mapping: Path | None = None,
) -> Dict[str, Any]:
    """分析 Schema 漂移。"""

    # 加载 TBox
    tbox_relations = load_tbox_relations(tbox_path)
    tbox_classes = load_tbox_classes(tbox_path)
    tbox_relations_norm = {normalize_label(r) for r in tbox_relations if r}
    tbox_classes_norm = {normalize_label(c) for c in tbox_classes if c}

    # 加载 Gold
    gold_relations = load_gold_relations(gold_path)
    gold_events = load_gold_events(gold_path)

    # 分析关系漂移
    standard_relations: Dict[str, int] = {}
    drifted_relations: Dict[str, int] = {}

    for rel, count in gold_relations.items():
        if normalize_label(rel) in tbox_relations_norm:
            standard_relations[rel] = count
        else:
            drifted_relations[rel] = count

    # 分析事件类型漂移
    standard_events: Dict[str, int] = {}
    drifted_events: Dict[str, int] = {}

    for event_type, count in gold_events.items():
        if normalize_label(event_type) in tbox_classes_norm:
            standard_events[event_type] = count
        else:
            drifted_events[event_type] = count

    # 统计
    total_triples = sum(gold_relations.values())
    drifted_triple_count = sum(drifted_relations.values())
    drift_ratio = drifted_triple_count / total_triples if total_triples > 0 else 0

    total_events = sum(gold_events.values())
    drifted_event_count = sum(drifted_events.values())
    event_drift_ratio = drifted_event_count / total_events if total_events > 0 else 0

    # 打印报告
    print("=" * 70)
    print("Schema 漂移分析报告")
    print("=" * 70)
    print()

    print(f"TBox 关系数: {len(tbox_relations)}")
    print(f"TBox 类数:   {len(tbox_classes)}")
    print()

    print("-" * 70)
    print("关系分析")
    print("-" * 70)
    print(f"Gold 关系种类: {len(gold_relations)}")
    print(f"Gold 三元组总数: {total_triples}")
    print(f"标准关系三元组: {total_triples - drifted_triple_count} ({100*(1-drift_ratio):.1f}%)")
    print(f"漂移关系三元组: {drifted_triple_count} ({100*drift_ratio:.1f}%)")
    print()

    print(f"{'关系名称':<35} {'频次':<10} {'状态'}")
    print("-" * 70)

    for rel, count in sorted(gold_relations.items(), key=lambda x: -x[1]):
        status = "✅ 标准" if normalize_label(rel) in tbox_relations_norm else "❌ 漂移"
        print(f"{rel:<35} {count:<10} {status}")

    print()
    print("-" * 70)
    print("事件类型分析")
    print("-" * 70)
    print(f"Gold 事件类型种类: {len(gold_events)}")
    print(f"Gold 事件总数: {total_events}")
    print(f"标准事件: {total_events - drifted_event_count} ({100*(1-event_drift_ratio):.1f}%)")
    print(f"漂移事件: {drifted_event_count} ({100*event_drift_ratio:.1f}%)")
    print()

    if drifted_events:
        print(f"{'事件类型':<35} {'频次':<10} {'状态'}")
        print("-" * 70)
        for event_type, count in sorted(drifted_events.items(), key=lambda x: -x[1]):
            print(f"{event_type:<35} {count:<10} ❌ 漂移")

    # 生成映射建议
    if drifted_relations:
        print()
        print("=" * 70)
        print("建议的关系映射配置")
        print("=" * 70)

        mapping_template = {
            "relation_mapping": {},
            "inverse_relations": {},
            "ignore_relations": []
        }

        for rel in sorted(drifted_relations.keys()):
            mapping_template["relation_mapping"][rel] = "IGNORE"  # 默认忽略

        print(json.dumps(mapping_template, indent=2, ensure_ascii=False))

        if output_mapping:
            output_mapping.parent.mkdir(parents=True, exist_ok=True)
            output_mapping.write_text(
                json.dumps(mapping_template, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            print(f"\n映射模板已保存: {output_mapping}")

    # 返回分析结果
    return {
        "tbox_relations": len(tbox_relations),
        "tbox_classes": len(tbox_classes),
        "gold_relation_types": len(gold_relations),
        "gold_triple_count": total_triples,
        "standard_triple_count": total_triples - drifted_triple_count,
        "drifted_triple_count": drifted_triple_count,
        "drift_ratio": drift_ratio,
        "drifted_relations": dict(sorted(drifted_relations.items(), key=lambda x: -x[1])),
        "gold_event_types": len(gold_events),
        "gold_event_count": total_events,
        "drifted_event_count": drifted_event_count,
        "event_drift_ratio": event_drift_ratio,
        "drifted_events": dict(sorted(drifted_events.items(), key=lambda x: -x[1])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Schema 漂移分析")
    parser.add_argument("--gold", required=True, help="Gold 标注文件（jsonl）")
    parser.add_argument("--tbox", required=True, help="TBox 文件（json）")
    parser.add_argument("--output-mapping", default=None, help="输出映射模板路径（可选）")
    parser.add_argument("--output-report", default=None, help="输出分析报告路径（可选）")

    args = parser.parse_args()

    gold_path = Path(args.gold)
    tbox_path = Path(args.tbox)
    output_mapping = Path(args.output_mapping) if args.output_mapping else None
    output_report = Path(args.output_report) if args.output_report else None

    if not gold_path.exists():
        print(f"[ERROR] Gold 文件不存在: {gold_path}")
        return
    if not tbox_path.exists():
        print(f"[ERROR] TBox 文件不存在: {tbox_path}")
        return

    result = analyze_drift(gold_path, tbox_path, output_mapping)

    if output_report:
        output_report.parent.mkdir(parents=True, exist_ok=True)
        output_report.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"\n分析报告已保存: {output_report}")


if __name__ == "__main__":
    main()
