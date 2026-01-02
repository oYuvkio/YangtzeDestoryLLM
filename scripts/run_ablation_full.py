#!/usr/bin/env python3
"""
消融实验全流程脚本 - 支持一键运行所有消融变体

消融实验设计：
┌─────────────────────────────────────────────────────────────────┐
│                        消融实验矩阵                               │
├─────────────────────────────────────────────────────────────────┤
│ 本体(TBox)消融:                                                   │
│   - full_tbox:      完整流程 (CQ + P3层次 + P4文献增强)            │
│   - wo_cq:          无CQ增强 (仅专家骨架 + P4文献增强)              │
│   - wo_p4:          无P4文献增强 (CQ + P3层次)                     │
│   - wo_cq_p4:       无CQ和文献增强 (仅专家骨架)                    │
├─────────────────────────────────────────────────────────────────┤
│ 抽取(ABox)消融:                                                   │
│   - full_extract:   完整流程 (CoT + 后验证 + 幻觉过滤)             │
│   - wo_cot:         无CoT (普通prompt)                            │
│   - wo_verify:      无后验证 (跳过幻觉过滤)                        │
│   - wo_cot_verify:  无CoT和后验证                                 │
└─────────────────────────────────────────────────────────────────┘

评估指标：
┌─────────────────────────────────────────────────────────────────┐
│ TBox 指标 (OntoQA):                                              │
│   - #Classes, #Relations, #Attributes                           │
│   - RR (Relationship Richness) = P / (P + SC)                   │
│   - IR (Inheritance Richness) = SC / C                          │
│   - AR (Attribute Richness) = A / C                             │
│   - CQ Coverage (基于句向量的CQ覆盖度)                            │
├─────────────────────────────────────────────────────────────────┤
│ ABox 指标 (抽取质量):                                             │
│   - Event F1 (事件抽取)                                          │
│   - Triple F1 Strict (严格三元组匹配)                             │
│   - Triple F1 Relaxed (宽松匹配，允许时间/地名容忍)               │
│   - TBox Consistency (谓词存在性 + domain/range符合率)            │
└─────────────────────────────────────────────────────────────────┘

使用方式：
  # 完整消融实验
  python scripts/run_ablation_full.py --all

  # 仅运行 TBox 消融
  python scripts/run_ablation_full.py --tbox-ablation

  # 仅运行 ABox 消融
  python scripts/run_ablation_full.py --abox-ablation

  # 仅评估（使用已有结果）
  python scripts/run_ablation_full.py --eval-only
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.tbox_metrics import compute_tbox_metrics, compare_tbox_metrics
from tools.abox_metrics import compute_full_metrics
from tools.cq_coverage import CQCoverageEvaluator
from tools.relation_mapping import map_triples, STANDARD_RELATIONS

# ========== 配置 ==========
@dataclass
class AblationConfig:
    """消融实验配置"""
    name: str
    description: str
    # TBox 配置
    tbox_path: Optional[str] = None
    use_cq: bool = True
    use_p4_enhancement: bool = True
    # ABox 配置
    use_cot: bool = True
    use_verification: bool = True
    # 输出
    output_dir: str = ""


# TBox 消融变体
TBOX_ABLATION_VARIANTS = {
    "full_tbox": AblationConfig(
        name="full_tbox",
        description="完整本体 (CQ + P3 + P4文献增强)",
        tbox_path="outputs/cq_pipeline/final/p4_tbox_augmented.json",
        use_cq=True,
        use_p4_enhancement=True,
    ),
    "wo_cq": AblationConfig(
        name="wo_cq",
        description="无CQ增强 (专家骨架 + P4文献增强)",
        tbox_path=None,  # 需要重新生成
        use_cq=False,
        use_p4_enhancement=True,
    ),
    "wo_p4": AblationConfig(
        name="wo_p4",
        description="无P4文献增强 (CQ + P3层次)",
        tbox_path="outputs/cq_pipeline/final/p3_tbox_normalized.json",
        use_cq=True,
        use_p4_enhancement=False,
    ),
    "wo_cq_p4": AblationConfig(
        name="wo_cq_p4",
        description="无CQ和文献增强 (仅专家骨架)",
        tbox_path="data/expert_skeleton.json",
        use_cq=False,
        use_p4_enhancement=False,
    ),
}

# ABox 消融变体
ABOX_ABLATION_VARIANTS = {
    "full_extract": AblationConfig(
        name="full_extract",
        description="完整抽取 (CoT + 后验证 + 幻觉过滤)",
        use_cot=True,
        use_verification=True,
    ),
    "wo_cot": AblationConfig(
        name="wo_cot",
        description="无CoT (普通prompt抽取)",
        use_cot=False,
        use_verification=True,
    ),
    "wo_verify": AblationConfig(
        name="wo_verify",
        description="无后验证 (跳过幻觉过滤)",
        use_cot=True,
        use_verification=False,
    ),
    "wo_cot_verify": AblationConfig(
        name="wo_cot_verify",
        description="无CoT和后验证",
        use_cot=False,
        use_verification=False,
    ),
}


# ========== 日志设置 ==========
def setup_logging(log_file: Optional[str] = None) -> logging.Logger:
    log_format = "%(asctime)s | %(levelname)s | %(message)s"
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=handlers,
        force=True,
    )
    return logging.getLogger(__name__)


# ========== TBox 评估 ==========
def evaluate_tbox(
    tbox_path: str,
    test_cqs_path: str,
    logger: logging.Logger,
) -> Dict[str, Any]:
    """评估 TBox 质量"""
    logger.info(f"[TBox] 评估: {tbox_path}")

    tbox = json.loads(Path(tbox_path).read_text(encoding="utf-8"))

    # OntoQA 指标
    metrics = compute_tbox_metrics(tbox)
    result = metrics.to_dict()

    # CQ 覆盖度
    if Path(test_cqs_path).exists():
        cqs_raw = json.loads(Path(test_cqs_path).read_text(encoding="utf-8"))
        cqs = cqs_raw.get("cqs", []) if isinstance(cqs_raw, dict) else cqs_raw

        evaluator = CQCoverageEvaluator()
        coverage = evaluator.evaluate(cqs, tbox)
        result["cq_coverage"] = {str(k): v["cq_coverage"] for k, v in coverage.items()}

    logger.info(f"[TBox] 结果: {metrics.summary()}")
    return result


# ========== ABox 抽取 ==========
def run_extraction(
    corpus_path: str,
    tbox_path: str,
    output_path: str,
    use_cot: bool,
    use_verification: bool,
    logger: logging.Logger,
) -> str:
    """运行知识抽取"""
    from kg.cq_pipeline import CQKGPipeline

    logger.info(f"[P5] 开始抽取: cot={use_cot}, verify={use_verification}")

    pipeline = CQKGPipeline()
    tbox = json.loads(Path(tbox_path).read_text(encoding="utf-8"))

    # 读取语料
    corpus = []
    with open(corpus_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                corpus.append(json.loads(line))

    results = []
    for doc in corpus:
        text = doc.get("text", "")
        doc_id = doc.get("id", doc.get("doc_id", ""))

        if not text:
            continue

        try:
            if use_verification:
                # 使用 P5+ 完整抽取（含幻觉过滤）
                extraction = pipeline.p5_plus_extraction(
                    doc_text=text,
                    tbox=tbox,
                    use_cot=use_cot,
                )
            else:
                # 仅 P5 抽取，不做后验证
                extraction = pipeline.p5_extraction(
                    doc_text=text,
                    tbox=tbox,
                    use_cot=use_cot,
                )

            extraction["doc_id"] = doc_id
            results.append(extraction)
        except Exception as e:
            logger.warning(f"[P5] 抽取失败: doc_id={doc_id}, error={e}")
            results.append({"doc_id": doc_id, "events": [], "triples": []})

    # 保存结果
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info(f"[P5] 抽取完成: {len(results)} 条，保存至 {output_path}")
    return output_path


# ========== ABox 评估 ==========
def evaluate_abox(
    pred_path: str,
    gold_path: str,
    tbox_path: str,
    time_tolerance_days: int = 3,
    use_relation_mapping: bool = True,
    logger: logging.Logger = None,
) -> Dict[str, Any]:
    """
    评估 ABox 抽取质量

    Args:
        pred_path: 预测结果文件路径
        gold_path: 黄金标注文件路径
        tbox_path: TBox文件路径
        time_tolerance_days: 时间容忍天数
        use_relation_mapping: 是否使用关系映射（将项目关系映射到标准关系）
        logger: 日志记录器
    """
    if logger:
        logger.info(f"[ABox] 评估: pred={pred_path}, gold={gold_path}")
        if use_relation_mapping:
            logger.info("[ABox] 使用关系映射对齐到标准Schema")

    preds = json.loads(Path(pred_path).read_text(encoding="utf-8"))
    gold = json.loads(Path(gold_path).read_text(encoding="utf-8"))
    tbox = json.loads(Path(tbox_path).read_text(encoding="utf-8"))

    # 如果使用关系映射，对预测结果进行映射
    if use_relation_mapping:
        if isinstance(preds, list):
            for pred in preds:
                if "triples" in pred:
                    mapped_triples, _ = map_triples(pred["triples"])
                    pred["triples"] = mapped_triples
        elif isinstance(preds, dict) and "triples" in preds:
            mapped_triples, _ = map_triples(preds["triples"])
            preds["triples"] = mapped_triples

    # 处理列表格式
    if isinstance(preds, list) and isinstance(gold, list):
        all_metrics = []
        for p, g in zip(preds, gold):
            m = compute_full_metrics(p, g, tbox, time_tolerance_days=time_tolerance_days)
            all_metrics.append(m)

        import numpy as np
        result = {
            "event_f1": round(np.mean([m["event_f1"] for m in all_metrics]), 4),
            "triple_f1_strict": round(np.mean([m["triple_f1_strict"] for m in all_metrics]), 4),
            "triple_f1_relaxed": round(np.mean([m["triple_f1_relaxed"] for m in all_metrics]), 4),
            "tbox_consistency": round(np.mean([m["tbox_consistency"] for m in all_metrics]), 4),
            "sample_count": len(all_metrics),
        }
    else:
        result = compute_full_metrics(preds, gold, tbox, time_tolerance_days=time_tolerance_days)

    if logger:
        logger.info(f"[ABox] 结果: Event F1={result['event_f1']}, Triple F1 (strict/relaxed)={result['triple_f1_strict']}/{result['triple_f1_relaxed']}")

    return result


# ========== 消融实验主流程 ==========
def run_tbox_ablation(
    output_dir: Path,
    test_cqs_path: str,
    logger: logging.Logger,
) -> Dict[str, Dict[str, Any]]:
    """运行 TBox 消融实验"""
    logger.info("=" * 60)
    logger.info("开始 TBox 消融实验")
    logger.info("=" * 60)

    results = {}
    for name, config in TBOX_ABLATION_VARIANTS.items():
        logger.info(f"\n[TBox Ablation] {name}: {config.description}")

        tbox_path = config.tbox_path
        if tbox_path and Path(tbox_path).exists():
            metrics = evaluate_tbox(tbox_path, test_cqs_path, logger)
            results[name] = {
                "config": {
                    "name": name,
                    "description": config.description,
                    "use_cq": config.use_cq,
                    "use_p4_enhancement": config.use_p4_enhancement,
                    "tbox_path": tbox_path,
                },
                "metrics": metrics,
            }
        else:
            logger.warning(f"[TBox Ablation] {name}: TBox 文件不存在，跳过")
            results[name] = {"config": config.__dict__, "error": "TBox文件不存在"}

    return results


def run_abox_ablation(
    output_dir: Path,
    corpus_path: str,
    gold_path: str,
    tbox_path: str,
    logger: logging.Logger,
    skip_extraction: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """运行 ABox 消融实验"""
    logger.info("=" * 60)
    logger.info("开始 ABox 消融实验")
    logger.info("=" * 60)

    results = {}
    for name, config in ABOX_ABLATION_VARIANTS.items():
        logger.info(f"\n[ABox Ablation] {name}: {config.description}")

        pred_path = output_dir / name / "predictions.json"

        if not skip_extraction:
            # 运行抽取
            pred_path.parent.mkdir(parents=True, exist_ok=True)
            run_extraction(
                corpus_path=corpus_path,
                tbox_path=tbox_path,
                output_path=str(pred_path),
                use_cot=config.use_cot,
                use_verification=config.use_verification,
                logger=logger,
            )

        # 评估
        if pred_path.exists():
            metrics = evaluate_abox(
                pred_path=str(pred_path),
                gold_path=gold_path,
                tbox_path=tbox_path,
                logger=logger,
            )
            results[name] = {
                "config": {
                    "name": name,
                    "description": config.description,
                    "use_cot": config.use_cot,
                    "use_verification": config.use_verification,
                },
                "metrics": metrics,
            }
        else:
            logger.warning(f"[ABox Ablation] {name}: 预测文件不存在，跳过评估")
            results[name] = {"config": config.__dict__, "error": "预测文件不存在"}

    return results


def generate_report(
    tbox_results: Dict[str, Any],
    abox_results: Dict[str, Any],
    output_path: Path,
    logger: logging.Logger,
) -> str:
    """生成消融实验报告"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "tbox_ablation": tbox_results,
        "abox_ablation": abox_results,
    }

    # 保存 JSON 报告
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 生成 Markdown 表格
    md_lines = ["# 消融实验报告", "", f"生成时间: {report['timestamp']}", ""]

    # TBox 消融表
    md_lines.extend([
        "## 本体(TBox)消融实验",
        "",
        "| 变体 | 描述 | #Classes | #Relations | #Attrs | RR | IR | AR | CQ覆盖@0.7 |",
        "|------|------|----------|------------|--------|-----|-----|-----|------------|",
    ])
    for name, data in tbox_results.items():
        if "error" in data:
            md_lines.append(f"| {name} | {data['config'].get('description', '')} | - | - | - | - | - | - | - |")
        else:
            m = data["metrics"]
            cov = m.get("cq_coverage", {}).get("0.7", "-")
            md_lines.append(
                f"| {name} | {data['config']['description']} | "
                f"{m['num_classes']} | {m['num_relations']} | {m['num_attributes']} | "
                f"{m['relationship_richness']:.3f} | {m['inheritance_richness']:.3f} | "
                f"{m['attribute_richness']:.3f} | {cov} |"
            )

    # ABox 消融表
    md_lines.extend([
        "",
        "## 抽取(ABox)消融实验",
        "",
        "| 变体 | 描述 | Event F1 | Triple F1 (Strict) | Triple F1 (Relaxed) | TBox一致性 |",
        "|------|------|----------|-------------------|---------------------|------------|",
    ])
    for name, data in abox_results.items():
        if "error" in data:
            md_lines.append(f"| {name} | {data['config'].get('description', '')} | - | - | - | - |")
        else:
            m = data["metrics"]
            md_lines.append(
                f"| {name} | {data['config']['description']} | "
                f"{m['event_f1']:.4f} | {m['triple_f1_strict']:.4f} | "
                f"{m['triple_f1_relaxed']:.4f} | {m['tbox_consistency']:.4f} |"
            )

    md_content = "\n".join(md_lines)
    md_path = output_path.with_suffix(".md")
    md_path.write_text(md_content, encoding="utf-8")

    logger.info(f"[Report] JSON 报告: {output_path}")
    logger.info(f"[Report] Markdown 报告: {md_path}")

    return md_content


# ========== CLI ==========
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="消融实验全流程脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 完整消融实验（TBox + ABox）
  python scripts/run_ablation_full.py --all

  # 仅 TBox 消融（评估不同本体配置）
  python scripts/run_ablation_full.py --tbox-ablation

  # 仅 ABox 消融（评估不同抽取策略）
  python scripts/run_ablation_full.py --abox-ablation

  # 仅评估模式（使用已有抽取结果）
  python scripts/run_ablation_full.py --eval-only
        """,
    )

    # 实验选择
    parser.add_argument("--all", action="store_true", help="运行所有消融实验")
    parser.add_argument("--tbox-ablation", action="store_true", help="仅运行 TBox 消融")
    parser.add_argument("--abox-ablation", action="store_true", help="仅运行 ABox 消融")
    parser.add_argument("--eval-only", action="store_true", help="仅评估（跳过抽取）")

    # 路径配置
    parser.add_argument("--output-dir", default="outputs/ablation", help="输出目录")
    parser.add_argument("--tbox", default="outputs/cq_pipeline/final/p4_tbox_augmented.json",
                        help="用于 ABox 消融的基准 TBox")
    parser.add_argument("--test-cqs", default="outputs/cq_pipeline/final/p1_cqs_test.json",
                        help="测试集 CQ（用于 CQ 覆盖度）")
    parser.add_argument("--corpus", default="data/p5_eval_pool/test.jsonl",
                        help="测试语料（用于 ABox 抽取）")
    parser.add_argument("--gold", default="data/p5_eval_pool/gold.json",
                        help="黄金标注")

    # 其他
    parser.add_argument("--log-file", default="", help="日志文件")

    return parser.parse_args()


def main():
    args = parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log_file = args.log_file or str(output_dir / "ablation.log")
    logger = setup_logging(log_file)

    logger.info("=" * 60)
    logger.info("消融实验开始")
    logger.info(f"输出目录: {output_dir}")
    logger.info("=" * 60)

    tbox_results = {}
    abox_results = {}

    # 判断运行哪些实验
    run_tbox = args.all or args.tbox_ablation
    run_abox = args.all or args.abox_ablation

    if not run_tbox and not run_abox:
        logger.warning("未指定任何实验，请使用 --all, --tbox-ablation 或 --abox-ablation")
        print("使用 --help 查看帮助")
        return

    # TBox 消融
    if run_tbox:
        tbox_results = run_tbox_ablation(
            output_dir=output_dir / "tbox",
            test_cqs_path=args.test_cqs,
            logger=logger,
        )

    # ABox 消融
    if run_abox:
        if not Path(args.gold).exists():
            logger.error(f"黄金标注不存在: {args.gold}")
            logger.info("请先准备黄金标注文件，或使用 --gold 参数指定路径")
        else:
            abox_results = run_abox_ablation(
                output_dir=output_dir / "abox",
                corpus_path=args.corpus,
                gold_path=args.gold,
                tbox_path=args.tbox,
                logger=logger,
                skip_extraction=args.eval_only,
            )

    # 生成报告
    report_path = output_dir / "ablation_report.json"
    md_content = generate_report(tbox_results, abox_results, report_path, logger)

    print("\n" + "=" * 60)
    print("消融实验完成！报告摘要：")
    print("=" * 60)
    print(md_content)


if __name__ == "__main__":
    main()
