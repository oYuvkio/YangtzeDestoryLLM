#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立Schema黄金标注生成脚本

重要设计原则（参考 txts/project/kg/标注/*.md）：
┌───────────────────────────────────────────────────────────────────────────┐
│ 标注Schema与项目Schema完全独立，避免循环依赖，确保评估公平性              │
├───────────────────────────────────────────────────────────────────────────┤
│ 标注Schema：预定义的9种通用实体类型 + 9种通用关系类型（固定）            │
│ 项目Schema：CQ驱动 + 文献增强生成的Schema（动态）                         │
│ 评估时：通过映射表将抽取结果对齐到标注Schema                              │
└───────────────────────────────────────────────────────────────────────────┘

使用方式:
    # 标注测试集
    python scripts/generate_gold_independent.py \
        --input data/p5_eval_pool/test.jsonl \
        --out data/p5_eval_pool/gold_independent.jsonl

    # 指定模型（推荐使用最强模型）
    python scripts/generate_gold_independent.py \
        --input data/p5_eval_pool/test.jsonl \
        --out data/p5_eval_pool/gold_independent.jsonl \
        --model gpt-4o \
        --temperature 0.1

    # 断点续跑
    python scripts/generate_gold_independent.py \
        --input data/p5_eval_pool/test.jsonl \
        --out data/p5_eval_pool/gold_independent.jsonl \
        --resume
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

# 项目路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kg.llm_core import LLMFactory


# ==============================================================================
# 版本信息
# ==============================================================================
SCRIPT_VERSION = "3.0.0"
PROMPT_VERSION = "independent_v1"


# ==============================================================================
# 预定义的通用Schema（独立于项目Schema）
# ==============================================================================

# 通用实体类型
STANDARD_ENTITY_TYPES = """
请识别以下类型的实体：
- TIME：时间表达（年份、日期、时间段，如"1998年8月"、"7月至9月"）
- LOCATION：地理位置（省市、河流、湖泊、水库、水文站点，如"长江中下游"、"沙市站"）
- EVENT：灾害事件名称（如"1998年长江特大洪水"）
- VALUE：数值指标（水位、流量、损失数据，如"45.22米"、"2.23亿人"）
- CAUSE：致灾因子（如"持续性强降雨"、"上游来水偏多"）
- MEASURE：应急措施/响应（如"启动防汛II级应急响应"、"启用分洪区"）
- FACILITY：水利工程设施（如"三峡水库"、"荆江分洪区"）
- ORG：机构组织（如"国家防总"、"水利部"）
- IMPACT：灾害影响描述（如"倒塌房屋680万间"）
"""

# 通用关系类型
STANDARD_RELATION_TYPES = """
请识别实体间的以下关系：

| 关系名称 | 中文含义 | 主语类型 | 宾语类型 | 示例 |
|---------|---------|---------|---------|------|
| occurs_at | 发生于（时间） | EVENT | TIME | 1998年长江洪水 - occurs_at - 1998年 |
| located_in | 位于/发生地点 | EVENT/FACILITY | LOCATION | 沙市站 - located_in - 长江干流 |
| has_cause | 由...引起 | EVENT | CAUSE | 洪水 - has_cause - 强降雨 |
| causes_impact | 造成影响 | EVENT | IMPACT/VALUE | 洪水 - causes_impact - 死亡4150人 |
| has_value | 测量值为 | FACILITY/LOCATION | VALUE | 沙市站 - has_value - 水位45.22米 |
| triggers | 触发 | EVENT/VALUE | MEASURE | 超警戒水位 - triggers - 启动应急响应 |
| implements | 实施/采取 | ORG | MEASURE | 国家防总 - implements - 启动I级响应 |
| part_of | 属于/包含于 | LOCATION | LOCATION | 洞庭湖 - part_of - 长江流域 |
| affects | 影响/波及 | EVENT | LOCATION | 洪水 - affects - 湖北省 |

**注意**：如果文中存在上表未列出但明确表达的关系，可以自定义关系名（使用英文下划线格式），但需在annotation_notes中说明。
"""


# ==============================================================================
# 黄金标注Prompt（独立于项目Schema）
# ==============================================================================

GOLD_ANNOTATION_SYSTEM_INDEPENDENT = """你是一名资深的水旱灾害领域知识图谱标注专家。
你的任务是为给定文本生成**高质量的黄金标准标注**。

【核心原则】
1. **完整性**：尽可能抽取所有有意义的实体和关系
2. **准确性**：所有标注必须有原文依据，实体必须是原文的**精确子串**
3. **规范性**：严格遵循输出格式要求

请严格按 JSON 格式输出，不要添加任何解释性文字。"""


GOLD_ANNOTATION_USER_INDEPENDENT = """请从以下文本中标注所有灾害事件、实体和三元组。

---

【预定义实体类型】

{entity_types}

---

【预定义关系类型】

{relation_types}

---

【标注步骤】

**Step 1: 实体识别**
逐句阅读文本，识别所有符合上述类型的实体。
注意：实体必须是原文的**精确子串**，不可改写。

**Step 2: 关系抽取**
对于识别出的实体对，判断它们之间是否存在上述预定义关系。
只标注**原文明确表达**的关系，不要推断。

**Step 3: 自我校验**【必须执行】
对每个三元组检查：
- subject是否在原文中原样出现？
- object是否在原文中原样出现？
- 原文是否明确支持这个关系？

如果任一检查不通过，请**删除**该三元组。

---

【待标注文本】

```
{text}
```

---

【输出格式】

请严格按以下 JSON 格式输出（只输出 JSON，不要添加任何其他文字）：

{{
  "entities": [
    {{"name": "实体名（原文子串）", "type": "实体类型"}}
  ],
  "triples": [
    {{
      "subject": "主语（原文子串）",
      "subject_type": "主语类型",
      "predicate": "关系类型",
      "object": "宾语（原文子串）",
      "object_type": "宾语类型",
      "evidence": "原文支撑句",
      "confidence": "high/medium/low"
    }}
  ],
  "events": [
    {{
      "name": "事件名称",
      "type": "FloodEvent/DroughtEvent/Other",
      "time": {{
        "start_time": "YYYY-MM-DD或空字符串",
        "end_time": "YYYY-MM-DD或空字符串"
      }},
      "location": ["地点列表"],
      "causes": ["致灾因子"],
      "impacts": ["影响列表"]
    }}
  ],
  "annotation_notes": "标注备注（如自定义关系说明、不确定之处等）"
}}

**置信度说明**：
- high：关系在原文中直接、明确表述
- medium：关系需要简单推理但有明确依据
- low：关系较隐含或不太确定

请直接输出JSON："""


# ==============================================================================
# 关系映射表（用于评估时对齐）
# ==============================================================================

RELATION_MAPPING = {
    # 标注Schema -> 项目Schema 的可能映射
    # 格式：标注中的关系 -> [项目Schema中可能的关系列表]

    # 时间关系
    "occurs_at": ["occurs_at", "has_time", "start_time", "occurs_at_time"],
    "发生时间": ["occurs_at", "has_time", "start_time"],
    "开始时间": ["occurs_at", "start_time"],
    "结束时间": ["end_time"],

    # 空间关系
    "located_in": ["located_in", "occurs_in", "located_at"],
    "affects": ["affects", "affects_region", "impacts"],
    "part_of": ["part_of", "belongs_to", "contained_in"],
    "发生地点": ["located_in", "affects_region", "occurs_in"],
    "影响区域": ["affects_region", "affects", "impacts"],
    "位于": ["located_in"],

    # 因果关系
    "has_cause": ["has_cause", "caused_by", "has_hazard_factor"],
    "causes_impact": ["causes_impact", "has_impact", "results_in", "causes"],
    "triggers": ["triggers", "triggers_response", "activates"],
    "导致": ["has_cause", "causes", "leads_to"],
    "造成": ["causes", "has_impact", "results_in", "causes_impact"],
    "引发": ["triggers", "causes"],

    # 数值关系
    "has_value": ["has_value", "has_measurement", "water_level", "discharge"],
    "水位为": ["water_level", "has_value"],
    "流量为": ["discharge", "has_value"],
    "损失金额": ["economic_loss", "has_loss", "direct_economic_loss"],
    "受灾人口": ["affected_population", "has_impact"],
    "死亡人数": ["death_toll", "deaths", "has_impact"],

    # 措施关系
    "implements": ["implements", "takes_action", "executes"],
    "采取措施": ["has_response", "takes_action", "implements"],
    "启动响应": ["triggers_response", "has_response", "activates_response"],
}


def get_standard_schema_relations() -> List[str]:
    """获取标准Schema中的关系列表"""
    return [
        "occurs_at", "located_in", "has_cause", "causes_impact",
        "has_value", "triggers", "implements", "part_of", "affects"
    ]


# ==============================================================================
# 工具函数
# ==============================================================================

def extract_json_object(text: str) -> Optional[str]:
    """从文本中提取首个完整的 JSON 对象 {...}。"""
    text = text.strip()

    # 1. 尝试去除 markdown 代码块
    if "```" in text:
        pattern = r"```(?:json)?\s*([\s\S]*?)```"
        match = re.search(pattern, text)
        if match:
            text = match.group(1).strip()

    # 2. 查找首个完整的 JSON 对象 {...}
    start_idx = text.find("{")
    if start_idx == -1:
        return None

    brace_count = 0
    in_string = False
    escape_next = False

    for i, char in enumerate(text[start_idx:], start=start_idx):
        if escape_next:
            escape_next = False
            continue
        if char == "\\":
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0:
                return text[start_idx:i+1]

    return text[start_idx:] if start_idx != -1 else None


def compute_file_hash(path: Path) -> str:
    """计算文件的 MD5 哈希值。"""
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()[:12]


def is_retryable_error(error: Exception) -> bool:
    """判断是否是可重试的错误。"""
    error_str = str(error).lower()
    retryable_keywords = [
        "429", "rate limit", "too many requests",
        "timeout", "timed out",
        "connection", "network",
        "server error", "500", "502", "503", "504",
    ]
    return any(kw in error_str for kw in retryable_keywords)


def generate_gold_for_sample(
    text: str,
    llm,
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> Dict[str, Any]:
    """
    为单个样本生成黄金标注（使用独立Schema）。

    Args:
        text: 待标注文本
        llm: LLM 客户端
        max_retries: 最大重试次数
        base_delay: 基础退避延迟（秒）

    Returns:
        包含 entities, triples, events 的字典
    """
    user_prompt = GOLD_ANNOTATION_USER_INDEPENDENT.format(
        entity_types=STANDARD_ENTITY_TYPES,
        relation_types=STANDARD_RELATION_TYPES,
        text=text,
    )
    messages = [
        {"role": "system", "content": GOLD_ANNOTATION_SYSTEM_INDEPENDENT},
        {"role": "user", "content": user_prompt},
    ]

    last_error = None
    resp = ""

    for attempt in range(max_retries + 1):
        try:
            resp = llm.chat_messages(messages, json_mode=True)

            # 提取 JSON
            json_str = extract_json_object(resp)
            if not json_str:
                return {
                    "entities": [],
                    "triples": [],
                    "events": [],
                    "parse_error": True,
                    "error_msg": "无法从响应中提取 JSON 对象",
                    "raw_response": resp[:500],
                }

            parsed = json.loads(json_str)

            # 标准化输出格式
            result = {
                "entities": parsed.get("entities", []),
                "triples": parsed.get("triples", []),
                "events": parsed.get("events", []),
                "annotation_notes": parsed.get("annotation_notes", ""),
                "parse_error": False,
            }

            # 转换为 abox_metrics 兼容格式
            result = convert_to_abox_format(result)

            return result

        except json.JSONDecodeError as e:
            return {
                "entities": [],
                "triples": [],
                "events": [],
                "parse_error": True,
                "error_msg": f"JSON 解析错误: {e}",
                "raw_response": resp[:500] if resp else "",
            }
        except Exception as e:
            last_error = e
            if is_retryable_error(e) and attempt < max_retries:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"\n  ⚠️ 重试 {attempt + 1}/{max_retries}（等待 {delay:.1f}s）: {e}")
                time.sleep(delay)
                continue
            else:
                break

    return {
        "entities": [],
        "triples": [],
        "events": [],
        "parse_error": True,
        "error_msg": f"LLM 调用失败: {last_error}",
        "raw_response": "",
    }


def convert_to_abox_format(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    将标注结果转换为 abox_metrics.py 兼容格式。

    abox_metrics 期望的格式:
    {
        "events": [{"name": ..., "event_type": ..., "time": {...}}],
        "triples": [{"subject": ..., "predicate": ..., "object": ...}]
    }
    """
    # 转换 events
    converted_events = []
    for evt in result.get("events", []):
        converted_evt = {
            "name": evt.get("name", ""),
            "event_type": evt.get("type", "DisasterEvent"),
            "time": evt.get("time", {"start_time": "", "end_time": ""}),
        }
        # 保留其他字段
        if "location" in evt:
            converted_evt["location"] = evt["location"]
        if "causes" in evt:
            converted_evt["causes"] = evt["causes"]
        if "impacts" in evt:
            converted_evt["impacts"] = evt["impacts"]
        converted_events.append(converted_evt)

    # 转换 triples（简化格式）
    converted_triples = []
    for triple in result.get("triples", []):
        converted_triple = {
            "subject": triple.get("subject", ""),
            "predicate": triple.get("predicate", ""),
            "object": triple.get("object", ""),
        }
        # 保留可选字段
        if "evidence" in triple:
            converted_triple["evidence"] = triple["evidence"]
        if "confidence" in triple:
            converted_triple["confidence"] = triple["confidence"]
        converted_triples.append(converted_triple)

    result["events"] = converted_events
    result["triples"] = converted_triples

    return result


def load_samples(path: Path) -> List[Dict[str, Any]]:
    """加载样本（支持 JSON 和 JSONL）。"""
    samples = []
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    samples.append(json.loads(line))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        samples = data if isinstance(data, list) else [data]
    return samples


def load_processed_ids(out_path: Path) -> Set[str]:
    """加载已处理的样本 ID（用于断点续跑）。"""
    processed = set()
    if out_path.exists():
        with out_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        item = json.loads(line)
                        doc_id = item.get("doc_id", "")
                        if doc_id:
                            processed.add(doc_id)
                    except json.JSONDecodeError:
                        continue
    return processed


def save_config(
    out_path: Path,
    args: argparse.Namespace,
    input_count: int,
    processed_count: int,
    success_count: int,
    error_count: int,
    elapsed: float,
) -> None:
    """保存配置记录文件。"""
    config_path = out_path.with_suffix(".config.json")
    config = {
        "script_version": SCRIPT_VERSION,
        "prompt_version": PROMPT_VERSION,
        "schema_type": "independent",  # 标记使用独立Schema
        "timestamp": datetime.now().isoformat(),
        "input": {
            "path": str(args.input),
            "total_samples": input_count,
        },
        "llm": {
            "model": args.model,
            "temperature": args.temperature,
        },
        "output": {
            "path": str(out_path),
            "processed": processed_count,
            "success": success_count,
            "errors": error_count,
        },
        "elapsed_seconds": round(elapsed, 2),
        "standard_schema": {
            "entity_types": [
                "TIME", "LOCATION", "EVENT", "VALUE", "CAUSE",
                "MEASURE", "FACILITY", "ORG", "IMPACT"
            ],
            "relation_types": get_standard_schema_relations(),
        },
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📋 配置已保存: {config_path}")


# ==============================================================================
# 主流程
# ==============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用独立Schema生成黄金标注（避免与项目Schema循环依赖）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 标注测试集
    python scripts/generate_gold_independent.py \\
        --input data/p5_eval_pool/test.jsonl \\
        --out data/p5_eval_pool/gold_independent.jsonl

    # 使用 GPT-4o 标注
    python scripts/generate_gold_independent.py \\
        --input data/p5_eval_pool/test.jsonl \\
        --out data/p5_eval_pool/gold_independent.jsonl \\
        --model gpt-4o

    # 断点续跑
    python scripts/generate_gold_independent.py \\
        --input data/p5_eval_pool/test.jsonl \\
        --out data/p5_eval_pool/gold_independent.jsonl \\
        --resume
        """,
    )

    parser.add_argument("--input", required=True, help="输入文件路径（JSONL 或 JSON）")
    parser.add_argument("--out", required=True, help="输出文件路径（JSONL）")
    parser.add_argument("--model", default="", help="LLM 模型名称（留空使用配置文件默认值）")
    parser.add_argument("--temperature", type=float, default=0.1, help="温度参数（默认 0.1）")
    parser.add_argument("--resume", action="store_true", help="断点续跑（跳过已标注样本）")
    parser.add_argument("--interval", type=float, default=1.0, help="调用间隔秒数（默认 1.0）")
    parser.add_argument("--max-retries", type=int, default=3, help="最大重试次数（默认 3）")
    parser.add_argument("--cfg", default="configs/cfg.yaml", help="配置文件路径")
    parser.add_argument("--limit", type=int, default=0, help="最多处理样本数（0=不限制）")

    return parser.parse_args()


def main():
    args = parse_args()

    input_path = Path(args.input)
    out_path = Path(args.out)

    if not input_path.exists():
        print(f"❌ 输入文件不存在: {input_path}")
        sys.exit(1)

    # 加载配置
    cfg = {}
    cfg_path = Path(args.cfg)
    if cfg_path.exists():
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            print(f"⚠️ 配置文件加载失败: {e}")

    # 初始化 LLM
    llm_cfg = cfg.get("llm", {})
    if args.model:
        llm_cfg["model"] = args.model
    llm_cfg["temperature"] = args.temperature

    print("=" * 60)
    print("🏷️  独立Schema黄金标注生成器")
    print("=" * 60)
    print(f"📁 输入: {input_path}")
    print(f"📁 输出: {out_path}")
    print(f"🤖 模型: {llm_cfg.get('model', '默认')}")
    print(f"🌡️  温度: {args.temperature}")
    print(f"📋 Schema类型: 独立通用Schema（9种实体类型 + 9种关系类型）")
    print("=" * 60)

    llm = LLMFactory.create(llm_cfg)

    # 加载样本
    samples = load_samples(input_path)
    print(f"\n📊 加载样本: {len(samples)} 条")

    # 断点续跑
    processed_ids = set()
    if args.resume and out_path.exists():
        processed_ids = load_processed_ids(out_path)
        print(f"📌 断点续跑: 已处理 {len(processed_ids)} 条")

    # 过滤待处理样本
    pending_samples = []
    for s in samples:
        doc_id = s.get("doc_id", s.get("id", ""))
        if doc_id not in processed_ids:
            pending_samples.append(s)

    if args.limit > 0:
        pending_samples = pending_samples[:args.limit]

    print(f"📝 待处理: {len(pending_samples)} 条")

    if not pending_samples:
        print("\n✅ 无待处理样本，退出")
        return

    # 确保输出目录存在
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 开始标注
    start_time = time.time()
    success_count = 0
    error_count = 0

    # 打开输出文件（追加模式）
    mode = "a" if args.resume else "w"
    with out_path.open(mode, encoding="utf-8") as f_out:
        for idx, sample in enumerate(pending_samples):
            doc_id = sample.get("doc_id", sample.get("id", f"doc_{idx}"))
            text = sample.get("text", sample.get("content", ""))

            if not text:
                print(f"  ⚠️ [{idx+1}/{len(pending_samples)}] {doc_id}: 空文本，跳过")
                continue

            print(f"  📝 [{idx+1}/{len(pending_samples)}] {doc_id}...", end="", flush=True)

            # 生成标注
            result = generate_gold_for_sample(
                text=text,
                llm=llm,
                max_retries=args.max_retries,
            )

            # 添加元信息
            result["doc_id"] = doc_id
            result["source_text"] = text[:500] + "..." if len(text) > 500 else text

            # 写入输出
            f_out.write(json.dumps(result, ensure_ascii=False) + "\n")
            f_out.flush()

            if result.get("parse_error"):
                error_count += 1
                print(f" ❌ 错误: {result.get('error_msg', '未知')[:50]}")
            else:
                success_count += 1
                n_events = len(result.get("events", []))
                n_triples = len(result.get("triples", []))
                print(f" ✅ 事件={n_events}, 三元组={n_triples}")

            # 调用间隔
            if idx < len(pending_samples) - 1:
                time.sleep(args.interval)

    elapsed = time.time() - start_time

    # 统计输出
    print("\n" + "=" * 60)
    print("📊 标注完成统计")
    print("=" * 60)
    print(f"✅ 成功: {success_count}")
    print(f"❌ 失败: {error_count}")
    print(f"⏱️  耗时: {elapsed:.1f} 秒")
    print(f"📁 输出: {out_path}")

    # 保存配置
    save_config(
        out_path=out_path,
        args=args,
        input_count=len(samples),
        processed_count=len(processed_ids) + success_count + error_count,
        success_count=success_count,
        error_count=error_count,
        elapsed=elapsed,
    )

    print("\n" + "=" * 60)
    print("💡 后续步骤")
    print("=" * 60)
    print("1. 检查标注质量: less", out_path)
    print("2. 运行评估时需要使用关系映射")
    print("3. 评估命令示例:")
    print(f"   python tools/abox_metrics.py \\")
    print(f"       --gold {out_path} \\")
    print(f"       --pred outputs/kg_extraction/predictions.json \\")
    print(f"       --tbox outputs/cq_pipeline/final/p4_tbox_augmented.json \\")
    print(f"       --out outputs/evaluation/metrics.json")


if __name__ == "__main__":
    main()
