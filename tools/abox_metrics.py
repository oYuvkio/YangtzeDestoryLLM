"""
ABox 抽取质量评估：事件 F1、三元组 F1（严格/宽松）、TBox 一致性。

对应 txts/improve/5-kg抽取/todo - ABox 抽取评测.md 的口径：
- Event F1：事件类型 + 时间窗命中（支持 ±N 天容忍）
- Triple F1（Strict/Relaxed）：(h,r,t) 匹配；宽松允许时间±N日、地名同义/上位合并
- TBox Consistency：谓词存在性 +（可推断时）domain/range 符合率

特性：
- 支持输入 dict / list / jsonl（批量时自动扁平化）
- 文本做归一化（去空格/标点、转小写）
- 输出 error_breakdown，便于论文分析
- 提供 CLI：python tools/abox_metrics.py --gold ... --pred ... --tbox ...
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import argparse
import json
import logging
import re
import sys


# =========================
# 数据结构
# =========================
@dataclass
class ExtractionMetrics:
    """用于统一返回精确率/召回率/F1。"""

    precision: float
    recall: float
    f1: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


# =========================
# 内部工具函数
# =========================
def _normalize_text(text: str) -> str:
    """标准化文本：去掉空白/常见标点，转小写，便于宽容匹配。"""
    text = str(text).strip()
    # 去除括号及内容（针对 "长江(Yangtze)" 这种情况）
    text = re.sub(r"（[^）]*）|\([^\)]*\)", "", text)
    # 去除标点和空格
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。、""''：；（）【】《》/\\-]", "", text)
    return text.lower()


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


def _calc_prf(tp: int, pred_total: int, gold_total: int) -> ExtractionMetrics:
    """统一计算 Precision / Recall / F1。"""
    if pred_total == 0 and gold_total == 0:
        return ExtractionMetrics(precision=1.0, recall=1.0, f1=1.0)
    precision = tp / pred_total if pred_total > 0 else 0.0
    recall = tp / gold_total if gold_total > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return ExtractionMetrics(precision=precision, recall=recall, f1=f1)


def _extract_event_keys(events: List[Dict[str, Any]]) -> Set[str]:
    """
    为事件生成匹配 key（用于粗筛/统计），默认使用 name+type（都做归一化）。
    真实匹配使用时间容忍算法（见 _match_events_with_tolerance）。
    """
    keys: Set[str] = set()
    for e in events:
        name = _normalize_text(e.get("name", ""))
        etype = _normalize_text(e.get("event_type", ""))
        key = f"{name}_{etype}".strip("_")
        if key:
            keys.add(key)
    return keys


def _extract_triple_keys(triples: List[Dict[str, Any]], strict: bool) -> Set[Tuple[str, str, str]]:
    """
    生成三元组匹配 key。
    strict=True  : (s,p,o) 全部一致
    strict=False : 只要求 p 一致，s/o 任一可模糊（在上层做判断）
    """
    keys: Set[Tuple[str, str, str]] = set()
    for t in triples:
        s = _normalize_text(t.get("subject", ""))
        p = _normalize_text(t.get("predicate", ""))
        o = _normalize_text(t.get("object", ""))
        if not p:
            continue
        if strict:
            if s and o:
                keys.add((s, p, o))
        else:
            keys.add((s, p, o))
    return keys


def _parse_iso_date(text: str) -> Optional[date]:
    """解析 YYYY-MM-DD 日期，失败返回 None。"""
    if not text:
        return None
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def _get_event_time_range(event: Dict[str, Any]) -> Tuple[Optional[date], Optional[date]]:
    """从事件中提取 start/end 日期。"""
    time_block = event.get("time") or {}
    if not isinstance(time_block, dict):
        time_block = {}
    start_raw = time_block.get("start_time", "")
    end_raw = time_block.get("end_time", "")
    return _parse_iso_date(start_raw), _parse_iso_date(end_raw)


def _ranges_match_with_tolerance(
    pred_start: Optional[date],
    pred_end: Optional[date],
    gold_start: Optional[date],
    gold_end: Optional[date],
    tolerance_days: int,
) -> bool:
    """
    判断两个时间窗是否命中：
    - 若两边都缺失时间，不阻塞匹配；
    - 若只有一边缺失时间，也视为命中（偏宽松，避免惩罚空时间）。
    - 否则要求 start/end 在 ±N 天内接近或区间重叠。
    """
    if pred_start is None and pred_end is None:
        return True
    if gold_start is None and gold_end is None:
        return True

    tol = timedelta(days=max(0, tolerance_days))

    pred_start_eff = pred_start or pred_end
    pred_end_eff = pred_end or pred_start
    gold_start_eff = gold_start or gold_end
    gold_end_eff = gold_end or gold_start
    if pred_start_eff is None or pred_end_eff is None or gold_start_eff is None or gold_end_eff is None:
        return True

    pred_start_eff = pred_start_eff - tol
    pred_end_eff = pred_end_eff + tol
    gold_start_eff = gold_start_eff - tol
    gold_end_eff = gold_end_eff + tol
    return not (pred_end_eff < gold_start_eff or gold_end_eff < pred_start_eff)


def _match_events_with_tolerance(
    pred_events: List[Dict[str, Any]],
    gold_events: List[Dict[str, Any]],
    tolerance_days: int,
) -> Tuple[int, Dict[str, int]]:
    """
    事件一对一匹配：
    - event_type 必须一致
    - name 非空时优先要求一致
    - time 窗口满足容忍匹配
    返回 tp 数与错误分类统计。
    """
    error_breakdown: Dict[str, int] = {
        "matched": 0,
        "type_mismatch": 0,
        "name_mismatch": 0,
        "time_mismatch": 0,
        "missing_time_pred": 0,
        "missing_time_gold": 0,
        "unmatched_pred": 0,
        "unmatched_gold": 0,
    }

    # 预归一化
    norm_pred = []
    for event_item in pred_events:
        pred_name = _normalize_text(event_item.get("name", ""))
        pred_type = _normalize_text(event_item.get("event_type", ""))
        pred_start, pred_end = _get_event_time_range(event_item)
        if pred_start is None and pred_end is None:
            error_breakdown["missing_time_pred"] += 1
        norm_pred.append((event_item, pred_name, pred_type, pred_start, pred_end))

    norm_gold = []
    for event_item in gold_events:
        gold_name = _normalize_text(event_item.get("name", ""))
        gold_type = _normalize_text(event_item.get("event_type", ""))
        gold_start, gold_end = _get_event_time_range(event_item)
        if gold_start is None and gold_end is None:
            error_breakdown["missing_time_gold"] += 1
        norm_gold.append((event_item, gold_name, gold_type, gold_start, gold_end))

    used_gold_indices: Set[int] = set()
    tp = 0

    for pred_item, pred_name, pred_type, pred_start, pred_end in norm_pred:
        best_match_index = None
        best_score = -1
        for gold_index, (_, gold_name, gold_type, gold_start, gold_end) in enumerate(norm_gold):
            if gold_index in used_gold_indices:
                continue
            if pred_type != gold_type or not pred_type:
                continue
            time_ok = _ranges_match_with_tolerance(pred_start, pred_end, gold_start, gold_end, tolerance_days)
            if not time_ok:
                continue
            name_ok = True
            if pred_name and gold_name:
                name_ok = pred_name == gold_name
            score = 1
            if name_ok and pred_name and gold_name:
                score += 1
            if score > best_score:
                best_score = score
                best_match_index = gold_index

        if best_match_index is not None:
            used_gold_indices.add(best_match_index)
            tp += 1
            error_breakdown["matched"] += 1
            continue

        # 无匹配时做粗分类
        has_type_match = any(pred_type == gold_type and pred_type for _, _, gold_type, _, _ in norm_gold)
        if not has_type_match:
            error_breakdown["type_mismatch"] += 1
        else:
            # type 匹配但 time/name 不匹配
            type_candidates = [g for g in norm_gold if g[2] == pred_type]
            time_candidates = []
            for _, gold_name, _, gold_start, gold_end in type_candidates:
                if _ranges_match_with_tolerance(pred_start, pred_end, gold_start, gold_end, tolerance_days):
                    time_candidates.append(gold_name)
            if time_candidates:
                error_breakdown["name_mismatch"] += 1
            else:
                error_breakdown["time_mismatch"] += 1
        error_breakdown["unmatched_pred"] += 1

    error_breakdown["unmatched_gold"] = max(0, len(gold_events) - len(used_gold_indices))
    return tp, error_breakdown


def _load_geo_synonyms(geo_syn_path: Optional[str]) -> Dict[str, str]:
    """
    读取地名同义/上位映射，返回 alias->canonical 映射。
    支持两种格式：
    1) {canonical: [alias1, alias2, ...]}
    2) {alias: canonical}
    """
    if not geo_syn_path:
        return {}
    path = Path(geo_syn_path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    alias_to_canonical: Dict[str, str] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            key_norm = _normalize_text(key)
            if isinstance(value, list):
                alias_to_canonical[key_norm] = key_norm
                for alias in value:
                    alias_to_canonical[_normalize_text(alias)] = key_norm
            else:
                alias_to_canonical[key_norm] = _normalize_text(str(value))
    return alias_to_canonical


def _canonicalize_geo(text: str, alias_to_canonical: Dict[str, str]) -> str:
    if not alias_to_canonical:
        return _normalize_text(text)
    normalized = _normalize_text(text)
    return alias_to_canonical.get(normalized, normalized)


def _fuzzy_entity_match(pred_norm: str, gold_norm: str, threshold: float = 0.7) -> bool:
    """
    模糊实体匹配：
    1. 子串匹配（一方包含另一方）
    2. 字符相似度匹配
    """
    if not pred_norm or not gold_norm:
        return False

    # 子串匹配（长度 >= 2 才允许）
    if len(pred_norm) >= 2 and len(gold_norm) >= 2:
        if pred_norm in gold_norm or gold_norm in pred_norm:
            return True

    # 字符相似度匹配
    from difflib import SequenceMatcher
    ratio = SequenceMatcher(None, pred_norm, gold_norm).ratio()
    return ratio >= threshold


def _entities_match_relaxed(
    pred_entity: str,
    gold_entity: str,
    tolerance_days: int,
    geo_alias_to_canonical: Dict[str, str],
    fuzzy_threshold: float = 0.7,
) -> Tuple[bool, Optional[str]]:
    """
    relaxed 实体等价：
    - 若双方都是日期：允许 ±N 天
    - 否则按 geo 同义/上位归一化后比较
    - 支持子串匹配和模糊匹配
    返回 (是否匹配, mismatch_type)
    """
    pred_date = _parse_iso_date(pred_entity)
    gold_date = _parse_iso_date(gold_entity)
    if pred_date and gold_date:
        if abs((pred_date - gold_date).days) <= max(0, tolerance_days):
            return True, None
        return False, "time_mismatch"

    # 归一化后精确匹配
    pred_geo = _canonicalize_geo(pred_entity, geo_alias_to_canonical)
    gold_geo = _canonicalize_geo(gold_entity, geo_alias_to_canonical)
    if pred_geo == gold_geo:
        return True, None

    # 模糊匹配（子串 + 相似度）
    pred_norm = _normalize_text(pred_entity)
    gold_norm = _normalize_text(gold_entity)
    if _fuzzy_entity_match(pred_norm, gold_norm, fuzzy_threshold):
        return True, None

    if pred_entity or gold_entity:
        return False, "geo_mismatch"
    return False, "other_mismatch"


# =========================
# 指标计算
# =========================
def compute_event_f1(
    predictions: Any,
    gold: Any,
    time_tolerance_days: int = 0,
    use_original_type: bool = False,
) -> Tuple[ExtractionMetrics, Dict[str, int]]:
    """
    计算事件抽取 F1，基于事件名称+类型匹配。
    支持输入 dict 或 list（批量）。
    新口径：在名称/类型一致的基础上加入时间窗容忍。
    返回 (metrics, error_breakdown)。
    """
    pred_records = _ensure_records(predictions, use_original_type=use_original_type)
    gold_records = _ensure_records(gold)

    pred_events = pred_records["events"]
    gold_events = gold_records["events"]

    if not pred_events and not gold_events:
        return _calc_prf(0, 0, 0), {"matched": 0, "unmatched_pred": 0, "unmatched_gold": 0}
    if not pred_events or not gold_events:
        return _calc_prf(0, len(pred_events), len(gold_events)), {
            "matched": 0,
            "unmatched_pred": len(pred_events),
            "unmatched_gold": len(gold_events),
        }

    tp, error_breakdown = _match_events_with_tolerance(pred_events, gold_events, time_tolerance_days)
    metrics = _calc_prf(tp, len(pred_events), len(gold_events))
    return metrics, error_breakdown


def compute_triple_f1(
    predictions: Any,
    gold: Any,
    time_tolerance_days: int = 0,
    geo_synonyms: Optional[str] = None,
) -> Tuple[Dict[str, ExtractionMetrics], Dict[str, int]]:
    """
    计算三元组抽取 F1。
    - strict=True : (s,p,o) 完全一致
    - relaxed     : predicate 一致，subject/object 允许时间±N日、地名同义/上位归一
    返回 ({strict, relaxed}, error_breakdown)，各自包含 precision/recall/f1。
    """
    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)

    pred_triples = pred_records["triples"]
    gold_triples = gold_records["triples"]
    geo_alias_to_canonical = _load_geo_synonyms(geo_synonyms)

    # 严格匹配
    pred_strict = _extract_triple_keys(pred_triples, strict=True)
    gold_strict = _extract_triple_keys(gold_triples, strict=True)

    tp_s = len(pred_strict & gold_strict)
    strict_metrics = _calc_prf(tp_s, len(pred_strict), len(gold_strict))

    error_breakdown: Dict[str, int] = {
        "strict_matched": len(pred_strict & gold_strict),
        "relaxed_matched": 0,
        "predicate_mismatch": 0,
        "geo_mismatch": 0,
        "time_mismatch": 0,
        "other_mismatch": 0,
        "unmatched_pred": 0,
        "unmatched_gold": 0,
    }

    # 宽松匹配：predicate 必须一致，subject/object 允许 relaxed 等价
    used_gold_indices: Set[int] = set()
    for pred_triple in pred_triples:
        pred_predicate = _normalize_text(pred_triple.get("predicate", ""))
        pred_subject = str(pred_triple.get("subject", "") or "")
        pred_object = str(pred_triple.get("object", "") or "")
        if not pred_predicate:
            continue

        matched = False
        mismatch_type = None
        for gold_index, gold_triple in enumerate(gold_triples):
            if gold_index in used_gold_indices:
                continue
            gold_predicate = _normalize_text(gold_triple.get("predicate", ""))
            if pred_predicate != gold_predicate or not gold_predicate:
                continue
            gold_subject = str(gold_triple.get("subject", "") or "")
            gold_object = str(gold_triple.get("object", "") or "")

            subject_ok, subject_mismatch = _entities_match_relaxed(
                pred_subject, gold_subject, time_tolerance_days, geo_alias_to_canonical
            )
            object_ok, object_mismatch = _entities_match_relaxed(
                pred_object, gold_object, time_tolerance_days, geo_alias_to_canonical
            )
            if subject_ok and object_ok:
                matched = True
                used_gold_indices.add(gold_index)
                error_breakdown["relaxed_matched"] += 1
                break
            mismatch_type = subject_mismatch or object_mismatch

        if not matched:
            if mismatch_type == "time_mismatch":
                error_breakdown["time_mismatch"] += 1
            elif mismatch_type == "geo_mismatch":
                error_breakdown["geo_mismatch"] += 1
            elif mismatch_type:
                error_breakdown["other_mismatch"] += 1
            else:
                error_breakdown["predicate_mismatch"] += 1
            error_breakdown["unmatched_pred"] += 1

    error_breakdown["unmatched_gold"] = max(0, len(gold_triples) - len(used_gold_indices))

    tp_relaxed = error_breakdown["relaxed_matched"]
    relaxed_metrics = _calc_prf(tp_relaxed, len(pred_triples), len(gold_triples))

    return {
        "strict": strict_metrics,
        "relaxed": relaxed_metrics,
    }, error_breakdown


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
    has_location = sum(1 for e in events if e.get("location") or e.get("space"))

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

    # 不使用 numpy 的实现
    bin_width = 1.0 / n_bins
    ece = 0.0
    total = len(data)
    bin_stats = []

    for i in range(n_bins):
        bin_lower = i * bin_width
        bin_upper = (i + 1) * bin_width

        # 筛选落入当前 bin 的样本
        bin_samples = [(c, a) for c, a in data if bin_lower < c <= bin_upper]

        if len(bin_samples) > 0:
            avg_conf = sum(c for c, a in bin_samples) / len(bin_samples)
            avg_acc = sum(a for c, a in bin_samples) / len(bin_samples)
            bin_ece = abs(avg_acc - avg_conf) * (len(bin_samples) / total)
            ece += bin_ece
            bin_stats.append({
                "bin_range": f"({bin_lower:.2f}, {bin_upper:.2f}]",
                "count": len(bin_samples),
                "avg_confidence": round(avg_conf, 4),
                "avg_accuracy": round(avg_acc, 4),
                "bin_ece": round(bin_ece, 4),
            })

    return {
        "ece": round(ece, 4),
        "bin_stats": bin_stats,
        "total_samples": total,
    }


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


def _iter_records(obj: Any) -> List[Dict[str, Any]]:
    if isinstance(obj, list):
        return [r for r in obj if isinstance(r, dict)]
    if isinstance(obj, dict):
        return [obj]
    return []


def compute_hallucination_rate(predictions: Any) -> Dict[str, Any]:
    """计算幻觉率：被过滤三元组数 / 原始三元组数（仅当有校验信息时）。"""
    total = 0
    filtered = 0
    has_data = False

    for record in _iter_records(predictions):
        meta = record.get("_meta_hallucination")
        if isinstance(meta, dict) and meta.get("is_filtered") is True:
            orig = meta.get("original_count", 0)
            filt = meta.get("filtered_count", 0)
            if isinstance(orig, int) and isinstance(filt, int) and orig > 0:
                total += orig
                filtered += filt
                has_data = True
                continue

        stats = record.get("stats")
        if isinstance(stats, dict):
            orig = stats.get("total_triples")
            filt = stats.get("filtered_triples")
            if isinstance(orig, int) and isinstance(filt, int) and orig > 0:
                total += orig
                filtered += filt
                has_data = True
                continue

        rate = record.get("hallucination_rate")
        if isinstance(rate, (int, float)):
            triples = record.get("triples", []) or []
            orig = len(triples)
            if orig > 0:
                total += orig
                filtered += int(round(rate * orig))
                has_data = True

    if not has_data:
        return {"hallucination_rate": None, "total": 0, "filtered": 0}
    rate = filtered / total if total > 0 else 0.0
    return {"hallucination_rate": round(rate, 4), "total": total, "filtered": filtered}


def compute_entity_redundancy_rate(predictions: Any) -> Dict[str, Any]:
    """基于三元组实体统计冗余率（重复实体占比）。"""
    pred_records = _ensure_records(predictions)
    triples = pred_records["triples"]
    entities: List[str] = []
    for triple_item in triples:
        if not isinstance(triple_item, dict):
            continue
        subject = triple_item.get("subject", "")
        obj = triple_item.get("object", "")
        if subject:
            entities.append(str(subject))
        if obj:
            entities.append(str(obj))

    total = len(entities)
    unique = len({_normalize_text(e) for e in entities if e})
    redundant = max(0, total - unique)
    rate = redundant / total if total > 0 else 0.0
    return {
        "entity_redundancy_rate": round(rate, 4),
        "total": total,
        "unique": unique,
        "redundant": redundant,
    }


def compute_entity_f1(predictions: Any, gold: Any) -> Tuple[ExtractionMetrics, Dict[str, int]]:
    """
    计算实体抽取 F1。
    从 entities 字段和 triples 的 subject/object 中提取实体，只比较名称。
    """
    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)

    def extract_entities(records: Dict[str, Any]) -> Set[str]:
        entities: Set[str] = set()
        # 从 entities 字段提取
        for e in records.get("entities", []):
            if isinstance(e, dict):
                name = _normalize_text(e.get("name", ""))
                if name:
                    entities.add(name)
        # 从 triples 的 subject/object 提取
        for t in records.get("triples", []):
            if isinstance(t, dict):
                subj = _normalize_text(t.get("subject", ""))
                obj = _normalize_text(t.get("object", ""))
                if subj:
                    entities.add(subj)
                if obj:
                    entities.add(obj)
        return entities

    pred_entities = extract_entities(pred_records)
    gold_entities = extract_entities(gold_records)

    tp = len(pred_entities & gold_entities)
    metrics = _calc_prf(tp, len(pred_entities), len(gold_entities))

    stats = {
        "pred_count": len(pred_entities),
        "gold_count": len(gold_entities),
        "matched": tp,
    }
    return metrics, stats


def compute_relation_f1(predictions: Any, gold: Any) -> Tuple[ExtractionMetrics, Dict[str, int]]:
    """
    计算关系类型抽取 F1。
    只看 predicate 是否正确预测，不考虑 subject/object 的正确性。
    用于评估模型对关系类型的识别能力。
    """
    from collections import Counter

    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)

    pred_relations: Counter = Counter()
    for t in pred_records.get("triples", []):
        if isinstance(t, dict):
            pred = _normalize_text(t.get("predicate", ""))
            if pred:
                pred_relations[pred] += 1

    gold_relations: Counter = Counter()
    for t in gold_records.get("triples", []):
        if isinstance(t, dict):
            pred = _normalize_text(t.get("predicate", ""))
            if pred:
                gold_relations[pred] += 1

    # 计算每种关系的匹配数量（取最小值）
    tp = 0
    for rel in set(pred_relations.keys()) & set(gold_relations.keys()):
        tp += min(pred_relations[rel], gold_relations[rel])

    pred_total = sum(pred_relations.values())
    gold_total = sum(gold_relations.values())

    metrics = _calc_prf(tp, pred_total, gold_total)

    stats = {
        "pred_total": pred_total,
        "gold_total": gold_total,
        "matched": tp,
        "pred_types": len(pred_relations),
        "gold_types": len(gold_relations),
    }
    return metrics, stats


def compute_schema_coverage(predictions: Any, tbox: Dict[str, Any]) -> Dict[str, Any]:
    """
    计算 TBox 中定义的类和关系被使用的比例。
    """
    pred_records = _ensure_records(predictions)

    # TBox 中定义的关系
    defined_relations = {
        _normalize_text(r.get("name", ""))
        for r in tbox.get("relations", [])
        if r.get("name")
    }

    # TBox 中定义的类
    defined_classes = {
        _normalize_text(c.get("name", ""))
        for c in tbox.get("classes", [])
        if c.get("name")
    }

    # 预测中使用的关系
    used_relations: Set[str] = set()
    for t in pred_records.get("triples", []):
        if isinstance(t, dict):
            pred = _normalize_text(t.get("predicate", ""))
            if pred:
                used_relations.add(pred)

    # 预测中使用的类
    used_classes: Set[str] = set()
    for e in pred_records.get("entities", []):
        if isinstance(e, dict):
            etype = _normalize_text(e.get("type", ""))
            if etype:
                used_classes.add(etype)
    # 从 events 中也提取类型
    for ev in pred_records.get("events", []):
        if isinstance(ev, dict):
            etype = _normalize_text(ev.get("event_type", ""))
            if etype:
                used_classes.add(etype)

    # 计算覆盖率
    rel_coverage = len(used_relations & defined_relations) / len(defined_relations) if defined_relations else 0
    cls_coverage = len(used_classes & defined_classes) / len(defined_classes) if defined_classes else 0

    return {
        "relation_coverage": round(rel_coverage, 4),
        "class_coverage": round(cls_coverage, 4),
        "used_relations": len(used_relations & defined_relations),
        "defined_relations": len(defined_relations),
        "used_classes": len(used_classes & defined_classes),
        "defined_classes": len(defined_classes),
    }


def compute_per_relation_metrics(
    predictions: Any, gold: Any
) -> Dict[str, Dict[str, Any]]:
    """
    计算每种关系类型的 P/R/F1，便于分析哪些关系抽取效果好/差。
    """
    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)

    pred_triples = pred_records.get("triples", [])
    gold_triples = gold_records.get("triples", [])

    # 按关系分组
    pred_by_rel: Dict[str, List[Dict]] = {}
    for t in pred_triples:
        if isinstance(t, dict):
            rel = _normalize_text(t.get("predicate", ""))
            if rel:
                pred_by_rel.setdefault(rel, []).append(t)

    gold_by_rel: Dict[str, List[Dict]] = {}
    for t in gold_triples:
        if isinstance(t, dict):
            rel = _normalize_text(t.get("predicate", ""))
            if rel:
                gold_by_rel.setdefault(rel, []).append(t)

    all_relations = set(pred_by_rel.keys()) | set(gold_by_rel.keys())

    results: Dict[str, Dict[str, Any]] = {}
    for rel in all_relations:
        pred_set = _extract_triple_keys(pred_by_rel.get(rel, []), strict=True)
        gold_set = _extract_triple_keys(gold_by_rel.get(rel, []), strict=True)

        tp = len(pred_set & gold_set)
        p = tp / len(pred_set) if pred_set else 0
        r = tp / len(gold_set) if gold_set else 0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0

        results[rel] = {
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
            "pred_count": len(pred_set),
            "gold_count": len(gold_set),
            "matched": tp,
        }

    return results


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


def _filter_by_tbox(record: Dict[str, Any], tbox: Dict[str, Any]) -> Dict[str, Any]:
    """
    过滤掉不在 TBox 中的三元组和实体。
    返回过滤后的记录副本，用于计算 TBox 过滤后的指标。
    保留幻觉统计字段，便于汇总指标。
    """
    valid_relations = {r.get("name") for r in tbox.get("relations", []) if r.get("name")}
    valid_classes = {c.get("name") for c in tbox.get("classes", []) if c.get("name")}

    # 过滤三元组（排除 _invalid_predicate=True 或 predicate 不在 TBox 中的）
    filtered_triples = []
    for t in record.get("triples", []):
        if t.get("_invalid_predicate"):
            continue
        pred = t.get("predicate", "")
        if pred in valid_relations:
            filtered_triples.append(t)

    # 过滤实体（排除 _invalid_type=True 或 type 不在 TBox 中的）
    filtered_entities = []
    for e in record.get("entities", []):
        if e.get("_invalid_type"):
            continue
        etype = e.get("type", "")
        if etype in valid_classes or not etype:  # 允许无类型
            filtered_entities.append(e)

    # 过滤事件（排除 _invalid_event_type=True 或 event_type 不在 TBox 中的）
    filtered_events = []
    for ev in record.get("events", []):
        if ev.get("_invalid_event_type"):
            continue
        etype = ev.get("event_type", "")
        if etype in valid_classes or not etype:
            filtered_events.append(ev)

    filtered_record = {
        "events": filtered_events,
        "triples": filtered_triples,
        "entities": filtered_entities,
    }
    for key in ["_meta_hallucination", "stats", "hallucination_rate"]:
        if key in record:
            filtered_record[key] = record[key]
    return filtered_record


def _load_json_or_jsonl(path: str) -> Any:
    """加载 JSON 或 JSONL 文件。"""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    if file_path.suffix.lower() == ".jsonl":
        items: List[Dict[str, Any]] = []
        for line in file_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                continue
        return items
    return json.loads(file_path.read_text(encoding="utf-8"))


def setup_logger(log_file: Optional[str] = None) -> logging.Logger:
    log_format = "%(asctime)s | %(levelname)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
        force=True,
    )
    return logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ABox 抽取评测（事件/三元组 F1 + TBox 一致性）")
    parser.add_argument("--gold", required=True, help="gold 标注（json/jsonl）")
    parser.add_argument("--pred", required=True, help="pred 预测（json/jsonl）")
    parser.add_argument("--tbox", required=True, help="TBox 路径（json）")
    parser.add_argument("--time-tolerance-days", type=int, default=0, help="时间容忍天数（默认 0）")
    parser.add_argument("--geo-syn", default="", help="地名同义/上位映射 json 文件（可选）")
    parser.add_argument(
        "--use-original-type",
        action="store_true",
        help="使用原始 event_type 进行评测（忽略回退逻辑）",
    )
    parser.add_argument("--out", required=True, help="输出指标 JSON 路径")
    parser.add_argument("--log-file", default="", help="日志文件（可选）")
    return parser.parse_args()


def _compute_aggregated_report(
    preds: List[Dict[str, Any]],
    gold: List[Dict[str, Any]],
    tbox: Dict[str, Any],
    time_tolerance_days: int,
    geo_synonyms: str,
    use_original_type: bool,
) -> Dict[str, Any]:
    """计算聚合报告（内部辅助函数）"""
    pair_count = min(len(gold), len(preds))
    all_metrics = []
    for idx in range(pair_count):
        all_metrics.append(
            compute_full_metrics(
                preds[idx],
                gold[idx],
                tbox,
                time_tolerance_days=time_tolerance_days,
                geo_synonyms=geo_synonyms,
                use_original_type=use_original_type,
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

    return {
        "use_original_type": use_original_type,

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

        # 版本1：原始数据（不剔除）
        logging.info("[ABox] 计算原始指标（raw）...")
        report_raw = _compute_aggregated_report(
            preds[:pair_count],
            gold[:pair_count],
            tbox,
            time_tolerance_days=args.time_tolerance_days,
            geo_synonyms=args.geo_syn,
            use_original_type=args.use_original_type,
        )
        report_raw["version"] = "raw"

        # 版本2：TBox 过滤后
        logging.info("[ABox] 计算 TBox 过滤后指标（tbox_filtered）...")
        gold_filtered = [_filter_by_tbox(g, tbox) for g in gold[:pair_count]]
        preds_filtered = [_filter_by_tbox(p, tbox) for p in preds[:pair_count]]
        report_filtered = _compute_aggregated_report(
            preds_filtered,
            gold_filtered,
            tbox,
            time_tolerance_days=args.time_tolerance_days,
            geo_synonyms=args.geo_syn,
            use_original_type=args.use_original_type,
        )
        report_filtered["version"] = "tbox_filtered"

        # 合并输出
        report = {
            "raw": report_raw,
            "tbox_filtered": report_filtered,
        }
    else:
        # 单条记录模式
        report_raw = compute_full_metrics(
            preds,
            gold,
            tbox,
            time_tolerance_days=args.time_tolerance_days,
            geo_synonyms=args.geo_syn,
            use_original_type=args.use_original_type,
        )
        report_raw["version"] = "raw"

        preds_filtered = _filter_by_tbox(preds, tbox)
        gold_filtered = _filter_by_tbox(gold, tbox)
        report_filtered = compute_full_metrics(
            preds_filtered,
            gold_filtered,
            tbox,
            time_tolerance_days=args.time_tolerance_days,
            geo_synonyms=args.geo_syn,
            use_original_type=args.use_original_type,
        )
        report_filtered["version"] = "tbox_filtered"

        report = {
            "raw": report_raw,
            "tbox_filtered": report_filtered,
        }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info(f"[ABox] 指标已保存：{out_path}")


if __name__ == "__main__":
    main()
