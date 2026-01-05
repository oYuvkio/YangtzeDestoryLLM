#!/usr/bin/env python3
"""
在测试集上运行 P5 抽取，用于模型对比评测。

从 test_final.jsonl 读取 source_text + doc_id，调用 LLM 抽取事件/三元组，
输出带 doc_id 的预测结果，便于后续与 gold 对齐和指标计算。

使用方式：
    # 使用默认配置
    python scripts/p5/run_extraction_on_test.py

    # 指定模型
    python scripts/p5/run_extraction_on_test.py \
        --model "gpt-4o-mini" \
        --output outputs/eval_models/gpt4o_mini/predictions.jsonl

    # 小批量测试
    python scripts/p5/run_extraction_on_test.py --limit 10
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from kg.cq_pipeline import (
    CQLLMPipeline,
    TBoxSchema,
    ClassDef,
    RelationDef,
    AttributeDef,
)


def setup_logger(log_file: Optional[str] = None) -> logging.Logger:
    log_format = "%(asctime)s | %(levelname)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
        force=True,
    )
    return logging.getLogger(__name__)


def load_tbox(tbox_path: Path) -> TBoxSchema:
    """从 JSON 文件加载 TBox。"""
    data = json.loads(tbox_path.read_text(encoding="utf-8"))
    return TBoxSchema(
        classes=[ClassDef(**c) for c in data.get("classes", [])],
        relations=[RelationDef(**r) for r in data.get("relations", [])],
        attributes=[AttributeDef(**a) for a in data.get("attributes", [])],
    )


def load_test_samples(test_file: Path) -> List[Dict[str, Any]]:
    """加载测试集样本。"""
    samples = []
    with open(test_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return samples


def is_quota_error(msg: str) -> bool:
    """检测是否为配额/限流错误。"""
    lower = msg.lower()
    return ("quota" in lower) or ("insufficient" in lower) or ("429" in lower)


def is_error_record(record: Dict[str, Any]) -> bool:
    """判断是否为错误记录。"""
    return bool(record.get("error"))


def main() -> None:
    parser = argparse.ArgumentParser(description="在测试集上运行 P5 抽取")
    parser.add_argument("--cfg", default="configs/cfg.yaml", help="配置文件路径")
    parser.add_argument(
        "--test-file",
        default="data/p5_eval_pool/final/test_final.jsonl",
        help="测试集文件路径",
    )
    parser.add_argument(
        "--tbox",
        default="outputs/cq_pipeline/final/tbox_s2_optimized.json",
        help="TBox 文件路径",
    )
    parser.add_argument("--provider", default=None, help="LLM 提供商（覆盖配置）")
    parser.add_argument("--model", default=None, help="模型名称（覆盖配置）")
    parser.add_argument("--base-url", default=None, help="API base URL（覆盖配置）")
    parser.add_argument("--temperature", type=float, default=None, help="温度参数")
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="输出文件路径（默认 outputs/eval_models/{model}/predictions.jsonl）",
    )
    parser.add_argument("--limit", type=int, default=None, help="最多处理的样本数")
    parser.add_argument("--skip-existing", action="store_true", help="跳过已存在的预测")
    parser.add_argument("--retry-errors", action="store_true", help="重新跑 error 记录（跳过正常记录）")
    parser.add_argument("--interval", type=float, default=1.0, help="请求间隔秒数")
    # 使用互斥组处理 favor-existing-classes
    parser.add_argument("--favor-existing-classes", action="store_true", dest="favor_existing",
                        help="优先使用已有类（保守模式，默认）")
    parser.add_argument("--no-favor-existing-classes", action="store_false", dest="favor_existing",
                        help="允许创建新类")
    parser.set_defaults(favor_existing=True)
    # CoT 开关（默认开启，通过 --no-cot 关闭）
    parser.add_argument("--no-cot", action="store_true",
                        help="禁用思维链 Prompt（用于消融实验，默认开启 CoT）")
    # 后校验开关（默认开启，通过 --no-verify 关闭）
    parser.add_argument("--no-verify", action="store_true",
                        help="禁用原文回溯校验（用于消融实验，默认开启校验）")
    # 完整文本来源
    parser.add_argument("--text-source", type=str, default=None,
                        help="完整文本来源文件（如 pool_v3.jsonl），用 id 字段与输入文件的 doc_id 映射")

    args = parser.parse_args()

    # 逻辑转换：默认都开启，通过 --no-* 关闭
    use_cot = not args.no_cot
    use_verify = not args.no_verify
    logger = setup_logger()

    # 加载配置
    cfg = {}
    if Path(args.cfg).exists():
        try:
            cfg = yaml.safe_load(Path(args.cfg).read_text(encoding="utf-8")) or {}
        except Exception:
            pass

    cfg_llm = cfg.get("llm", {})

    # 解析 LLM 配置
    provider = args.provider or cfg_llm.get("provider", "openai")
    model_name = args.model or cfg_llm.get("model_name", "gpt-4o-mini")
    base_url = args.base_url or cfg_llm.get("base_url")
    temperature = args.temperature if args.temperature is not None else cfg_llm.get("temperature", 0.1)

    # 输出路径
    if args.output:
        output_path = Path(args.output)
    else:
        model_dir_name = model_name.replace("/", "_").replace(":", "_")
        output_path = Path(f"outputs/eval_models/{model_dir_name}/predictions.jsonl")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 加载测试集
    test_file = Path(args.test_file)
    if not test_file.exists():
        logger.error(f"测试集文件不存在: {test_file}")
        return

    samples = load_test_samples(test_file)
    if args.limit:
        samples = samples[:args.limit]

    logger.info(f"测试集样本数: {len(samples)}")

    # 加载完整文本映射（如果指定了 --text-source）
    text_lookup = {}
    if args.text_source:
        text_source_path = Path(args.text_source)
        if text_source_path.exists():
            logger.info(f"加载完整文本来源: {args.text_source}")
            with open(text_source_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            d = json.loads(line)
                            doc_id = d.get("id", d.get("doc_id", ""))
                            if doc_id:
                                text_lookup[doc_id] = d.get("text", "")
                        except json.JSONDecodeError:
                            continue
            logger.info(f"已加载 {len(text_lookup)} 条完整文本")
        else:
            logger.warning(f"文本来源文件不存在: {args.text_source}，将使用输入文件中的文本")

    # 加载 TBox
    tbox_path = Path(args.tbox)
    if not tbox_path.exists():
        logger.error(f"TBox 文件不存在: {tbox_path}")
        return

    tbox = load_tbox(tbox_path)
    logger.info(f"TBox: 类 {len(tbox.classes)}, 关系 {len(tbox.relations)}, 属性 {len(tbox.attributes)}")

    # 初始化 Pipeline
    llm_config = {
        "provider": provider,
        "model_name": model_name,
        "temperature": temperature,
    }
    if base_url:
        llm_config["base_url"] = base_url

    logger.info(
        "LLM 配置: provider=%s, model=%s, temperature=%s, use_cot=%s, use_verify=%s",
        provider,
        model_name,
        temperature,
        use_cot,
        use_verify,
    )

    pipeline = CQLLMPipeline(
        llm_config=llm_config,
        output_dir=str(output_path.parent),
    )

    # 加载已有预测（用于断点续跑 / 重跑错误记录）
    existing_predictions: Dict[str, Dict[str, Any]] = {}
    existing_order: List[str] = []
    error_doc_ids: set[str] = set()
    if (args.skip_existing or args.retry_errors) and output_path.exists():
        seen_doc_ids: set[str] = set()
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    pred = json.loads(line)
                except json.JSONDecodeError:
                    continue
                doc_id = pred.get("doc_id", "")
                if not doc_id:
                    continue
                if doc_id not in seen_doc_ids:
                    existing_order.append(doc_id)
                    seen_doc_ids.add(doc_id)
                existing_predictions[doc_id] = pred
        for doc_id in existing_order:
            record = existing_predictions.get(doc_id, {})
            if is_error_record(record):
                error_doc_ids.add(doc_id)
        logger.info("已有预测: %d 条 (error=%d)", len(existing_predictions), len(error_doc_ids))

    # 运行抽取（流式写文件，避免中断丢失）
    success_count = 0
    skip_count = 0
    error_count = 0
    quota_exhausted = False

    logger.info("=" * 60)
    logger.info("开始抽取")
    logger.info("=" * 60)

    write_mode = "w"
    if args.skip_existing and output_path.exists() and not args.retry_errors:
        write_mode = "a"
    with open(output_path, write_mode, encoding="utf-8") as out_f:
        if args.retry_errors and output_path.exists():
            preserved_count = 0
            for doc_id in existing_order:
                record = existing_predictions.get(doc_id)
                if record and not is_error_record(record):
                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    preserved_count += 1
            out_f.flush()
            logger.info("保留正常记录: %d 条（准备重跑 error 记录）", preserved_count)

        for idx, sample in enumerate(samples, start=1):
            doc_id = sample.get("doc_id", f"sample_{idx}")

            # 获取文本（优先从 text_lookup 获取完整文本）
            if text_lookup and doc_id in text_lookup:
                source_text = text_lookup[doc_id]
            else:
                source_text = sample.get("source_text", "")

            if not source_text:
                logger.warning(f"[{idx}/{len(samples)}] {doc_id}: 无 source_text，跳过")
                error_result = {
                    "doc_id": doc_id,
                    "events": [],
                    "triples": [],
                    "error": "empty_source_text",
                }
                out_f.write(json.dumps(error_result, ensure_ascii=False) + "\n")
                out_f.flush()
                error_count += 1
                continue

            # 跳过已存在的
            if doc_id in existing_predictions and (args.skip_existing or args.retry_errors):
                if args.retry_errors and doc_id in error_doc_ids:
                    logger.info(f"[{idx}/{len(samples)}] {doc_id}: 发现 error 记录，重新抽取")
                else:
                    skip_count += 1
                    logger.info(f"[{idx}/{len(samples)}] {doc_id}: 跳过已存在")
                    continue

            # 执行抽取
            try:
                if use_verify:
                    res = pipeline.extract_events_with_verification(
                        source_text,
                        schema=tbox,
                        save_path=None,
                        favor_existing_classes=args.favor_existing,
                        use_cot=use_cot,
                        strict_filter=True,
                        fuzzy_threshold=0.85,  # 与 Gold 保持一致，确保评测公平
                    )

                    filtered_triples = res.get("filtered_triples", []) or []
                    filtered_with_reason = [
                        {
                            "triple": {k: v for k, v in t.items() if k != "filter_reason"},
                            "reason": t.get("filter_reason", ""),
                        }
                        for t in filtered_triples
                    ]
                    stats = res.get("stats", {}) if isinstance(res.get("stats"), dict) else {}
                    total_triples = stats.get(
                        "total_triples",
                        len(res.get("triples", [])) + len(filtered_triples),
                    )
                    valid_triples = stats.get("valid_triples", len(res.get("triples", [])))
                    filtered_count = stats.get("filtered_triples", len(filtered_triples))
                    rate = res.get("hallucination_rate", 0.0)

                    # 记录幻觉过滤元数据，方便后续案例分析
                    res["_meta_hallucination"] = {
                        "is_filtered": True,
                        "original_count": total_triples,
                        "valid_count": valid_triples,
                        "filtered_count": filtered_count,
                        "rate": rate,
                        "filtered_triples": filtered_with_reason,
                    }

                    event_count = len(res.get("events", []))
                    if filtered_count > 0:
                        logger.info(
                            f"[{idx}/{len(samples)}] {doc_id}: 事件 {event_count}, "
                            f"三元组 {total_triples} → {valid_triples} (幻觉率: {rate:.1%})"
                        )
                    else:
                        logger.info(
                            f"[{idx}/{len(samples)}] {doc_id}: 事件 {event_count}, "
                            f"三元组 {valid_triples} (无幻觉)"
                        )
                else:
                    res = pipeline.extract_events(
                        source_text,
                        schema=tbox,
                        save_path=None,
                        favor_existing_classes=args.favor_existing,
                        use_cot=use_cot,
                    )
                    # 不校验时也记录状态
                    res["_meta_hallucination"] = {"is_filtered": False}
                    event_count = len(res.get("events", []))
                    triple_count = len(res.get("triples", []))
                    logger.info(f"[{idx}/{len(samples)}] {doc_id}: 事件 {event_count}, 三元组 {triple_count} [Raw]")

                res["doc_id"] = doc_id
                res["use_cot"] = use_cot  # 记录是否使用 CoT
                res["use_verify"] = use_verify  # 记录是否使用后校验

                out_f.write(json.dumps(res, ensure_ascii=False) + "\n")
                out_f.flush()
                success_count += 1

            except Exception as e:
                error_msg = str(e)
                error_result = {
                    "doc_id": doc_id,
                    "events": [],
                    "triples": [],
                    "error": error_msg,
                }
                out_f.write(json.dumps(error_result, ensure_ascii=False) + "\n")
                out_f.flush()
                error_count += 1
                logger.error(f"[{idx}/{len(samples)}] {doc_id}: {error_msg}")

                if is_quota_error(error_msg):
                    quota_exhausted = True
                    logger.error("检测到配额/429 错误，停止后续任务")
                    break

            # 间隔
            if args.interval > 0 and idx < len(samples):
                time.sleep(args.interval)

    # 保存元数据
    meta = {
        "timestamp": datetime.now().isoformat(),
        "model": model_name,
        "tbox": str(tbox_path),
        "test_file": str(test_file),
        "total_samples": len(samples),
        "success_count": success_count,
        "skip_count": skip_count,
        "error_count": error_count,
        "quota_exhausted": quota_exhausted,
        "use_cot": use_cot,
        "use_verify": use_verify,
        "retry_errors": args.retry_errors,
        "output": str(output_path),
    }
    meta_path = output_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("=" * 60)
    logger.info("抽取完成")
    logger.info("=" * 60)
    logger.info(f"总样本: {len(samples)}")
    logger.info(f"成功: {success_count}")
    logger.info(f"跳过: {skip_count}")
    logger.info(f"错误: {error_count}")
    logger.info(f"输出: {output_path}")
    logger.info(f"元数据: {meta_path}")


if __name__ == "__main__":
    main()
