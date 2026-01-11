#!/usr/bin/env python3
"""
使用 TBox 约束生成 Gold 标注（图结构 CoT + 后校验）。

核心逻辑：
1. 与 Pred 使用同一条抽取链路（CQLLMPipeline）
2. 默认启用图结构 CoT + 原文回溯校验 + Schema 一致性校验
3. 输出结构与 Pred 完全一致
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kg.cq_pipeline import CQLLMPipeline, TBoxSchema, ClassDef, RelationDef, AttributeDef
from kg.extraction_output import build_extraction_record
from kg.utils.text_source import (
    load_text_lookup,
    resolve_doc_id,
    resolve_source_text,
)


def load_tbox(tbox_path: Path) -> TBoxSchema:
    """加载 TBox（JSON -> TBoxSchema）。"""
    data = json.loads(tbox_path.read_text(encoding="utf-8"))
    return TBoxSchema(
        classes=[ClassDef(**c) for c in data.get("classes", [])],
        relations=[RelationDef(**r) for r in data.get("relations", [])],
        attributes=[AttributeDef(**a) for a in data.get("attributes", [])],
    )


def log(message: str) -> None:
    """统一为 Gold 输出增加时间戳。"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp} | {message}", flush=True)


def create_pipeline(args: argparse.Namespace) -> CQLLMPipeline:
    """创建抽取流水线，统一 LLM 配置入口。"""
    llm_config: Dict[str, Any] = {
        "model_name": args.model,
        "base_url": args.base_url,
        "temperature": args.temperature,
        "max_retries": args.max_retries,
        "timeout": 180,
        "no_retry": True,
    }
    if args.top_p is not None:
        llm_config["top_p"] = args.top_p

    if args.api_key:
        os.environ["OPENAI_API_KEYS"] = args.api_key

    return CQLLMPipeline(llm_config=llm_config, output_dir=str(args.output_dir))


def generate_gold_for_sample(
    text: str,
    pipeline: CQLLMPipeline,
    tbox: TBoxSchema,
    use_cot: bool = True,
    use_verification: bool = True,
    strict_filter: bool = True,
    fuzzy_threshold: float = 0.9,
    strict_schema: bool = True,
    favor_existing_classes: bool = True,
) -> Dict[str, Any]:
    """
    为单个样本生成 Gold 标注（单次请求）。

    Args:
        text: 待标注文本
        pipeline: CQLLMPipeline 实例
        tbox: TBoxSchema
        use_cot: 是否启用图结构 CoT
        use_verification: 是否启用原文回溯校验
        strict_filter: 是否严格过滤（仅精确匹配）
        fuzzy_threshold: 模糊匹配阈值
        strict_schema: 是否严格执行 Schema 约束
        favor_existing_classes: 是否优先使用既有类
    """
    if use_verification:
        return pipeline.extract_events_with_verification(
            paragraph=text,
            schema=tbox,
            save_path=None,
            favor_existing_classes=favor_existing_classes,
            use_cot=use_cot,
            strict_filter=strict_filter,
            fuzzy_threshold=fuzzy_threshold,
            strict_schema=strict_schema,
        )

    return pipeline.extract_events(
        paragraph=text,
        schema=tbox,
        save_path=None,
        favor_existing_classes=favor_existing_classes,
        use_cot=use_cot,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="使用 TBox 约束生成 Gold 标注（图结构 CoT + 后校验）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # 输入输出
    parser.add_argument("--input", required=True, help="输入文件（JSONL）")
    parser.add_argument("--tbox", required=True, help="TBox 文件")
    parser.add_argument("--output", required=True, help="输出文件（JSONL）")
    parser.add_argument("--output-dir", default="outputs/eval_models/gold", help="临时输出目录")

    # 模型配置
    parser.add_argument("--model", default="gpt-4o", help="模型名称")
    parser.add_argument("--base-url", default="https://api.openai.com/v1", help="API 基础地址")
    parser.add_argument("--api-key", default="", help="API Key（可选，默认从环境变量读取）")
    parser.add_argument("--temperature", type=float, default=0.1, help="温度参数")
    parser.add_argument("--top-p", type=float, default=None, help="Top-P 参数")
    parser.add_argument("--max-retries", type=int, default=3, help="最大重试次数")

    # CoT 配置
    cot_group = parser.add_mutually_exclusive_group()
    cot_group.add_argument("--use-cot", action="store_true", default=True,
                           help="使用 CoT 思维链（默认开启）")
    cot_group.add_argument("--no-cot", action="store_true", help="禁用 CoT")

    # 幻觉过滤配置
    verify_group = parser.add_mutually_exclusive_group()
    verify_group.add_argument("--use-verification", action="store_true", default=True,
                              help="使用幻觉过滤后校验（默认开启）")
    verify_group.add_argument("--no-verification", action="store_true", help="禁用后校验")
    parser.add_argument("--verification-threshold", type=float, default=0.9,
                        help="Gold 模糊匹配阈值（默认 0.9，严格模式）")
    parser.add_argument("--strict-mode", action="store_true",
                        help="严格模式（仅精确匹配，不推荐用于 Gold）")

    # Schema 约束
    schema_group = parser.add_mutually_exclusive_group()
    schema_group.add_argument("--strict-schema", action="store_true", dest="strict_schema",
                              default=True, help="严格执行 Schema 约束（默认开启）")
    schema_group.add_argument("--no-strict-schema", action="store_false", dest="strict_schema",
                              help="关闭严格 Schema 约束（仅标记不剔除）")

    # 类使用策略
    class_group = parser.add_mutually_exclusive_group()
    class_group.add_argument("--favor-existing-classes", action="store_true", dest="favor_existing",
                             default=True, help="优先使用已有类（默认）")
    class_group.add_argument("--no-favor-existing-classes", action="store_false", dest="favor_existing",
                             help="允许使用新类")

    # 运行控制
    parser.add_argument("--resume", action="store_true", help="断点续跑")
    parser.add_argument("--retry-errors", action="store_true",
                        help="重新跑 error 记录（跳过成功记录，重试失败记录）")
    parser.add_argument("--limit", type=int, default=0, help="限制样本数（0=不限制）")
    parser.add_argument("--interval", type=float, default=0.5, help="请求间隔（秒）")
    parser.add_argument("--text-source", type=str, default=None,
                        help="完整文本来源文件（doc_id 映射 id 字段）")

    args = parser.parse_args()

    # 逻辑转换：默认都开启，通过 --no-* 关闭
    use_cot = not args.no_cot
    use_verification = not args.no_verification

    input_path = Path(args.input)
    tbox_path = Path(args.tbox)
    output_path = Path(args.output)
    output_dir = Path(args.output_dir)

    if not input_path.exists():
        log(f"❌ 输入文件不存在: {input_path}")
        return
    if not tbox_path.exists():
        log(f"❌ TBox 文件不存在: {tbox_path}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # 加载 TBox
    log(f"📋 加载 TBox: {tbox_path}")
    tbox = load_tbox(tbox_path)
    log(f"   - 类数: {len(tbox.classes)}")
    log(f"   - 关系数: {len(tbox.relations)}")

    # 初始化 Pipeline
    log(f"🤖 创建 LLM 客户端: {args.model}")
    log(f"   - base_url: {args.base_url}")
    log(f"   - temperature: {args.temperature}")
    pipeline = create_pipeline(args)

    # 打印配置
    log("⚙️  运行配置:")
    log(f"   - CoT 思维链: {'✅ 开启' if use_cot else '❌ 关闭'}")
    log(f"   - 幻觉过滤: {'✅ 开启' if use_verification else '❌ 关闭'}")
    if use_verification:
        log(f"   - 匹配阈值: {args.verification_threshold}")
        log(f"   - 精确匹配模式: {'是' if args.strict_mode else '否（模糊匹配）'}")
    log(f"   - Schema 严格约束: {'是' if args.strict_schema else '否'}")
    log(f"   - 优先使用已有类: {'是' if args.favor_existing else '否'}")

    # 加载样本
    samples: List[Dict[str, Any]] = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))

    if args.limit > 0:
        samples = samples[: args.limit]

    log(f"📊 样本数: {len(samples)}")

    # 加载完整文本映射
    text_lookup: Dict[str, str] = {}
    if args.text_source:
        log(f"📂 加载完整文本来源: {args.text_source}")
        try:
            text_lookup = load_text_lookup(Path(args.text_source))
        except FileNotFoundError as exc:
            log(str(exc))
            return
        log(f"   已加载 {len(text_lookup)} 条完整文本")

    # 断点续跑 / 重试错误
    processed_ids = set()
    error_ids = set()
    existing_results: Dict[str, Dict[str, Any]] = {}

    if (args.resume or args.retry_errors) and output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    doc_id = item.get("doc_id", "")
                    if item.get("error"):
                        error_ids.add(doc_id)
                    else:
                        processed_ids.add(doc_id)
                    existing_results[doc_id] = item

        if args.retry_errors:
            log(f"📌 已处理成功: {len(processed_ids)}，需重试: {len(error_ids)}")
        else:
            processed_ids.update(error_ids)
            log(f"📌 已处理: {len(processed_ids)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # retry-errors 模式：需要重写整个文件（保留成功的，重试失败的）
    mode = "a" if args.resume and not args.retry_errors else "w"

    success = 0
    errors = 0

    log("🚀 开始处理...")
    log("-" * 70)

    with open(output_path, mode, encoding="utf-8") as f_out:
        if args.retry_errors:
            for doc_id in processed_ids:
                if doc_id in existing_results:
                    f_out.write(json.dumps(existing_results[doc_id], ensure_ascii=False) + "\n")

        for idx, sample in enumerate(samples):
            doc_id = resolve_doc_id(sample, idx)

            # 跳过已处理
            if doc_id in processed_ids:
                continue
            if args.retry_errors and doc_id not in error_ids:
                continue

            # 获取文本
            text, source_tag = resolve_source_text(
                sample,
                doc_id,
                text_lookup,
                require_text_source=bool(args.text_source),
            )
            if not text:
                error_reason = (
                    "missing_text_source"
                    if source_tag == "missing_text_source"
                    else "empty_source_text"
                )
                result = build_extraction_record(
                    doc_id=doc_id,
                    source_text="",
                    extraction_result=None,
                    use_cot=use_cot,
                    use_verify=use_verification,
                    include_source_text=False,
                    error=error_reason,
                )
                f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
                f_out.flush()
                errors += 1
                continue

            log(f"[{idx+1}/{len(samples)}] {doc_id[:30]}...")

            try:
                extraction = generate_gold_for_sample(
                    text=text,
                    pipeline=pipeline,
                    tbox=tbox,
                    use_cot=use_cot,
                    use_verification=use_verification,
                    strict_filter=args.strict_mode,
                    fuzzy_threshold=args.verification_threshold,
                    strict_schema=args.strict_schema,
                    favor_existing_classes=args.favor_existing,
                )
                result = build_extraction_record(
                    doc_id=doc_id,
                    source_text=text,
                    extraction_result=extraction,
                    use_cot=use_cot,
                    use_verify=use_verification,
                    include_source_text=False,
                )
            except Exception as e:
                result = build_extraction_record(
                    doc_id=doc_id,
                    source_text=text,
                    extraction_result=None,
                    use_cot=use_cot,
                    use_verify=use_verification,
                    include_source_text=False,
                    error=str(e),
                )

            f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
            f_out.flush()

            if result.get("error"):
                errors += 1
                err_msg = result.get("error", "未知错误")[:30]
                log(f"❌ {err_msg}")
            else:
                success += 1
                triple_count = len(result.get("triples", []))
                event_count = len(result.get("events", []))
                filtered_count = result.get("hallucination", {}).get("filtered_count", 0)
                if filtered_count > 0:
                    log(f"✅ 事件={event_count}, 三元组={triple_count}, 过滤={filtered_count}")
                else:
                    log(f"✅ 事件={event_count}, 三元组={triple_count}")

            time.sleep(args.interval)

    log("-" * 70)
    log("✅ 完成!")
    log(f"   - 成功: {success}")
    log(f"   - 错误: {errors}")
    log(f"📁 输出: {output_path}")


if __name__ == "__main__":
    main()
