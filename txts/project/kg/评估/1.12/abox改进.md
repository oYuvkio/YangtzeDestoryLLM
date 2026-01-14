# 知识图谱三种典型任务（NER、RE、EE）指标计算详解

## 1. 三种任务定义与评估标准

| 任务 | 全称 | 评估目标 | 匹配条件 |
|------|------|----------|----------|
| **NER** | Named Entity Recognition | 实体识别 | 实体名称（+类型） |
| **RE** | Relation Extraction | 关系抽取 | (subject, predicate, object) 三元组 |
| **EE** | Event Extraction | 事件抽取 | 事件类型 + 触发词/名称 + 论元 |

---

## 2. 基于您提供的数据的详细计算

### 2.1 NER (实体识别) F1

```python
# ============= Gold实体 (10个) =============
gold_entities = {
    "2016年洪水",           # FloodEvent
    "巢湖",                 # WaterBody
    "安徽",                 # AdministrativeRegion
    "华阳河湖群",           # WaterBody
    "南漪湖",               # WaterBody
    "病险水库除险加固",     # EmergencyResponse
    "水库",                 # Facility
    "2016年的洪水",         # FloodEvent
    "长期投入不足",         # HazardFactor
    "沿湖圩堤设防标准偏低"  # Impact
}

# ============= Pred实体 (2个) =============
pred_entities = {
    "2016年洪水",           # FloodEvent ✓ 匹配
    "病险水库除险加固取得效果"  # HazardFactor ✗ 不匹配
}

# ============= 计算 =============
TP = len(gold_entities & pred_entities)  # = 1 ("2016年洪水")
FP = len(pred_entities - gold_entities)  # = 1 ("病险水库除险加固取得效果")
FN = len(gold_entities - pred_entities)  # = 9

Precision = TP / (TP + FP) = 1 / 2 = 0.5
Recall    = TP / (TP + FN) = 1 / 10 = 0.1
F1        = 2 * P * R / (P + R) = 2 * 0.5 * 0.1 / 0.6 = 0.1667
```

### 2.2 RE (关系抽取) F1

```python
# ============= Gold三元组 (8个) =============
gold_triples = {
    ("巢湖", "located_in", "安徽"),
    ("华阳河湖群", "located_in", "安徽"),
    ("南漪湖", "located_in", "安徽"),
    ("病险水库除险加固", "operates", "水库"),
    ("2016年的洪水", "occurs_at", "安徽"),
    ("2016年的洪水", "triggers_response", "病险水库除险加固"),
    ("长期投入不足", "causes", "沿湖圩堤设防标准偏低"),
    ("水库", "located_in", "安徽")
}

# ============= Pred三元组 (1个) =============
pred_triples = {
    ("2016年洪水", "has_cause", "病险水库除险加固取得效果")
}

# ============= 严格匹配计算 =============
TP = 0  # 完全没有匹配（s,p,o必须全部一致）
Precision = 0 / 1 = 0.0
Recall    = 0 / 8 = 0.0
F1_strict = 0.0

# ============= 宽松匹配（仅predicate一致时尝试模糊s/o匹配）=============
# "has_cause" 不在 gold predicates 中，所以宽松匹配也是 0
F1_relaxed = 0.0
```

### 2.3 EE (事件抽取) F1

```python
# ============= Gold事件 (1个) =============
gold_events = [
    {"event_type": "FloodEvent", "name": "2016年洪水", 
     "time": {"start_time": "2016", "end_time": "2016"}}
]

# ============= Pred事件 (1个) =============
pred_events = [
    {"event_type": "FloodEvent", "name": "2016年洪水",
     "time": {"start_time": "2016年", "end_time": "2016年"}}
]

# ============= 匹配条件 =============
# 1. event_type 一致: FloodEvent == FloodEvent ✓
# 2. name 一致: "2016年洪水" == "2016年洪水" ✓
# 3. time 容忍匹配: "2016" ≈ "2016年" (归一化后可匹配) ✓

TP = 1
Precision = 1 / 1 = 1.0
Recall    = 1 / 1 = 1.0
F1        = 1.0
```

---

## 3. 汇总表

| 指标 | Gold数量 | Pred数量 | TP | Precision | Recall | F1 |
|------|----------|----------|-----|-----------|--------|-----|
| **NER (Entity)** | 10 | 2 | 1 | 0.5000 | 0.1000 | **0.1667** |
| **RE (Triple-Strict)** | 8 | 1 | 0 | 0.0000 | 0.0000 | **0.0000** |
| **RE (Triple-Relaxed)** | 8 | 1 | 0 | 0.0000 | 0.0000 | **0.0000** |
| **EE (Event)** | 1 | 1 | 1 | 1.0000 | 1.0000 | **1.0000** |

---

## 4. 代码改进建议

### 4.1 NER评估需要区分"仅名称匹配"和"名称+类型匹配"

```python
def compute_entity_f1(
    predictions: Any, 
    gold: Any, 
    match_type: bool = False,  # 新增参数
    fuzzy_threshold: float = 0.0  # 模糊匹配阈值
) -> Tuple[ExtractionMetrics, Dict[str, int]]:
    """
    计算实体抽取 F1。
    
    Args:
        match_type: True时需要(name, type)都匹配，False时只匹配name
        fuzzy_threshold: >0时启用模糊匹配
    """
    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)

    def extract_entities(records: Dict[str, Any], with_type: bool) -> Set[Tuple[str, ...]]:
        entities: Set[Tuple[str, ...]] = set()
        for e in records.get("entities", []):
            if isinstance(e, dict):
                name = _normalize_text(e.get("name", ""))
                if name:
                    if with_type:
                        etype = _normalize_text(e.get("type", ""))
                        entities.add((name, etype))
                    else:
                        entities.add((name,))
        # 从 triples 补充
        for t in records.get("triples", []):
            if isinstance(t, dict):
                for field, type_field in [("subject", "subject_type"), ("object", "object_type")]:
                    val = _normalize_text(t.get(field, ""))
                    if val:
                        if with_type:
                            vtype = _normalize_text(t.get(type_field, ""))
                            entities.add((val, vtype))
                        else:
                            entities.add((val,))
        return entities

    pred_entities = extract_entities(pred_records, with_type=match_type)
    gold_entities = extract_entities(gold_records, with_type=match_type)

    # 精确匹配
    tp = len(pred_entities & gold_entities)
    
    # 模糊匹配（可选）
    if fuzzy_threshold > 0:
        unmatched_pred = pred_entities - gold_entities
        unmatched_gold = gold_entities - pred_entities
        for p in unmatched_pred:
            for g in unmatched_gold:
                if _fuzzy_entity_match(p[0], g[0], fuzzy_threshold):
                    if not match_type or (len(p) > 1 and len(g) > 1 and p[1] == g[1]):
                        tp += 1
                        break

    metrics = _calc_prf(tp, len(pred_entities), len(gold_entities))
    stats = {
        "pred_count": len(pred_entities),
        "gold_count": len(gold_entities),
        "matched": tp,
        "match_type_enabled": match_type,
    }
    return metrics, stats
```

### 4.2 增加Micro/Macro F1计算支持

```python
def compute_corpus_metrics(
    all_predictions: List[Dict], 
    all_golds: List[Dict],
    aggregation: str = "micro"  # "micro" | "macro"
) -> Dict[str, ExtractionMetrics]:
    """
    语料库级别的指标计算。
    
    micro: 全局TP/FP/FN汇总后计算P/R/F1
    macro: 每个样本计算P/R/F1后取平均
    """
    if aggregation == "micro":
        total_tp, total_pred, total_gold = 0, 0, 0
        for pred, gold in zip(all_predictions, all_golds):
            metrics, stats = compute_entity_f1(pred, gold)
            total_tp += stats["matched"]
            total_pred += stats["pred_count"]
            total_gold += stats["gold_count"]
        return {"entity": _calc_prf(total_tp, total_pred, total_gold)}
    
    else:  # macro
        all_f1s = []
        for pred, gold in zip(all_predictions, all_golds):
            metrics, _ = compute_entity_f1(pred, gold)
            all_f1s.append(metrics.f1)
        avg_f1 = sum(all_f1s) / len(all_f1s) if all_f1s else 0
        return {"entity": ExtractionMetrics(precision=0, recall=0, f1=avg_f1)}
```

### 4.3 RE评估增加部分匹配统计

您的代码已有 `compute_partial_match_metrics`，建议增加返回详细的匹配类型：

```python
def compute_triple_f1_enhanced(
    predictions: Any,
    gold: Any,
    **kwargs
) -> Dict[str, Any]:
    """增强版三元组F1，返回更详细的匹配信息"""
    
    # 原有计算
    triple_metrics, errors = compute_triple_f1(predictions, gold, **kwargs)
    partial = compute_partial_match_metrics(predictions, gold)
    
    # 增加：按predicate分组的P/R/F1
    per_relation = compute_per_relation_metrics(predictions, gold)
    
    return {
        "strict": triple_metrics["strict"].to_dict(),
        "relaxed": triple_metrics["relaxed"].to_dict(),
        "partial_match": partial,
        "per_relation": per_relation,
        "errors": errors,
    }
```

---

## 5. 完整评测脚本示例

```python
#!/usr/bin/env python3
"""使用示例：计算NER/RE/EE三种任务的F1"""

import json
from pathlib import Path
from abox_metrics import (
    compute_entity_f1,
    compute_triple_f1, 
    compute_event_f1,
    compute_relation_f1,
    compute_full_metrics,
)

def main():
    # 加载数据
    gold = json.loads(Path("gold.json").read_text())
    pred = json.loads(Path("pred.json").read_text())
    tbox = json.loads(Path("tbox.json").read_text())
    
    # ========== NER (Entity F1) ==========
    ner_metrics, ner_stats = compute_entity_f1(pred, gold)
    print(f"[NER] Entity F1: {ner_metrics.f1:.4f}")
    print(f"       Precision: {ner_metrics.precision:.4f}")
    print(f"       Recall:    {ner_metrics.recall:.4f}")
    print(f"       Matched: {ner_stats['matched']} / Gold: {ner_stats['gold_count']} / Pred: {ner_stats['pred_count']}")
    
    # ========== RE (Relation Extraction) ==========
    # 方式1: 三元组级别 (s,p,o)
    triple_metrics, triple_errors = compute_triple_f1(pred, gold)
    print(f"\n[RE] Triple F1 (Strict):  {triple_metrics['strict'].f1:.4f}")
    print(f"[RE] Triple F1 (Relaxed): {triple_metrics['relaxed'].f1:.4f}")
    
    # 方式2: 仅关系类型 (不考虑s/o)
    rel_metrics, rel_stats = compute_relation_f1(pred, gold)
    print(f"[RE] Relation Type F1: {rel_metrics.f1:.4f}")
    
    # ========== EE (Event Extraction) ==========
    event_metrics, event_errors = compute_event_f1(pred, gold)
    print(f"\n[EE] Event F1: {event_metrics.f1:.4f}")
    print(f"       Precision: {event_metrics.precision:.4f}")
    print(f"       Recall:    {event_metrics.recall:.4f}")
    
    # ========== 综合报告 ==========
    full_report = compute_full_metrics(pred, gold, tbox)
    print(f"\n========== 综合指标 ==========")
    print(f"Entity F1:         {full_report['entity_f1']:.4f}")
    print(f"Relation F1:       {full_report['relation_f1']:.4f}")
    print(f"Event F1:          {full_report['event_f1']:.4f}")
    print(f"Triple F1 (Strict): {full_report['triple_f1_strict']:.4f}")
    print(f"TBox Consistency:  {full_report['tbox_consistency']:.4f}")
    print(f"Hallucination Rate: {full_report['hallucination_rate']}")

if __name__ == "__main__":
    main()
```

**预期输出（基于您的数据）**：
```
[NER] Entity F1: 0.1667
       Precision: 0.5000
       Recall:    0.1000
       Matched: 1 / Gold: 10 / Pred: 2

[RE] Triple F1 (Strict):  0.0000
[RE] Triple F1 (Relaxed): 0.0000
[RE] Relation Type F1: 0.0000

[EE] Event F1: 1.0000
       Precision: 1.0000
       Recall:    1.0000
```

---

## 6. 关键问题总结

| 问题 | 您的代码现状 | 建议改进 |
|------|-------------|----------|
| NER类型匹配 | 只匹配名称 | 添加 `match_type` 参数 |
| RE宽松匹配 | 已有模糊匹配 | 阈值可配置化 |
| EE论元匹配 | 只匹配name+type | 可扩展到time/location论元匹配 |
| Micro/Macro | 使用平均 | 添加聚合方式选项 |
| 边界匹配 | 无（无span信息） | 如有span可添加 |

您的代码整体设计很完善，主要建议是增加更细粒度的配置选项！