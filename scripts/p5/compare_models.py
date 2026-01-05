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


def main() -> None:
    parser = argparse.ArgumentParser(description="汇总多模型评测结果")
    parser.add_argument("--input-dir", required=True, help="评测结果目录")
    parser.add_argument("--models", required=True, help="模型列表（空格分隔）")
    parser.add_argument("--output", "-o", required=True, help="输出报告路径")

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_path = Path(args.output)
    model_names = args.models.split()

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

        result = {
            "model": model_name,
            "event_f1": metrics.get("event_f1", 0),
            "triple_f1_strict": metrics.get("triple_f1_strict", 0),
            "triple_f1_relaxed": metrics.get("triple_f1_relaxed", 0),
            "tbox_consistency": metrics.get("tbox_consistency", 0),
            "sample_count": metrics.get("sample_count", 0),
        }

        # 添加对齐信息
        if align_report:
            result["align_matched"] = align_report.get("matched_count", 0)
            result["align_missing"] = align_report.get("missing_count", 0)

        # 添加错误统计
        error_breakdown = metrics.get("error_breakdown", {})
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
        "results": results,
        "best_model": results[0]["model"] if results else None,
        "ranking": [r["model"] for r in results],
    }

    # 保存报告
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 打印对比表格
    print()
    print("=" * 80)
    print("评测结果对比")
    print("=" * 80)
    print()
    print(f"{'模型':<20} {'Event F1':>10} {'Triple(S)':>10} {'Triple(R)':>10} {'TBox':>10}")
    print("-" * 80)

    for r in results:
        print(
            f"{r['model']:<20} "
            f"{r['event_f1']:>10.4f} "
            f"{r['triple_f1_strict']:>10.4f} "
            f"{r['triple_f1_relaxed']:>10.4f} "
            f"{r['tbox_consistency']:>10.4f}"
        )

    print("-" * 80)
    print()

    if results:
        best = results[0]
        print(f"最佳模型: {best['model']}")
        print(f"  Event F1: {best['event_f1']:.4f}")
        print(f"  Triple F1 (Strict): {best['triple_f1_strict']:.4f}")
        print(f"  Triple F1 (Relaxed): {best['triple_f1_relaxed']:.4f}")
        print()

    print(f"报告已保存: {output_path}")


if __name__ == "__main__":
    main()
