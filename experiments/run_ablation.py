"""
消融实验入口：按变体配置运行评估，输出报告。
使用方式示例：
python experiments/run_ablation.py \
  --cqs outputs/cq_pipeline/final/p1_cqs_test.json \
  --gold data/p5_eval_pool/gold.json \
  --out-dir outputs/ablation \
  --tbox-map full:outputs/cq_pipeline/final/p4_tbox_augmented.json \
  --tbox-map wo_p4:outputs/cq_pipeline/final/p3_tbox_normalized.json \
  --preds-map full:outputs/kg_pred/full.json \
  --preds-map wo_p4:outputs/kg_pred/wo_p4.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 允许运行时找到项目根
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.ablation_configs import ABLATION_VARIANTS  # noqa: E402
from scripts.run_full_evaluation import run_evaluation  # noqa: E402


def parse_map(items):
    mapping = {}
    for it in items or []:
        if ":" in it:
            k, v = it.split(":", 1)
            mapping[k] = v
    return mapping


def main():
    parser = argparse.ArgumentParser(description="运行消融实验（需要已生成的 TBox、预测和黄金标注）")
    parser.add_argument("--variants", nargs="+", default=list(ABLATION_VARIANTS.keys()),
                        help="要运行的变体列表，默认全部")
    parser.add_argument("--cqs", required=True, help="测试集 CQ 路径")
    parser.add_argument("--gold", required=True, help="黄金标注（events/triples）路径")
    parser.add_argument("--out-dir", default="outputs/ablation", help="输出根目录")
    parser.add_argument("--tbox-map", nargs="+", help="变体到 TBox 路径的映射，如 full:path/to.json")
    parser.add_argument("--preds-map", nargs="+", help="变体到预测文件路径的映射，如 full:path/to_pred.json")
    args = parser.parse_args()

    tbox_map = parse_map(args.tbox_map)
    preds_map = parse_map(args.preds_map)
    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    for name in args.variants:
        if name not in ABLATION_VARIANTS:
            print(f"[WARN] 未知变体 {name}，跳过")
            continue
        if name not in tbox_map or name not in preds_map:
            print(f"[WARN] 变体 {name} 未提供 tbox/preds，跳过")
            continue
        tbox_path = tbox_map[name]
        preds_path = preds_map[name]
        out_dir = out_root / name
        out_dir.mkdir(parents=True, exist_ok=True)
        report_path = out_dir / "report.json"
        print(f"[ABLA] 运行 {name} -> tbox={tbox_path}, preds={preds_path}")
        report = run_evaluation(
            tbox_path=tbox_path,
            test_cqs_path=args.cqs,
            gold_annotations_path=args.gold,
            predictions_path=preds_path,
            output_report_path=report_path,
        )
        (out_dir / "config.json").write_text(json.dumps(ABLATION_VARIANTS[name], ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ABLA] 完成 {name}，报告写入 {report_path}")


if __name__ == "__main__":
    main()
