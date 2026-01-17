"""
评测模块

集成对齐和指标计算功能。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .utils import load_jsonl, pick_doc_id, normalize_text, compute_f1

logger = logging.getLogger(__name__)


def setup_logger() -> logging.Logger:
    """设置日志"""
    log_format = "%(asctime)s | %(levelname)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    return logging.getLogger(__name__)


def align_predictions(
    gold: List[Dict[str, Any]],
    preds: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """按 gold 顺序对齐预测结果
    
    Args:
        gold: gold 标注列表
        preds: 预测结果列表
    
    Returns:
        (对齐后的预测列表, 对齐报告)
    """
    # 构建预测索引
    pred_index = {}
    for item in preds:
        doc_id = pick_doc_id(item)
        if doc_id and doc_id not in pred_index:
            pred_index[doc_id] = item
    
    # 对齐
    aligned = []
    missing_doc_ids = []
    
    for idx, gold_item in enumerate(gold):
        doc_id = pick_doc_id(gold_item) or f"index_{idx}"
        
        pred_item = pred_index.get(doc_id)
        if pred_item is None:
            missing_doc_ids.append(doc_id)
            pred_item = {"doc_id": doc_id, "events": [], "triples": [], "entities": []}
        else:
            pred_item = dict(pred_item)
            pred_item["doc_id"] = doc_id
        
        aligned.append(pred_item)
    
    # 统计
    gold_doc_ids = set(pick_doc_id(g) or f"index_{i}" for i, g in enumerate(gold))
    extra_doc_ids = [doc_id for doc_id in pred_index.keys() if doc_id not in gold_doc_ids]
    
    report = {
        "gold_count": len(gold),
        "pred_count": len(preds),
        "aligned_count": len(aligned),
        "matched_count": len(aligned) - len(missing_doc_ids),
        "missing_count": len(missing_doc_ids),
        "extra_count": len(extra_doc_ids),
        "missing_doc_ids": missing_doc_ids[:10],
        "extra_doc_ids": extra_doc_ids[:10],
    }
    
    return aligned, report


def _flatten_entities(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """展开实体格式，兼容分组与扁平结构"""
    flattened: List[Dict[str, Any]] = []
    for item in entities:
        if not isinstance(item, dict):
            continue
        if "name" in item and "type" in item:
            name = str(item.get("name", "")).strip()
            etype = str(item.get("type", "")).strip()
            if name:
                flattened.append({"name": name, "type": etype})
            continue
        for etype, values in item.items():
            if isinstance(values, list):
                for value in values:
                    name = str(value).strip()
                    if name:
                        flattened.append({"name": name, "type": str(etype)})
            elif values:
                name = str(values).strip()
                if name:
                    flattened.append({"name": name, "type": str(etype)})
    return flattened


def compute_entity_f1(
    pred_entities: List[Dict[str, Any]],
    gold_entities: List[Dict[str, Any]],
) -> Dict[str, float]:
    """计算实体 F1"""
    pred_entities = _flatten_entities(pred_entities)
    gold_entities = _flatten_entities(gold_entities)

    pred_set = set()
    for e in pred_entities:
        name = normalize_text(e.get("name", ""))
        etype = normalize_text(e.get("type", ""))
        if name:
            pred_set.add((name, etype))
    
    gold_set = set()
    for e in gold_entities:
        name = normalize_text(e.get("name", ""))
        etype = normalize_text(e.get("type", ""))
        if name:
            gold_set.add((name, etype))
    
    tp = len(pred_set & gold_set)
    precision = tp / len(pred_set) if pred_set else 0
    recall = tp / len(gold_set) if gold_set else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "pred_count": len(pred_set),
        "gold_count": len(gold_set),
        "matched": tp,
    }


def compute_triple_f1(
    pred_triples: List[Dict[str, Any]],
    gold_triples: List[Dict[str, Any]],
    strict: bool = True,
) -> Dict[str, float]:
    """计算三元组 F1
    
    Args:
        pred_triples: 预测三元组
        gold_triples: gold 三元组
        strict: 是否严格匹配
    
    Returns:
        指标字典
    """
    def extract_key(t: Dict[str, Any]) -> Tuple[str, str, str]:
        s = normalize_text(t.get("subject", ""))
        p = normalize_text(t.get("predicate", ""))
        o = normalize_text(t.get("object", ""))
        return (s, p, o)
    
    pred_set = set(extract_key(t) for t in pred_triples if extract_key(t)[1])
    gold_set = set(extract_key(t) for t in gold_triples if extract_key(t)[1])
    
    if strict:
        tp = len(pred_set & gold_set)
    else:
        # 宽松匹配：predicate 相同，subject/object 允许子串匹配
        tp = 0
        used_gold = set()
        for pred_key in pred_set:
            for gold_key in gold_set:
                if gold_key in used_gold:
                    continue
                if pred_key[1] != gold_key[1]:
                    continue
                # 检查 subject 和 object
                s_match = pred_key[0] == gold_key[0] or pred_key[0] in gold_key[0] or gold_key[0] in pred_key[0]
                o_match = pred_key[2] == gold_key[2] or pred_key[2] in gold_key[2] or gold_key[2] in pred_key[2]
                if s_match and o_match:
                    tp += 1
                    used_gold.add(gold_key)
                    break
    
    precision = tp / len(pred_set) if pred_set else 0
    recall = tp / len(gold_set) if gold_set else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "pred_count": len(pred_set),
        "gold_count": len(gold_set),
        "matched": tp,
    }


def compute_event_f1(
    pred_events: List[Dict[str, Any]],
    gold_events: List[Dict[str, Any]],
) -> Dict[str, float]:
    """计算事件 F1"""
    def extract_key(e: Dict[str, Any]) -> str:
        name = normalize_text(e.get("name", "") or e.get("event_type", ""))
        etype = normalize_text(e.get("event_type", ""))
        return f"{name}_{etype}"
    
    pred_set = set(extract_key(e) for e in pred_events if extract_key(e).strip("_"))
    gold_set = set(extract_key(e) for e in gold_events if extract_key(e).strip("_"))
    
    tp = len(pred_set & gold_set)
    precision = tp / len(pred_set) if pred_set else 0
    recall = tp / len(gold_set) if gold_set else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "pred_count": len(pred_set),
        "gold_count": len(gold_set),
        "matched": tp,
    }


def evaluate(
    gold_path: Path,
    pred_path: Path,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """运行评测
    
    Args:
        gold_path: gold 文件路径
        pred_path: 预测文件路径
        output_path: 输出报告路径
    
    Returns:
        评测结果
    """
    logger.info(f"加载 gold: {gold_path}")
    gold = load_jsonl(gold_path)
    logger.info(f"加载 pred: {pred_path}")
    preds = load_jsonl(pred_path)
    
    # 对齐
    aligned, align_report = align_predictions(gold, preds)
    logger.info(
        f"对齐: gold={align_report['gold_count']}, pred={align_report['pred_count']}, "
        f"matched={align_report['matched_count']}, missing={align_report['missing_count']}"
    )
    
    # 汇总所有实体、三元组、事件
    all_pred_entities = []
    all_gold_entities = []
    all_pred_triples = []
    all_gold_triples = []
    all_pred_events = []
    all_gold_events = []
    
    for pred_item, gold_item in zip(aligned, gold):
        all_pred_entities.extend(pred_item.get("entities", []))
        all_gold_entities.extend(gold_item.get("entities", []) or gold_item.get("gold_entities", []))
        
        all_pred_triples.extend(pred_item.get("triples", []))
        all_gold_triples.extend(gold_item.get("triples", []) or gold_item.get("gold_triples", []))
        
        all_pred_events.extend(pred_item.get("events", []))
        all_gold_events.extend(gold_item.get("events", []) or gold_item.get("gold_events", []))
    
    # 计算指标
    entity_metrics = compute_entity_f1(all_pred_entities, all_gold_entities)
    triple_strict = compute_triple_f1(all_pred_triples, all_gold_triples, strict=True)
    triple_relaxed = compute_triple_f1(all_pred_triples, all_gold_triples, strict=False)
    event_metrics = compute_event_f1(all_pred_events, all_gold_events)
    
    # 汇总结果
    results = {
        "align_report": align_report,
        "entity_f1": entity_metrics,
        "triple_f1_strict": triple_strict,
        "triple_f1_relaxed": triple_relaxed,
        "event_f1": event_metrics,
        "summary": {
            "entity_f1": entity_metrics["f1"],
            "triple_f1_strict": triple_strict["f1"],
            "triple_f1_relaxed": triple_relaxed["f1"],
            "event_f1": event_metrics["f1"],
        },
    }
    
    # 保存结果
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"评测结果已保存: {output_path}")
    
    # 打印结果
    logger.info("=" * 60)
    logger.info("评测结果")
    logger.info("=" * 60)
    logger.info(f"Entity F1:        {entity_metrics['f1']:.4f} (P={entity_metrics['precision']:.4f}, R={entity_metrics['recall']:.4f})")
    logger.info(f"Triple F1 (S):    {triple_strict['f1']:.4f} (P={triple_strict['precision']:.4f}, R={triple_strict['recall']:.4f})")
    logger.info(f"Triple F1 (R):    {triple_relaxed['f1']:.4f} (P={triple_relaxed['precision']:.4f}, R={triple_relaxed['recall']:.4f})")
    logger.info(f"Event F1:         {event_metrics['f1']:.4f} (P={event_metrics['precision']:.4f}, R={event_metrics['recall']:.4f})")
    
    return results


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="YAYI-UIE 评测")
    parser.add_argument("--gold", "-g", required=True, help="gold 文件路径")
    parser.add_argument("--pred", "-p", required=True, help="预测文件路径")
    parser.add_argument("--output", "-o", default=None, help="输出报告路径")
    
    args = parser.parse_args()
    setup_logger()
    
    output_path = Path(args.output) if args.output else None
    evaluate(Path(args.gold), Path(args.pred), output_path)


if __name__ == "__main__":
    main()
