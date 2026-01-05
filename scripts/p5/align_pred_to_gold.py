#!/usr/bin/env python3
"""
将预测结果按 gold 的 doc_id 顺序对齐，便于评测时逐条匹配。

使用方式：
    python scripts/p5/align_pred_to_gold.py \
        --gold data/p5_eval_pool/final/test_final.jsonl \
        --pred outputs/p5_small_model_test/p5_batch_results_mapped.jsonl \
        --out outputs/p5_small_model_test/p5_batch_results_aligned.jsonl \
        --report outputs/p5_small_model_test/align_report.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def setup_logger() -> logging.Logger:
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


def load_json_or_jsonl(path: Path) -> List[Dict[str, Any]]:
    """加载 JSON/JSONL 为列表结构。"""
    if path.suffix.lower() == ".jsonl":
        items: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return items
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def pick_doc_id(record: Dict[str, Any]) -> str:
    """优先从常见字段中提取 doc_id。"""
    for key in ("doc_id", "docid", "id", "document_id"):
        value = record.get(key)
        if value not in [None, ""]:
            return str(value)
    meta = record.get("meta") or record.get("_meta") or {}
    if isinstance(meta, dict):
        for key in ("doc_id", "docid", "id", "document_id"):
            value = meta.get(key)
            if value not in [None, ""]:
                return str(value)
    return ""


def build_pred_index(
    preds: List[Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, int]]:
    """构建 pred 的 doc_id 索引，并统计重复 doc_id。"""
    index: Dict[str, Dict[str, Any]] = {}
    duplicates: Dict[str, int] = {}
    for item in preds:
        doc_id = pick_doc_id(item)
        if not doc_id:
            continue
        if doc_id in index:
            duplicates[doc_id] = duplicates.get(doc_id, 1) + 1
            continue
        index[doc_id] = item
    return index, duplicates


def build_empty_pred(doc_id: str) -> Dict[str, Any]:
    """构建空预测，用于缺失的 doc_id。"""
    return {"doc_id": doc_id, "events": [], "triples": []}


def align_predictions(
    gold: List[Dict[str, Any]],
    preds: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """按 gold 顺序对齐 pred，缺失项补空。"""
    pred_index, duplicates = build_pred_index(preds)
    gold_doc_ids: List[str] = []
    aligned: List[Dict[str, Any]] = []
    missing_doc_ids: List[str] = []

    for idx, gold_item in enumerate(gold):
        doc_id = pick_doc_id(gold_item)
        if not doc_id:
            doc_id = f"index_{idx}"
        gold_doc_ids.append(doc_id)
        pred_item = pred_index.get(doc_id)
        if pred_item is None:
            missing_doc_ids.append(doc_id)
            pred_item = build_empty_pred(doc_id)
        else:
            pred_item = dict(pred_item)
            pred_item["doc_id"] = doc_id
        aligned.append(pred_item)

    gold_doc_id_set = set(gold_doc_ids)
    extra_doc_ids = [doc_id for doc_id in pred_index.keys() if doc_id not in gold_doc_id_set]

    report = {
        "gold_count": len(gold),
        "pred_count": len(preds),
        "aligned_count": len(aligned),
        "matched_count": len(aligned) - len(missing_doc_ids),
        "missing_count": len(missing_doc_ids),
        "extra_count": len(extra_doc_ids),
        "duplicate_pred_doc_ids": duplicates,
        "missing_doc_ids": missing_doc_ids,
        "extra_doc_ids": extra_doc_ids,
    }
    return aligned, report


def main() -> None:
    parser = argparse.ArgumentParser(description="按 gold 的 doc_id 对齐 pred 顺序")
    parser.add_argument("--gold", required=True, help="gold 文件（json/jsonl）")
    parser.add_argument("--pred", required=True, help="pred 文件（json/jsonl）")
    parser.add_argument("--out", required=True, help="对齐后的输出（jsonl）")
    parser.add_argument("--report", default="", help="对齐报告输出路径（json，可选）")
    args = parser.parse_args()

    logger = setup_logger()

    gold_path = Path(args.gold)
    pred_path = Path(args.pred)
    out_path = Path(args.out)
    report_path = Path(args.report) if args.report else out_path.with_suffix(".align_report.json")

    if not gold_path.exists():
        logger.error(f"[ERROR] gold 文件不存在: {gold_path}")
        return
    if not pred_path.exists():
        logger.error(f"[ERROR] pred 文件不存在: {pred_path}")
        return

    gold = load_json_or_jsonl(gold_path)
    preds = load_json_or_jsonl(pred_path)
    if not gold:
        logger.error("[ERROR] gold 为空，无法对齐")
        return

    aligned, report = align_predictions(gold, preds)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for item in aligned:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"[ALIGN] 输出: {out_path}")
    logger.info(f"[ALIGN] 报告: {report_path}")
    logger.info(
        "[ALIGN] gold=%d pred=%d matched=%d missing=%d extra=%d",
        report["gold_count"],
        report["pred_count"],
        report["matched_count"],
        report["missing_count"],
        report["extra_count"],
    )


if __name__ == "__main__":
    main()
