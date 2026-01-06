#!/usr/bin/env python3
"""
UIE 基线抽取：基于 TBox 关系构造 schema，输出 P5 风格 events/triples。

说明：
- 使用 PaddleNLP PP-UIE 模型（paddlenlp.Taskflow）。
- 按 doc_id 流式写入 JSONL，避免中断丢结果。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from paddlenlp import Taskflow
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def setup_logger(log_file: str | None = None) -> logging.Logger:
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


def load_test_samples(test_file: Path) -> List[Dict[str, Any]]:
    samples = []
    with test_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return samples


def _build_event_candidates(classes: List[Dict[str, Any]]) -> Tuple[List[Tuple[str, str]], str]:
    """构建事件类型关键词列表与默认回退类型。"""
    keywords: List[Tuple[str, str]] = []
    fallback_type = ""

    for c in classes:
        name = c.get("name", "")
        cn_name = c.get("cn_name", "")
        if name == "DisasterEvent":
            fallback_type = name
        if not name:
            continue
        if name.endswith("Event") or ("事件" in cn_name):
            if cn_name:
                keywords.append((cn_name, name))
                if cn_name.endswith("事件"):
                    keywords.append((cn_name[:-2], name))
            if name.endswith("Event"):
                keywords.append((name[:-5], name))

    if not fallback_type:
        for c in classes:
            if c.get("name"):
                fallback_type = c.get("name")
                break

    keywords = sorted(
        [(k, v) for k, v in keywords if k],
        key=lambda x: len(x[0]),
        reverse=True,
    )
    return keywords, fallback_type


def load_tbox_config(tbox_path: Path) -> Tuple[str, List[str], Dict[str, str], Dict[str, str], List[Tuple[str, str]], str]:
    """加载 TBox，构建 UIE schema 与映射关系。"""
    tbox = json.loads(tbox_path.read_text(encoding="utf-8"))
    relations = tbox.get("relations", []) or []
    classes = tbox.get("classes", []) or []

    relation_labels: List[str] = []
    label_to_relation: Dict[str, str] = {}
    for rel in relations:
        rel_name = rel.get("name", "")
        rel_label = rel.get("cn_name") or rel_name
        if not rel_label:
            continue
        if rel_label in label_to_relation and label_to_relation[rel_label] != rel_name:
            logging.warning(f"[UIE] 关系标签冲突: {rel_label} -> {label_to_relation[rel_label]} / {rel_name}")
            continue
        label_to_relation[rel_label] = rel_name or rel_label
        relation_labels.append(rel_label)

    label_to_event_type: Dict[str, str] = {}
    event_label = "灾害事件"
    for c in classes:
        name = c.get("name", "")
        cn_name = c.get("cn_name", "")
        if cn_name and name:
            label_to_event_type[cn_name] = name
        if name == "DisasterEvent" and cn_name:
            event_label = cn_name

    event_keywords, fallback_type = _build_event_candidates(classes)
    return event_label, relation_labels, label_to_relation, label_to_event_type, event_keywords, fallback_type


def guess_event_type(text: str, keywords: List[Tuple[str, str]], fallback_type: str) -> str:
    for kw, etype in keywords:
        if kw and kw in text:
            return etype
    return fallback_type


def build_event_record(name: str, event_type: str) -> Dict[str, Any]:
    return {
        "event_id": "",
        "event_type": event_type,
        "original_event_type": event_type,
        "name": name,
        "source": "",
        "time": {"start_time": "", "end_time": ""},
        "space": {"main_stream": [], "tributaries": [], "provinces": []},
        "causes": [],
        "impacts": {"affected_population": "", "deaths": "", "direct_economic_loss": ""},
        "responses": [],
    }


def parse_uie_output(
    output: Any,
    default_label: str,
    label_to_relation: Dict[str, str],
    label_to_event_type: Dict[str, str],
    event_keywords: List[Tuple[str, str]],
    fallback_type: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    events: List[Dict[str, Any]] = []
    triples: List[Dict[str, Any]] = []
    seen_events = set()
    seen_triples = set()

    def add_event(subject_text: str, event_type: str) -> None:
        key = (subject_text, event_type)
        if key in seen_events:
            return
        events.append(build_event_record(subject_text, event_type))
        seen_events.add(key)

    def add_triple(subject_text: str, predicate_label: str, object_text: str) -> None:
        predicate = label_to_relation.get(predicate_label, predicate_label)
        key = (subject_text, predicate, object_text)
        if key in seen_triples:
            return
        triples.append(
            {
                "subject": subject_text,
                "predicate": predicate,
                "object": object_text,
                "event_id": "",
                "evidence": "",
            }
        )
        seen_triples.add(key)

    def handle_subject(item: Dict[str, Any], schema_label: str) -> None:
        subject_text = str(item.get("text", "") or "")
        if not subject_text:
            return
        event_type = label_to_event_type.get(schema_label)
        if not event_type:
            event_type = guess_event_type(subject_text, event_keywords, fallback_type)
        add_event(subject_text, event_type)

        relations = item.get("relations", {}) if isinstance(item.get("relations", {}), dict) else {}
        for rel_label, rel_items in relations.items():
            if not isinstance(rel_items, list):
                continue
            for rel_obj in rel_items:
                if not isinstance(rel_obj, dict):
                    continue
                obj_text = str(rel_obj.get("text", "") or "")
                if not obj_text:
                    continue
                add_triple(subject_text, rel_label, obj_text)

    if isinstance(output, dict):
        for label, items in output.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    handle_subject(item, label)
        return events, triples

    if isinstance(output, list):
        for item in output:
            if isinstance(item, dict):
                handle_subject(item, default_label)
        return events, triples

    return events, triples


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="UIE Baseline 抽取（基于 TBox schema）")
    parser.add_argument("--model-name", default="paddlenlp/PP-UIE-0.5B", help="PP-UIE 模型名称 (paddlenlp/PP-UIE-0.5B, 1.5B, 7B, 14B)")
    parser.add_argument("--tbox", required=True, help="TBox 路径（json）")
    parser.add_argument("--test-file", required=True, help="测试集文件（jsonl）")
    parser.add_argument("--output", "-o", required=True, help="输出预测文件（jsonl）")
    parser.add_argument("--limit", type=int, default=None, help="最多处理样本数")
    parser.add_argument("--skip-existing", action="store_true", help="跳过已存在的 doc_id")
    parser.add_argument("--precision", default="float16", help="模型精度 (float16/bfloat16/float32)")
    parser.add_argument("--batch-size", type=int, default=1, help="批处理大小")
    parser.add_argument("--interval", type=float, default=0.0, help="请求间隔秒数")
    parser.add_argument("--log-file", default="", help="日志文件（可选）")
    parser.add_argument("--text-source", type=str, default=None,
        help="完整文本来源文件（可选，通过 doc_id/id 映射获取完整文本）")
    return parser.parse_args()


def main() -> None:
    if load_dotenv:
        load_dotenv()
    args = parse_args()
    logger = setup_logger(args.log_file or None)

    tbox_path = Path(args.tbox)
    test_path = Path(args.test_file)
    output_path = Path(args.output)

    if not tbox_path.exists():
        logger.error(f"TBox 文件不存在: {tbox_path}")
        return
    if not test_path.exists():
        logger.error(f"测试集文件不存在: {test_path}")
        return

    event_label, relation_labels, label_to_relation, label_to_event_type, event_keywords, fallback_type = load_tbox_config(tbox_path)
    schema = {event_label: relation_labels}

    logger.info(f"UIE Schema: subject={event_label}, relations={len(relation_labels)}")
    logger.info(f"事件回退类型: {fallback_type}")
    logger.info(f"模型: {args.model_name}, 精度: {args.precision}, 批大小: {args.batch_size}")

    ie = Taskflow(
        'information_extraction',
        schema=schema,
        schema_lang="zh",
        batch_size=args.batch_size,
        model=args.model_name,
        precision=args.precision
    )

    samples = load_test_samples(test_path)
    if args.limit:
        samples = samples[:args.limit]
    logger.info(f"样本数: {len(samples)}")

    # 加载完整文本映射（如果指定了 --text-source）
    text_lookup: Dict[str, str] = {}
    if args.text_source:
        text_source_path = Path(args.text_source)
        if text_source_path.exists():
            logger.info(f"加载完整文本来源: {args.text_source}")
            with open(text_source_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            d = json.loads(line)
                            tid = d.get("id", d.get("doc_id", ""))
                            if tid:
                                text_lookup[tid] = d.get("text", "")
                        except json.JSONDecodeError:
                            continue
            logger.info(f"已加载 {len(text_lookup)} 条完整文本")
        else:
            logger.warning(f"文本来源文件不存在: {args.text_source}，将使用输入文件中的文本")

    existing_predictions: Dict[str, Dict[str, Any]] = {}
    if args.skip_existing and output_path.exists():
        for line in output_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                doc_id = obj.get("doc_id", "")
                if doc_id:
                    existing_predictions[doc_id] = obj
            except Exception:
                continue
        logger.info(f"已有预测: {len(existing_predictions)} 条")

    write_mode = "a" if args.skip_existing and output_path.exists() else "w"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open(write_mode, encoding="utf-8") as out_f:
        for idx, sample in enumerate(samples, start=1):
            doc_id = sample.get("doc_id", f"sample_{idx}")
            # 优先使用完整文本映射，其次使用输入文件中的文本
            source_text = text_lookup.get(doc_id) or sample.get("source_text", "")
            if doc_id in existing_predictions:
                logger.info(f"[{idx}/{len(samples)}] {doc_id}: 跳过已存在")
                continue
            if not source_text:
                logger.warning(f"[{idx}/{len(samples)}] {doc_id}: 无 source_text")
                out_f.write(json.dumps({"doc_id": doc_id, "events": [], "triples": [], "error": "empty_source_text"}, ensure_ascii=False) + "\n")
                out_f.flush()
                continue

            try:
                result = ie(source_text)
                if isinstance(result, list) and len(result) > 0:
                    result = result[0]
            except Exception as e:
                logger.warning(f"[{idx}/{len(samples)}] {doc_id}: 推理失败 - {e}")
                out_f.write(json.dumps({"doc_id": doc_id, "events": [], "triples": [], "error": str(e)}, ensure_ascii=False) + "\n")
                out_f.flush()
                continue

            events, triples = parse_uie_output(
                result,
                default_label=event_label,
                label_to_relation=label_to_relation,
                label_to_event_type=label_to_event_type,
                event_keywords=event_keywords,
                fallback_type=fallback_type,
            )

            record = {
                "doc_id": doc_id,
                "events": events,
                "triples": triples,
                "baseline": "uie",
                "schema_label": event_label,
            }
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_f.flush()
            logger.info(f"[{idx}/{len(samples)}] {doc_id}: 事件 {len(events)}, 三元组 {len(triples)}")

            if args.interval > 0 and idx < len(samples):
                time.sleep(args.interval)


if __name__ == "__main__":
    main()
