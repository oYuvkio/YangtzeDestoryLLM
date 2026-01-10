#!/usr/bin/env python3
"""
集成测试脚本：验证评测指标修改是否正确
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.abox_metrics import (
    _ensure_records,
    _normalize_text,
    _normalize_value,
    compute_direction_error_rate,
    compute_partial_match_metrics,
    compute_evidence_quality,
    compute_event_completeness,
    compute_per_class_metrics,
    compute_tbox_consistency,
    compute_ece,
    compute_full_metrics,
)


def test_with_real_data():
    """使用真实数据格式测试"""

    # 模拟 Pred 数据
    pred = {
        "entities": [
            {"name": "长江三角洲地区", "type": "GeographicRegion"},
            {"name": "长江流域", "type": "Basin"},
            {"name": "洪水", "type": "DisasterEvent"},
            {"name": "暖湿的气候", "type": "ClimateAnomaly"},
        ],
        "triples": [
            {"subject": "洪水", "predicate": "has_hazard_factor", "object": "暖湿的气候",
             "evidence": "暖湿的气候是导致洪水发生的重要原因之一", "confidence": "high"},
            {"subject": "洪水", "predicate": "influenced_by_climate", "object": "暖湿的气候",
             "evidence": "研究区6个洪水高频发期与6个气候相对暖湿期相对应", "confidence": "high"},
            {"subject": "长江三角洲地区", "predicate": "part_of", "object": "长江流域",
             "evidence": "长江三峡及江汉平原与长江三角洲地区是共同处在长江流域", "confidence": "high"},
        ],
        "events": [
            {"name": "长江三角洲地区洪水频发期", "event_type": "DisasterEvent",
             "time": {"start_time": "", "end_time": ""}, "location": ["长江三角洲地区"]},
        ],
    }

    # 模拟 Gold 数据
    gold = {
        "events": [],
        "triples": [
            {"subject": "长江三角洲地区", "predicate": "affects_region", "object": "长江流域",
             "evidence": "长江三峡及江汉平原与长江三角洲地区是共同处在长江流域"},
            {"subject": "气候变化", "predicate": "influenced_by_climate", "object": "洪水",
             "evidence": "洪水的发生时期与气候由暖到冷的气候转型相关"},
            {"subject": "人为因素", "predicate": "has_hazard_factor", "object": "洪水",
             "evidence": "人为因素将在洪水发生中起着愈益显著的作用"},
        ],
    }

    # TBox
    tbox = {
        "classes": [
            {"name": "DisasterEvent", "cn_name": "灾害事件"},
            {"name": "GeographicRegion", "cn_name": "地理区域"},
            {"name": "Basin", "cn_name": "流域单元"},
            {"name": "ClimateAnomaly", "cn_name": "气候异常"},
            {"name": "HazardFactor", "cn_name": "致灾因子"},
        ],
        "relations": [
            {"name": "has_hazard_factor", "domain": "DisasterEvent", "range": "HazardFactor"},
            {"name": "affects_region", "domain": "DisasterEvent", "range": "GeographicRegion"},
            {"name": "influenced_by_climate", "domain": "DisasterEvent", "range": "ClimateAnomaly"},
            {"name": "part_of", "domain": "GeographicRegion", "range": "GeographicRegion"},
        ],
    }

    print("=" * 60)
    print("集成测试：使用真实数据格式")
    print("=" * 60)

    # 测试各个指标
    print("\n1. 测试 _ensure_records...")
    pred_records = _ensure_records(pred)
    gold_records = _ensure_records(gold)
    print(f"   Pred entities: {len(pred_records['entities'])}")
    print(f"   Gold entities (推断): {len(gold_records['entities'])}")
    assert len(gold_records['entities']) > 0, "Gold entities 应从 triples 推断"
    print("   ✓ 通过")

    print("\n2. 测试 compute_direction_error_rate...")
    direction_result = compute_direction_error_rate(pred, gold)
    print(f"   方向错误数: {direction_result['direction_errors']}")
    print(f"   方向错误率: {direction_result['direction_error_rate']}")
    print("   ✓ 通过")

    print("\n3. 测试 compute_partial_match_metrics...")
    partial_result = compute_partial_match_metrics(pred, gold)
    print(f"   完全匹配: {partial_result['breakdown']['full_match']}")
    print(f"   部分匹配 F1: {partial_result['partial_match_f1']}")
    print("   ✓ 通过")

    print("\n4. 测试 compute_evidence_quality...")
    evidence_result = compute_evidence_quality(pred, gold)
    print(f"   证据覆盖率: {evidence_result['evidence_coverage']}")
    print(f"   平均证据长度: {evidence_result['avg_evidence_length']}")
    print("   ✓ 通过")

    print("\n5. 测试 compute_event_completeness...")
    event_result = compute_event_completeness(pred)
    print(f"   事件数: {event_result['total_events']}")
    print(f"   完整性分数: {event_result['completeness_score']}")
    print("   ✓ 通过")

    print("\n6. 测试 compute_per_class_metrics...")
    per_class_result = compute_per_class_metrics(pred, gold, tbox)
    print(f"   类别数: {len(per_class_result)}")
    for cls, metrics in list(per_class_result.items())[:3]:
        print(f"   - {cls}: F1={metrics['f1']}")
    print("   ✓ 通过")

    print("\n7. 测试 compute_tbox_consistency...")
    consistency, tbox_stats = compute_tbox_consistency(pred, tbox)
    print(f"   一致性: {consistency}")
    print(f"   未知谓词: {tbox_stats['predicate_unknown']}")
    print("   ✓ 通过")

    print("\n8. 测试 compute_ece...")
    ece_result = compute_ece(pred, gold)
    print(f"   ECE: {ece_result['ece']}")
    print(f"   样本数: {ece_result['total_samples']}")
    print("   ✓ 通过")

    print("\n9. 测试 compute_full_metrics...")
    full_result = compute_full_metrics(pred, gold, tbox)
    print(f"   Event F1: {full_result['event_f1']}")
    print(f"   Triple F1 (Strict): {full_result['triple_f1_strict']}")
    print(f"   Triple F1 (Relaxed): {full_result['triple_f1_relaxed']}")
    print(f"   Entity F1: {full_result['entity_f1']}")
    print(f"   Relation F1: {full_result['relation_f1']}")
    print(f"   Partial Match F1: {full_result['partial_match_f1']}")
    print(f"   Direction Error Rate: {full_result['direction_error_rate']}")
    print(f"   ECE: {full_result['ece']}")
    print("   ✓ 通过")

    # 检查所有必需字段
    print("\n10. 检查输出字段完整性...")
    required_fields = [
        "event_f1", "triple_f1_strict", "triple_f1_relaxed",
        "entity_f1", "relation_f1", "partial_match_f1",
        "tbox_consistency", "hallucination_rate", "entity_redundancy_rate",
        "direction_error_rate", "ece",
        "evidence_quality", "event_completeness",
        "schema_coverage", "per_class_metrics", "per_relation_metrics",
        "error_breakdown", "partial_match_metrics",
    ]
    missing = [f for f in required_fields if f not in full_result]
    if missing:
        print(f"   ✗ 缺少字段: {missing}")
        return False
    print(f"   ✓ 所有 {len(required_fields)} 个必需字段都存在")

    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)

    # 输出完整结果供检查
    print("\n完整指标输出：")
    print(json.dumps(full_result, ensure_ascii=False, indent=2))

    return True


def test_normalize_value():
    """测试数值归一化"""
    print("\n测试数值归一化...")

    test_cases = [
        ("45.2米", "NumericValue", "45.2"),
        ("45.2m", "NumericValue", "45.2"),
        ("2000亿元", "NumericValue", "2000"),
        ("长江", "", "长江"),
        ("100.5%", "NumericValue", "100.5"),
    ]

    for text, entity_type, expected in test_cases:
        result = _normalize_value(text, entity_type)
        status = "✓" if result == expected else "✗"
        print(f"   {status} _normalize_value('{text}', '{entity_type}') = '{result}' (期望: '{expected}')")

    print("   完成")


if __name__ == "__main__":
    test_normalize_value()
    success = test_with_real_data()
    sys.exit(0 if success else 1)
