#!/usr/bin/env python3
"""
使用 TBox 约束生成 Gold 标注（支持 CoT + 幻觉过滤）

核心改动：
1. 将 TBox 中的 classes 和 relations 作为 Prompt 约束
2. 支持 CoT（思维链）提高 Schema 遵循度
3. 支持幻觉过滤（后校验）确保实体在原文中存在

使用方式：
    # 推荐配置：CoT + 宽松校验
    python scripts/generate_gold_with_tbox.py \
        --input data/p5_eval_pool/pool_v3.jsonl \
        --tbox outputs/cq_pipeline/final/tbox_s2_optimized.json \
        --output data/p5_eval_pool/gold_s2.jsonl \
        --model "gpt-4o" \
        --base-url "https://api.openai.com/v1" \
        --use-cot \
        --use-verification \
        --verification-threshold 0.7 \
        --resume

    # 禁用 CoT（快速模式）
    python scripts/generate_gold_with_tbox.py \
        --input data/p5_eval_pool/pool_v3.jsonl \
        --tbox outputs/cq_pipeline/final/tbox_s2_optimized.json \
        --output data/p5_eval_pool/gold_s2.jsonl \
        --no-cot \
        --no-verification
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kg.hallucination_filter import HallucinationFilter
from kg.cq_pipeline import format_schema_for_prompt
from kg.entity_fusion import SimpleEntityNormalizer
from kg.prompts import (
    parse_cot_response,
    extract_cot_thought,
    UNIFIED_SYSTEM_PROMPT_COT,
    UNIFIED_USER_PROMPT_COT,
    UNIFIED_VERIFICATION_THRESHOLD,
)


# ==============================================================================
# TBox 加载与格式化
# ==============================================================================

def load_tbox(tbox_path: Path) -> Dict[str, Any]:
    """加载 TBox"""
    return json.loads(tbox_path.read_text(encoding="utf-8"))


def format_extraction_text(text: str) -> str:
    """与 Pred 抽取保持一致的输入格式。"""
    return f"【待抽取文本】\n{text.strip()}"


# ==============================================================================
# Prompt 模板（使用统一的 Prompt，确保 Gold 和 Pred 一致）
# ==============================================================================

# 普通模式 System Prompt
SYSTEM_PROMPT = """你是一名水旱灾害领域知识图谱标注专家。
你的任务是从文本中抽取实体和关系三元组。

【核心规则】
1. 实体必须是原文的**精确子串**，不可改写、不可合并、不可省略
2. 实体类型和关系类型**必须**从给定的 Schema 中选择
3. **严禁**发明 Schema 中不存在的类型或关系
4. 宁可漏抽，不可错抽
5. 每个三元组必须有原文支撑

请严格按 JSON 格式输出。"""

# 普通模式 User Prompt
USER_PROMPT_TEMPLATE = """请从以下文本中抽取实体和关系三元组。

{tbox_schema}

---

【待标注文本】
```
{text}
```

---

【输出格式】
请严格按以下 JSON 格式输出（只输出 JSON，不要其他内容）：

{{
  "entities": [
    {{"name": "实体名（必须是原文精确子串）", "type": "实体类型（必须来自Schema）"}}
  ],
  "triples": [
    {{
      "subject": "主语（原文子串）",
      "predicate": "关系（必须来自Schema的关系名，如 affects_region）",
      "object": "宾语（原文子串）",
      "evidence": "原文支撑句"
    }}
  ],
  "events": [
    {{
      "name": "事件名称（原文子串）",
      "event_type": "事件类型（必须来自Schema，如 DisasterEvent）",
      "time": {{"start_time": "", "end_time": ""}},
      "location": ["地点"]
    }}
  ]
}}

请直接输出JSON："""

# CoT 模式使用统一的 Prompt（从 kg/prompts.py 导入）
SYSTEM_PROMPT_COT = UNIFIED_SYSTEM_PROMPT_COT
USER_PROMPT_COT = UNIFIED_USER_PROMPT_COT


# ==============================================================================
# JSON 解析
# ==============================================================================

def extract_json(text: str) -> Dict[str, Any]:
    """从响应中提取 JSON（普通模式）"""

    # 去除 markdown 代码块
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1)

    # 找到 JSON 对象
    start = text.find("{")
    if start == -1:
        return {"entities": [], "triples": [], "events": [], "parse_error": True}

    brace_count = 0
    for i, c in enumerate(text[start:], start):
        if c == "{":
            brace_count += 1
        elif c == "}":
            brace_count -= 1
            if brace_count == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return {"entities": [], "triples": [], "events": [], "parse_error": True}

    return {"entities": [], "triples": [], "events": [], "parse_error": True}


# ==============================================================================
# LLM 客户端
# ==============================================================================

def create_llm_client(args: argparse.Namespace):
    """创建 LLM 客户端"""
    from kg.llm_core import LLMFactory

    llm_config = {
        "model_name": args.model,
        "base_url": args.base_url,
        "temperature": args.temperature,
        "max_retries": 3,
        "timeout": 180,
    }

    # 如果指定了 API Key，设置环境变量
    if args.api_key:
        os.environ["OPENAI_API_KEYS"] = args.api_key

    # 可选参数
    if args.top_p is not None:
        llm_config["top_p"] = args.top_p

    return LLMFactory.create(llm_config)


# ==============================================================================
# 核心生成函数
# ==============================================================================


def generate_gold_for_sample(
    text: str,
    tbox_schema: str,
    llm,
    tbox: Dict[str, Any],
    use_cot: bool = True,
    use_verification: bool = True,
    verification_threshold: float = 0.85,
    strict_mode: bool = True,
) -> Dict[str, Any]:
    """
    为单个样本生成 Gold 标注（单次请求，不重试）

    设计说明：
    - 对于 RPM 限制严格的 API（如 RPM=3），函数内部不重试
    - 遇到任何错误直接返回带 error 字段的结果
    - 由调用方通过 --interval 控制请求间隔
    - 失败的记录可以后续用 --retry-errors 重试

    Args:
        text: 待标注文本
        tbox_schema: 格式化后的 TBox Schema 文本
        llm: LLM 客户端
        tbox: TBox 字典（用于验证）
        use_cot: 是否使用 CoT 思维链
        use_verification: 是否使用幻觉过滤
        verification_threshold: 模糊匹配阈值（Gold 推荐 0.85，更严格）
        strict_mode: 是否使用严格模式（Gold 推荐 True，零噪声）

    Returns:
        包含 entities, triples, events 的字典
    """
    # 选择 Prompt
    prompt_text = format_extraction_text(text)
    if use_cot:
        system_prompt = SYSTEM_PROMPT_COT
        user_prompt = USER_PROMPT_COT.format(tbox_schema=tbox_schema, text=prompt_text)
    else:
        system_prompt = SYSTEM_PROMPT
        user_prompt = USER_PROMPT_TEMPLATE.format(tbox_schema=tbox_schema, text=prompt_text)

    raw_response = ""

    try:
        # 调用 LLM（单次请求，不重试）
        raw_response = llm.chat(user_prompt, system_prompt=system_prompt)

        # 解析响应
        if use_cot:
            # 使用 kg/prompts.py 中的解析函数
            result = parse_cot_response(raw_response)
            if result is None:
                result = {"entities": [], "triples": [], "events": [], "parse_error": True}
            else:
                result["parse_error"] = False

            # 提取思考过程
            thought = extract_cot_thought(raw_response)
            result["_thinking"] = thought
        else:
            result = extract_json(raw_response)

    except Exception as e:
        # 任何错误都直接返回，不重试
        # 由调用方通过 --interval 控制请求间隔，后续用 --retry-errors 重试
        return {
            "entities": [],
            "triples": [],
            "events": [],
            "error": str(e),
            "raw_response": raw_response[:500] if raw_response else "",
        }

    # 确保 result 存在
    if result is None:
        result = {"entities": [], "triples": [], "events": [], "parse_error": True}

    # 后校验（幻觉过滤）
    if use_verification and not result.get("parse_error") and not result.get("error"):
        halluc_filter = HallucinationFilter(
            strict_mode=strict_mode,
            fuzzy_threshold=verification_threshold,
            verbose=False,
        )

        verified = halluc_filter.verify(result, text)

        # 保存原始三元组数量
        original_triple_count = len(result.get("triples", []))

        # 替换为验证通过的三元组
        result["triples"] = verified.valid_triples
        result["events"] = verified.valid_events

        # 记录验证统计
        result["_verification_stats"] = {
            "original": verified.total_triples,
            "valid": verified.valid_count,
            "filtered": verified.filtered_count,
            "hallucination_rate": round(verified.hallucination_rate, 2),
        }

        # 保存被过滤的三元组（便于调试）
        if verified.filtered_triples:
            result["_filtered_by_verification"] = verified.filtered_triples

    # 实体标准化（与 Pred 抽取保持一致）
    normalizer = SimpleEntityNormalizer()
    result["triples"] = normalizer.normalize_triples(result.get("triples", []))

    # TBox 约束过滤
    result = validate_against_tbox(result, tbox)

    return result


def validate_against_tbox(result: Dict, tbox: Dict) -> Dict:
    """验证结果是否符合 TBox 约束，只标记不剔除（与 Pred 抽取保持一致）"""

    valid_relations = {r["name"] for r in tbox.get("relations", [])}
    valid_classes = {c["name"] for c in tbox.get("classes", [])}

    # 标记三元组（不剔除）
    invalid_predicate_count = 0
    for t in result.get("triples", []):
        pred = t.get("predicate", "")
        if pred and pred not in valid_relations:
            t["_invalid_predicate"] = True
            invalid_predicate_count += 1

    if invalid_predicate_count > 0:
        result["_tbox_invalid_predicates"] = invalid_predicate_count

    # 标记实体（不剔除）
    invalid_entity_count = 0
    for e in result.get("entities", []):
        etype = e.get("type", "")
        if etype and etype not in valid_classes:
            e["_invalid_type"] = True
            invalid_entity_count += 1

    if invalid_entity_count > 0:
        result["_tbox_invalid_entities"] = invalid_entity_count

    # 标记事件（不剔除）
    invalid_event_count = 0
    for ev in result.get("events", []):
        etype = ev.get("event_type", "")
        if etype and etype not in valid_classes:
            ev["_invalid_event_type"] = True
            invalid_event_count += 1

    if invalid_event_count > 0:
        result["_tbox_invalid_events"] = invalid_event_count

    return result


# ==============================================================================
# 主函数
# ==============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="使用 TBox 约束生成 Gold 标注（支持 CoT + 幻觉过滤）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
    # 推荐配置：CoT + 宽松校验
    python scripts/generate_gold_with_tbox.py \\
        --input data/p5_eval_pool/pool_v3.jsonl \\
        --tbox outputs/cq_pipeline/final/tbox_s2_optimized.json \\
        --output data/p5_eval_pool/gold_s2.jsonl \\
        --model "gpt-4o" \\
        --use-cot \\
        --use-verification \\
        --verification-threshold 0.7

    # 快速模式（无 CoT、无校验）
    python scripts/generate_gold_with_tbox.py \\
        --input data/p5_eval_pool/pool_v3.jsonl \\
        --tbox outputs/cq_pipeline/final/tbox_s2_optimized.json \\
        --output data/p5_eval_pool/gold_s2.jsonl \\
        --no-cot \\
        --no-verification
        """,
    )

    # 输入输出
    parser.add_argument("--input", required=True, help="输入文件（JSONL）")
    parser.add_argument("--tbox", required=True, help="TBox 文件")
    parser.add_argument("--output", required=True, help="输出文件（JSONL）")

    # 模型配置
    parser.add_argument("--model", default="gpt-4o", help="模型名称")
    parser.add_argument(
        "--base-url",
        default="https://api.openai.com/v1",
        help="API 基础地址",
    )
    parser.add_argument("--api-key", default="", help="API Key（可选，默认从环境变量读取）")
    parser.add_argument("--temperature", type=float, default=0.1, help="温度参数")
    parser.add_argument("--top-p", type=float, default=None, help="Top-P 参数")

    # CoT 配置
    cot_group = parser.add_mutually_exclusive_group()
    cot_group.add_argument("--use-cot", action="store_true", default=True,
                           help="使用 CoT 思维链（默认开启）")
    cot_group.add_argument("--no-cot", action="store_true",
                           help="禁用 CoT")

    # 幻觉过滤配置
    verify_group = parser.add_mutually_exclusive_group()
    verify_group.add_argument("--use-verification", action="store_true", default=True,
                              help="使用幻觉过滤后校验（默认开启）")
    verify_group.add_argument("--no-verification", action="store_true",
                              help="禁用后校验")

    parser.add_argument("--verification-threshold", type=float, default=UNIFIED_VERIFICATION_THRESHOLD,
                        help=f"模糊匹配阈值（默认 {UNIFIED_VERIFICATION_THRESHOLD}，与 Pred 保持一致）")
    parser.add_argument("--strict-mode", action="store_true",
                        help="严格模式（仅精确匹配，不推荐用于 Gold）")

    # 运行控制
    parser.add_argument("--resume", action="store_true", help="断点续跑")
    parser.add_argument("--retry-errors", action="store_true",
                        help="重新跑 error 记录（跳过成功记录，重试失败记录）")
    parser.add_argument("--limit", type=int, default=0, help="限制样本数（0=不限制）")
    parser.add_argument("--interval", type=float, default=0.5, help="请求间隔（秒）")
    parser.add_argument("--max-retries", type=int, default=3, help="最大重试次数")
    parser.add_argument("--text-source", type=str, default=None,
                        help="完整文本来源文件（如 pool_v3.jsonl），用 id 字段与输入文件的 doc_id 映射")

    args = parser.parse_args()

    # 处理互斥参数
    use_cot = not args.no_cot
    use_verification = not args.no_verification

    input_path = Path(args.input)
    tbox_path = Path(args.tbox)
    output_path = Path(args.output)

    # 检查文件
    if not input_path.exists():
        print(f"❌ 输入文件不存在: {input_path}")
        return
    if not tbox_path.exists():
        print(f"❌ TBox 文件不存在: {tbox_path}")
        return

    # 加载 TBox
    print(f"📋 加载 TBox: {tbox_path}")
    tbox = load_tbox(tbox_path)
    tbox_schema = format_schema_for_prompt(tbox, style="markdown")
    print(f"   - 类数: {len(tbox.get('classes', []))}")
    print(f"   - 关系数: {len(tbox.get('relations', []))}")

    # 创建 LLM 客户端
    print(f"\n🤖 创建 LLM 客户端: {args.model}")
    print(f"   - base_url: {args.base_url}")
    print(f"   - temperature: {args.temperature}")
    llm = create_llm_client(args)

    # 打印配置
    print(f"\n⚙️  运行配置:")
    print(f"   - CoT 思维链: {'✅ 开启' if use_cot else '❌ 关闭'}")
    print(f"   - 幻觉过滤: {'✅ 开启' if use_verification else '❌ 关闭'}")
    if use_verification:
        print(f"   - 匹配阈值: {args.verification_threshold}")
        print(f"   - 严格模式: {'是' if args.strict_mode else '否'}")

    # 加载样本
    samples = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))

    if args.limit > 0:
        samples = samples[: args.limit]

    print(f"\n📊 样本数: {len(samples)}")

    # 加载完整文本映射（如果指定了 --text-source）
    text_lookup = {}
    if args.text_source:
        text_source_path = Path(args.text_source)
        if text_source_path.exists():
            print(f"📂 加载完整文本来源: {args.text_source}")
            with open(text_source_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        doc_id = d.get("id", d.get("doc_id", ""))
                        if doc_id:
                            text_lookup[doc_id] = d.get("text", "")
            print(f"   已加载 {len(text_lookup)} 条完整文本")
        else:
            print(f"⚠️  文本来源文件不存在: {args.text_source}，将使用输入文件中的文本")

    # 断点续跑 / 重试错误
    processed_ids = set()
    error_ids = set()  # 需要重试的 error 记录
    existing_results = {}  # 保存已有结果，用于 retry-errors 模式

    if (args.resume or args.retry_errors) and output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    doc_id = item.get("doc_id", "")
                    if item.get("error") or item.get("parse_error"):
                        error_ids.add(doc_id)
                    else:
                        processed_ids.add(doc_id)
                    existing_results[doc_id] = item

        if args.retry_errors:
            print(f"📌 已处理成功: {len(processed_ids)}，需重试: {len(error_ids)}")
        else:
            # resume 模式：跳过所有已处理的（包括 error）
            processed_ids.update(error_ids)
            print(f"📌 已处理: {len(processed_ids)}")

    # 处理
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # retry-errors 模式：需要重写整个文件（保留成功的，重试失败的）
    if args.retry_errors:
        mode = "w"
    else:
        mode = "a" if args.resume else "w"

    success = 0
    errors = 0
    total_triples = 0
    total_tbox_invalid = 0
    total_verification_filtered = 0

    print(f"\n🚀 开始处理...")
    print("-" * 70)

    with open(output_path, mode, encoding="utf-8") as f_out:
        # retry-errors 模式：先写入所有成功的记录
        if args.retry_errors:
            for doc_id in processed_ids:
                if doc_id in existing_results:
                    f_out.write(json.dumps(existing_results[doc_id], ensure_ascii=False) + "\n")

        for idx, sample in enumerate(samples):
            doc_id = sample.get("doc_id", sample.get("id", f"doc_{idx}"))

            # 跳过已成功处理的
            if doc_id in processed_ids:
                continue

            # retry-errors 模式：只处理 error_ids 中的记录
            if args.retry_errors and doc_id not in error_ids:
                continue

            # 获取文本（优先从 text_lookup 获取完整文本）
            if text_lookup and doc_id in text_lookup:
                text = text_lookup[doc_id]
            else:
                text = sample.get("source_text", sample.get("text", sample.get("content", "")))
            if not text:
                continue

            print(f"  [{idx+1}/{len(samples)}] {doc_id[:30]}...", end="", flush=True)

            # 生成标注（单次请求，不重试；遇到错误记录后等待 interval 处理下一条）
            result = generate_gold_for_sample(
                text=text,
                tbox_schema=tbox_schema,
                llm=llm,
                tbox=tbox,
                use_cot=use_cot,
                use_verification=use_verification,
                verification_threshold=args.verification_threshold,
                strict_mode=args.strict_mode,
            )

            # 添加元信息
            result["doc_id"] = doc_id
            result["source_text"] = text[:500] + "..." if len(text) > 500 else text

            # 如果有 parse_error，统一添加 error 字段以支持 --retry-errors
            if result.get("parse_error") and not result.get("error"):
                result["error"] = "JSON解析失败"

            f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
            f_out.flush()

            if result.get("parse_error") or result.get("error"):
                errors += 1
                err_msg = result.get("error", "解析失败")[:30]
                print(f" ❌ {err_msg}")
            else:
                success += 1
                n_triples = len(result.get("triples", []))
                n_tbox_invalid = result.get("_tbox_invalid_predicates", 0)
                total_triples += n_triples
                total_tbox_invalid += n_tbox_invalid

                # 统计幻觉过滤
                v_stats = result.get("_verification_stats", {})
                n_v_filtered = v_stats.get("filtered", 0)
                total_verification_filtered += n_v_filtered

                # 输出信息
                info_parts = [f"三元组={n_triples}"]
                if n_tbox_invalid > 0:
                    info_parts.append(f"TBox无效谓词={n_tbox_invalid}")
                if n_v_filtered > 0:
                    info_parts.append(f"幻觉过滤={n_v_filtered}")
                if result.get("_thinking"):
                    info_parts.append("CoT✓")

                print(f" ✅ {', '.join(info_parts)}")

            time.sleep(args.interval)

    print("-" * 70)
    print(f"\n✅ 完成!")
    print(f"   - 成功: {success}")
    print(f"   - 错误: {errors}")
    print(f"   - 总三元组: {total_triples}")
    print(f"   - TBox 无效谓词: {total_tbox_invalid}")
    print(f"   - 幻觉过滤: {total_verification_filtered}")
    print(f"📁 输出: {output_path}")


if __name__ == "__main__":
    main()
