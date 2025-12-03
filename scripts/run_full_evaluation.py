"""
一键评估脚本：TBox 结构指标 + CQ 覆盖度 + 抽取 F1（事件/三元组）。
增强点：
- 统一读取 cfg 作为默认值，CLI 优先；
- 支持批量样本（gold/preds 为列表时自动平均）；
- 输出时间戳、输入路径记录、摘要信息，便于报告引用。
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import yaml

from tools.tbox_metrics import compute_tbox_metrics
from tools.cq_coverage import CQCoverageEvaluator
from tools.abox_metrics import compute_full_metrics


def run_evaluation(
    tbox_path: str,
    test_cqs_path: str,
    gold_annotations_path: str,
    predictions_path: str,
    output_report_path: str,
    p3_hierarchy_path: str | None = None,
) -> Dict[str, Any]:
    """运行完整评估并生成报告。"""
    report: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "inputs": {
            "tbox": tbox_path,
            "test_cqs": test_cqs_path,
            "gold": gold_annotations_path,
            "predictions": predictions_path,
            "p3_hierarchy": p3_hierarchy_path,
        },
        "tbox_metrics": {},
        "cq_coverage": {},
        "extraction_metrics": {},
        "summary": {},
    }

    tbox = json.loads(Path(tbox_path).read_text(encoding="utf-8"))
    metrics = compute_tbox_metrics(tbox)
    report["tbox_metrics"] = metrics.to_dict()

    # P3 层次（可选）
    if p3_hierarchy_path and Path(p3_hierarchy_path).exists():
        try:
            p3_data = json.loads(Path(p3_hierarchy_path).read_text(encoding="utf-8"))
            metrics = compute_tbox_metrics(tbox, p3_data.get("class_hierarchy", []))
            report["tbox_metrics"] = metrics.to_dict()
        except Exception:
            pass

    test_cqs_raw = json.loads(Path(test_cqs_path).read_text(encoding="utf-8"))
    if isinstance(test_cqs_raw, dict) and "cqs" in test_cqs_raw:
        test_cqs = test_cqs_raw.get("cqs", [])
    else:
        test_cqs = test_cqs_raw

    evaluator = CQCoverageEvaluator()
    coverage = evaluator.evaluate(test_cqs, tbox)
    report["cq_coverage"] = {str(k): v["cq_coverage"] for k, v in coverage.items()}

    gold = json.loads(Path(gold_annotations_path).read_text(encoding="utf-8"))
    preds = json.loads(Path(predictions_path).read_text(encoding="utf-8"))
    if isinstance(gold, list) and isinstance(preds, list):
        all_metrics = [compute_full_metrics(p, g, tbox) for g, p in zip(gold, preds)]
        import numpy as np

        report["extraction_metrics"] = {
            "event_f1": round(np.mean([m["event_f1"] for m in all_metrics]), 4),
            "triple_f1_strict": round(np.mean([m["triple_f1_strict"] for m in all_metrics]), 4),
            "triple_f1_relaxed": round(np.mean([m["triple_f1_relaxed"] for m in all_metrics]), 4),
            "tbox_consistency": round(np.mean([m["tbox_consistency"] for m in all_metrics]), 4),
            "sample_count": len(all_metrics),
        }
    else:
        report["extraction_metrics"] = compute_full_metrics(preds, gold, tbox)

    out_path = Path(output_report_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[EVAL] 报告已保存：{out_path}")
    return report


def main():
    parser = argparse.ArgumentParser(description="一键评估：TBox 指标 + CQ 覆盖 + 抽取 F1")
    parser.add_argument("--cfg", default="configs/cfg.yaml", help="默认配置文件（命令行优先）")
    parser.add_argument("--tbox", required=False, help="TBox 路径（默认为 cfg.paths.output_dir/p4_tbox_augmented.json）")
    parser.add_argument("--cqs", required=False, help="测试集 CQ 路径（JSON，含 cqs 字段或数组）")
    parser.add_argument("--gold", required=True, help="黄金标注路径（events/triples）")
    parser.add_argument("--preds", required=True, help="预测结果路径（events/triples）")
    parser.add_argument("--p3-hierarchy", default=None, help="P3 输出（含 class_hierarchy）路径，可选")
    parser.add_argument("--out", default=None, help="评估报告输出路径（默认写入 cfg.paths.output_dir/report.json）")
    args = parser.parse_args()

    cfg = {}
    if args.cfg:
        cfg_path = Path(args.cfg)
        if cfg_path.exists():
            try:
                cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            except Exception:
                cfg = {}

    def pick(*vals, default=None):
        for v in vals:
            if v not in [None, ""]:
                return v
        return default

    cfg_paths = cfg.get("paths", {}) if isinstance(cfg, dict) else {}
    default_output_dir = cfg_paths.get("output_dir", "outputs/cq_pipeline/final")

    tbox_path = pick(args.tbox, str(Path(default_output_dir) / "p4_tbox_augmented.json"))
    cqs_path = pick(args.cqs, str(Path(default_output_dir) / "p1_cqs_test.json"))
    out_path = pick(args.out, str(Path(default_output_dir) / "evaluation_report.json"))

    run_evaluation(
        tbox_path=tbox_path,
        test_cqs_path=cqs_path,
        gold_annotations_path=args.gold,
        predictions_path=args.preds,
        output_report_path=out_path,
        p3_hierarchy_path=args.p3_hierarchy,
    )


if __name__ == "__main__":
    main()
