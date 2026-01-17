"""
抽取结果统一输出模块。

用于 Gold/Pred 统一输出结构，包含实体、关系、事件、证据与幻觉统计等信息。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def clip_text(text: str, max_len: Optional[int] = None) -> str:
    """截断文本，避免输出过长。"""
    if not text:
        return ""
    if max_len and len(text) > max_len:
        return f"{text[:max_len]}..."
    return text


def _ensure_list(value: Any) -> List[Any]:
    """确保返回列表类型。"""
    return value if isinstance(value, list) else []


def _normalize_triple(triple: Dict[str, Any]) -> Dict[str, Any]:
    """补齐三元组关键字段，避免下游缺失。"""
    if not isinstance(triple, dict):
        return {}
    normalized = dict(triple)
    for key in ["subject", "predicate", "object", "subject_type", "object_type", "event_id", "evidence"]:
        normalized.setdefault(key, "")
    return normalized


def _normalize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """补齐事件关键字段，避免下游缺失。"""
    if not isinstance(event, dict):
        return {}
    normalized = dict(event)
    normalized.setdefault("event_id", "")
    normalized.setdefault("event_type", "")
    normalized.setdefault("name", "")
    return normalized


def _split_filter_reason(item: Dict[str, Any]) -> Dict[str, Any]:
    """将过滤原因与三元组拆分，统一输出结构。"""
    if not isinstance(item, dict):
        return {"triple": {}, "reason": "invalid_item"}
    reason = item.get("filter_reason", "")
    triple = {k: v for k, v in item.items() if k != "filter_reason"}
    return {"triple": _normalize_triple(triple), "reason": reason}


def _dedup_entities(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按 (name, type) 去重，保留首次出现顺序。"""
    seen: set[Tuple[str, str]] = set()
    deduped: List[Dict[str, Any]] = []
    for item in entities:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        etype = str(item.get("type", "")).strip()
        if not name:
            continue
        key = (name, etype)
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"name": name, "type": etype})
    return deduped


def _collect_entities(
    entities_from_result: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    triples: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """从 events/triples 中补充实体列表。"""
    entities: List[Dict[str, Any]] = []

    for entity in entities_from_result:
        if isinstance(entity, dict):
            entities.append({"name": entity.get("name", ""), "type": entity.get("type", "")})

    for event in events:
        if not isinstance(event, dict):
            continue
        name = event.get("name", "")
        event_type = event.get("event_type", "")
        if name:
            entities.append({"name": name, "type": event_type})

    for triple in triples:
        if not isinstance(triple, dict):
            continue
        subject = triple.get("subject", "")
        subject_type = triple.get("subject_type", "")
        if subject:
            entities.append({"name": subject, "type": subject_type})

        obj = triple.get("object", "")
        object_type = triple.get("object_type", "")
        if obj:
            entities.append({"name": obj, "type": object_type})

    return _dedup_entities(entities)


def _group_entities_by_type(entities: List[Dict[str, Any]]) -> List[Dict[str, List[str]]]:
    """按类型分组实体，输出为 {type: [name]} 的列表结构。"""
    grouped: Dict[str, List[str]] = {}
    for item in entities:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        etype = str(item.get("type", "")).strip()
        if not name:
            continue
        names = grouped.setdefault(etype, [])
        if name not in names:
            names.append(name)
    return [grouped] if grouped else []


def build_extraction_record(
    doc_id: str,
    source_text: str,
    extraction_result: Optional[Dict[str, Any]] = None,
    *,
    use_cot: bool = True,
    use_verify: bool = True,
    use_graph: bool = True,
    max_source_text_len: Optional[int] = None,
    include_source_text: bool = True,
    error: str = "",
) -> Dict[str, Any]:
    """
    构建统一输出结构。

    Args:
        doc_id: 文档ID
        source_text: 抽取使用的文本
        extraction_result: 抽取结果（来自 pipeline）
        use_cot: 是否使用 CoT
        use_verify: 是否使用后校验
        use_graph: 是否使用图结构自动检测
        max_source_text_len: 文本最大长度（None 表示不截断）
        include_source_text: 是否在输出中保留 source_text 字段
        error: 错误信息（优先级高于 extraction_result 内的 error）

    Returns:
        统一格式的输出字典
    """
    record: Dict[str, Any] = {
        "doc_id": doc_id,
        "use_cot": use_cot,
        "use_verify": use_verify,
        "use_graph": use_graph,
        "entities": [],
        "events": [],
        "triples": [],
        "filtered_triples": [],
        "schema_filtered_triples": [],
        "hallucination": {
            "enabled": use_verify,
            "original_count": 0,
            "valid_count": 0,
            "filtered_count": 0,
            "schema_filtered_count": 0,
            "rate": 0.0,
        },
    }
    if include_source_text:
        record["source_text"] = clip_text(source_text, max_source_text_len)

    if error:
        record["error"] = error
        return record

    if not extraction_result:
        record["error"] = "empty_extraction_result"
        return record

    if extraction_result.get("error"):
        record["error"] = extraction_result.get("error")
        return record

    events = [_normalize_event(e) for e in _ensure_list(extraction_result.get("events"))]
    triples = [_normalize_triple(t) for t in _ensure_list(extraction_result.get("triples"))]

    filtered_raw = _ensure_list(extraction_result.get("filtered_triples"))
    schema_filtered_raw = _ensure_list(extraction_result.get("schema_filtered_triples"))

    filtered_triples = [_split_filter_reason(t) for t in filtered_raw]
    schema_filtered_triples = [_split_filter_reason(t) for t in schema_filtered_raw]

    entities_from_result = _ensure_list(extraction_result.get("entities"))
    entities = _collect_entities(entities_from_result, events, triples)
    grouped_entities = _group_entities_by_type(entities)

    record["entities"] = grouped_entities
    record["events"] = events
    record["triples"] = triples
    record["filtered_triples"] = filtered_triples
    record["schema_filtered_triples"] = schema_filtered_triples

    stats = extraction_result.get("stats", {}) if isinstance(extraction_result.get("stats"), dict) else {}
    total_triples = stats.get("total_triples")
    if total_triples is None:
        total_triples = len(triples) + len(filtered_raw)
    valid_triples = stats.get("valid_triples", len(triples))
    filtered_count = stats.get("filtered_triples", len(filtered_raw))
    schema_filtered_count = stats.get("schema_filtered_triples", len(schema_filtered_raw))

    rate = extraction_result.get("hallucination_rate")
    if isinstance(rate, (int, float)):
        rate_value = float(rate)
    else:
        rate_value = filtered_count / total_triples if total_triples else 0.0

    record["hallucination"] = {
        "enabled": use_verify,
        "original_count": total_triples,
        "valid_count": valid_triples,
        "filtered_count": filtered_count,
        "schema_filtered_count": schema_filtered_count,
        "rate": round(rate_value, 4),
    }

    if extraction_result.get("thought"):
        record["thought"] = extraction_result.get("thought")
    if extraction_result.get("verification_log"):
        record["verification_log"] = extraction_result.get("verification_log")
    if stats:
        record["stats"] = stats

    return record
