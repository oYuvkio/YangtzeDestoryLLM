#!/usr/bin/env python3
"""
汇总多模型评测结果，生成对比报告。

使用方式：
    python scripts/p5/compare_models.py \
        --input-dir outputs/eval_models \
        --models "gpt-4o-mini glm-4-flash qwen-turbo" \
        --output outputs/eval_models/comparison_report.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_metrics(metrics_path: Path) -> Optional[Dict[str, Any]]:
    """加载指标文件。"""
    if not metrics_path.exists():
        return None
    try:
        return json.loads(metrics_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_align_report(report_path: Path) -> Optional[Dict[str, Any]]:
    """加载对齐报告。"""
    if not report_path.exists():
        return None
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def format_model_dir(model_name: str) -> str:
    """将模型名转换为目录名。"""
    return model_name.replace("/", "_").replace(":", "_")


def select_metrics(metrics: Dict[str, Any], version: str) -> Dict[str, Any]:
    """选择指标版本（兼容 raw/tbox_filtered 或旧格式）。"""
    if "raw" in metrics and "tbox_filtered" in metrics:
        return metrics.get(version) or metrics.get("raw") or metrics.get("tbox_filtered") or {}
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="汇总多模型评测结果")
    parser.add_argument("--input-dir", required=True, help="评测结果目录")
    parser.add_argument("--models", required=True, help="模型列表（空格分隔）")
    parser.add_argument("--output", "-o", required=True, help="输出报告路径")
    parser.add_argument(
        "--version",
        choices=["raw", "tbox_filtered"],
        default="raw",
        help="指标版本（默认 raw）",
    )

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_path = Path(args.output)
    model_names = args.models.split()
    metrics_version = args.version

    print("=" * 60)
    print("多模型评测汇总")
    print("=" * 60)
    print(f"模型数: {len(model_names)}")
    print(f"输入目录: {input_dir}")
    print()

    results: List[Dict[str, Any]] = []

    for model_name in model_names:
        model_dir = input_dir / format_model_dir(model_name)
        metrics_path = model_dir / "metrics.json"
        align_report_path = model_dir / "align_report.json"
        meta_path = model_dir / "predictions.meta.json"

        metrics = load_metrics(metrics_path)
        align_report = load_align_report(align_report_path)

        if metrics is None:
            print(f"[WARN] {model_name}: 未找到 metrics.json")
            continue

        selected_metrics = select_metrics(metrics, metrics_version)
        triple_strict = selected_metrics.get("triple_f1_strict", 0)
        triple_relaxed = selected_metrics.get("triple_f1_relaxed", 0)
        result = {
            "model": model_name,
            "metrics_version": metrics_version,
            "entity_f1": selected_metrics.get("entity_f1", 0),
            "relation_f1_strict": triple_strict,
            "relation_f1_relaxed": triple_relaxed,
            "event_f1": selected_metrics.get("event_f1", 0),
            "hallucination_rate": selected_metrics.get("hallucination_rate", 0),
            "tbox_consistency": selected_metrics.get("tbox_consistency", 0),
            "sample_count": selected_metrics.get("sample_count", 0),
            "triple_f1_strict": triple_strict,
            "triple_f1_relaxed": triple_relaxed,
        }

        # 添加对齐信息
        if align_report:
            result["align_matched"] = align_report.get("matched_count", 0)
            result["align_missing"] = align_report.get("missing_count", 0)

        # 添加错误统计
        error_breakdown = selected_metrics.get("error_breakdown", {})
        if error_breakdown:
            events_errors = error_breakdown.get("events", {})
            triples_errors = error_breakdown.get("triples", {})
            result["event_matched"] = events_errors.get("matched", 0)
            result["event_unmatched_pred"] = events_errors.get("unmatched_pred", 0)
            result["event_unmatched_gold"] = events_errors.get("unmatched_gold", 0)
            result["triple_matched"] = triples_errors.get("matched", 0)

        results.append(result)

    # 按 event_f1 排序
    results.sort(key=lambda x: x.get("event_f1", 0), reverse=True)

    # 生成报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "model_count": len(results),
        "input_dir": str(input_dir),
        "metrics_version": metrics_version,
        "results": results,
        "best_model": results[0]["model"] if results else None,
        "ranking": [r["model"] for r in results],
    }

    # 保存报告
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def fmt_metric(value: Any, width: int = 8) -> str:
        if value is None:
            return f"{'N/A':>{width}}"
        try:
            return f"{float(value):>{width}.4f}"
        except (TypeError, ValueError):
            return f"{'N/A':>{width}}"

    # 打印对比表格
    print()
    print("=" * 80)
    print(f"评测结果对比（版本: {metrics_version}）")
    print("=" * 80)
    print()
    print(
        f"{'模型':<20} {'Entity':>8} {'Rel(S)':>8} {'Rel(R)':>8} "
        f"{'Event':>8} {'Halluc':>8} {'TBox':>8}"
    )
    print("-" * 80)

    for r in results:
        print(
            f"{r['model']:<20} "
            f"{fmt_metric(r.get('entity_f1'))} "
            f"{fmt_metric(r.get('relation_f1_strict'))} "
            f"{fmt_metric(r.get('relation_f1_relaxed'))} "
            f"{fmt_metric(r.get('event_f1'))} "
            f"{fmt_metric(r.get('hallucination_rate'))} "
            f"{fmt_metric(r.get('tbox_consistency'))}"
        )

    print("-" * 80)
    print()

    if results:
        best = results[0]
        print(f"最佳模型: {best['model']}")
        print(f"  Entity F1: {fmt_metric(best.get('entity_f1'), width=0).strip()}")
        print(f"  Relation F1 (Strict): {fmt_metric(best.get('relation_f1_strict'), width=0).strip()}")
        print(f"  Relation F1 (Relaxed): {fmt_metric(best.get('relation_f1_relaxed'), width=0).strip()}")
        print(f"  Event F1: {fmt_metric(best.get('event_f1'), width=0).strip()}")
        print(f"  Hallucination Rate: {fmt_metric(best.get('hallucination_rate'), width=0).strip()}")
        print(f"  TBox Consistency: {fmt_metric(best.get('tbox_consistency'), width=0).strip()}")
        print()

    print(f"报告已保存: {output_path}")


if __name__ == "__main__":
    main()
