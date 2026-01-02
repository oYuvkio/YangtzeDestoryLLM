#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关系映射与评估对齐工具

设计原则：
┌─────────────────────────────────────────────────────────────────────────┐
│ 标注Schema（独立）  ──映射──>  项目Schema（动态生成）                    │
│                                                                         │
│ 评估时：将抽取结果的关系名映射到标注Schema的标准关系，再进行匹配       │
└─────────────────────────────────────────────────────────────────────────┘

使用方式：
    # 将抽取结果映射到标准Schema
    python tools/relation_mapping.py \
        --pred outputs/kg_extraction/predictions.json \
        --out outputs/kg_extraction/predictions_mapped.json

    # 查看映射统计
    python tools/relation_mapping.py --show-mapping

    # 生成映射配置文件
    python tools/relation_mapping.py --generate-config --tbox outputs/cq_pipeline/final/p4_tbox_augmented.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# 项目路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ==============================================================================
# 标准关系Schema定义
# ==============================================================================

# 9种标准关系类型
STANDARD_RELATIONS = {
    "occurs_at": {
        "cn_name": "发生于（时间）",
        "description": "事件发生的时间",
        "domain": "EVENT",
        "range": "TIME",
    },
    "located_in": {
        "cn_name": "位于/发生地点",
        "description": "实体或事件所在的地理位置",
        "domain": "EVENT/FACILITY",
        "range": "LOCATION",
    },
    "has_cause": {
        "cn_name": "由...引起",
        "description": "事件的致灾因子或原因",
        "domain": "EVENT",
        "range": "CAUSE",
    },
    "causes_impact": {
        "cn_name": "造成影响",
        "description": "事件造成的影响或损失",
        "domain": "EVENT",
        "range": "IMPACT/VALUE",
    },
    "has_value": {
        "cn_name": "测量值为",
        "description": "设施或位置的测量数值",
        "domain": "FACILITY/LOCATION",
        "range": "VALUE",
    },
    "triggers": {
        "cn_name": "触发",
        "description": "事件或阈值触发的响应措施",
        "domain": "EVENT/VALUE",
        "range": "MEASURE",
    },
    "implements": {
        "cn_name": "实施/采取",
        "description": "组织实施的措施",
        "domain": "ORG",
        "range": "MEASURE",
    },
    "part_of": {
        "cn_name": "属于/包含于",
        "description": "位置的包含关系",
        "domain": "LOCATION",
        "range": "LOCATION",
    },
    "affects": {
        "cn_name": "影响/波及",
        "description": "事件影响的区域",
        "domain": "EVENT",
        "range": "LOCATION",
    },
}


# ==============================================================================
# 项目Schema -> 标准Schema 映射表
# ==============================================================================

# 格式：项目Schema中的关系名 -> 标准Schema中的关系名
# 支持多对一映射（多个项目关系映射到同一个标准关系）

PROJECT_TO_STANDARD_MAPPING = {
    # 时间关系
    "occurs_at": "occurs_at",
    "occurs_at_time": "occurs_at",
    "has_time": "occurs_at",
    "start_time": "occurs_at",
    "end_time": "occurs_at",
    "发生时间": "occurs_at",
    "开始时间": "occurs_at",
    "时间": "occurs_at",

    # 空间关系 - located_in
    "located_in": "located_in",
    "located_at": "located_in",
    "occurs_in": "located_in",
    "发生地点": "located_in",
    "位于": "located_in",
    "地点": "located_in",

    # 空间关系 - affects
    "affects": "affects",
    "affects_region": "affects",
    "impacts_region": "affects",
    "影响区域": "affects",
    "波及": "affects",

    # 空间关系 - part_of
    "part_of": "part_of",
    "belongs_to": "part_of",
    "contained_in": "part_of",
    "属于": "part_of",
    "包含于": "part_of",

    # 因果关系 - has_cause
    "has_cause": "has_cause",
    "caused_by": "has_cause",
    "has_hazard_factor": "has_cause",
    "hazard_factor": "has_cause",
    "致灾因子": "has_cause",
    "原因": "has_cause",
    "导致": "has_cause",
    "由于": "has_cause",

    # 因果关系 - causes_impact
    "causes_impact": "causes_impact",
    "has_impact": "causes_impact",
    "results_in": "causes_impact",
    "causes": "causes_impact",
    "leads_to": "causes_impact",
    "造成": "causes_impact",
    "影响": "causes_impact",
    "损失": "causes_impact",
    "受灾人口": "causes_impact",
    "死亡人数": "causes_impact",
    "经济损失": "causes_impact",
    "direct_economic_loss": "causes_impact",
    "affected_population": "causes_impact",
    "death_toll": "causes_impact",
    "deaths": "causes_impact",

    # 数值关系
    "has_value": "has_value",
    "has_measurement": "has_value",
    "water_level": "has_value",
    "discharge": "has_value",
    "peak_discharge": "has_value",
    "peak_water_level": "has_value",
    "水位": "has_value",
    "流量": "has_value",
    "洪峰流量": "has_value",
    "洪峰水位": "has_value",
    "测量值": "has_value",

    # 触发关系
    "triggers": "triggers",
    "triggers_response": "triggers",
    "activates": "triggers",
    "activates_response": "triggers",
    "启动": "triggers",
    "触发": "triggers",
    "引发": "triggers",

    # 措施关系
    "implements": "implements",
    "takes_action": "implements",
    "executes": "implements",
    "has_response": "implements",
    "采取": "implements",
    "实施": "implements",
    "执行": "implements",
    "响应措施": "implements",
}


# ==============================================================================
# 映射函数
# ==============================================================================

def normalize_relation_name(name: str) -> str:
    """标准化关系名（小写、去空格）"""
    if not name:
        return ""
    return name.lower().strip().replace(" ", "_").replace("-", "_")


def map_relation_to_standard(
    relation: str,
    custom_mapping: Optional[Dict[str, str]] = None,
) -> Tuple[str, bool]:
    """
    将项目Schema的关系映射到标准Schema。

    Args:
        relation: 项目Schema中的关系名
        custom_mapping: 自定义映射表（可选，用于覆盖默认映射）

    Returns:
        (标准关系名, 是否成功映射)
    """
    if not relation:
        return "", False

    # 使用自定义映射或默认映射
    mapping = custom_mapping if custom_mapping else PROJECT_TO_STANDARD_MAPPING

    # 直接查找
    if relation in mapping:
        return mapping[relation], True

    # 标准化后查找
    normalized = normalize_relation_name(relation)
    if normalized in mapping:
        return mapping[normalized], True

    # 检查是否已经是标准关系
    if relation in STANDARD_RELATIONS:
        return relation, True
    if normalized in STANDARD_RELATIONS:
        return normalized, True

    # 无法映射
    return relation, False


def map_triples(
    triples: List[Dict[str, Any]],
    custom_mapping: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    批量映射三元组的关系。

    Args:
        triples: 三元组列表
        custom_mapping: 自定义映射表

    Returns:
        (映射后的三元组列表, 映射统计)
    """
    mapped_triples = []
    stats = Counter()

    for triple in triples:
        original_pred = triple.get("predicate", "")
        mapped_pred, success = map_relation_to_standard(original_pred, custom_mapping)

        new_triple = triple.copy()
        new_triple["predicate"] = mapped_pred
        new_triple["original_predicate"] = original_pred
        new_triple["mapping_success"] = success

        mapped_triples.append(new_triple)

        if success:
            stats[f"mapped:{original_pred}->{mapped_pred}"] += 1
        else:
            stats[f"unmapped:{original_pred}"] += 1

    return mapped_triples, dict(stats)


def map_predictions_file(
    input_path: Path,
    output_path: Path,
    custom_mapping: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    映射整个预测文件。

    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径
        custom_mapping: 自定义映射表

    Returns:
        映射统计信息
    """
    # 加载预测结果
    if input_path.suffix.lower() == ".jsonl":
        predictions = []
        with input_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    predictions.append(json.loads(line))
    else:
        predictions = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(predictions, list):
            predictions = [predictions]

    # 映射
    total_stats = Counter()
    mapped_predictions = []

    for pred in predictions:
        triples = pred.get("triples", [])
        mapped_triples, stats = map_triples(triples, custom_mapping)

        new_pred = pred.copy()
        new_pred["triples"] = mapped_triples
        mapped_predictions.append(new_pred)

        for k, v in stats.items():
            total_stats[k] += v

    # 保存
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".jsonl":
        with output_path.open("w", encoding="utf-8") as f:
            for pred in mapped_predictions:
                f.write(json.dumps(pred, ensure_ascii=False) + "\n")
    else:
        output_path.write_text(
            json.dumps(mapped_predictions, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    return {
        "input": str(input_path),
        "output": str(output_path),
        "total_triples": sum(len(p.get("triples", [])) for p in predictions),
        "mapping_stats": dict(total_stats),
    }


# ==============================================================================
# 从TBox自动生成映射建议
# ==============================================================================

def suggest_mapping_from_tbox(tbox_path: Path) -> Dict[str, str]:
    """
    根据TBox定义自动生成映射建议。

    Args:
        tbox_path: TBox文件路径

    Returns:
        建议的映射表
    """
    tbox = json.loads(tbox_path.read_text(encoding="utf-8"))
    relations = tbox.get("relations", [])

    suggestions = {}

    # 关键词到标准关系的映射
    keyword_mapping = {
        "time": "occurs_at",
        "时间": "occurs_at",
        "date": "occurs_at",
        "when": "occurs_at",

        "location": "located_in",
        "place": "located_in",
        "地点": "located_in",
        "位置": "located_in",

        "cause": "has_cause",
        "factor": "has_cause",
        "原因": "has_cause",
        "因子": "has_cause",

        "impact": "causes_impact",
        "loss": "causes_impact",
        "damage": "causes_impact",
        "影响": "causes_impact",
        "损失": "causes_impact",

        "value": "has_value",
        "level": "has_value",
        "measure": "has_value",
        "水位": "has_value",
        "流量": "has_value",

        "trigger": "triggers",
        "response": "triggers",
        "启动": "triggers",
        "触发": "triggers",

        "implement": "implements",
        "action": "implements",
        "措施": "implements",
        "执行": "implements",

        "affect": "affects",
        "region": "affects",
        "area": "affects",
        "波及": "affects",
        "区域": "affects",

        "part": "part_of",
        "belong": "part_of",
        "contain": "part_of",
        "属于": "part_of",
    }

    for rel in relations:
        name = rel.get("name", "")
        cn_name = rel.get("cn_name", "")
        definition = rel.get("definition", "")

        if not name:
            continue

        # 已在默认映射中
        if name in PROJECT_TO_STANDARD_MAPPING:
            suggestions[name] = PROJECT_TO_STANDARD_MAPPING[name]
            continue

        # 基于关键词匹配
        combined = f"{name} {cn_name} {definition}".lower()
        for keyword, standard in keyword_mapping.items():
            if keyword in combined:
                suggestions[name] = standard
                break
        else:
            # 无法自动映射，标记需要人工确认
            suggestions[name] = f"UNKNOWN (需人工确认: {cn_name or name})"

    return suggestions


# ==============================================================================
# CLI
# ==============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="关系映射与评估对齐工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--pred", help="预测结果文件路径")
    parser.add_argument("--out", help="映射后的输出文件路径")
    parser.add_argument("--mapping-config", help="自定义映射配置文件（JSON）")
    parser.add_argument("--show-mapping", action="store_true", help="显示默认映射表")
    parser.add_argument("--show-standard", action="store_true", help="显示标准关系Schema")
    parser.add_argument("--generate-config", action="store_true", help="生成映射配置文件")
    parser.add_argument("--tbox", help="TBox文件路径（用于生成映射建议）")

    return parser.parse_args()


def main():
    args = parse_args()

    # 显示标准Schema
    if args.show_standard:
        print("\n📋 标准关系Schema（9种）\n")
        print("-" * 80)
        for name, info in STANDARD_RELATIONS.items():
            print(f"  {name}")
            print(f"    中文名: {info['cn_name']}")
            print(f"    描述: {info['description']}")
            print(f"    Domain: {info['domain']} -> Range: {info['range']}")
            print()
        return

    # 显示默认映射表
    if args.show_mapping:
        print("\n📋 默认关系映射表\n")
        print("-" * 80)

        # 按目标关系分组
        grouped = {}
        for src, dst in PROJECT_TO_STANDARD_MAPPING.items():
            if dst not in grouped:
                grouped[dst] = []
            grouped[dst].append(src)

        for standard, sources in sorted(grouped.items()):
            print(f"\n  {standard} ({STANDARD_RELATIONS.get(standard, {}).get('cn_name', '')})")
            for src in sorted(sources):
                print(f"    <- {src}")
        return

    # 生成映射配置
    if args.generate_config:
        if not args.tbox:
            print("❌ 需要指定 --tbox 参数")
            sys.exit(1)

        tbox_path = Path(args.tbox)
        if not tbox_path.exists():
            print(f"❌ TBox文件不存在: {tbox_path}")
            sys.exit(1)

        suggestions = suggest_mapping_from_tbox(tbox_path)

        config = {
            "description": "关系映射配置（项目Schema -> 标准Schema）",
            "standard_relations": list(STANDARD_RELATIONS.keys()),
            "mapping": suggestions,
        }

        out_path = Path(args.out) if args.out else Path("configs/relation_mapping.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"\n✅ 映射配置已生成: {out_path}")
        print(f"\n📋 包含 {len(suggestions)} 个关系映射")

        # 显示需要人工确认的
        unknown = [k for k, v in suggestions.items() if "UNKNOWN" in v]
        if unknown:
            print(f"\n⚠️ 以下 {len(unknown)} 个关系需要人工确认:")
            for k in unknown:
                print(f"    - {k}: {suggestions[k]}")
        return

    # 映射预测文件
    if args.pred:
        if not args.out:
            print("❌ 需要指定 --out 参数")
            sys.exit(1)

        pred_path = Path(args.pred)
        out_path = Path(args.out)

        if not pred_path.exists():
            print(f"❌ 预测文件不存在: {pred_path}")
            sys.exit(1)

        # 加载自定义映射
        custom_mapping = None
        if args.mapping_config:
            config_path = Path(args.mapping_config)
            if config_path.exists():
                config = json.loads(config_path.read_text(encoding="utf-8"))
                custom_mapping = config.get("mapping", {})
                # 过滤掉UNKNOWN的
                custom_mapping = {k: v for k, v in custom_mapping.items() if "UNKNOWN" not in v}

        print(f"\n📊 映射预测结果...")
        print(f"  输入: {pred_path}")
        print(f"  输出: {out_path}")

        result = map_predictions_file(pred_path, out_path, custom_mapping)

        print(f"\n✅ 映射完成")
        print(f"  总三元组数: {result['total_triples']}")

        # 统计
        mapped_count = sum(1 for k in result['mapping_stats'] if k.startswith("mapped:"))
        unmapped_count = sum(1 for k in result['mapping_stats'] if k.startswith("unmapped:"))
        print(f"  成功映射: {mapped_count} 种关系")
        print(f"  未能映射: {unmapped_count} 种关系")

        if unmapped_count > 0:
            print("\n  未映射的关系:")
            for k, v in result['mapping_stats'].items():
                if k.startswith("unmapped:"):
                    rel = k.replace("unmapped:", "")
                    print(f"    - {rel}: {v} 次")
        return

    # 无参数时显示帮助
    print("使用 --help 查看帮助信息")


if __name__ == "__main__":
    main()
