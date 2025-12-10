"""
使用 Teacher LLM 生成黄金标注（events + triples），用于评估抽取质量。
增强点：
- CLI 优先，回退 cfg（llm/provider/model 等）；
- 兼容 JSON/JSONL eval_pool，支持 max-samples 裁剪；
- 去除代码块围栏，JSON 解析更鲁棒，错误样本保留 error 字段；
- 低温度、json_mode 确保输出稳定。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import yaml

from kg.llm_core import LLMFactory

GOLD_ANNOTATION_PROMPT = """
你是长江流域水旱灾害领域的知识图谱标注专家。

请仔细阅读以下文本，严格按照 TBox 定义标注：
1. 事件：识别所有灾害事件（事件类型必须来自 TBox）
2. 三元组：抽取所有符合 TBox 关系定义的 (subject, predicate, object)

TBox 关系列表：
{relations_list}

待标注文本：
\"\"\"
{text}
\"\"\"

请按 JSON 格式输出，结构示例：
{{
  "events": [
    {{
      "event_id": "evt_001",
      "event_type": "FloodEvent",
      "name": "事件名称",
      "time": {{"start_time": "", "end_time": ""}},
      "space": {{"provinces": [], "main_stream": []}},
      "impacts": {{}}
    }}
  ],
  "triples": [
    {{
      "subject": "主语",
      "predicate": "关系名（必须来自 TBox）",
      "object": "宾语",
      "evidence": "原文依据"
    }}
  ]
}}
"""


def _clean_json(text: str) -> str:
    """去除围栏等非 JSON 内容，返回纯 JSON 字符串。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[-1].strip().startswith("```"):
            cleaned = "\n".join(lines[1:-1])
        else:
            cleaned = "\n".join(lines[1:])
    return cleaned


def generate_gold_for_sample(text: str, tbox: Dict[str, Any], llm) -> Dict[str, Any]:
    """为单个样本生成黄金标注。"""
    relations_list = "\n".join(
        [f"- {r['name']} ({r.get('cn_name', '')}): {r.get('definition', '')}" for r in tbox.get("relations", [])]
    )
    prompt = GOLD_ANNOTATION_PROMPT.format(relations_list=relations_list, text=text)
    messages = [
        {"role": "system", "content": "你是专业的知识图谱标注专家，请严格按 JSON 格式输出。"},
        {"role": "user", "content": prompt},
    ]
    resp = llm.chat_messages(messages, json_mode=True)
    try:
        return json.loads(_clean_json(resp))
    except Exception:
        return {"events": [], "triples": [], "parse_error": True, "raw": resp}


def load_samples(path: Path, max_samples: int | None = None) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    samples.append(json.loads(line))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        samples = data if isinstance(data, list) else [data]
    return samples[:max_samples] if max_samples else samples


def main():
    parser = argparse.ArgumentParser(description="使用 Teacher LLM 生成黄金标注")
    parser.add_argument("--cfg", default="configs/cfg.yaml", help="配置文件（命令行优先）")
    parser.add_argument("--eval-pool", required=True, help="评估语料路径（JSON/JSONL，每条含 text/id）")
    parser.add_argument("--tbox", required=True, help="TBox 路径")
    parser.add_argument("--out", required=True, help="输出路径（JSON）")
    parser.add_argument("--max-samples", type=int, default=100, help="裁剪样本数，默认 100")
    parser.add_argument("--provider", default=None, help="LLM provider，默认取 cfg.llm.provider 或 env")
    parser.add_argument("--model", default=None, help="LLM 模型名，默认取 cfg.llm.model_name 或 env")
    parser.add_argument("--temperature", type=float, default=0.1, help="LLM 温度，默认 0.1 保证稳定")
    args = parser.parse_args()

    # 读取 cfg（CLI 优先）
    cfg = {}
    if Path(args.cfg).exists():
        try:
            cfg = yaml.safe_load(Path(args.cfg).read_text(encoding="utf-8")) or {}
        except Exception:
            cfg = {}
    cfg_llm = cfg.get("llm", {}) if isinstance(cfg, dict) else {}

    def pick(*vals, default=None):
        for v in vals:
            if v not in [None, ""]:
                return v
        return default

    llm_conf = {
        "provider": pick(args.provider, cfg_llm.get("provider"), default="openai"),
        "model_name": pick(args.model, cfg_llm.get("model_name"), default="gpt-4o"),
        "temperature": args.temperature,
        "enable_thinking": cfg_llm.get("enable_thinking", False),
    }
    # 从 cfg 读取 base_url
    if cfg_llm.get("base_url"):
        llm_conf["base_url"] = cfg_llm.get("base_url")

    llm = LLMFactory.create(llm_conf)
    tbox = json.loads(Path(args.tbox).read_text(encoding="utf-8"))

    samples = load_samples(Path(args.eval_pool), args.max_samples)
    print(f"[Gold] 待标注样本: {len(samples)} 条")

    results = []
    for i, sample in enumerate(samples):
        text = sample.get("text", "")
        sid = sample.get("id", f"sample_{i:04d}")
        print(f"[{i+1}/{len(samples)}] 标注 {sid} ...")
        try:
            ann = generate_gold_for_sample(text, tbox, llm)
            results.append(
                {
                    "id": sid,
                    "text": text,
                    "gold_events": ann.get("events", []),
                    "gold_triples": ann.get("triples", []),
                    "error": ann.get("parse_error", False),
                }
            )
        except Exception as e:
            results.append({"id": sid, "text": text, "gold_events": [], "gold_triples": [], "error": str(e)})
            print(f"  [ERROR] {e}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Gold] 完成，保存至 {out_path}")


if __name__ == "__main__":
    main()
