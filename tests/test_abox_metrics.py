"""
ABox 评测指标单元测试
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

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
    compute_entity_f1,
    compute_corpus_metrics,
)


class TestNormalization:
    """测试归一化函数"""

    def test_normalize_text_basic(self):
        assert _normalize_text("长江流域") == "长江流域"
        assert _normalize_text("  长江  流域  ") == "长江流域"
        assert _normalize_text("长江（Yangtze）") == "长江"
        assert _normalize_text("长江(Yangtze River)") == "长江"

    def test_normalize_value(self):
        assert _normalize_value("45.2米", "NumericValue") == "45.2"
        assert _normalize_value("45.2m", "NumericValue") == "45.2"
        assert _normalize_value("2000亿元", "NumericValue") == "2000"
        assert _normalize_value("长江", "") == "长江"


class TestEnsureRecords:
    """测试记录统一化"""

    def test_with_entities(self):
        test_input = {
            "events": [],
            "triples": [
                {"subject": "长江", "predicate": "flows_into", "object": "东海"},
            ],
            "entities": [{"name": "长江", "type": "River"}]
        }
        result = _ensure_records(test_input)
        assert len(result["entities"]) == 1
        assert result["entities"][0]["type"] == "River"

    def test_infer_entities_from_triples(self):
        test_input = {
            "events": [],
            "triples": [
                {"subject": "长江", "predicate": "flows_into", "object": "东海"},
                {"subject": "洪水", "predicate": "affects_region", "object": "武汉"}
            ]
        }
        result = _ensure_records(test_input)
        assert len(result["entities"]) == 4
        entity_names = {e["name"] for e in result["entities"]}
        assert "长江" in entity_names
        assert "东海" in entity_names
        assert "洪水" in entity_names
        assert "武汉" in entity_names


class TestDirectionErrorRate:
    """测试方向错误检测"""

    def test_direction_error_detected(self):
        pred = {"triples": [{"subject": "洪水", "predicate": "has_hazard_factor", "object": "暴雨"}]}
        gold = {"triples": [{"subject": "暴雨", "predicate": "has_hazard_factor", "object": "洪水"}]}
        result = compute_direction_error_rate(pred, gold)
        assert result["direction_errors"] == 1
        assert result["direction_error_rate"] == 1.0

    def test_no_direction_error(self):
        pred = {"triples": [{"subject": "洪水", "predicate": "has_hazard_factor", "object": "暴雨"}]}
        gold = {"triples": [{"subject": "洪水", "predicate": "has_hazard_factor", "object": "暴雨"}]}
        result = compute_direction_error_rate(pred, gold)
        assert result["direction_errors"] == 0
        assert result["direction_error_rate"] == 0.0


class TestPartialMatchMetrics:
    """测试部分匹配指标"""

    def test_full_match(self):
        pred = {"triples": [
            {"subject": "洪水", "predicate": "affects_region", "object": "武汉"},
        ]}
        gold = {"triples": [
            {"subject": "洪水", "predicate": "affects_region", "object": "武汉"},
        ]}
        result = compute_partial_match_metrics(pred, gold)
        assert result["breakdown"]["full_match"] == 1
        assert result["partial_match_f1"] == 1.0

    def test_partial_matches(self):
        pred = {"triples": [
            {"subject": "洪水", "predicate": "affects_region", "object": "武汉"},  # 完全匹配
            {"subject": "洪水", "predicate": "affects_region", "object": "南京"},  # head+relation 匹配
            {"subject": "干旱", "predicate": "affects_region", "object": "武汉"},  # relation+tail 匹配
        ]}
        gold = {"triples": [
            {"subject": "洪水", "predicate": "affects_region", "object": "武汉"},
            {"subject": "洪水", "predicate": "affects_region", "object": "上海"},
            {"subject": "暴雨", "predicate": "affects_region", "object": "武汉"},
        ]}
        result = compute_partial_match_metrics(pred, gold)
        assert result["breakdown"]["full_match"] == 1
        assert result["breakdown"]["head_relation_match"] == 1
        assert result["breakdown"]["relation_tail_match"] == 1

    def test_no_match(self):
        pred = {"triples": [
            {"subject": "A", "predicate": "rel1", "object": "B"},
        ]}
        gold = {"triples": [
            {"subject": "X", "predicate": "rel2", "object": "Y"},
        ]}
        result = compute_partial_match_metrics(pred, gold)
        assert result["breakdown"]["no_match"] == 1
        assert result["partial_match_f1"] == 0.0


class TestEvidenceQuality:
    """测试证据质量评估"""

    def test_evidence_coverage(self):
        pred = {"triples": [
            {"subject": "洪水", "predicate": "affects_region", "object": "武汉", "evidence": "1998年洪水影响武汉"},
            {"subject": "干旱", "predicate": "affects_region", "object": "南京", "evidence": ""},
        ]}
        gold = {"triples": []}
        result = compute_evidence_quality(pred, gold)
        assert result["evidence_coverage"] == 0.5
        assert result["total_with_evidence"] == 1
        assert result["total_triples"] == 2

    def test_evidence_similarity(self):
        pred = {"triples": [
            {"subject": "洪水", "predicate": "affects_region", "object": "武汉",
             "evidence": "1998年洪水影响武汉地区"},
        ]}
        gold = {"triples": [
            {"subject": "洪水", "predicate": "affects_region", "object": "武汉",
             "evidence": "1998年洪水影响武汉地区造成重大损失"},
        ]}
        result = compute_evidence_quality(pred, gold)
        assert result["avg_evidence_similarity"] > 0.5


class TestEventCompleteness:
    """测试事件完整性评估"""

    def test_complete_event(self):
        pred = {"events": [
            {
                "name": "1998年洪水",
                "event_type": "FloodEvent",
                "time": {"start_time": "1998-07-01", "end_time": "1998-08-31"},
                "location": ["武汉", "南京"]
            },
        ]}
        result = compute_event_completeness(pred)
        assert result["total_events"] == 1
        assert result["has_name_rate"] == 1.0
        assert result["has_type_rate"] == 1.0
        assert result["has_time_rate"] == 1.0
        assert result["has_location_rate"] == 1.0
        assert result["completeness_score"] == 1.0

    def test_incomplete_event(self):
        pred = {"events": [
            {"name": "1998年洪水", "event_type": "FloodEvent", "time": {}, "location": []},
            {"name": "2022年干旱", "event_type": "", "time": {}, "location": []},
        ]}
        result = compute_event_completeness(pred)
        assert result["total_events"] == 2
        assert result["has_name_rate"] == 1.0
        assert result["has_type_rate"] == 0.5
        assert result["has_time_rate"] == 0.0
        assert result["has_location_rate"] == 0.0

    def test_no_events(self):
        pred = {"events": []}
        result = compute_event_completeness(pred)
        assert result["total_events"] == 0
        assert result["completeness_score"] == 0


class TestPerClassMetrics:
    """测试分类别指标"""

    def test_per_class_metrics(self):
        pred = {"entities": [
            {"name": "洪水", "type": "DisasterEvent"},
            {"name": "武汉", "type": "GeographicRegion"},
            {"name": "南京", "type": "GeographicRegion"},
        ]}
        gold = {"entities": [
            {"name": "洪水", "type": "DisasterEvent"},
            {"name": "武汉", "type": "GeographicRegion"},
            {"name": "上海", "type": "GeographicRegion"},
        ]}
        tbox = {"classes": [{"name": "DisasterEvent"}, {"name": "GeographicRegion"}]}
        result = compute_per_class_metrics(pred, gold, tbox)

        assert "disasterevent" in result
        assert result["disasterevent"]["matched"] == 1
        assert result["disasterevent"]["f1"] == 1.0

        assert "geographicregion" in result
        assert result["geographicregion"]["matched"] == 1  # 只有武汉匹配


class TestTBoxConsistency:
    """测试 TBox 一致性"""

    def test_consistency_with_entities(self):
        pred = {
            "entities": [
                {"name": "洪水", "type": "DisasterEvent"},
                {"name": "武汉", "type": "GeographicRegion"},
            ],
            "events": [],
            "triples": [
                {"subject": "洪水", "predicate": "affects_region", "object": "武汉"},
            ]
        }
        tbox = {
            "relations": [
                {"name": "affects_region", "domain": "DisasterEvent", "range": "GeographicRegion"}
            ]
        }
        consistency, stats = compute_tbox_consistency(pred, tbox)
        assert consistency == 1.0
        assert stats["domain_range_violations"] == 0

    def test_unknown_predicate(self):
        pred = {
            "entities": [],
            "events": [],
            "triples": [
                {"subject": "A", "predicate": "unknown_relation", "object": "B"},
            ]
        }
        tbox = {
            "relations": [
                {"name": "affects_region", "domain": "DisasterEvent", "range": "GeographicRegion"}
            ]
        }
        consistency, stats = compute_tbox_consistency(pred, tbox)
        assert consistency == 0.0
        assert stats["predicate_unknown"] == 1


class TestECE:
    """测试置信度校准误差"""

    def test_ece_perfect_calibration(self):
        # 高置信度且正确
        pred = {"triples": [
            {"subject": "洪水", "predicate": "affects_region", "object": "武汉", "confidence": "high"},
        ]}
        gold = {"triples": [
            {"subject": "洪水", "predicate": "affects_region", "object": "武汉"},
        ]}
        result = compute_ece(pred, gold)
        # 置信度 0.9，准确率 1.0，差距 0.1
        assert result["ece"] <= 0.1

    def test_ece_overconfident(self):
        # 高置信度但错误
        pred = {"triples": [
            {"subject": "A", "predicate": "rel", "object": "B", "confidence": "high"},
        ]}
        gold = {"triples": [
            {"subject": "X", "predicate": "rel", "object": "Y"},
        ]}
        result = compute_ece(pred, gold)
        # 置信度 0.9，准确率 0.0，差距 0.9
        assert result["ece"] >= 0.8


class TestFullMetrics:
    """测试完整指标计算"""

    def test_full_metrics_structure(self):
        pred = {
            "entities": [{"name": "洪水", "type": "DisasterEvent"}],
            "events": [{"name": "1998年洪水", "event_type": "DisasterEvent", "time": {}, "location": []}],
            "triples": [
                {"subject": "洪水", "predicate": "affects_region", "object": "武汉",
                 "evidence": "洪水影响武汉", "confidence": "high"}
            ],
        }
        gold = {
            "entities": [{"name": "洪水", "type": "DisasterEvent"}],
            "events": [],
            "triples": [
                {"subject": "洪水", "predicate": "affects_region", "object": "武汉",
                 "evidence": "洪水影响武汉地区"}
            ],
        }
        tbox = {
            "classes": [{"name": "DisasterEvent"}, {"name": "GeographicRegion"}],
            "relations": [
                {"name": "affects_region", "domain": "DisasterEvent", "range": "GeographicRegion"}
            ]
        }

        result = compute_full_metrics(pred, gold, tbox)

        # 检查必需字段存在
        required_fields = [
            "event_f1", "triple_f1_strict", "triple_f1_relaxed",
            "entity_f1", "relation_f1", "partial_match_f1",
            "tbox_consistency", "hallucination_rate", "entity_redundancy_rate",
            "direction_error_rate", "ece",
            "evidence_quality", "event_completeness",
            "schema_coverage", "per_class_metrics", "per_relation_metrics",
            "error_breakdown", "partial_match_metrics",
        ]
        for field in required_fields:
            assert field in result, f"缺少字段: {field}"

        # 检查新增的 entity_f1_with_type 字段
        assert "entity_f1_with_type" in result, "缺少字段: entity_f1_with_type"
        assert "entity_metrics_with_type" in result, "缺少字段: entity_metrics_with_type"


class TestEntityF1:
    """测试实体 F1 计算"""

    def test_entity_f1_name_only(self):
        """仅名称匹配"""
        pred = {"entities": [
            {"name": "洪水", "type": "DisasterEvent"},
            {"name": "武汉", "type": "GeographicRegion"},
        ]}
        gold = {"entities": [
            {"name": "洪水", "type": "FloodEvent"},  # 类型不同
            {"name": "武汉", "type": "GeographicRegion"},
        ]}
        metrics, stats = compute_entity_f1(pred, gold, match_type=False)
        assert stats["matched"] == 2  # 名称匹配即可
        assert metrics.f1 == 1.0
        assert stats["match_type_enabled"] == False

    def test_entity_f1_with_type(self):
        """名称+类型匹配"""
        pred = {"entities": [
            {"name": "洪水", "type": "DisasterEvent"},
            {"name": "武汉", "type": "GeographicRegion"},
        ]}
        gold = {"entities": [
            {"name": "洪水", "type": "FloodEvent"},  # 类型不同
            {"name": "武汉", "type": "GeographicRegion"},
        ]}
        metrics, stats = compute_entity_f1(pred, gold, match_type=True)
        assert stats["matched"] == 1  # 只有武汉匹配
        assert stats["match_type_enabled"] == True

    def test_entity_f1_fuzzy_match(self):
        """模糊匹配"""
        pred = {"entities": [{"name": "1998年洪水灾害", "type": ""}]}
        gold = {"entities": [{"name": "1998年洪水", "type": ""}]}
        # 不启用模糊匹配时应该不匹配
        metrics_strict, stats_strict = compute_entity_f1(pred, gold, fuzzy_threshold=0.0)
        assert stats_strict["matched"] == 0

        # 启用模糊匹配时应该匹配（子串匹配）
        metrics_fuzzy, stats_fuzzy = compute_entity_f1(pred, gold, fuzzy_threshold=0.7)
        assert stats_fuzzy["matched"] == 1
        assert stats_fuzzy["fuzzy_matched"] == 1

    def test_entity_f1_from_triples(self):
        """从三元组中提取实体"""
        pred = {"triples": [
            {"subject": "洪水", "predicate": "affects", "object": "武汉"},
        ]}
        gold = {"triples": [
            {"subject": "洪水", "predicate": "affects", "object": "武汉"},
        ]}
        metrics, stats = compute_entity_f1(pred, gold)
        assert stats["matched"] == 2  # 洪水和武汉
        assert metrics.f1 == 1.0


class TestCorpusMetrics:
    """测试语料库级别指标计算"""

    def test_micro_aggregation(self):
        """Micro F1 聚合"""
        preds = [
            {"entities": [{"name": "A", "type": ""}]},
            {"entities": [{"name": "B", "type": ""}, {"name": "C", "type": ""}]},
        ]
        golds = [
            {"entities": [{"name": "A", "type": ""}]},
            {"entities": [{"name": "B", "type": ""}, {"name": "D", "type": ""}]},
        ]
        result = compute_corpus_metrics(preds, golds, aggregation="micro")
        # 全局: TP=2 (A, B), pred=3, gold=3
        # P = 2/3, R = 2/3, F1 = 2/3
        assert abs(result["entity"].f1 - 0.6667) < 0.01

    def test_macro_aggregation(self):
        """Macro F1 聚合"""
        preds = [
            {"entities": [{"name": "A", "type": ""}]},
            {"entities": [{"name": "B", "type": ""}]},
        ]
        golds = [
            {"entities": [{"name": "A", "type": ""}]},
            {"entities": [{"name": "C", "type": ""}]},
        ]
        result = compute_corpus_metrics(preds, golds, aggregation="macro")
        # 样本1: F1=1.0, 样本2: F1=0.0
        # Macro F1 = (1.0 + 0.0) / 2 = 0.5
        assert abs(result["entity"].f1 - 0.5) < 0.01

    def test_corpus_metrics_with_type(self):
        """带类型匹配的语料库指标"""
        preds = [
            {"entities": [{"name": "A", "type": "TypeA"}]},
            {"entities": [{"name": "B", "type": "TypeB"}]},
        ]
        golds = [
            {"entities": [{"name": "A", "type": "TypeA"}]},
            {"entities": [{"name": "B", "type": "TypeC"}]},  # 类型不同
        ]
        result = compute_corpus_metrics(preds, golds, aggregation="micro", match_type=True)
        # 只有第一个样本的 A 匹配
        assert result["entity"].f1 == 0.5


# 运行测试
if __name__ == "__main__":
    if HAS_PYTEST:
        pytest.main([__file__, "-v"])
    else:
        # 手动运行测试
        print("运行单元测试（无 pytest）...")
        test_classes = [
            TestNormalization,
            TestEnsureRecords,
            TestDirectionErrorRate,
            TestPartialMatchMetrics,
            TestEvidenceQuality,
            TestEventCompleteness,
            TestPerClassMetrics,
            TestTBoxConsistency,
            TestECE,
            TestFullMetrics,
            TestEntityF1,
            TestCorpusMetrics,
        ]

        passed = 0
        failed = 0

        for test_class in test_classes:
            instance = test_class()
            for method_name in dir(instance):
                if method_name.startswith("test_"):
                    try:
                        getattr(instance, method_name)()
                        print(f"  ✓ {test_class.__name__}.{method_name}")
                        passed += 1
                    except AssertionError as e:
                        print(f"  ✗ {test_class.__name__}.{method_name}: {e}")
                        failed += 1
                    except Exception as e:
                        print(f"  ✗ {test_class.__name__}.{method_name}: {type(e).__name__}: {e}")
                        failed += 1

        print(f"\n总计: {passed} 通过, {failed} 失败")
        sys.exit(0 if failed == 0 else 1)
