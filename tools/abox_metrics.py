"""
ABox 抽取质量评估：事件 F1、三元组 F1（严格/宽松）、TBox 一致性。
设计要点：
- 兼容单条样本与批量列表两种输入；批量场景下先扁平化再计算。
- 文本做统一归一化（去空格/标点、转小写），降低微小差异的影响。
- 严格匹配要求 (subject, predicate, object) 全部一致，宽松匹配只要求
  predicate 一致且 subject/object 任一命中，用于更宽容的对比。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Set
import re


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
    text = re.sub(r"\s+", "", str(text))
    text = re.sub(r"[，。、“”‘’：；（）【】《》/\\-]", "", text)
    return text.lower()


def _ensure_records(obj: Any) -> Dict[str, List[Dict[str, Any]]]:
    """
    将输入统一转换为 {events: [...], triples: [...]} 结构。
    - 若 obj 是 dict，直接返回其中 events/triples 字段（不存在则空列表）。
    - 若 obj 是 list，假定列表元素为 dict，分别汇总 events/triples。
    """
    if isinstance(obj, dict):
        return {
            "events": obj.get("events", []) or obj.get("gold_events", []) or [],
            "triples": obj.get("triples", []) or obj.get("gold_triples", []) or [],
        }
    if isinstance(obj, list):
        events, triples = [], []
        for item in obj:
            if not isinstance(item, dict):
                continue
            e = item.get("events", []) or item.get("gold_events", []) or []
            t = item.get("triples", []) or item.get("gold_triples", []) or []
            events.extend(e)
            triples.extend(t)
        return {"events": events, "triples": triples}
    return {"events": [], "triples": []}


def _extract_event_keys(events: List[Dict[str, Any]]) -> Set[str]:
    """
    为事件生成匹配 key，默认使用 name+type（都做归一化）。
    如有需要可扩展加入 time/location 作为补充。
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


# =========================
# 指标计算
# =========================
def compute_event_f1(predictions: Any, gold: Any) -> float:
    """
    计算事件抽取 F1，基于事件名称+类型匹配。
    支持输入 dict 或 list（批量）。
    """
    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)

    pred_keys = _extract_event_keys(pred_records["events"])
    gold_keys = _extract_event_keys(gold_records["events"])

    if not pred_keys and not gold_keys:
        return 1.0
    if not pred_keys or not gold_keys:
        return 0.0

    tp = len(pred_keys & gold_keys)
    precision = tp / len(pred_keys) if pred_keys else 0.0
    recall = tp / len(gold_keys) if gold_keys else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return round(f1, 4)


def compute_triple_f1(predictions: Any, gold: Any, strict: bool = True) -> Dict[str, float]:
    """
    计算三元组抽取 F1。
    - strict=True : (s,p,o) 完全一致
    - strict=False: predicate 一致且 subject/object 任一一致
    返回同时包含严格/宽松两种得分，便于一次调用。
    """
    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)

    pred_triples = pred_records["triples"]
    gold_triples = gold_records["triples"]

    # 严格匹配
    pred_strict = _extract_triple_keys(pred_triples, strict=True)
    gold_strict = _extract_triple_keys(gold_triples, strict=True)

    if not pred_strict and not gold_strict:
        f1_strict = 1.0
    elif not pred_strict or not gold_strict:
        f1_strict = 0.0
    else:
        tp_s = len(pred_strict & gold_strict)
        p_s = tp_s / len(pred_strict) if pred_strict else 0.0
        r_s = tp_s / len(gold_strict) if gold_strict else 0.0
        f1_strict = 2 * p_s * r_s / (p_s + r_s) if (p_s + r_s) > 0 else 0.0

    # 宽松匹配：predicate 必须一致，subject 或 object 任一一致即可
    tp_relaxed = 0
    for pt in pred_triples:
        p_pred = _normalize_text(pt.get("predicate", ""))
        s_pred = _normalize_text(pt.get("subject", ""))
        o_pred = _normalize_text(pt.get("object", ""))
        for gt in gold_triples:
            p_gold = _normalize_text(gt.get("predicate", ""))
            s_gold = _normalize_text(gt.get("subject", ""))
            o_gold = _normalize_text(gt.get("object", ""))
            if p_pred == p_gold and (s_pred == s_gold or o_pred == o_gold):
                tp_relaxed += 1
                break

    p_r = tp_relaxed / len(pred_triples) if pred_triples else 0.0
    r_r = tp_relaxed / len(gold_triples) if gold_triples else 0.0
    f1_relaxed = 2 * p_r * r_r / (p_r + r_r) if (p_r + r_r) > 0 else 0.0

    return {
        "strict": round(f1_strict, 4),
        "relaxed": round(f1_relaxed, 4),
    }


def compute_tbox_consistency(predictions: Any, tbox: Dict[str, Any]) -> float:
    """
    计算三元组与 TBox 的一致率：predicate 是否在 TBox 定义中。
    """
    pred_records = _ensure_records(predictions)
    triples = pred_records["triples"]
    if not triples:
        return 1.0

    valid_predicates = {
        _normalize_text(r.get("name", ""))
        for r in tbox.get("relations", [])
        if r.get("name")
    }
    if not valid_predicates:
        return 0.0

    consistent = sum(
        1 for t in triples if _normalize_text(t.get("predicate", "")) in valid_predicates
    )
    return round(consistent / len(triples), 4)


def compute_full_metrics(predictions: Any, gold: Any, tbox: Dict[str, Any]) -> Dict[str, Any]:
    """
    一次性返回全量指标，便于实验脚本直接调用。
    返回字段：
        - event_f1
        - triple_f1_strict / triple_f1_relaxed
        - tbox_consistency
        - 预测/标注的事件、三元组数量
    """
    event_f1 = compute_event_f1(predictions, gold)
    triple_f1 = compute_triple_f1(predictions, gold)
    tbox_consist = compute_tbox_consistency(predictions, tbox)

    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)

    return {
        "event_f1": event_f1,
        "triple_f1_strict": triple_f1["strict"],
        "triple_f1_relaxed": triple_f1["relaxed"],
        "tbox_consistency": tbox_consist,
        "num_pred_events": len(pred_records["events"]),
        "num_gold_events": len(gold_records["events"]),
        "num_pred_triples": len(pred_records["triples"]),
        "num_gold_triples": len(gold_records["triples"]),
    }
