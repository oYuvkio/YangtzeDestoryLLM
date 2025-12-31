#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强版 Ground Truth 标注脚本 - 使用 Teacher LLM 自动生成黄金标注。

增强特性：
- 断点续跑：自动跳过已标注样本（按 doc_id 匹配）
- 调用间隔控制：避免触发限流
- 指数退避重试：遇到 429/超时自动重试
- JSONL 流式输出：边标注边保存
- 完整 TBox 信息：同时传递类和关系定义
- 配置记录：保存 *.config.json 便于复现
- 鲁棒 JSON 解析：提取响应中首个完整 JSON 对象
- 与 abox_metrics.py 格式对齐

使用示例:
    # 标注 dev 集（使用配置文件中的 LLM）
    python scripts/generate_gold_v2.py \
        --input data/p5_eval_pool/dev.jsonl \
        --tbox outputs/cq_pipeline/final/p4_tbox_enhanced.json \
        --out data/p5_eval_pool/dev_gold.jsonl

    # 标注 test 集（指定模型）
    python scripts/generate_gold_v2.py \
        --input data/p5_eval_pool/test.jsonl \
        --tbox outputs/cq_pipeline/final/p4_tbox_enhanced.json \
        --out data/p5_eval_pool/test_gold.jsonl \
        --model gpt-4o \
        --temperature 0.1

    # 断点续跑（自动检测已标注样本）
    python scripts/generate_gold_v2.py \
        --input data/p5_eval_pool/dev.jsonl \
        --tbox outputs/cq_pipeline/final/p4_tbox_enhanced.json \
        --out data/p5_eval_pool/dev_gold.jsonl \
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
SCRIPT_VERSION = "2.1.0"
PROMPT_VERSION = "v1"


# ==============================================================================
# 标注 Prompt 模板
# ==============================================================================
GOLD_ANNOTATION_SYSTEM = """你是长江流域水旱灾害领域的知识图谱标注专家。
你的任务是从文本中标注出所有灾害事件和知识三元组。
请严格按照给定的 TBox（本体模式）进行标注，确保：
1. event_type 必须来自 TBox 的类定义
2. predicate 必须来自 TBox 的关系定义
3. 时间格式使用 ISO 8601 (YYYY-MM-DD)
4. 每个三元组必须有原文依据（evidence）

重要：请只输出 JSON，不要添加任何解释性文字。"""

GOLD_ANNOTATION_USER = """请根据以下 TBox 定义，标注文本中的事件和三元组。

## TBox 事件类型（event_type 必须来自此列表）
{classes_list}

## TBox 关系定义（predicate 必须来自此列表）
{relations_list}

## 待标注文本
```
{text}
```

## 输出要求
请严格按以下 JSON 格式输出（只输出 JSON，不要添加任何其他文字）：

{{
  "events": [
    {{
      "event_id": "evt_序号",
      "event_type": "类名(必须来自TBox)",
      "name": "事件中文名称",
      "time": {{
        "start_time": "YYYY-MM-DD或空字符串",
        "end_time": "YYYY-MM-DD或空字符串"
      }},
      "space": {{
        "provinces": ["省份列表"],
        "main_stream": ["干流位置"],
        "tributaries": ["支流/湖泊"]
      }},
      "causes": ["致灾因子"],
      "impacts": {{
        "affected_population": "受灾人口",
        "deaths": "死亡人数",
        "direct_economic_loss": "直接经济损失"
      }},
      "responses": [
        {{"stage": "响应阶段", "measures": ["措施列表"]}}
      ]
    }}
  ],
  "triples": [
    {{
      "subject": "主语实体",
      "predicate": "关系名(必须来自TBox)",
      "object": "宾语实体",
      "event_id": "关联事件ID(可选)",
      "evidence": "原文支撑句"
    }}
  ]
}}

注意：
- 如果文本中没有明确的事件或三元组，返回空列表
- 不要虚构信息，只抽取文本中明确提及的内容
- evidence 必须是原文的直接引用或近似引用"""


# ==============================================================================
# 工具函数
# ==============================================================================
def extract_json_object(text: str) -> Optional[str]:
    """
    从文本中提取首个完整的 JSON 对象 {...}。

    处理以下情况：
    1. 纯 JSON
    2. ```json ... ``` 包裹的 JSON
    3. JSON 前后有解释性文字
    """
    text = text.strip()

    # 1. 尝试去除 markdown 代码块
    if "```" in text:
        # 匹配 ```json ... ``` 或 ``` ... ```
        pattern = r"```(?:json)?\s*([\s\S]*?)```"
        match = re.search(pattern, text)
        if match:
            text = match.group(1).strip()

    # 2. 查找首个完整的 JSON 对象 {...}
    # 使用括号匹配来找到完整的 JSON
    start_idx = text.find("{")
    if start_idx == -1:
        return None

    # 从 start_idx 开始，找到匹配的 }
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

    # 如果没找到匹配的，返回从 { 开始到末尾的内容（可能不完整）
    return text[start_idx:] if start_idx != -1 else None


def compute_file_hash(path: Path) -> str:
    """计算文件的 MD5 哈希值。"""
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()[:12]


def is_retryable_error(error: Exception) -> bool:
    """判断是否是可重试的错误（限流、超时等）。"""
    error_str = str(error).lower()
    retryable_keywords = [
        "429", "rate limit", "too many requests",
        "timeout", "timed out",
        "connection", "network",
        "server error", "500", "502", "503", "504",
    ]
    return any(kw in error_str for kw in retryable_keywords)


def build_tbox_context(tbox: Dict[str, Any]) -> Tuple[str, str]:
    """构建 TBox 上下文信息。"""
    # 构建类列表
    classes = tbox.get("classes", [])
    classes_lines = []
    for c in classes:
        name = c.get("name", "")
        cn_name = c.get("cn_name", "")
        definition = c.get("definition", "")
        parent = c.get("parent", "")
        line = f"- {name}"
        if cn_name:
            line += f" ({cn_name})"
        if parent:
            line += f" [继承自: {parent}]"
        if definition:
            line += f": {definition}"
        classes_lines.append(line)
    classes_list = "\n".join(classes_lines) if classes_lines else "（无类定义）"

    # 构建关系列表
    relations = tbox.get("relations", [])
    relations_lines = []
    for r in relations:
        name = r.get("name", "")
        cn_name = r.get("cn_name", "")
        definition = r.get("definition", "")
        domain = r.get("domain", "")
        range_ = r.get("range", "")
        line = f"- {name}"
        if cn_name:
            line += f" ({cn_name})"
        if domain and range_:
            line += f" [{domain} → {range_}]"
        if definition:
            line += f": {definition}"
        relations_lines.append(line)
    relations_list = "\n".join(relations_lines) if relations_lines else "（无关系定义）"

    return classes_list, relations_list


def generate_gold_for_sample(
    text: str,
    tbox: Dict[str, Any],
    llm,
    classes_list: str,
    relations_list: str,
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> Dict[str, Any]:
    """
    为单个样本生成黄金标注，带指数退避重试。

    Args:
        text: 待标注文本
        tbox: TBox 定义
        llm: LLM 客户端
        classes_list: 格式化的类列表
        relations_list: 格式化的关系列表
        max_retries: 最大重试次数
        base_delay: 基础退避延迟（秒）

    Returns:
        包含 events, triples 的字典，出错时包含 parse_error 等错误信息
    """
    user_prompt = GOLD_ANNOTATION_USER.format(
        classes_list=classes_list,
        relations_list=relations_list,
        text=text,
    )
    messages = [
        {"role": "system", "content": GOLD_ANNOTATION_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            resp = llm.chat_messages(messages, json_mode=True)

            # 提取 JSON
            json_str = extract_json_object(resp)
            if not json_str:
                return {
                    "events": [],
                    "triples": [],
                    "parse_error": True,
                    "error_msg": "无法从响应中提取 JSON 对象",
                    "raw_response": resp[:500],
                }

            parsed = json.loads(json_str)
            return {
                "events": parsed.get("events", []),
                "triples": parsed.get("triples", []),
                "parse_error": False,
            }

        except json.JSONDecodeError as e:
            return {
                "events": [],
                "triples": [],
                "parse_error": True,
                "error_msg": f"JSON 解析错误: {e}",
                "raw_response": resp[:500] if "resp" in locals() else "",
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

    # 所有重试都失败
    return {
        "events": [],
        "triples": [],
        "parse_error": True,
        "error_msg": f"LLM 调用失败: {last_error}",
        "raw_response": "",
    }


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
                        # 过滤空值
                        if doc_id:
                            processed.add(doc_id)
                    except json.JSONDecodeError:
                        continue
    return processed


def save_config(
    out_path: Path,
    args: argparse.Namespace,
    tbox_path: Path,
    llm_conf: Dict[str, Any],
    input_count: int,
    processed_count: int,
    success_count: int,
    error_count: int,
    elapsed: float,
) -> None:
    """保存配置记录文件，便于复现。"""
    config_path = out_path.with_suffix(".config.json")
    config = {
        "script_version": SCRIPT_VERSION,
        "prompt_version": PROMPT_VERSION,
        "timestamp": datetime.now().isoformat(),
        "input": {
            "path": str(args.input),
            "total_samples": input_count,
        },
        "tbox": {
            "path": str(args.tbox),
            "hash": compute_file_hash(tbox_path),
        },
        "llm": {
            "model": llm_conf.get("model_name"),
            "temperature": args.temperature,
            "provider": llm_conf.get("provider"),
        },
        "params": {
            "max_samples": args.max_samples,
            "resume": args.resume,
            "max_retries": args.max_retries,
            "sleep_min": args.sleep_min,
            "sleep_max": args.sleep_max,
        },
        "results": {
            "processed_count": processed_count,
            "success_count": success_count,
            "error_count": error_count,
            "elapsed_seconds": round(elapsed, 2),
        },
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 配置已保存到: {config_path}")


def main():
    parser = argparse.ArgumentParser(
        description="增强版 Ground Truth 标注脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", required=True, help="输入评测语料（JSONL）")
    parser.add_argument("--tbox", required=True, help="TBox 文件路径")
    parser.add_argument("--out", required=True, help="输出标注文件（JSONL）")
    parser.add_argument("--cfg", default="configs/cfg.yaml", help="配置文件")
    parser.add_argument("--model", default=None, help="LLM 模型名（覆盖配置）")
    parser.add_argument("--temperature", type=float, default=0.1, help="LLM 温度")
    parser.add_argument("--resume", action="store_true", help="断点续跑（跳过已标注）")
    parser.add_argument("--max-samples", type=int, default=None, help="最大标注数量")
    parser.add_argument("--max-retries", type=int, default=3, help="单样本最大重试次数")
    parser.add_argument("--sleep-min", type=float, default=1.0, help="调用间隔最小秒数")
    parser.add_argument("--sleep-max", type=float, default=3.0, help="调用间隔最大秒数")
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划，不实际标注")
    args = parser.parse_args()

    # 加载配置
    cfg = {}
    cfg_path = Path(args.cfg)
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg_llm = cfg.get("llm", {})

    # 构建 LLM 配置
    llm_conf = {
        "provider": cfg_llm.get("provider", "openai"),
        "model_name": args.model or cfg_llm.get("model_name", "gpt-4o"),
        "temperature": args.temperature,
        "base_url": cfg_llm.get("base_url"),
        "enable_thinking": cfg_llm.get("enable_thinking", False),
    }

    print("=" * 60)
    print(f"Ground Truth 自动标注脚本 v{SCRIPT_VERSION}")
    print("=" * 60)
    print(f"输入文件: {args.input}")
    print(f"TBox: {args.tbox}")
    print(f"输出文件: {args.out}")
    print(f"LLM 模型: {llm_conf['model_name']}")
    print(f"温度: {args.temperature}")
    print(f"断点续跑: {'是' if args.resume else '否'}")
    print(f"最大重试: {args.max_retries} 次")
    print(f"调用间隔: {args.sleep_min}-{args.sleep_max}s")
    print("=" * 60)

    # 加载 TBox
    tbox_path = Path(args.tbox)
    tbox = json.loads(tbox_path.read_text(encoding="utf-8"))
    classes_list, relations_list = build_tbox_context(tbox)
    print(f"TBox 加载完成: {len(tbox.get('classes', []))} 类, {len(tbox.get('relations', []))} 关系")
    print(f"TBox 哈希: {compute_file_hash(tbox_path)}")

    # 加载样本
    samples = load_samples(Path(args.input))
    input_count = len(samples)
    print(f"输入样本: {input_count} 条")

    # 限制数量
    if args.max_samples:
        samples = samples[:args.max_samples]
        print(f"限制为: {len(samples)} 条")

    # 断点续跑
    out_path = Path(args.out)
    processed_ids = set()
    if args.resume and out_path.exists():
        processed_ids = load_processed_ids(out_path)
        print(f"已处理: {len(processed_ids)} 条（将跳过）")

    # 过滤待处理样本（保持原始顺序，只过滤已处理的）
    to_process = []
    for sample in samples:
        doc_id = sample.get("id", sample.get("doc_id", ""))
        if not doc_id:
            # 如果没有 id，生成一个基于内容的哈希作为 id
            doc_id = hashlib.md5(sample.get("text", "")[:200].encode()).hexdigest()[:12]
            sample["id"] = doc_id
        if doc_id not in processed_ids:
            to_process.append(sample)
    print(f"待标注: {len(to_process)} 条")

    if args.dry_run:
        print("\n[Dry Run] 不执行实际标注")
        return

    if not to_process:
        print("\n所有样本已标注完成！")
        return

    # 创建 LLM 客户端
    llm = LLMFactory.create(llm_conf)

    # 确保输出目录存在
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 开始标注
    print("\n开始标注...")
    success_count = 0
    error_count = 0
    start_time = datetime.now()

    try:
        with out_path.open("a", encoding="utf-8") as out_f:
            for i, sample in enumerate(to_process):
                doc_id = sample.get("id", sample.get("doc_id", f"sample_{i:04d}"))
                text = sample.get("text", "")

                print(f"[{i+1}/{len(to_process)}] 标注 {doc_id}...", end=" ", flush=True)

                result = generate_gold_for_sample(
                    text=text,
                    tbox=tbox,
                    llm=llm,
                    classes_list=classes_list,
                    relations_list=relations_list,
                    max_retries=args.max_retries,
                )

                # 构建输出记录（与 abox_metrics.py 格式对齐）
                output_record = {
                    "doc_id": doc_id,
                    "text": text,
                    "events": result["events"],
                    "triples": result["triples"],
                }

                if result.get("parse_error"):
                    output_record["_parse_error"] = True
                    output_record["_error_msg"] = result.get("error_msg", "")
                    if result.get("raw_response"):
                        output_record["_raw_response"] = result["raw_response"]
                    error_count += 1
                    print(f"⚠️ 解析错误: {result.get('error_msg', '')[:50]}")
                else:
                    success_count += 1
                    n_events = len(result["events"])
                    n_triples = len(result["triples"])
                    print(f"✅ {n_events} 事件, {n_triples} 三元组")

                # 写入输出文件
                out_f.write(json.dumps(output_record, ensure_ascii=False) + "\n")
                out_f.flush()

                # 调用间隔
                if i < len(to_process) - 1:
                    sleep_time = random.uniform(args.sleep_min, args.sleep_max)
                    time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断，已保存已完成的标注")
    finally:
        # 统计
        elapsed = (datetime.now() - start_time).total_seconds()
        processed_count = success_count + error_count

        print("\n" + "=" * 60)
        print("标注完成！")
        print("=" * 60)
        print(f"成功: {success_count} 条")
        print(f"错误: {error_count} 条")
        if processed_count > 0:
            print(f"耗时: {elapsed:.1f}s ({elapsed/processed_count:.2f}s/条)")
        print(f"输出: {out_path}")

        # 保存配置记录
        save_config(
            out_path=out_path,
            args=args,
            tbox_path=tbox_path,
            llm_conf=llm_conf,
            input_count=input_count,
            processed_count=processed_count,
            success_count=success_count,
            error_count=error_count,
            elapsed=elapsed,
        )

        # 关闭 LLM 客户端
        llm.close()


if __name__ == "__main__":
    main()
