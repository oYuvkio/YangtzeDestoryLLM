"""
基线方法对比实验：
- 支持多种零样本/指南式 Prompt（Zero-Shot/ChatIE/GoLLIE-Style）
- 运行基线 → 保存预测 → 调用 run_full_evaluation 生成报告与摘要
- 支持 JSON/JSONL 输入，最大样本数可裁剪，CLI > cfg 默认
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import yaml

from kg.llm_core import LLMFactory
from scripts.run_full_evaluation import run_evaluation


# ======================
# Prompt 定义
# ======================
BASELINE_PROMPTS = {
    "Zero-Shot": """
请从以下文本中抽取与水旱灾害相关的事件和三元组关系。

文本：
\"\"\"{text}\"\"\"

输出 JSON 格式：
{{"events": [...], "triples": [{{"subject": "", "predicate": "", "object": ""}}]}}
""",
    "ChatIE": """
我需要你帮我从文本中抽取灾害信息。

第一步：识别所有灾害事件（洪水、干旱等）
第二步：提取每个事件的时间、地点、影响
第三步：抽取事件之间或事件与其他实体之间的关系

文本：
\"\"\"{text}\"\"\"

请按 JSON 格式输出。
""",
    "GoLLIE-Style": """
## 任务：水旱灾害知识抽取

### 抽取指南：
1. 事件类型：洪水事件(FloodEvent)、干旱事件(DroughtEvent)
2. 常见关系：
   - has_cause: 致灾因子
   - affects_region: 影响区域
   - has_impact: 造成影响
   - triggers_response: 触发响应

### 输入文本：
\"\"\"{text}\"\"\"

### 输出要求：
按照指南抽取事件和三元组，输出 JSON 格式。
""",
}


# ======================
# 基线运行
# ======================
def _clean_json_text(resp: str) -> str:
    """去除围栏，保持纯 JSON。"""
    cleaned = resp.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[-1].strip().startswith("```"):
            cleaned = "\n".join(lines[1:-1])
        else:
            cleaned = "\n".join(lines[1:])
    return cleaned


def run_baseline(
    baseline_name: str,
    test_samples: List[Dict[str, Any]],
    llm_config: Dict[str, Any],
    output_path: Path,
) -> List[Dict[str, Any]]:
    """运行单个基线方法，返回预测列表。"""
    prompt_template = BASELINE_PROMPTS.get(baseline_name)
    if not prompt_template:
        raise ValueError(f"未知基线: {baseline_name}")

    llm = LLMFactory.create(llm_config)
    results: List[Dict[str, Any]] = []

    for i, sample in enumerate(test_samples):
        text = sample.get("text", "")
        prompt = prompt_template.format(text=text)
        try:
            resp = llm.chat_messages(
                [
                    {"role": "system", "content": "你是知识抽取专家，请严格按 JSON 输出。"},
                    {"role": "user", "content": prompt},
                ],
                json_mode=True,
            )
            cleaned = _clean_json_text(resp)
            parsed = json.loads(cleaned)
            results.append(
                {
                    "id": sample.get("id", f"sample_{i}"),
                    "events": parsed.get("events", []),
                    "triples": parsed.get("triples", []),
                }
            )
        except Exception as e:
            print(f"[{baseline_name}][{i}] Error: {e}")
            results.append(
                {
                    "id": sample.get("id", f"sample_{i}"),
                    "events": [],
                    "triples": [],
                    "error": str(e),
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


# ======================
# 主流程
# ======================
def main():
    parser = argparse.ArgumentParser(description="运行基线对比实验")
    parser.add_argument("--cfg", default="configs/cfg.yaml", help="配置文件（命令行优先）")
    parser.add_argument(
        "--baselines",
        nargs="+",
        default=["Zero-Shot", "ChatIE", "GoLLIE-Style"],
        help="要运行的基线列表",
    )
    parser.add_argument("--test-data", required=True, help="测试数据路径（JSON 或 JSONL）")
    parser.add_argument("--gold", required=True, help="黄金标注路径（JSON/JSONL）")
    parser.add_argument("--tbox", required=True, help="TBox 路径（用于一致性计算）")
    parser.add_argument("--cqs", required=True, help="测试 CQ 路径")
    parser.add_argument("--out-dir", default="outputs/baselines", help="输出目录")
    parser.add_argument("--provider", default=None, help="LLM provider，默认取 cfg 或 env")
    parser.add_argument("--model", default=None, help="LLM 模型名，默认取 cfg 或 env")
    parser.add_argument("--temperature", type=float, default=0.1, help="LLM 温度")
    parser.add_argument("--max-samples", type=int, default=100, help="裁剪测试样本数")
    args = parser.parse_args()

    # 读取 cfg（CLI 优先）
    cfg = {}
    if Path(args.cfg).exists():
        try:
            cfg = yaml.safe_load(Path(args.cfg).read_text(encoding="utf-8")) or {}
        except Exception:
            cfg = {}

    def pick(*vals, default=None):
        for v in vals:
            if v not in [None, ""]:
                return v
        return default

    cfg_llm = cfg.get("llm", {}) if isinstance(cfg, dict) else {}
    llm_config = {
        "provider": pick(args.provider, cfg_llm.get("provider"), default="zhipu"),
        "model_name": pick(args.model, cfg_llm.get("model_name"), default="GLM-4.5-Air"),
        "temperature": args.temperature,
        "enable_thinking": cfg_llm.get("enable_thinking", False),
    }
    # 从 cfg 读取 base_url
    if cfg_llm.get("base_url"):
        llm_config["base_url"] = cfg_llm.get("base_url")

    # 加载测试数据（JSON/JSONL）
    test_samples: List[Dict[str, Any]] = []
    test_path = Path(args.test_data)
    if test_path.suffix.lower() == ".jsonl":
        with test_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    test_samples.append(json.loads(line))
    else:
        data = json.loads(test_path.read_text(encoding="utf-8"))
        test_samples = data if isinstance(data, list) else [data]
    if args.max_samples:
        test_samples = test_samples[: args.max_samples]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_reports: Dict[str, Any] = {}

    for baseline in args.baselines:
        print(f"\n[Baseline] 运行 {baseline} ...")
        preds_path = out_dir / f"{baseline}_preds.json"
        run_baseline(baseline, test_samples, llm_config, preds_path)

        report_path = out_dir / f"{baseline}_report.json"
        report = run_evaluation(
            tbox_path=args.tbox,
            test_cqs_path=args.cqs,
            gold_annotations_path=args.gold,
            predictions_path=str(preds_path),
            output_report_path=str(report_path),
        )
        all_reports[baseline] = report.get("summary", report)

    # 如果已有“我方”报告，可合并展示
    ours_report_path = out_dir.parent / "evaluation_report.json"
    if ours_report_path.exists():
        ours_report = json.loads(ours_report_path.read_text(encoding="utf-8"))
        all_reports["Ours"] = ours_report.get("summary", ours_report)

    # 生成对比表格
    print("\n" + "=" * 80)
    print("基线对比结果")
    print("=" * 80)
    print(f"{'方法':<15} {'RR':>8} {'CQ@0.5':>10} {'Event-F1':>10} {'Triple-F1':>12} {'Consist':>10}")
    print("-" * 80)
    for name, summary in all_reports.items():
        print(
            f"{name:<15} {summary.get('RR', 0):>8.4f} {summary.get('CQ-Cov@0.5', 0):>10.4f} "
            f"{summary.get('Event-F1', 0):>10.4f} {summary.get('Triple-F1', 0):>12.4f} "
            f"{summary.get('TBox-Consist', 0):>10.4f}"
        )

    summary_path = out_dir / "comparison_summary.json"
    summary_path.write_text(json.dumps(all_reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n汇总已保存至: {summary_path}")


if __name__ == "__main__":
    main()
