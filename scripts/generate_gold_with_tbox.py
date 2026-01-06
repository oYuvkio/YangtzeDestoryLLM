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
from kg.prompts import parse_cot_response, extract_cot_thought


# ==============================================================================
# TBox 加载与格式化
# ==============================================================================

def load_tbox(tbox_path: Path) -> Dict[str, Any]:
    """加载 TBox"""
    return json.loads(tbox_path.read_text(encoding="utf-8"))


def format_tbox_for_prompt(tbox: Dict[str, Any], max_classes: int = 40) -> str:
    """将 TBox 格式化为 Prompt 可用的文本"""

    # 格式化类
    classes_text = "【实体类型（必须使用以下类型）】\n"
    for cls in tbox.get("classes", [])[:max_classes]:
        name = cls.get("name", "")
        cn_name = cls.get("cn_name", "")
        definition = cls.get("definition", "")
        if len(definition) > 60:
            definition = definition[:60] + "..."
        classes_text += f"- {name} ({cn_name}): {definition}\n"

    if len(tbox.get("classes", [])) > max_classes:
        classes_text += f"... 共 {len(tbox['classes'])} 个类\n"

    # 格式化关系
    relations_text = "\n【关系类型（必须使用以下关系）】\n"
    relations_text += "| 关系名 | 中文名 | 主语类型 | 宾语类型 |\n"
    relations_text += "|--------|--------|----------|----------|\n"
    for rel in tbox.get("relations", []):
        name = rel.get("name", "")
        cn_name = rel.get("cn_name", "")
        domain = rel.get("domain", "")
        range_ = rel.get("range", "")
        relations_text += f"| {name} | {cn_name} | {domain} | {range_} |\n"

    return classes_text + relations_text


# ==============================================================================
# Prompt 模板
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

# CoT 模式 System Prompt
SYSTEM_PROMPT_COT = """你是一名水旱灾害领域知识图谱标注专家。
你的任务是从文本中抽取高质量的实体和关系三元组，作为评测标准。

【核心原则】
1. **准确性优先**：所有实体必须是原文的**精确子串**，不可改写
2. **完整性**：尽可能发现所有符合 Schema 的三元组
3. **规范性**：严格使用 Schema 中定义的类型和关系
4. **可追溯**：每条三元组必须有原文证据支撑"""

# CoT 模式 User Prompt
USER_PROMPT_COT = """请从以下文本中抽取实体和关系三元组。

{tbox_schema}

---

【待标注文本】
```
{text}
```

---

【⚠️ 关键规则 - 必须严格遵守】

**规则1：区分时间和事件**
- 判断标准：是否包含灾害性质词（洪水/旱灾/大水/奇旱/涝/决口等）
- ❌ 错误："乾隆二十九年(1764年)" → DisasterEvent
  【原因：只有年份，无灾害性质词】
- ✅ 正确："乾隆二十九年(1764年)" → TemporalEntity
- ✅ 正确："乾隆五十年(1785年)奇旱" → DroughtEvent
  【原因：包含"奇旱"灾害词】

**规则2：三元组主语规范**
- 纯时间不能独立表达"发生了什么"，必须有事件主体
- ❌ ("1998年", affects_region, "长江流域")
  【问题：1998年发生了什么？缺少事件主体】
- ✅ ("1998年长江洪水", affects_region, "长江流域")
- ✅ ("1998年长江洪水", occurs_at, "1998年")

**规则3：实体必须是原文精确子串**
- ❌ 合并："长江中下游地区" ← 原文是"长江中下游"
- ❌ 推断："三峡大坝" ← 原文只有"三峡"
- ✅ 保持原样：使用原文中完全一致的表述

**规则4：不确定情况的处理**
- 如果实体类型不确定，优先选择上位类（如用 DisasterEvent 而非具体子类）
- 如果关系不在 Schema 中，**不要发明新关系**，跳过该三元组
- **宁可漏抽，不可错抽**

---

【示例1：现代水文干旱】

原文片段：
"以收集的实测水文气象资料为依据,以洞庭湖水系出口控制站岳阳城陵矶水文站水位流量过程线和相关水文气象因子变化情况为参照,兼顾全省抗旱应急调度有关时间节点,将2022年水文干旱过程划分为四个阶段...第一阶段(干旱露头):2022年7月8日—8月底。7月8日全省集中降雨基本结束,天气转入高温少雨阶段,来水偏少,洞庭湖8月4日达到枯水位(24.50 m),为1971年以来最早,洞庭湖汛期反枯,涝旱急转,8月12日全省启动抗旱Ⅳ级应急响应。"

正确输出：
```json
{{
  "entities": [
    {{"name": "2022年水文干旱过程", "type": "DroughtEvent"}},
    {{"name": "城陵矶水文站", "type": "HydrologicalStation"}},
    {{"name": "洞庭湖", "type": "Lake"}},
    {{"name": "2022年7月8日", "type": "TemporalEntity"}},
    {{"name": "抗旱Ⅳ级应急响应", "type": "EmergencyResponse"}}
  ],
  "triples": [
    {{"subject": "城陵矶水文站", "predicate": "monitors_river", "object": "洞庭湖", "evidence": "洞庭湖水系出口控制站岳阳城陵矶水文站", "confidence": "high"}},
    {{"subject": "2022年水文干旱过程", "predicate": "occurs_at", "object": "2022年7月8日", "evidence": "2022年7月8日—8月底", "confidence": "high"}},
    {{"subject": "2022年水文干旱过程", "predicate": "triggers_response", "object": "抗旱Ⅳ级应急响应", "evidence": "8月12日全省启动抗旱Ⅳ级应急响应", "confidence": "high"}}
  ]
}}
```

---

【示例2：历史灾害记录】

原文片段：
"清代无为有水、旱、震、疫、风、雪、雹、虫等自然灾害共158次。其中水灾达60次,占比近38%,旱灾33次,占比近21%...乾隆五十年(1785年)奇旱,"自去冬至是年终岁无雨,江潮闭,山田籽粒无收,圩之滨河者收三十之一";五十一年(1786年)春仍旱,大饥而疫死者弥望。"

正确输出：
```json
{{
  "entities": [
    {{"name": "无为", "type": "GeographicRegion"}},
    {{"name": "乾隆五十年(1785年)奇旱", "type": "DroughtEvent"}},
    {{"name": "水灾", "type": "DisasterEvent"}},
    {{"name": "大饥", "type": "DisasterImpact"}}
  ],
  "triples": [
    {{"subject": "水灾", "predicate": "affects_region", "object": "无为", "evidence": "其中水灾达60次", "confidence": "high"}},
    {{"subject": "乾隆五十年(1785年)奇旱", "predicate": "affects_region", "object": "无为", "evidence": "乾隆五十年(1785年)奇旱,自去冬至是年终岁无雨", "confidence": "high"}},
    {{"subject": "乾隆五十年(1785年)奇旱", "predicate": "causes_impact", "object": "大饥", "evidence": "大饥而疫死者弥望", "confidence": "high"}}
  ]
}}
```

---

【抽取步骤】请严格按以下步骤思考（Chain-of-Thought）：

**Step 1: 实体扫描**
仔细阅读文本，识别所有可能的实体，标注其类型。
- 自检：每个实体是否在原文中**原样出现**？
- 自检：实体类型是否在 Schema 的 classes 列表中？
- 特别注意：纯时间（如"1998年"）应标为 TemporalEntity，不是 DisasterEvent

**Step 2: 关系识别**
对识别出的实体对，判断是否存在 Schema 定义的关系。
- 检查：关系是否在 Schema 的 relations 列表中？
- 检查：主语/宾语类型是否符合 domain/range 约束？
- 检查：原文是否明确支持这个关系？
- 特别注意：纯时间不能作为三元组主语，应使用 occurs_at 连接事件和时间

**Step 3: 证据回溯**
为每条三元组标注原文支撑句（evidence）。
- 如找不到明确支撑，标记 confidence 为 "low"
- 如关系需要推理，标记 confidence 为 "medium"
- 如关系在原文中直接表述，标记 confidence 为 "high"

**Step 4: 输出**

请先输出【思考过程】（50-150字，简述关键实体和推理逻辑），然后输出 JSON：

```json
{{
  "entities": [
    {{"name": "实体名（原文子串）", "type": "Schema中的类型"}}
  ],
  "triples": [
    {{
      "subject": "主语（原文子串）",
      "predicate": "Schema中的关系名",
      "object": "宾语（原文子串）",
      "evidence": "原文支撑句",
      "confidence": "high/medium/low"
    }}
  ],
  "events": [
    {{
      "name": "事件名称",
      "event_type": "DisasterEvent/DroughtEvent等",
      "time": {{"start_time": "", "end_time": ""}},
      "location": ["地点"]
    }}
  ]
}}
```

请直接输出："""


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
    if use_cot:
        system_prompt = SYSTEM_PROMPT_COT
        user_prompt = USER_PROMPT_COT.format(tbox_schema=tbox_schema, text=text)
    else:
        system_prompt = SYSTEM_PROMPT
        user_prompt = USER_PROMPT_TEMPLATE.format(tbox_schema=tbox_schema, text=text)

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

    # TBox 约束过滤
    result = validate_against_tbox(result, tbox)

    return result


def validate_against_tbox(result: Dict, tbox: Dict) -> Dict:
    """验证结果是否符合 TBox 约束，过滤不合规的"""

    valid_relations = {r["name"] for r in tbox.get("relations", [])}
    valid_classes = {c["name"] for c in tbox.get("classes", [])}

    # 过滤三元组
    valid_triples = []
    filtered_count = 0
    for t in result.get("triples", []):
        pred = t.get("predicate", "")
        if pred in valid_relations:
            valid_triples.append(t)
        else:
            filtered_count += 1

    result["triples"] = valid_triples
    if filtered_count > 0:
        result["_tbox_filtered"] = filtered_count

    # 过滤实体（可选，不太严格）
    valid_entities = []
    for e in result.get("entities", []):
        etype = e.get("type", "")
        if etype in valid_classes or not etype:  # 允许无类型
            valid_entities.append(e)
    result["entities"] = valid_entities

    # 过滤事件
    valid_events = []
    for ev in result.get("events", []):
        etype = ev.get("event_type", "")
        if etype in valid_classes or not etype:
            valid_events.append(ev)
    result["events"] = valid_events

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

    parser.add_argument("--verification-threshold", type=float, default=0.7,
                        help="模糊匹配阈值（Gold 推荐 0.7，默认 0.7）")
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
    tbox_schema = format_tbox_for_prompt(tbox)
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
    total_tbox_filtered = 0
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
                n_tbox_filtered = result.get("_tbox_filtered", 0)
                total_triples += n_triples
                total_tbox_filtered += n_tbox_filtered

                # 统计幻觉过滤
                v_stats = result.get("_verification_stats", {})
                n_v_filtered = v_stats.get("filtered", 0)
                total_verification_filtered += n_v_filtered

                # 输出信息
                info_parts = [f"三元组={n_triples}"]
                if n_tbox_filtered > 0:
                    info_parts.append(f"TBox过滤={n_tbox_filtered}")
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
    print(f"   - TBox 过滤: {total_tbox_filtered}")
    print(f"   - 幻觉过滤: {total_verification_filtered}")
    print(f"📁 输出: {output_path}")


if __name__ == "__main__":
    main()
