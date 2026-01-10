# 综合代码改进指导文档

## 文档概述

本文档整合了两份优化需求，提供完整的代码修改指导。修改涉及以下核心模块：

1. **评测指标增强** (`tools/abox_metrics.py`)
2. **Prompt 与 Schema 注入优化** (`kg/prompts.py`, `kg/cq_pipeline.py`)
3. **统一抽取流程** (新建 `kg/unified_extraction.py`)
4. **归一化逻辑增强** (`tools/abox_metrics.py`)

---

## 第一部分：评测指标增强

### 文件：`tools/abox_metrics.py`

### 1.1 修改 `_normalize_text` 函数

**目的**：增强文本归一化，处理中文括号和特殊字符

```python
def _normalize_text(text: str) -> str:
    """标准化文本：去掉空白/常见标点，转小写，便于宽容匹配。"""
    text = str(text).strip()
    # 去除括号及内容（针对 "长江(Yangtze)" 这种情况）
    text = re.sub(r"（[^）]*）|\([^\)]*\)", "", text)
    # 去除标点和空格
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。、""''：；（）【】《》/\\-]", "", text)
    return text.lower()
```

### 1.2 新增 `_normalize_value` 函数

**目的**：处理数值类型实体的匹配问题

```python
def _normalize_value(text: str, entity_type: str = "") -> str:
    """
    提取纯数字进行比较，解决 '45.2米' vs '45.2m' 的问题。
    如果实体类型包含 Value 或文本包含数字，提取第一个数字。
    """
    if "value" in str(entity_type).lower() or re.search(r'\d', str(text)):
        nums = re.findall(r"[-+]?\d*\.?\d+", str(text))
        if nums:
            return nums[0]
    return _normalize_text(text)
```

### 1.3 修改 `_ensure_records` 函数

**目的**：统一处理 `entities` 字段，当输入缺少时从 `triples` 推断

```python
def _ensure_records(obj: Any, *, use_original_type: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    """
    将输入统一转换为 {events: [...], triples: [...], entities: [...]} 结构。
    新增：当 entities 为空时，从 triples 的 subject/object 推断实体列表。
    """
    def _normalize_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not use_original_type:
            return events
        normalized: List[Dict[str, Any]] = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            raw_type = ev.get("original_event_type") or ev.get("event_type", "")
            ev_copy = dict(ev)
            ev_copy["event_type"] = raw_type
            normalized.append(ev_copy)
        return normalized

    def _extract_entities_from_triples(triples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从三元组中提取实体（当 entities 字段缺失时使用）"""
        seen: Set[str] = set()
        entities: List[Dict[str, Any]] = []
        for t in triples:
            if not isinstance(t, dict):
                continue
            for field in ["subject", "object"]:
                val = str(t.get(field, "") or "")
                if val and val not in seen:
                    entities.append({"name": val, "type": ""})
                    seen.add(val)
        return entities

    if isinstance(obj, dict):
        events = obj.get("events", []) or obj.get("gold_events", []) or []
        triples = obj.get("triples", []) or obj.get("gold_triples", []) or []
        entities = obj.get("entities", []) or []
      
        if not entities:
            entities = _extract_entities_from_triples(triples)
      
        return {
            "events": _normalize_events(events),
            "triples": triples,
            "entities": entities,
        }
  
    if isinstance(obj, list):
        events, triples, entities = [], [], []
        for item in obj:
            if not isinstance(item, dict):
                continue
            e = item.get("events", []) or item.get("gold_events", []) or []
            t = item.get("triples", []) or item.get("gold_triples", []) or []
            ent = item.get("entities", []) or []
            events.extend(_normalize_events(e))
            triples.extend(t)
            entities.extend(ent)
      
        if not entities:
            entities = _extract_entities_from_triples(triples)
      
        return {"events": events, "triples": triples, "entities": entities}
  
    return {"events": [], "triples": [], "entities": []}
```

### 1.4 新增指标函数

#### 1.4.1 `compute_direction_error_rate`

```python
def compute_direction_error_rate(predictions: Any, gold: Any) -> Dict[str, Any]:
    """
    检测主宾语颠倒的错误率。
    当 predicate 相同但 subject 和 object 互换时，视为方向错误。
    """
    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)
  
    pred_triples = pred_records.get("triples", [])
    gold_triples = gold_records.get("triples", [])
  
    direction_errors = 0
    checked = 0
  
    for pred_t in pred_triples:
        pred_s = _normalize_text(pred_t.get("subject", ""))
        pred_p = _normalize_text(pred_t.get("predicate", ""))
        pred_o = _normalize_text(pred_t.get("object", ""))
      
        if not pred_p:
            continue
        checked += 1
      
        for gold_t in gold_triples:
            gold_s = _normalize_text(gold_t.get("subject", ""))
            gold_p = _normalize_text(gold_t.get("predicate", ""))
            gold_o = _normalize_text(gold_t.get("object", ""))
          
            if pred_p == gold_p and pred_s == gold_o and pred_o == gold_s:
                direction_errors += 1
                break
  
    rate = direction_errors / checked if checked > 0 else 0
    return {
        "direction_error_rate": round(rate, 4),
        "direction_errors": direction_errors,
        "total_checked": checked,
    }
```

#### 1.4.2 `compute_partial_match_metrics`

```python
def compute_partial_match_metrics(predictions: Any, gold: Any) -> Dict[str, Any]:
    """
    计算三元组部分匹配指标：
    - full_match: 完全匹配
    - head_relation_match: 主语+关系正确
    - relation_tail_match: 关系+宾语正确
    - head_only_match: 仅主语正确
    - tail_only_match: 仅宾语正确
    - relation_only_match: 仅关系正确
    """
    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)
  
    pred_triples = pred_records.get("triples", [])
    gold_triples = gold_records.get("triples", [])
  
    stats = {
        "full_match": 0,
        "head_relation_match": 0,
        "relation_tail_match": 0,
        "head_only_match": 0,
        "tail_only_match": 0,
        "relation_only_match": 0,
        "no_match": 0,
        "total_pred": len(pred_triples),
        "total_gold": len(gold_triples),
    }
  
    for pred_t in pred_triples:
        pred_s = _normalize_text(pred_t.get("subject", ""))
        pred_p = _normalize_text(pred_t.get("predicate", ""))
        pred_o = _normalize_text(pred_t.get("object", ""))
      
        if not pred_p:
            stats["no_match"] += 1
            continue
      
        best_match_type = "no_match"
        best_score = 0
      
        for gold_t in gold_triples:
            gold_s = _normalize_text(gold_t.get("subject", ""))
            gold_p = _normalize_text(gold_t.get("predicate", ""))
            gold_o = _normalize_text(gold_t.get("object", ""))
          
            s_match = (pred_s == gold_s) if pred_s and gold_s else False
            p_match = (pred_p == gold_p) if pred_p and gold_p else False
            o_match = (pred_o == gold_o) if pred_o and gold_o else False
          
            score = int(s_match) + int(p_match) + int(o_match)
          
            if score > best_score:
                best_score = score
                if s_match and p_match and o_match:
                    best_match_type = "full_match"
                elif s_match and p_match:
                    best_match_type = "head_relation_match"
                elif p_match and o_match:
                    best_match_type = "relation_tail_match"
                elif s_match:
                    best_match_type = "head_only_match"
                elif o_match:
                    best_match_type = "tail_only_match"
                elif p_match:
                    best_match_type = "relation_only_match"
      
        stats[best_match_type] += 1
  
    # 计算加权 F1
    weights = {
        "full_match": 1.0,
        "head_relation_match": 0.67,
        "relation_tail_match": 0.67,
        "head_only_match": 0.33,
        "tail_only_match": 0.33,
        "relation_only_match": 0.33,
        "no_match": 0.0,
    }
  
    weighted_tp = sum(stats[k] * weights[k] for k in weights)
    precision = weighted_tp / stats["total_pred"] if stats["total_pred"] > 0 else 0
    recall = weighted_tp / stats["total_gold"] if stats["total_gold"] > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
  
    return {
        "partial_match_f1": round(f1, 4),
        "partial_precision": round(precision, 4),
        "partial_recall": round(recall, 4),
        "breakdown": stats,
    }
```

#### 1.4.3 `compute_evidence_quality`

```python
def compute_evidence_quality(predictions: Any, gold: Any, source_texts: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    评估预测三元组的证据质量：
    1. evidence_coverage: 有证据的三元组比例
    2. evidence_accuracy: 证据与 gold 匹配的比例
    3. evidence_source_match: 证据在原文中的匹配度（Rouge-L）
    """
    from difflib import SequenceMatcher
  
    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)
  
    pred_triples = pred_records.get("triples", [])
    gold_triples = gold_records.get("triples", [])
  
    # 构建 gold 证据索引
    gold_evidence_map = {}
    for g in gold_triples:
        key = (
            _normalize_text(g.get("subject", "")),
            _normalize_text(g.get("predicate", "")),
            _normalize_text(g.get("object", ""))
        )
        gold_evidence_map[key] = g.get("evidence", "")
  
    total_with_evidence = 0
    total_matched_evidence = 0
    evidence_lengths = []
    evidence_similarity_scores = []
  
    for pred_t in pred_triples:
        pred_evidence = pred_t.get("evidence", "")
        if pred_evidence:
            total_with_evidence += 1
            evidence_lengths.append(len(pred_evidence))
      
        key = (
            _normalize_text(pred_t.get("subject", "")),
            _normalize_text(pred_t.get("predicate", "")),
            _normalize_text(pred_t.get("object", ""))
        )
      
        if key in gold_evidence_map:
            gold_evidence = gold_evidence_map[key]
            if pred_evidence and gold_evidence:
                sim = SequenceMatcher(None, pred_evidence, gold_evidence).ratio()
                evidence_similarity_scores.append(sim)
                if sim > 0.5:
                    total_matched_evidence += 1
  
    total = len(pred_triples)
    return {
        "evidence_coverage": round(total_with_evidence / total, 4) if total > 0 else 0,
        "evidence_accuracy": round(total_matched_evidence / total_with_evidence, 4) if total_with_evidence > 0 else 0,
        "avg_evidence_length": round(sum(evidence_lengths) / len(evidence_lengths), 2) if evidence_lengths else 0,
        "avg_evidence_similarity": round(sum(evidence_similarity_scores) / len(evidence_similarity_scores), 4) if evidence_similarity_scores else 0,
        "total_with_evidence": total_with_evidence,
        "total_triples": total,
    }
```

#### 1.4.4 `compute_event_completeness`

```python
def compute_event_completeness(predictions: Any) -> Dict[str, Any]:
    """
    评估预测事件的完整性：
    - has_name_rate: 有名称的比例
    - has_type_rate: 有类型的比例
    - has_time_rate: 有时间的比例
    - has_location_rate: 有地点的比例
    - completeness_score: 综合完整性分数
    """
    pred_records = _ensure_records(predictions)
    events = pred_records.get("events", [])
  
    if not events:
        return {
            "total_events": 0,
            "has_name_rate": 0,
            "has_type_rate": 0,
            "has_time_rate": 0,
            "has_location_rate": 0,
            "completeness_score": 0,
        }
  
    has_name = sum(1 for e in events if e.get("name"))
    has_type = sum(1 for e in events if e.get("event_type"))
    has_time = sum(1 for e in events if _get_event_time_range(e)[0] or _get_event_time_range(e)[1])
    has_location = sum(1 for e in events if e.get("location"))
  
    total = len(events)
    completeness = (has_name + has_type + has_time + has_location) / (total * 4)
  
    return {
        "total_events": total,
        "has_name_rate": round(has_name / total, 4),
        "has_type_rate": round(has_type / total, 4),
        "has_time_rate": round(has_time / total, 4),
        "has_location_rate": round(has_location / total, 4),
        "completeness_score": round(completeness, 4),
    }
```

#### 1.4.5 `compute_per_class_metrics`

```python
def compute_per_class_metrics(predictions: Any, gold: Any, tbox: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """计算每种实体类型的 P/R/F1"""
    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)
  
    def extract_typed_entities(records: Dict[str, Any]) -> Dict[str, Set[str]]:
        type_to_entities: Dict[str, Set[str]] = {}
      
        for e in records.get("entities", []):
            if isinstance(e, dict):
                etype = _normalize_text(e.get("type", ""))
                name = _normalize_text(e.get("name", ""))
                if etype and name:
                    type_to_entities.setdefault(etype, set()).add(name)
      
        for ev in records.get("events", []):
            if isinstance(ev, dict):
                etype = _normalize_text(ev.get("event_type", ""))
                name = _normalize_text(ev.get("name", ""))
                if etype and name:
                    type_to_entities.setdefault(etype, set()).add(name)
      
        return type_to_entities
  
    pred_by_type = extract_typed_entities(pred_records)
    gold_by_type = extract_typed_entities(gold_records)
  
    all_types = set(pred_by_type.keys()) | set(gold_by_type.keys())
  
    results: Dict[str, Dict[str, Any]] = {}
    for etype in all_types:
        pred_set = pred_by_type.get(etype, set())
        gold_set = gold_by_type.get(etype, set())
      
        tp = len(pred_set & gold_set)
        p = tp / len(pred_set) if pred_set else 0
        r = tp / len(gold_set) if gold_set else 0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
      
        results[etype] = {
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
            "pred_count": len(pred_set),
            "gold_count": len(gold_set),
            "matched": tp,
        }
  
    return results
```

#### 1.4.6 `compute_ece` (置信度校准误差)

```python
def compute_ece(predictions: Any, gold: Any, n_bins: int = 5) -> Dict[str, Any]:
    """
    计算置信度校准误差 (Expected Calibration Error)。
    需要预测三元组包含 confidence 字段和 _is_correct 标记。
    """
    conf_map = {"high": 0.9, "medium": 0.7, "low": 0.5}
  
    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)
  
    pred_triples = pred_records.get("triples", [])
    gold_triples = gold_records.get("triples", [])
  
    # 构建 gold 集合用于匹配
    gold_set = set()
    for g in gold_triples:
        key = (
            _normalize_text(g.get("subject", "")),
            _normalize_text(g.get("predicate", "")),
            _normalize_text(g.get("object", ""))
        )
        gold_set.add(key)
  
    data = []
    for pred_t in pred_triples:
        conf_str = str(pred_t.get("confidence", "low")).lower()
        conf_score = conf_map.get(conf_str, 0.5)
      
        key = (
            _normalize_text(pred_t.get("subject", "")),
            _normalize_text(pred_t.get("predicate", "")),
            _normalize_text(pred_t.get("object", ""))
        )
        is_correct = 1.0 if key in gold_set else 0.0
        data.append((conf_score, is_correct))
  
    if not data:
        return {"ece": 0.0, "bin_stats": [], "total_samples": 0}
  
    import numpy as np
    data = np.array(data)
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    total = len(data)
    bin_stats = []
  
    for i in range(n_bins):
        mask = (data[:, 0] > bin_boundaries[i]) & (data[:, 0] <= bin_boundaries[i+1])
        bin_samples = data[mask]
        if len(bin_samples) > 0:
            avg_conf = float(np.mean(bin_samples[:, 0]))
            avg_acc = float(np.mean(bin_samples[:, 1]))
            bin_ece = abs(avg_acc - avg_conf) * (len(bin_samples) / total)
            ece += bin_ece
            bin_stats.append({
                "bin_range": f"({bin_boundaries[i]:.2f}, {bin_boundaries[i+1]:.2f}]",
                "count": int(len(bin_samples)),
                "avg_confidence": round(avg_conf, 4),
                "avg_accuracy": round(avg_acc, 4),
                "bin_ece": round(bin_ece, 4),
            })
  
    return {
        "ece": round(ece, 4),
        "bin_stats": bin_stats,
        "total_samples": total,
    }
```

### 1.5 修改 `compute_tbox_consistency` 函数

**目的**：从 entities 字段也推断实体类型

```python
def compute_tbox_consistency(
    predictions: Any,
    tbox: Dict[str, Any],
    *,
    use_original_type: bool = False,
) -> Tuple[float, Dict[str, int]]:
    """
    计算三元组与 TBox 的一致率：
    1) predicate 是否在 TBox 定义中
    2) 可推断 subject/object 类型时，domain/range 是否匹配
    """
    pred_records = _ensure_records(predictions, use_original_type=use_original_type)
    triples = pred_records["triples"]
    if not triples:
        return 1.0, {"total": 0, "predicate_unknown": 0, "domain_range_violations": 0}

    relations = tbox.get("relations", []) or []
    predicate_to_signature: Dict[str, Tuple[str, str]] = {}
    for relation_item in relations:
        rel_name = relation_item.get("name")
        if not rel_name:
            continue
        predicate_to_signature[_normalize_text(rel_name)] = (
            _normalize_text(relation_item.get("domain", "")),
            _normalize_text(relation_item.get("range", "")),
        )
    if not predicate_to_signature:
        return 0.0, {"total": len(triples), "predicate_unknown": len(triples), "domain_range_violations": 0}

    # 从 entities 推断实体类型
    entities = pred_records.get("entities", [])
    name_to_type: Dict[str, str] = {}
    for entity_item in entities:
        if not isinstance(entity_item, dict):
            continue
        entity_name = _normalize_text(entity_item.get("name", ""))
        entity_type = _normalize_text(entity_item.get("type", ""))
        if entity_name and entity_type:
            name_to_type[entity_name] = entity_type

    # 从 events 推断实体类型
    events = pred_records["events"]
    id_to_type: Dict[str, str] = {}
    for event_item in events:
        event_name = _normalize_text(event_item.get("name", ""))
        event_type = _normalize_text(event_item.get("event_type", ""))
        if event_name and event_type:
            name_to_type[event_name] = event_type
        event_id = _normalize_text(event_item.get("event_id", ""))
        if event_id and event_type:
            id_to_type[event_id] = event_type

    total = len(triples)
    predicate_unknown = 0
    domain_range_violations = 0
    domain_violations = 0
    range_violations = 0
    predicate_valid = 0

    for triple_item in triples:
        pred_name = _normalize_text(triple_item.get("predicate", ""))
        if pred_name not in predicate_to_signature:
            predicate_unknown += 1
            continue
        predicate_valid += 1
        domain_expected, range_expected = predicate_to_signature[pred_name]
        if not domain_expected and not range_expected:
            continue

        subject_name = _normalize_text(triple_item.get("subject", ""))
        object_name = _normalize_text(triple_item.get("object", ""))
        event_id = _normalize_text(triple_item.get("event_id", ""))

        subject_type = name_to_type.get(subject_name) or id_to_type.get(event_id)
        object_type = name_to_type.get(object_name)

        mismatch_flag = False
        if subject_type and domain_expected and subject_type != domain_expected:
            mismatch_flag = True
            domain_violations += 1
        if object_type and range_expected and object_type != range_expected:
            mismatch_flag = True
            range_violations += 1
        if mismatch_flag:
            domain_range_violations += 1

    consistent = sum(
        1 for t in triples if _normalize_text(t.get("predicate", "")) in predicate_to_signature
    )
    consistent = max(0, consistent - domain_range_violations)
    return round(consistent / total, 4), {
        "total": total,
        "predicate_unknown": predicate_unknown,
        "domain_range_violations": domain_range_violations,
        "domain_violations": domain_violations,
        "range_violations": range_violations,
        "predicate_valid": predicate_valid,
    }
```

### 1.6 修改 `compute_full_metrics` 函数

**目的**：整合所有新增指标

```python
def compute_full_metrics(
    predictions: Any,
    gold: Any,
    tbox: Dict[str, Any],
    *,
    time_tolerance_days: int = 0,
    geo_synonyms: Optional[str] = None,
    use_original_type: bool = False,
) -> Dict[str, Any]:
    """一次性返回全量指标"""
  
    # 现有指标计算
    event_metrics, event_errors = compute_event_f1(
        predictions, gold, time_tolerance_days=time_tolerance_days, use_original_type=use_original_type
    )
    triple_f1, triple_errors = compute_triple_f1(
        predictions, gold, time_tolerance_days=time_tolerance_days, geo_synonyms=geo_synonyms
    )
    tbox_consist, tbox_errors = compute_tbox_consistency(
        predictions, tbox, use_original_type=use_original_type
    )
  
    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)
    hallucination_stats = compute_hallucination_rate(predictions)
    redundancy_stats = compute_entity_redundancy_rate(predictions)
  
    entity_metrics, entity_stats = compute_entity_f1(predictions, gold)
    relation_metrics, relation_stats = compute_relation_f1(predictions, gold)
    schema_coverage = compute_schema_coverage(predictions, tbox)
  
    # 新增指标
    partial_match = compute_partial_match_metrics(predictions, gold)
    evidence_quality = compute_evidence_quality(predictions, gold)
    event_completeness = compute_event_completeness(predictions)
    direction_errors = compute_direction_error_rate(predictions, gold)
    per_class = compute_per_class_metrics(predictions, gold, tbox)
    per_relation = compute_per_relation_metrics(predictions, gold)
    ece_stats = compute_ece(predictions, gold)
  
    return {
        "use_original_type": use_original_type,
      
        # 核心 F1 指标
        "event_f1": round(event_metrics.f1, 4),
        "triple_f1_strict": round(triple_f1["strict"].f1, 4),
        "triple_f1_relaxed": round(triple_f1["relaxed"].f1, 4),
        "entity_f1": round(entity_metrics.f1, 4),
        "relation_f1": round(relation_metrics.f1, 4),
        "partial_match_f1": partial_match["partial_match_f1"],
      
        # 详细指标
        "event_metrics": event_metrics.to_dict(),
        "triple_metrics_strict": triple_f1["strict"].to_dict(),
        "triple_metrics_relaxed": triple_f1["relaxed"].to_dict(),
        "entity_metrics": entity_metrics.to_dict(),
        "relation_metrics": relation_metrics.to_dict(),
        "partial_match_metrics": partial_match,
      
        # 质量指标
        "tbox_consistency": tbox_consist,
        "hallucination_rate": hallucination_stats["hallucination_rate"],
        "entity_redundancy_rate": redundancy_stats["entity_redundancy_rate"],
        "direction_error_rate": direction_errors["direction_error_rate"],
        "ece": ece_stats["ece"],
      
        # 证据质量
        "evidence_quality": evidence_quality,
      
        # 事件完整性
        "event_completeness": event_completeness,
      
        # 覆盖率
        "schema_coverage": schema_coverage,
      
        # 统计信息
        "num_pred_events": len(pred_records["events"]),
        "num_gold_events": len(gold_records["events"]),
        "num_pred_triples": len(pred_records["triples"]),
        "num_gold_triples": len(gold_records["triples"]),
        "num_pred_entities": len(pred_records.get("entities", [])),
        "num_gold_entities": len(gold_records.get("entities", [])),
      
        # 详细统计
        "hallucination_stats": hallucination_stats,
        "entity_redundancy_stats": redundancy_stats,
        "direction_error_stats": direction_errors,
        "ece_stats": ece_stats,
        "entity_stats": entity_stats,
        "relation_stats": relation_stats,
      
        # 分类别指标
        "per_class_metrics": per_class,
        "per_relation_metrics": per_relation,
      
        # 错误分析
        "error_breakdown": {
            "events": event_errors,
            "triples": triple_errors,
            "tbox": tbox_errors,
        },
    }
```

### 1.7 修改 `main` 函数中的聚合逻辑

```python
def main() -> None:
    args = parse_args()
    setup_logger(log_file=args.log_file or None)

    gold = _load_json_or_jsonl(args.gold)
    preds = _load_json_or_jsonl(args.pred)
    tbox = json.loads(Path(args.tbox).read_text(encoding="utf-8"))

    if isinstance(gold, list) and isinstance(preds, list):
        if len(gold) != len(preds):
            logging.warning(
                f"gold/pred 条数不一致：gold={len(gold)}, pred={len(preds)}，将按最小长度对齐。"
            )
        pair_count = min(len(gold), len(preds))
        all_metrics = []
        for idx in range(pair_count):
            all_metrics.append(
                compute_full_metrics(
                    preds[idx],
                    gold[idx],
                    tbox,
                    time_tolerance_days=args.time_tolerance_days,
                    geo_synonyms=args.geo_syn,
                    use_original_type=args.use_original_type,
                )
            )
      
        def mean(values: List[float]) -> float:
            valid_values = [v for v in values if v is not None]
            return sum(valid_values) / len(valid_values) if valid_values else 0.0

        def sum_breakdown(items: List[Dict[str, int]]) -> Dict[str, int]:
            total_counts: Dict[str, int] = {}
            for item in items:
                for key, value in (item or {}).items():
                    if isinstance(value, (int, float)):
                        total_counts[key] = total_counts.get(key, 0) + int(value)
            return total_counts

        # 聚合计算
        hallucination_stats = compute_hallucination_rate(preds)
        redundancy_stats = compute_entity_redundancy_rate(preds)
        entity_metrics_agg, _ = compute_entity_f1(preds, gold)
        relation_metrics_agg, _ = compute_relation_f1(preds, gold)
        schema_coverage_agg = compute_schema_coverage(preds, tbox)
      
        # 新增聚合
        partial_match_agg = compute_partial_match_metrics(preds, gold)
        evidence_quality_agg = compute_evidence_quality(preds, gold)
        event_completeness_agg = compute_event_completeness(preds)
        direction_errors_agg = compute_direction_error_rate(preds, gold)
        per_class_agg = compute_per_class_metrics(preds, gold, tbox)
        per_relation_agg = compute_per_relation_metrics(preds, gold)
        ece_agg = compute_ece(preds, gold)

        report = {
            "use_original_type": args.use_original_type,
          
            # 核心 F1 指标（取平均）
            "event_f1": round(mean([m["event_f1"] for m in all_metrics]), 4),
            "triple_f1_strict": round(mean([m["triple_f1_strict"] for m in all_metrics]), 4),
            "triple_f1_relaxed": round(mean([m["triple_f1_relaxed"] for m in all_metrics]), 4),
            "entity_f1": round(mean([m["entity_f1"] for m in all_metrics]), 4),
            "relation_f1": round(mean([m["relation_f1"] for m in all_metrics]), 4),
            "partial_match_f1": partial_match_agg["partial_match_f1"],
          
            # 详细指标
            "event_metrics": {
                "precision": round(mean([m["event_metrics"]["precision"] for m in all_metrics]), 4),
                "recall": round(mean([m["event_metrics"]["recall"] for m in all_metrics]), 4),
                "f1": round(mean([m["event_metrics"]["f1"] for m in all_metrics]), 4),
            },
            "triple_metrics_strict": {
                "precision": round(mean([m["triple_metrics_strict"]["precision"] for m in all_metrics]), 4),
                "recall": round(mean([m["triple_metrics_strict"]["recall"] for m in all_metrics]), 4),
                "f1": round(mean([m["triple_metrics_strict"]["f1"] for m in all_metrics]), 4),
            },
            "triple_metrics_relaxed": {
                "precision": round(mean([m["triple_metrics_relaxed"]["precision"] for m in all_metrics]), 4),
                "recall": round(mean([m["triple_metrics_relaxed"]["recall"] for m in all_metrics]), 4),
                "f1": round(mean([m["triple_metrics_relaxed"]["f1"] for m in all_metrics]), 4),
            },
            "entity_metrics": entity_metrics_agg.to_dict(),
            "relation_metrics": relation_metrics_agg.to_dict(),
            "partial_match_metrics": partial_match_agg,
          
            # 质量指标
            "tbox_consistency": round(mean([m["tbox_consistency"] for m in all_metrics]), 4),
            "hallucination_rate": hallucination_stats["hallucination_rate"],
            "entity_redundancy_rate": redundancy_stats["entity_redundancy_rate"],
            "direction_error_rate": direction_errors_agg["direction_error_rate"],
            "ece": ece_agg["ece"],
          
            # 证据质量
            "evidence_quality": evidence_quality_agg,
          
            # 事件完整性
            "event_completeness": event_completeness_agg,
          
            # 覆盖率
            "schema_coverage": schema_coverage_agg,
          
            # 统计信息
            "sample_count": pair_count,
            "hallucination_stats": hallucination_stats,
            "entity_redundancy_stats": redundancy_stats,
            "direction_error_stats": direction_errors_agg,
            "ece_stats": ece_agg,
          
            # 分类别指标
            "per_class_metrics": per_class_agg,
            "per_relation_metrics": per_relation_agg,
          
            # 错误分析
            "error_breakdown": {
                "events": sum_breakdown([m["error_breakdown"]["events"] for m in all_metrics]),
                "triples": sum_breakdown([m["error_breakdown"]["triples"] for m in all_metrics]),
                "tbox": sum_breakdown([m["error_breakdown"]["tbox"] for m in all_metrics]),
            },
        }
    else:
        report = compute_full_metrics(
            preds,
            gold,
            tbox,
            time_tolerance_days=args.time_tolerance_days,
            geo_synonyms=args.geo_syn,
            use_original_type=args.use_original_type,
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info(f"[ABox] 指标已保存：{out_path}")
```

---

## 第二部分：Prompt 与 Schema 注入优化

### 文件：`kg/prompts.py`

### 2.1 新增统一抽取 Prompt

**目的**：Gold 和 Pred 使用完全相同的 Prompt，解决抽取不一致问题

```python
# 在 kg/prompts.py 中添加

UNIFIED_EXTRACTION_PROMPT = """你是一名水旱灾害领域知识图谱构建专家。

【Schema 定义】
{schema_text}

---

【⚠️ 核心原则：区分"通用知识"与"具体事件"】

1. **仅抽取具体实例**：
   - ❌ 拒绝通用描述：不要抽取 "洪水通常由暴雨引起" 这样的规律性描述
   - ✅ 仅抽取事实：只抽取 "1998年长江洪水由持续暴雨引起" 这样的具体记录
   - 如果文中是在讨论理论、规律或定义，而没有提及具体的时间/地点/事件实例，请返回空列表

2. **实体必须是实例**：
   - Subject 必须是具体的事件实例（如"98年洪水"）或具体的设施/机构
   - 不要将 "洪水"（泛指概念）作为 Subject

3. **实体必须是原文精确子串**：
   - ❌ 合并改写："长江中下游地区" ← 原文是"长江中下游"
   - ✅ 保持原样：使用原文中完全一致的表述

---

【⚠️ 关系方向说明 - 必须严格遵守】

关系的方向由 Schema 中的 domain（主语类型）和 range（宾语类型）决定：

| 关系名                | 正确方向                                    | 错误方向                                      |
| --------------------- | ------------------------------------------- | --------------------------------------------- |
| has_hazard_factor     | (灾害事件, has_hazard_factor, 致灾因子)     | ❌ (致灾因子, has_hazard_factor, 灾害事件)     |
| affects_region        | (灾害事件, affects_region, 地理区域)        | ❌ (地理区域, affects_region, 灾害事件)        |
| influenced_by_climate | (灾害事件, influenced_by_climate, 气候异常) | ❌ (气候异常, influenced_by_climate, 灾害事件) |
| causes_impact         | (灾害事件, causes_impact, 灾害影响)         | ❌ (灾害影响, causes_impact, 灾害事件)         |

**示例**：
- ✅ 正确：("1998年长江洪水", "has_hazard_factor", "持续暴雨")
- ❌ 错误：("持续暴雨", "has_hazard_factor", "1998年长江洪水")

---

【⚠️ 区分时间和事件】

- 判断标准：是否包含灾害性质词（洪水/旱灾/大水/奇旱/涝/决口等）
- ❌ 错误："乾隆二十九年(1764年)" → DisasterEvent
- ✅ 正确："乾隆二十九年(1764年)" → TemporalEntity
- ✅ 正确："乾隆五十年(1785年)奇旱" → DroughtEvent

---

【抽取步骤】请严格按以下步骤思考：

**Step 1: 实体扫描与定位**
- 识别文本中的具体实体（事件、地点、时间、机构等）
- 确认每个实体是"具体实例"而非"通用概念"

**Step 2: 事件识别与分类**
- 判断是否存在具体的灾害事件
- 确定事件类型（必须使用 Schema 中定义的类型 ID）

**Step 3: 关系判断与方向确认**
- 根据 Schema 的 domain/range 确定关系方向
- 主语类型必须匹配 domain，宾语类型必须匹配 range

**Step 4: 三元组组装与证据标注**
- 为每个三元组标注原文证据
- 标注置信度（high/medium/low）

---

【待抽取文本】
{input_text}

---

【输出格式】

请先输出【思考过程】（50-150字），然后输出 JSON：

```json
{{
  "entities": [
    {{"name": "实体名（原文子串）", "type": "类型ID（英文）"}}
  ],
  "events": [
    {{
      "name": "事件名称",
      "event_type": "事件类型ID（英文）",
      "time": {{"start_time": "YYYY-MM-DD", "end_time": "YYYY-MM-DD"}},
      "location": ["地点1", "地点2"]
    }}
  ],
  "triples": [
    {{
      "subject": "主语（原文子串）",
      "predicate": "关系ID（英文）",
      "object": "宾语（原文子串）",
      "evidence": "原文证据句",
      "confidence": "high/medium/low"
    }}
  ]
}}
```

**注意**：
1. 类型和关系必须使用英文 ID（如 DisasterEvent, affects_region）
2. 实体名称保持原文语言
3. 如果没有可抽取的内容，返回空列表
"""
```

### 2.2 新增 Schema 格式化函数

**文件**：`kg/cq_pipeline.py`

```python
def format_schema_for_prompt(schema_json: Dict[str, Any], style: str = "markdown") -> str:
    """
    将 TBox Schema 格式化为 Prompt 可用的文本。
  
    Args:
        schema_json: TBox JSON 对象
        style: 格式化风格，"markdown" 或 "json"
  
    Returns:
        格式化后的 Schema 文本
    """
    if style == "json":
        return json.dumps(schema_json, ensure_ascii=False, indent=2)
  
    lines = []
  
    # 格式化类（中文名在前）
    lines.append("【实体类型定义】\n")
    for cls in schema_json.get("classes", []):
        name = cls.get("name", "")
        cn_name = cls.get("cn_name", "")
        definition = cls.get("definition", "")
        examples = cls.get("examples", [])
      
        lines.append(f"- **{cn_name}** (ID: `{name}`)")
        lines.append(f"  - 定义：{definition}")
        if examples:
            lines.append(f"  - 示例：{', '.join(examples[:3])}")
  
    # 格式化关系（表格形式，强调方向）
    lines.append("\n【关系类型定义】\n")
    lines.append("| 中文名 | 关系ID | 主语类型(domain) | 宾语类型(range) | 说明 |")
    lines.append("|--------|--------|------------------|-----------------|------|")
  
    for rel in schema_json.get("relations", []):
        name = rel.get("name", "")
        cn_name = rel.get("cn_name", "")
        domain = rel.get("domain", "")
        range_ = rel.get("range", "")
        definition = rel.get("definition", "")[:30] + "..." if len(rel.get("definition", "")) > 30 else rel.get("definition", "")
      
        lines.append(f"| {cn_name} | `{name}` | {domain} | {range_} | {definition} |")
  
    return "\n".join(lines)
```

---

## 第三部分：统一抽取流程

### 新建文件：`kg/unified_extraction.py`

```python
"""
统一抽取流程模块。
Gold 和 Pred 使用相同的 Prompt、后处理逻辑和参数配置。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from kg.prompts import UNIFIED_EXTRACTION_PROMPT
from kg.cq_pipeline import format_schema_for_prompt
from kg.hallucination_filter import HallucinationFilter
from kg.entity_normalizer import SimpleEntityNormalizer


@dataclass
class ExtractionConfig:
    """统一的抽取配置"""
    fuzzy_threshold: float = 0.8      # 幻觉过滤阈值（统一）
    strict_mode: bool = False          # 严格模式（统一为 False）
    use_cot: bool = True               # 使用 CoT
    schema_style: str = "markdown"     # Schema 格式化风格
    enable_direction_fix: bool = True  # 启用方向修正


@dataclass
class ExtractionResult:
    """抽取结果"""
    events: List[Dict[str, Any]] = field(default_factory=list)
    triples: List[Dict[str, Any]] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    filtered_triples: List[Dict[str, Any]] = field(default_factory=list)
    thought: str = ""
    stats: Dict[str, Any] = field(default_factory=dict)
    parse_error: bool = False


class DirectionNormalizer:
    """三元组方向修正器"""
  
    def __init__(self, tbox: Dict[str, Any]):
        self.tbox = tbox
        self.relation_signatures = self._build_signatures()
  
    def _build_signatures(self) -> Dict[str, Tuple[str, str]]:
        """构建关系签名映射：relation_name -> (domain, range)"""
        signatures = {}
        for rel in self.tbox.get("relations", []):
            name = rel.get("name", "").lower()
            domain = rel.get("domain", "").lower()
            range_ = rel.get("range", "").lower()
            if name:
                signatures[name] = (domain, range_)
        return signatures
  
    def _get_entity_type(self, entity_name: str, entities: List[Dict], events: List[Dict]) -> Optional[str]:
        """推断实体类型"""
        entity_name_lower = entity_name.lower().strip()
      
        # 从 entities 查找
        for e in entities:
            if e.get("name", "").lower().strip() == entity_name_lower:
                return e.get("type", "").lower()
      
        # 从 events 查找
        for ev in events:
            if ev.get("name", "").lower().strip() == entity_name_lower:
                return ev.get("event_type", "").lower()
      
        return None
  
    def fix_directions(
        self, 
        triples: List[Dict[str, Any]], 
        entities: List[Dict[str, Any]] = None,
        events: List[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        修正三元组方向。
        如果检测到主宾语类型与 Schema 定义相反，则交换主宾语。
        """
        entities = entities or []
        events = events or []
        fixed_triples = []
      
        for triple in triples:
            subject = triple.get("subject", "")
            predicate = triple.get("predicate", "").lower()
            obj = triple.get("object", "")
          
            if predicate not in self.relation_signatures:
                fixed_triples.append(triple)
                continue
          
            expected_domain, expected_range = self.relation_signatures[predicate]
          
            # 推断实际类型
            subject_type = self._get_entity_type(subject, entities, events)
            object_type = self._get_entity_type(obj, entities, events)
          
            # 检查是否需要交换
            need_swap = False
            if subject_type and object_type:
                # 如果主语类型匹配 range 且宾语类型匹配 domain，则需要交换
                if subject_type == expected_range and object_type == expected_domain:
                    need_swap = True
          
            if need_swap:
                fixed_triple = dict(triple)
                fixed_triple["subject"] = obj
                fixed_triple["object"] = subject
                fixed_triple["_direction_fixed"] = True
                fixed_triples.append(fixed_triple)
                logging.debug(f"方向修正: ({subject}, {predicate}, {obj}) -> ({obj}, {predicate}, {subject})")
            else:
                fixed_triples.append(triple)
      
        return fixed_triples


class UnifiedExtractionPipeline:
    """统一的抽取后处理流程"""
  
    def __init__(
        self,
        tbox: Dict[str, Any],
        config: ExtractionConfig = None,
    ):
        self.tbox = tbox
        self.config = config or ExtractionConfig()
      
        self.halluc_filter = HallucinationFilter(
            strict_mode=self.config.strict_mode,
            fuzzy_threshold=self.config.fuzzy_threshold,
        )
        self.direction_fixer = DirectionNormalizer(tbox)
        self.entity_normalizer = SimpleEntityNormalizer()
  
    def build_prompt(self, source_text: str) -> str:
        """构建统一的抽取 Prompt"""
        schema_text = format_schema_for_prompt(self.tbox, style=self.config.schema_style)
        return UNIFIED_EXTRACTION_PROMPT.format(
            schema_text=schema_text,
            input_text=source_text,
        )
  
    def parse_response(self, raw_response: str) -> Tuple[Dict[str, Any], str]:
        """解析 LLM 响应"""
        thought = ""
        result = {"entities": [], "events": [], "triples": []}
      
        # 提取思考过程
        if "【思考过程】" in raw_response:
            parts = raw_response.split("```json")
            if len(parts) >= 2:
                thought = parts[0].replace("【思考过程】", "").strip()
      
        # 提取 JSON
        import re
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", raw_response)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                logging.warning("JSON 解析失败")
        else:
            # 尝试直接解析
            try:
                # 查找第一个 { 和最后一个 }
                start = raw_response.find("{")
                end = raw_response.rfind("}") + 1
                if start >= 0 and end > start:
                    result = json.loads(raw_response[start:end])
            except json.JSONDecodeError:
                logging.warning("无法解析响应中的 JSON")
      
        return result, thought
  
    def process(self, raw_result: Dict[str, Any], source_text: str) -> ExtractionResult:
        """统一后处理流程"""
      
        original_triples = raw_result.get("triples", [])
        entities = raw_result.get("entities", [])
        events = raw_result.get("events", [])
      
        # Step 1: 幻觉过滤
        verified = self.halluc_filter.verify(raw_result, source_text)
      
        # Step 2: 方向修正
        if self.config.enable_direction_fix:
            fixed_triples = self.direction_fixer.fix_directions(
                verified.valid_triples, 
                entities=entities,
                events=verified.valid_events
            )
        else:
            fixed_triples = verified.valid_triples
      
        # Step 3: 实体归一化
        normalized_triples = self.entity_normalizer.normalize_triples(fixed_triples)
      
        # Step 4: TBox 约束验证
        valid_triples = self._validate_tbox(normalized_triples)
      
        return ExtractionResult(
            events=verified.valid_events,
            triples=valid_triples,
            entities=entities,
            filtered_triples=verified.filtered_triples,
            thought=raw_result.get("_thinking", ""),
            stats={
                "original": len(original_triples),
                "after_halluc_filter": len(verified.valid_triples),
                "after_direction_fix": len(fixed_triples),
                "final": len(valid_triples),
                "direction_fixed_count": sum(1 for t in fixed_triples if t.get("_direction_fixed")),
            },
            parse_error=False,
        )
  
    def _validate_tbox(self, triples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """验证三元组是否符合 TBox 约束"""
        valid_predicates = {
            rel.get("name", "").lower() 
            for rel in self.tbox.get("relations", [])
        }
      
        valid_triples = []
        for triple in triples:
            predicate = triple.get("predicate", "").lower()
            if predicate in valid_predicates:
                valid_triples.append(triple)
            else:
                logging.debug(f"过滤未知谓词: {predicate}")
      
        return valid_triples


def create_unified_pipeline(tbox_path: str, **kwargs) -> UnifiedExtractionPipeline:
    """工厂函数：创建统一抽取流程"""
    from pathlib import Path
    tbox = json.loads(Path(tbox_path).read_text(encoding="utf-8"))
    config = ExtractionConfig(**kwargs)
    return UnifiedExtractionPipeline(tbox, config)
```

---

## 第四部分：验证测试

### 文件：`tests/test_abox_metrics.py`

```python
"""
ABox 评测指标单元测试
"""

import json
import pytest
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
  
    def test_full_### 文件：`tests/test_abox_metrics.py`（续）

```python
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
            "error_breakdown",
        ]
        for field in required_fields:
            assert field in result, f"缺少字段: {field}"


# 运行测试
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

---

## 第五部分：集成测试脚本

### 文件：`scripts/test_metrics_integration.py`

```python
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
```

---

## 第六部分：修改检查清单

完成所有修改后，请逐项确认：

### 评测指标 (`tools/abox_metrics.py`)

- [ ] `_normalize_text` 函数已增强，处理中文括号
- [ ] 新增 `_normalize_value` 函数
- [ ] `_ensure_records` 函数已添加 `entities` 字段处理和推断逻辑
- [ ] 新增 `compute_direction_error_rate` 函数
- [ ] 新增 `compute_partial_match_metrics` 函数
- [ ] 新增 `compute_evidence_quality` 函数
- [ ] 新增 `compute_event_completeness` 函数
- [ ] 新增 `compute_per_class_metrics` 函数
- [ ] 新增 `compute_ece` 函数
- [ ] `compute_tbox_consistency` 函数已修改为从 `entities` 推断类型
- [ ] `compute_full_metrics` 函数已整合所有新增指标
- [ ] `main` 函数的聚合逻辑已更新

### Prompt 优化 (`kg/prompts.py`)

- [ ] 新增 `UNIFIED_EXTRACTION_PROMPT` 统一 Prompt
- [ ] Prompt 中包含"区分通用知识与具体事件"的约束
- [ ] Prompt 中包含关系方向说明表格

### Schema 格式化 (`kg/cq_pipeline.py`)

- [ ] 新增 `format_schema_for_prompt` 函数
- [ ] 支持 Markdown 和 JSON 两种格式
- [ ] 中文名在前，强调 domain/range

### 统一抽取流程 (`kg/unified_extraction.py`)

- [ ] 新建文件
- [ ] 实现 `ExtractionConfig` 配置类
- [ ] 实现 `DirectionNormalizer` 方向修正器
- [ ] 实现 `UnifiedExtractionPipeline` 统一流程

### 测试

- [ ] 单元测试全部通过
- [ ] 集成测试输出包含所有新增字段
- [ ] 使用真实数据验证无报错

---

## 第七部分：输出示例

修改完成后，`metrics.json` 的输出格式示例：

```json
{
  "use_original_type": false,
  "event_f1": 0.0,
  "triple_f1_strict": 0.1234,
  "triple_f1_relaxed": 0.2345,
  "entity_f1": 0.3456,
  "relation_f1": 0.4567,
  "partial_match_f1": 0.3890,
  "event_metrics": {
    "precision": 0.0,
    "recall": 0.0,
    "f1": 0.0
  },
  "triple_metrics_strict": {
    "precision": 0.15,
    "recall": 0.10,
    "f1": 0.1234
  },
  "triple_metrics_relaxed": {
    "precision": 0.30,
    "recall": 0.20,
    "f1": 0.2345
  },
  "partial_match_metrics": {
    "partial_match_f1": 0.3890,
    "partial_precision": 0.40,
    "partial_recall": 0.38,
    "breakdown": {
      "full_match": 5,
      "head_relation_match": 8,
      "relation_tail_match": 3,
      "head_only_match": 2,
      "tail_only_match": 1,
      "relation_only_match": 4,
      "no_match": 7,
      "total_pred": 30,
      "total_gold": 25
    }
  },
  "tbox_consistency": 0.85,
  "hallucination_rate": 0.15,
  "entity_redundancy_rate": 0.08,
  "direction_error_rate": 0.12,
  "ece": 0.15,
  "evidence_quality": {
    "evidence_coverage": 0.90,
    "evidence_accuracy": 0.75,
    "avg_evidence_length": 45.5,
    "avg_evidence_similarity": 0.68,
    "total_with_evidence": 27,
    "total_triples": 30
  },
  "event_completeness": {
    "total_events": 10,
    "has_name_rate": 1.0,
    "has_type_rate": 0.90,
    "has_time_rate": 0.60,
    "has_location_rate": 0.70,
    "completeness_score": 0.80
  },
  "schema_coverage": {
    "relation_coverage": 0.45,
    "class_coverage": 0.38,
    "used_relations": 14,
    "defined_relations": 31,
    "used_classes": 22,
    "defined_classes": 58
  },
  "ece_stats": {
    "ece": 0.15,
    "bin_stats": [
      {"bin_range": "(0.40, 0.60]", "count": 5, "avg_confidence": 0.50, "avg_accuracy": 0.40},
      {"bin_range": "(0.60, 0.80]", "count": 10, "avg_confidence": 0.70, "avg_accuracy": 0.60},
      {"bin_range": "(0.80, 1.00]", "count": 15, "avg_confidence": 0.90, "avg_accuracy": 0.80}
    ],
    "total_samples": 30
  },
  "per_class_metrics": {
    "disasterevent": {
      "precision": 0.80,
      "recall": 0.60,
      "f1": 0.69,
      "pred_count": 10,
      "gold_count": 12,
      "matched": 8
    },
    "geographicregion": {
      "precision": 0.70,
      "recall": 0.50,
      "f1": 0.58,
      "pred_count": 20,
      "gold_count": 28,
      "matched": 14
    }
  },
  "per_relation_metrics": {
    "affects_region": {
      "precision": 0.60,
      "recall": 0.40,
      "f1": 0.48,
      "pred_count": 15,
      "gold_count": 20,
      "matched": 9
    },
    "has_hazard_factor": {
      "precision": 0.50,
      "recall": 0.30,
      "f1": 0.375,
      "pred_count": 8,
      "gold_count": 10,
      "matched": 4
    }
  },
  "error_breakdown": {
    "events": {
      "matched": 0,
      "type_mismatch": 0,
      "name_mismatch": 0,
      "time_mismatch": 0,
      "unmatched_pred": 10,
      "unmatched_gold": 0
    },
    "triples": {
      "strict_matched": 5,
      "relaxed_matched": 12,
      "predicate_mismatch": 8,
      "geo_mismatch": 3,
      "time_mismatch": 2,
      "other_mismatch": 0,
      "unmatched_pred": 13,
      "unmatched_gold": 10
    },
    "tbox": {
      "total": 30,
      "predicate_unknown": 2,
      "domain_range_violations": 3,
      "domain_violations": 2,
      "range_violations": 1,
      "predicate_valid": 28
    }
  },
  "direction_error_stats": {
    "direction_error_rate": 0.12,
    "direction_errors": 4,
    "total_checked": 30
  },
  "sample_count": 100
}
```

---

## 第九部分：新增指标汇总表

| 指标名称       | 字段路径                                   | 说明                         | 取值范围 | 用途                     |
| -------------- | ------------------------------------------ | ---------------------------- | -------- | ------------------------ |
| 部分匹配 F1    | `partial_match_f1`                         | 加权部分匹配分数             | 0-1      | 评估三元组部分正确的情况 |
| 方向错误率     | `direction_error_rate`                     | 主宾语颠倒的比例             | 0-1      | 检测关系方向理解错误     |
| 置信度校准误差 | `ece`                                      | 模型置信度与实际准确率的偏差 | 0-1      | 评估模型校准程度         |
| 证据覆盖率     | `evidence_quality.evidence_coverage`       | 有证据的三元组比例           | 0-1      | 评估证据完整性           |
| 证据准确率     | `evidence_quality.evidence_accuracy`       | 证据与 Gold 匹配的比例       | 0-1      | 评估证据质量             |
| 证据相似度     | `evidence_quality.avg_evidence_similarity` | 证据文本相似度               | 0-1      | 评估证据准确性           |
| 事件完整性     | `event_completeness.completeness_score`    | 事件四要素平均覆盖率         | 0-1      | 评估事件抽取完整性       |
| 分类别 F1      | `per_class_metrics.<type>.f1`              | 每种实体类型的 F1            | 0-1      | 细粒度实体评估           |
| 分关系 F1      | `per_relation_metrics.<rel>.f1`            | 每种关系的 F1                | 0-1      | 细粒度关系评估           |

---

## 第十部分：常见问题排查

### 问题2：Gold 中 events 为空导致 Event F1 为 0

**原因**：Gold 标注策略问题，不是代码 bug

**解决方案**：
1. 使用统一 Prompt 重新生成 Gold
2. 或在评测时忽略 Event F1，重点关注 Triple F1

### 问题3：方向错误率过高

**原因**：模型对关系方向理解错误

**解决方案**：
1. 在 Prompt 中增加关系方向示例表格（已在统一 Prompt 中添加）
2. 使用 `DirectionNormalizer` 自动修正方向

### 问题4：ECE 计算需要 confidence 字段

**原因**：部分三元组缺少 confidence 字段

**解决方案**：代码已处理，缺少时默认使用 "low" (0.5)

---

## 第十一部分：文件修改总结

| 文件路径                              | 修改类型 | 主要变更                                  |
| ------------------------------------- | -------- | ----------------------------------------- |
| `tools/abox_metrics.py`               | 修改     | 增强归一化、新增6个指标函数、修改聚合逻辑 |
| `kg/prompts.py`                       | 新增     | 添加 `UNIFIED_EXTRACTION_PROMPT`          |
| `kg/cq_pipeline.py`                   | 新增     | 添加 `format_schema_for_prompt` 函数      |
| `kg/unified_extraction.py`            | 新建     | 统一抽取流程模块                          |
| `tests/test_abox_metrics.py`          | 新建     | 单元测试                                  |
| `scripts/test_metrics_integration.py` | 新建     | 集成测试脚本                              |

---



**文档结束**

请按照本文档的指导进行代码修改，完成后运行测试脚本验证修改是否正确。如有问题，请检查错误日志并对照修改检查清单排查。