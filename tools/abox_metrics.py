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


def _entities_match_relaxed(
    pred_entity: str,
    gold_entity: str,
    tolerance_days: int,
    geo_alias_to_canonical: Dict[str, str],
) -> Tuple[bool, Optional[str]]:
    """
    relaxed 实体等价：
    - 若双方都是日期：允许 ±N 天
    - 否则按 geo 同义/上位归一化后严格比较
    返回 (是否匹配, mismatch_type)
    """
    pred_date = _parse_iso_date(pred_entity)
    gold_date = _parse_iso_date(gold_entity)
    if pred_date and gold_date:
        if abs((pred_date - gold_date).days) <= max(0, tolerance_days):
            return True, None
        return False, "time_mismatch"
    pred_geo = _canonicalize_geo(pred_entity, geo_alias_to_canonical)
    gold_geo = _canonicalize_geo(gold_entity, geo_alias_to_canonical)
    if pred_geo == gold_geo:
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
) -> Tuple[float, Dict[str, int]]:
    """
    计算事件抽取 F1，基于事件名称+类型匹配。
    支持输入 dict 或 list（批量）。
    新口径：在名称/类型一致的基础上加入时间窗容忍。
    返回 (f1, error_breakdown)。
    """
    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)

    pred_events = pred_records["events"]
    gold_events = gold_records["events"]

    if not pred_events and not gold_events:
        return 1.0, {"matched": 0, "unmatched_pred": 0, "unmatched_gold": 0}
    if not pred_events or not gold_events:
        return 0.0, {"matched": 0, "unmatched_pred": len(pred_events), "unmatched_gold": len(gold_events)}

    tp, error_breakdown = _match_events_with_tolerance(pred_events, gold_events, time_tolerance_days)
    precision = tp / len(pred_events) if pred_events else 0.0
    recall = tp / len(gold_events) if gold_events else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return round(f1, 4), error_breakdown


def compute_triple_f1(
    predictions: Any,
    gold: Any,
    time_tolerance_days: int = 0,
    geo_synonyms: Optional[str] = None,
) -> Tuple[Dict[str, float], Dict[str, int]]:
    """
    计算三元组抽取 F1。
    - strict=True : (s,p,o) 完全一致
    - relaxed     : predicate 一致，subject/object 允许时间±N日、地名同义/上位归一
    返回 ({strict, relaxed}, error_breakdown)。
    """
    pred_records = _ensure_records(predictions)
    gold_records = _ensure_records(gold)

    pred_triples = pred_records["triples"]
    gold_triples = gold_records["triples"]
    geo_alias_to_canonical = _load_geo_synonyms(geo_synonyms)

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
    p_r = tp_relaxed / len(pred_triples) if pred_triples else 0.0
    r_r = tp_relaxed / len(gold_triples) if gold_triples else 0.0
    f1_relaxed = 2 * p_r * r_r / (p_r + r_r) if (p_r + r_r) > 0 else 0.0

    return {
        "strict": round(f1_strict, 4),
        "relaxed": round(f1_relaxed, 4),
    }, error_breakdown


def compute_tbox_consistency(
    predictions: Any,
    tbox: Dict[str, Any],
) -> Tuple[float, Dict[str, int]]:
    """
    计算三元组与 TBox 的一致率：
    1) predicate 是否在 TBox 定义中
    2) 可推断 subject/object 类型时，domain/range 是否匹配
    """
    pred_records = _ensure_records(predictions)
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

    # 用 events 推断部分实体类型（event_id 或 name）
    events = pred_records["events"]
    name_to_type: Dict[str, str] = {}
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


def compute_full_metrics(
    predictions: Any,
    gold: Any,
    tbox: Dict[str, Any],
    *,
    time_tolerance_days: int = 0,
    geo_synonyms: Optional[str] = None,
) -> Dict[str, Any]:
    """
    一次性返回全量指标，便于实验脚本直接调用。
    返回字段：
        - event_f1
        - triple_f1_strict / triple_f1_relaxed
        - tbox_consistency
        - 预测/标注的事件、三元组数量
        - error_breakdown
    """
    event_f1, event_errors = compute_event_f1(
        predictions, gold, time_tolerance_days=time_tolerance_days
    )
    triple_f1, triple_errors = compute_triple_f1(
        predictions, gold, time_tolerance_days=time_tolerance_days, geo_synonyms=geo_synonyms
    )
    tbox_consist, tbox_errors = compute_tbox_consistency(predictions, tbox)

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
        "error_breakdown": {
            "events": event_errors,
            "triples": triple_errors,
            "tbox": tbox_errors,
        },
    }


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
    parser.add_argument("--out", required=True, help="输出指标 JSON 路径")
    parser.add_argument("--log-file", default="", help="日志文件（可选）")
    return parser.parse_args()


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
                )
            )
        # 聚合平均
        def mean(values: List[float]) -> float:
            return sum(values) / len(values) if values else 0.0

        # 汇总错误统计（按 key 相加）
        def sum_breakdown(items: List[Dict[str, int]]) -> Dict[str, int]:
            total_counts: Dict[str, int] = {}
            for item in items:
                for key, value in (item or {}).items():
                    total_counts[key] = total_counts.get(key, 0) + int(value)
            return total_counts

        report = {
            "event_f1": round(mean([m["event_f1"] for m in all_metrics]), 4),
            "triple_f1_strict": round(mean([m["triple_f1_strict"] for m in all_metrics]), 4),
            "triple_f1_relaxed": round(mean([m["triple_f1_relaxed"] for m in all_metrics]), 4),
            "tbox_consistency": round(mean([m["tbox_consistency"] for m in all_metrics]), 4),
            "sample_count": pair_count,
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
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info(f"[ABox] 指标已保存：{out_path}")


if __name__ == "__main__":
    main()
