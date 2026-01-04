#!/usr/bin/env python3
"""
黄金标注二次审查脚本

功能：
1. 合并多个标注文件
2. 过滤 parse_error=True 的样本
3. 调用 LLM 审查每个样本是否适合作为测试用例
4. 输出审查通过/拒绝的样本和统计报告

使用方式：
    python scripts/review_gold_annotations.py \
        --input data/p5_eval_pool/gold_independent_v1.jsonl \
                data/p5_eval_pool/gold_failed_retry_v1.jsonl \
        --out-accepted data/p5_eval_pool/gold_reviewed.jsonl \
        --out-rejected data/p5_eval_pool/gold_rejected.jsonl \
        --model gpt-4o-mini \
        --min-score 3 \
        --resume
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 添加项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from kg.llm_core import LLMFactory

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


# =============================================================================
# 审查 Prompt
# =============================================================================
REVIEW_PROMPT = """你是一名严格的知识图谱数据审计员，负责筛除政治宣传、会议通稿、空泛新闻等低价值样本。

请审查以下样本是否适合作为“长江流域水旱灾害知识图谱抽取”的测试用例。

【审查标准（必须全部满足才能通过）】
1. 事实性：包含具体灾害事件/水文事实（时间、地点、数值、影响）。
2. 客观性：以事实陈述为主，不是主观评价或口号。
3. 领域价值：三元组/事件体现水旱灾害领域信息，而非泛行政或宣传性内容。
4. 非敏感：不包含政治人物活动、意识形态争论或明显政治宣传。

【不合格示例特征】
- 纯政策宣传、领导讲话、会议纪要、工作汇报、新闻导语
- 只描述“贯彻落实/部署安排”等，无具体灾害事实
- 抽取三元组仅为行政信息（如“会议-召开-时间”）

【待审查样本】
原文：
{source_text}

已标注实体数：{entity_count}
已标注关系数：{triple_count}
已标注事件数：{event_count}

已抽取事件（截断）：
{events_preview}

已抽取三元组（截断）：
{triples_preview}

【输出要求】
只输出 JSON（不要Markdown、不要多余文字）：
{{
  "decision": "accept" 或 "reject",
  "reason": "简短说明原因（30字以内）",
  "quality_score": 1-5,
  "content_type": "disaster_record" 或 "policy" 或 "news" 或 "meeting" 或 "speech" 或 "other",
  "risk_flag": true/false,
  "fact_score": 0-10
}}"""


# =============================================================================
# 辅助函数
# =============================================================================
def load_annotations(file_paths: List[str]) -> List[Dict]:
    """
    加载并合并多个标注文件
    过滤 parse_error=True 的样本
    """
    all_samples = []
    seen_ids = set()

    for file_path in file_paths:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"文件不存在，跳过: {file_path}")
            continue

        count = 0
        skipped = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    sample = json.loads(line)
                    doc_id = sample.get("doc_id", "")

                    # 跳过 parse_error
                    if sample.get("parse_error", False):
                        skipped += 1
                        continue

                    # 跳过重复
                    if doc_id in seen_ids:
                        continue

                    seen_ids.add(doc_id)
                    all_samples.append(sample)
                    count += 1
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON 解析错误: {e}")
                    continue

        logger.info(f"加载 {path.name}: {count} 条有效, {skipped} 条跳过(parse_error)")

    return all_samples


def load_reviewed_ids(output_path: Path) -> set:
    """加载已审查的 doc_id（用于断点续跑）"""
    reviewed = set()
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        d = json.loads(line)
                        reviewed.add(d.get("doc_id", ""))
                    except:
                        pass
    return reviewed


def _extract_json_block(text: str) -> Optional[str]:
    """从响应中提取第一个完整 JSON 对象字符串"""
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)

    start = None
    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if ch == '"' and not escape:
            in_str = not in_str
        if ch == "\\" and in_str:
            escape = not escape
            continue
        escape = False
        if in_str:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                return text[start:i + 1]
    return None


def parse_review_response(response: str) -> Optional[Dict]:
    """解析 LLM 审查响应"""
    json_block = _extract_json_block(response)
    if json_block:
        try:
            result = json.loads(json_block)
            decision_raw = str(result.get("decision", "")).strip().lower()
            if decision_raw in {"keep", "accept", "yes", "true"}:
                decision = "accept"
            elif decision_raw in {"discard", "reject", "no", "false"}:
                decision = "reject"
            else:
                decision = "reject"

            quality_score = result.get("quality_score", None)
            if quality_score is None:
                fact_score = result.get("fact_score", None)
                if fact_score is not None:
                    try:
                        quality_score = max(1, min(5, round(float(fact_score) / 2)))
                    except (TypeError, ValueError):
                        quality_score = 1
                else:
                    quality_score = 1
            try:
                quality_score = int(float(quality_score))
            except (TypeError, ValueError):
                quality_score = 1
            quality_score = max(1, min(5, quality_score))

            content_type = result.get("content_type", result.get("type", "other"))
            risk_flag = bool(result.get("risk_flag", False))
            fact_score = result.get("fact_score", None)

            return {
                "decision": decision,
                "reason": str(result.get("reason", "")).strip(),
                "quality_score": int(quality_score),
                "content_type": str(content_type).strip() or "other",
                "risk_flag": risk_flag,
                "fact_score": fact_score
            }
        except json.JSONDecodeError:
            pass

    # 降级处理：根据关键词判断
    response_lower = response.lower()
    if "accept" in response_lower or "keep" in response_lower:
        return {
            "decision": "accept",
            "reason": "自动解析",
            "quality_score": 3,
            "content_type": "other",
            "risk_flag": False,
            "fact_score": None
        }
    return {
        "decision": "reject",
        "reason": "解析失败",
        "quality_score": 1,
        "content_type": "other",
        "risk_flag": False,
        "fact_score": None
    }


def review_sample(
    sample: Dict,
    llm,
    max_retries: int = 2
) -> Tuple[Dict, bool]:
    """
    审查单个样本

    Returns:
        (review_result, success)
    """
    source_text = sample.get("source_text", "")[:2000]  # 截断长文本
    entity_count = len(sample.get("entities", []))
    triple_count = len(sample.get("triples", []))
    event_count = len(sample.get("events", []))

    triples_preview = json.dumps(sample.get("triples", [])[:20], ensure_ascii=False)
    events_preview = json.dumps(sample.get("events", [])[:10], ensure_ascii=False)

    prompt = REVIEW_PROMPT.format(
        source_text=source_text,
        entity_count=entity_count,
        triple_count=triple_count,
        event_count=event_count,
        events_preview=events_preview,
        triples_preview=triples_preview
    )

    for attempt in range(max_retries):
        try:
            response = llm.chat(prompt)
            result = parse_review_response(response)
            if result:
                return result, True
        except Exception as e:
            logger.warning(f"审查失败 (尝试 {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    # 全部失败，默认拒绝
    return {"decision": "reject", "reason": "审查失败", "quality_score": 0, "content_type": "error"}, False


# =============================================================================
# 主函数
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="黄金标注二次审查")
    parser.add_argument("--input", "-i", nargs="+", required=True,
                        help="输入的标注文件（支持多个）")
    parser.add_argument("--out-accepted", "-o", default="data/p5_eval_pool/gold_reviewed.jsonl",
                        help="审查通过的输出文件")
    parser.add_argument("--out-rejected", default="data/p5_eval_pool/gold_rejected.jsonl",
                        help="被拒绝的输出文件")
    parser.add_argument("--report", default="data/p5_eval_pool/review_report.json",
                        help="审查报告输出路径")
    parser.add_argument("--api-key", default="", help="API Key（留空使用环境变量）")
    parser.add_argument("--base-url", default="", help="API Base URL（留空使用配置文件）")
    parser.add_argument("--model", default="", help="模型名称（留空使用配置文件）")
    parser.add_argument("--temperature", type=float, default=None, help="温度参数")
    parser.add_argument("--min-score", type=int, default=3,
                        help="最低质量分数（低于此分数的样本被拒绝）")
    parser.add_argument("--interval", type=float, default=1.0, help="请求间隔秒数")
    parser.add_argument("--max-retries", type=int, default=2, help="最大重试次数")
    parser.add_argument("--resume", action="store_true", help="断点续跑")
    parser.add_argument("--limit", type=int, default=0, help="最多处理样本数（0=不限制）")
    parser.add_argument("--dry-run", action="store_true", help="试运行（不调用LLM）")

    args = parser.parse_args()

    # 路径处理
    out_accepted = Path(args.out_accepted)
    out_rejected = Path(args.out_rejected)
    report_path = Path(args.report)

    out_accepted.parent.mkdir(parents=True, exist_ok=True)
    out_rejected.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    # 加载样本
    logger.info("=" * 60)
    logger.info("黄金标注二次审查")
    logger.info("=" * 60)

    samples = load_annotations(args.input)
    logger.info(f"总共加载 {len(samples)} 条有效样本")

    # 断点续跑
    reviewed_ids = set()
    if args.resume:
        reviewed_ids = load_reviewed_ids(out_accepted) | load_reviewed_ids(out_rejected)
        logger.info(f"断点续跑: 已审查 {len(reviewed_ids)} 条")

    # 过滤待审查
    pending = [s for s in samples if s.get("doc_id", "") not in reviewed_ids]
    if args.limit > 0:
        pending = pending[:args.limit]

    logger.info(f"待审查: {len(pending)} 条")

    if not pending:
        logger.info("无待审查样本")
        return

    # 加载默认配置
    cfg_path = PROJECT_ROOT / "configs" / "cfg.yaml"
    default_cfg = {"base_url": None, "model_name": None, "temperature": 0.1}
    if cfg_path.exists():
        try:
            import yaml
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            llm_cfg = cfg.get("llm", {})
            default_cfg["base_url"] = llm_cfg.get("base_url")
            default_cfg["model_name"] = llm_cfg.get("model_name")
            default_cfg["temperature"] = llm_cfg.get("temperature", 0.1)
        except Exception:
            pass

    # 初始化 LLM - 优先级：命令行 > cfg.yaml
    model_name = args.model if args.model else default_cfg["model_name"]
    base_url = args.base_url if args.base_url else default_cfg["base_url"]
    temperature = args.temperature if args.temperature is not None else default_cfg["temperature"]

    if not model_name:
        logger.error("❌ 未指定模型名称，请使用 --model 参数或在 cfg.yaml 中配置")
        return
    if not base_url:
        logger.error("❌ 未指定 base_url，请使用 --base-url 参数或在 cfg.yaml 中配置")
        return

    llm_config = {
        "model_name": model_name,
        "base_url": base_url,
        "temperature": temperature,
    }

    if args.api_key:
        os.environ["OPENAI_API_KEY"] = args.api_key

    logger.info(f"LLM 配置: model={model_name}, base_url={base_url[:50]}..., temperature={temperature}")

    if not args.dry_run:
        llm = LLMFactory.create(llm_config)
        logger.info(f"使用模型: {model_name}")
    else:
        llm = None
        logger.info("试运行模式（不调用LLM）")

    # 统计
    stats = {
        "total": len(pending),
        "accepted": 0,
        "rejected": 0,
        "errors": 0,
        "rule_rejects": 0,
        "by_type": {},
        "by_score": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    }

    start_time = time.time()

    # 审查
    logger.info("-" * 60)

    hard_reject_types = {"policy", "news", "meeting", "speech"}

    for i, sample in enumerate(pending):
        doc_id = sample.get("doc_id", f"unknown_{i}")

        if args.dry_run:
            # 试运行：随机决定
            review_result = {
                "decision": "accept" if i % 3 != 0 else "reject",
                "reason": "试运行",
                "quality_score": 3,
                "content_type": "other"
            }
            success = True
        else:
            review_result, success = review_sample(sample, llm, args.max_retries)
            time.sleep(args.interval)

        rule_rejected = False

        # 根据分数调整决定
        if review_result["quality_score"] < args.min_score:
            review_result["decision"] = "reject"
            review_result["reason"] = review_result.get("reason", "") or "低分拒绝"

        # 对敏感或低价值类型强制拒绝
        if review_result.get("risk_flag", False):
            review_result["decision"] = "reject"
            review_result["reason"] = review_result.get("reason", "") or "敏感内容"
            rule_rejected = True

        content_type = str(review_result.get("content_type", "other")).strip().lower()
        review_result["content_type"] = content_type or "other"
        if content_type in hard_reject_types:
            review_result["decision"] = "reject"
            review_result["reason"] = review_result.get("reason", "") or "低价值类型"
            rule_rejected = True

        if rule_rejected:
            stats["rule_rejects"] += 1

        # 添加审查结果到样本
        sample["review"] = review_result

        # 分流输出
        decision = review_result["decision"]
        output_path = out_accepted if decision == "accept" else out_rejected

        with open(output_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

        # 更新统计
        if decision == "accept":
            stats["accepted"] += 1
            icon = "✅"
        else:
            stats["rejected"] += 1
            icon = "❌"

        if not success:
            stats["errors"] += 1

        content_type = review_result.get("content_type", "other")
        stats["by_type"][content_type] = stats["by_type"].get(content_type, 0) + 1

        score = review_result.get("quality_score", 0)
        if score in stats["by_score"]:
            stats["by_score"][score] += 1

        # 日志
        reason = review_result.get("reason", "")[:30]
        logger.info(f"  [{i+1}/{len(pending)}] {doc_id[:12]}... {icon} {decision} (分数:{score}) {reason}")

    elapsed = time.time() - start_time

    # 保存报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "model": args.model,
        "min_score": args.min_score,
        "input_files": args.input,
        "output_files": {
            "accepted": str(out_accepted),
            "rejected": str(out_rejected)
        },
        "stats": stats,
        "elapsed_seconds": round(elapsed, 2)
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 打印总结
    logger.info("=" * 60)
    logger.info("审查完成")
    logger.info("=" * 60)
    logger.info(f"总样本: {stats['total']}")
    logger.info(f"通过: {stats['accepted']} ({stats['accepted']/stats['total']*100:.1f}%)")
    logger.info(f"拒绝: {stats['rejected']} ({stats['rejected']/stats['total']*100:.1f}%)")
    logger.info(f"错误: {stats['errors']}")
    logger.info(f"规则拒绝: {stats['rule_rejects']}")
    logger.info(f"耗时: {elapsed:.1f}秒")
    logger.info("-" * 60)
    logger.info("按内容类型:")
    for ctype, count in sorted(stats["by_type"].items(), key=lambda x: -x[1]):
        logger.info(f"  {ctype}: {count}")
    logger.info("-" * 60)
    logger.info("按质量分数:")
    for score in range(5, 0, -1):
        logger.info(f"  {score}分: {stats['by_score'].get(score, 0)}")
    logger.info("=" * 60)
    logger.info(f"通过样本: {out_accepted}")
    logger.info(f"拒绝样本: {out_rejected}")
    logger.info(f"审查报告: {report_path}")


if __name__ == "__main__":
    main()
