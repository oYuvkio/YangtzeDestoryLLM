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
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# 添加项目根目录到 Python 路径，避免直接运行脚本时找不到 kg 包
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kg.cq_pipeline import (
    CQLLMPipeline,
    TBoxSchema,
    ClassDef,
    RelationDef,
    AttributeDef,
)
from kg.extraction_output import build_extraction_record
from kg.utils.text_source import (
    load_text_lookup,
    resolve_doc_id,
    resolve_source_text,
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


def merge_worker_outputs(args: argparse.Namespace, num_workers: int) -> None:
    """合并多个 worker 的输出文件。"""
    logger = setup_logger()
    
    # 确定输出路径
    if args.output:
        base_output = Path(args.output)
    else:
        model_name = args.model or "unknown"
        model_dir_name = model_name.replace("/", "_").replace(":", "_")
        base_output = Path(f"outputs/eval_models/{model_dir_name}/predictions.jsonl")
    
    stem = base_output.stem
    suffix = base_output.suffix
    parent = base_output.parent
    
    # 收集所有 worker 文件
    worker_files = []
    for wid in range(num_workers):
        worker_file = parent / f"{stem}_worker{wid}{suffix}"
        if worker_file.exists():
            worker_files.append((wid, worker_file))
        else:
            logger.warning(f"Worker {wid} 输出文件不存在: {worker_file}")
    
    if not worker_files:
        logger.error("没有找到任何 worker 输出文件")
        return
    
    logger.info(f"找到 {len(worker_files)}/{num_workers} 个 worker 输出文件")
    
    # 读取所有记录，按 doc_id 去重（保留最新）
    all_records: Dict[str, Dict[str, Any]] = {}
    total_count = 0
    
    for wid, wfile in sorted(worker_files):
        count = 0
        with open(wfile, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    doc_id = record.get("doc_id", "")
                    if doc_id:
                        all_records[doc_id] = record
                        count += 1
                except json.JSONDecodeError:
                    continue
        logger.info(f"Worker {wid}: 读取 {count} 条记录")
        total_count += count
    
    # 写入合并文件
    merged_output = parent / f"{stem}_merged{suffix}"
    with open(merged_output, "w", encoding="utf-8") as f:
        for record in all_records.values():
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    logger.info(f"合并完成: {len(all_records)} 条唯一记录 (原始 {total_count} 条)")
    logger.info(f"输出文件: {merged_output}")


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
    parser.add_argument("--api-key", default=None, help="API Key（可选，支持逗号分隔多 Key）")
    parser.add_argument("--temperature", type=float, default=None, help="温度参数")
    parser.add_argument("--top-p", type=float, default=None, help="Top-P 参数")
    parser.add_argument("--timeout", type=int, default=180, help="请求超时时间（秒，默认 180）")
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
    # 图结构检测开关（默认开启，通过 --no-graph 关闭）
    parser.add_argument("--no-graph", action="store_true",
                        help="禁用图结构自动检测，强制使用通用结构（用于消融实验，默认开启图结构检测）")
    strict_schema_group = parser.add_mutually_exclusive_group()
    strict_schema_group.add_argument("--strict-schema", action="store_true", dest="strict_schema",
                                     default=True, help="严格执行 Schema 约束（默认开启）")
    strict_schema_group.add_argument("--no-strict-schema", action="store_false", dest="strict_schema",
                                     help="关闭严格 Schema 约束（仅标记不剔除）")
    # Pred 宽松模式配置
    parser.add_argument("--fuzzy-threshold", type=float, default=0.75,
                        help="Pred 模糊匹配阈值（默认 0.75，宽松模式）")
    parser.add_argument("--strict-filter", action="store_true", default=False,
                        help="启用严格过滤（默认关闭，使用宽松模式）")
    # 完整文本来源
    parser.add_argument("--text-source", type=str, default=None,
                        help="完整文本来源文件（如 pool_v3.jsonl），用 id 字段与输入文件的 doc_id 映射")
    
    # 多进程并行参数
    parser.add_argument("--num-workers", "-n", type=int, default=1,
                        help="总进程数（默认 1，单进程）")
    parser.add_argument("--worker-id", "-id", type=int, default=0,
                        help="当前进程编号（从 0 开始，默认 0）")
    parser.add_argument("--merge", action="store_true",
                        help="合并多个 worker 的输出文件（与 -n 配合使用）")

    args = parser.parse_args()

    if args.api_key:
        os.environ["OPENAI_API_KEYS"] = args.api_key
        os.environ["OPENAI_API_KEY"] = args.api_key.split(",")[0]

    # 验证多进程参数
    num_workers = args.num_workers
    worker_id = args.worker_id
    if num_workers < 1:
        num_workers = 1
    if worker_id < 0 or worker_id >= num_workers:
        print(f"错误: worker_id ({worker_id}) 必须在 [0, {num_workers - 1}] 范围内")
        return

    # 如果是合并模式，执行合并后退出
    if args.merge:
        merge_worker_outputs(args, num_workers)
        return

    # 逻辑转换：默认都开启，通过 --no-* 关闭
    use_cot = not args.no_cot
    use_verify = not args.no_verify
    use_graph = not args.no_graph
    strict_schema = args.strict_schema

    # 参数组合逻辑：--no-graph 在 --no-cot 模式下无效
    if not use_cot and not use_graph:
        use_graph = True  # 重置，避免混淆（图结构是 CoT 的一部分）

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
    top_p = args.top_p if args.top_p is not None else cfg_llm.get("top_p")
    timeout = args.timeout if args.timeout is not None else cfg_llm.get("timeout", 180)

    # 输出路径
    if args.output:
        output_path = Path(args.output)
    else:
        model_dir_name = model_name.replace("/", "_").replace(":", "_")
        output_path = Path(f"outputs/eval_models/{model_dir_name}/predictions.jsonl")

    # 多进程模式下，每个 worker 写入独立文件
    if num_workers > 1:
        stem = output_path.stem
        suffix = output_path.suffix
        output_path = output_path.with_name(f"{stem}_worker{worker_id}{suffix}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 加载测试集
    test_file = Path(args.test_file)
    if not test_file.exists():
        logger.error(f"测试集文件不存在: {test_file}")
        return

    samples = load_test_samples(test_file)
    if args.limit:
        samples = samples[:args.limit]

    # 多进程分片：按取模法筛选当前 worker 负责的样本
    total_samples = len(samples)
    if num_workers > 1:
        samples = [(i, s) for i, s in enumerate(samples) if i % num_workers == worker_id]
        logger.info(f"Worker {worker_id}/{num_workers}: 负责 {len(samples)}/{total_samples} 个样本")
    else:
        samples = [(i, s) for i, s in enumerate(samples)]

    logger.info(f"测试集样本数: {len(samples)}")

    # 加载完整文本映射（如果指定了 --text-source）
    text_lookup = {}
    if args.text_source:
        logger.info(f"加载完整文本来源: {args.text_source}")
        try:
            text_lookup = load_text_lookup(Path(args.text_source))
        except FileNotFoundError as exc:
            logger.error(str(exc))
            return
        logger.info(f"已加载 {len(text_lookup)} 条完整文本")

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
        "timeout": timeout,
        "no_retry": True,
    }
    if top_p is not None:
        llm_config["top_p"] = top_p
    if base_url:
        llm_config["base_url"] = base_url

    logger.info(
        "LLM 配置: provider=%s, model=%s, temperature=%s, top_p=%s, timeout=%ss, use_cot=%s, use_verify=%s, use_graph=%s",
        provider,
        model_name,
        temperature,
        top_p,
        timeout,
        use_cot,
        use_verify,
        use_graph,
    )
    logger.info("Schema 严格约束: %s", "开启" if strict_schema else "关闭")
    if num_workers > 1:
        logger.info("多进程模式: worker %d / %d", worker_id, num_workers)

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

        for proc_idx, (orig_idx, sample) in enumerate(samples, start=1):
            doc_id = resolve_doc_id(sample, orig_idx + 1)
            source_text, source_tag = resolve_source_text(
                sample,
                doc_id,
                text_lookup,
                require_text_source=bool(args.text_source),
            )

            if not source_text:
                error_reason = (
                    "missing_text_source"
                    if source_tag == "missing_text_source"
                    else "empty_source_text"
                )
                logger.warning(f"[{proc_idx}/{len(samples)}] {doc_id}: 无有效文本({source_tag})，跳过")
                error_record = build_extraction_record(
                    doc_id=doc_id,
                    source_text="",
                    extraction_result=None,
                    use_cot=use_cot,
                    use_verify=use_verify,
                    include_source_text=False,
                    error=error_reason,
                )
                out_f.write(json.dumps(error_record, ensure_ascii=False) + "\n")
                out_f.flush()
                error_count += 1
                continue

            # 跳过已存在的
            if doc_id in existing_predictions and (args.skip_existing or args.retry_errors):
                if args.retry_errors and doc_id in error_doc_ids:
                    logger.info(f"[{proc_idx}/{len(samples)}] {doc_id}: 发现 error 记录，重新抽取")
                else:
                    skip_count += 1
                    logger.info(f"[{proc_idx}/{len(samples)}] {doc_id}: 跳过已存在")
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
                        use_graph=use_graph,
                        strict_filter=args.strict_filter,
                        fuzzy_threshold=args.fuzzy_threshold,
                        strict_schema=strict_schema,
                    )
                else:
                    res = pipeline.extract_events(
                        source_text,
                        schema=tbox,
                        save_path=None,
                        favor_existing_classes=args.favor_existing,
                        use_cot=use_cot,
                        use_graph=use_graph,
                    )

                output_record = build_extraction_record(
                    doc_id=doc_id,
                    source_text=source_text,
                    extraction_result=res,
                    use_cot=use_cot,
                    use_verify=use_verify,
                    use_graph=use_graph,
                    include_source_text=False,
                )

                if output_record.get("error"):
                    error_count += 1
                    logger.error(
                        f"[{proc_idx}/{len(samples)}] {doc_id}: error={output_record.get('error')}"
                    )
                    out_f.write(json.dumps(output_record, ensure_ascii=False) + "\n")
                    out_f.flush()
                    continue

                hallucination = output_record.get("hallucination", {})
                event_count = len(output_record.get("events", []))
                triple_count = len(output_record.get("triples", []))
                filtered_count = hallucination.get("filtered_count", 0)
                rate = hallucination.get("rate", 0.0)
                if use_verify:
                    if filtered_count > 0:
                        logger.info(
                            f"[{proc_idx}/{len(samples)}] {doc_id}: 事件 {event_count}, "
                            f"三元组 {triple_count} (幻觉率: {rate:.1%})"
                        )
                    else:
                        logger.info(
                            f"[{proc_idx}/{len(samples)}] {doc_id}: 事件 {event_count}, "
                            f"三元组 {triple_count} (无幻觉)"
                        )
                else:
                    logger.info(
                        f"[{proc_idx}/{len(samples)}] {doc_id}: 事件 {event_count}, "
                        f"三元组 {triple_count} [Raw]"
                    )

                out_f.write(json.dumps(output_record, ensure_ascii=False) + "\n")
                out_f.flush()
                success_count += 1

            except Exception as e:
                error_msg = str(e)
                error_record = build_extraction_record(
                    doc_id=doc_id,
                    source_text=source_text,
                    extraction_result=None,
                    use_cot=use_cot,
                    use_verify=use_verify,
                    include_source_text=False,
                    error=error_msg,
                )
                out_f.write(json.dumps(error_record, ensure_ascii=False) + "\n")
                out_f.flush()
                error_count += 1
                logger.error(f"[{proc_idx}/{len(samples)}] {doc_id}: {error_msg}")

                if is_quota_error(error_msg):
                    quota_exhausted = True
                    logger.error("检测到配额/429 错误，停止后续任务")
                    break

            # 间隔
            if args.interval > 0 and proc_idx < len(samples):
                time.sleep(args.interval)

    # 保存元数据
    meta = {
        "timestamp": datetime.now().isoformat(),
        "model": model_name,
        "tbox": str(tbox_path),
        "test_file": str(test_file),
        "total_samples": total_samples,
        "worker_samples": len(samples),
        "num_workers": num_workers,
        "worker_id": worker_id,
        "success_count": success_count,
        "skip_count": skip_count,
        "error_count": error_count,
        "quota_exhausted": quota_exhausted,
        "use_cot": use_cot,
        "use_verify": use_verify,
        "use_graph": use_graph,
        "strict_schema": strict_schema,
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
