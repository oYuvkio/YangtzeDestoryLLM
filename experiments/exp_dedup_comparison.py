#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向量去重效果对比实验

本实验用于验证论文中提出的向量去重方法的有效性，对比分析：
1. 无去重 (baseline)
2. 向量去重 (threshold=0.7, 论文推荐值)
3. 向量去重 (threshold=0.75, 保守值)
4. 向量去重 (threshold=0.8, 严格值)

评估指标：
- TBox 规模：类数量、关系数量、属性数量
- OntoQA 指标：RR (关系丰富度)、IR (继承丰富度)、AR (属性丰富度)
- 去重效果：重复率、保留率、相似度分布

用法:
    # 完整对比实验
    conda activate YangtzeLLM
    python experiments/exp_dedup_comparison.py
    
    # 使用已有 TBox 数据
    python experiments/exp_dedup_comparison.py --input-tbox outputs/p2_tbox_init.json
    
    # 仅生成报告
    python experiments/exp_dedup_comparison.py --report-only
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
import time

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from kg.cq_pipeline import CQLLMPipeline, TBoxSchema, ClassDef, RelationDef, DEMO_DOMAIN_DESC
from kg.utils.deduplication import EmbeddingDeduplicator
from tools.tbox_metrics import calculate_ontoqa_metrics


def print_header(title: str) -> None:
    """打印标题。"""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


def calculate_tbox_stats(tbox: TBoxSchema) -> Dict[str, Any]:
    """计算 TBox 统计信息。"""
    tbox_dict = tbox.to_dict()
    
    # 基础统计
    stats = {
        "num_classes": len(tbox.classes),
        "num_relations": len(tbox.relations),
        "num_attributes": len(tbox.attributes),
    }
    
    # OntoQA 指标
    try:
        ontoqa = calculate_ontoqa_metrics(tbox_dict)
        stats.update({
            "RR": ontoqa.get("RR", 0),
            "IR": ontoqa.get("IR", 0),
            "AR": ontoqa.get("AR", 0),
        })
    except Exception as e:
        print(f"⚠️  OntoQA 计算失败: {e}")
        stats.update({"RR": 0, "IR": 0, "AR": 0})
    
    return stats


def run_dedup_with_threshold(
    tbox: TBoxSchema,
    threshold: float,
    output_path: Path = None
) -> Tuple[TBoxSchema, Dict[str, Any]]:
    """
    使用指定阈值进行去重。
    
    Returns:
        (去重后的TBox, 去重统计信息)
    """
    print(f"\n🔍 执行去重 (threshold={threshold})...")
    
    start_time = time.time()
    dedup = EmbeddingDeduplicator(threshold=threshold)
    
    # 去重类
    base_dict = tbox.to_dict()
    class_result = dedup.deduplicate_classes([], base_dict.get("classes", []))
    
    # 去重关系
    rel_result = dedup.deduplicate_relations([], base_dict.get("relations", []))
    
    # 构建新 TBox
    tbox_dedup = TBoxSchema(
        classes=[ClassDef(**c) for c in class_result.accepted],
        relations=[RelationDef(**r) for r in rel_result.accepted],
        attributes=tbox.attributes,  # 属性不去重
    )
    
    elapsed = time.time() - start_time
    
    # 统计信息
    stats = {
        "threshold": threshold,
        "classes": {
            "original": len(base_dict.get("classes", [])),
            "accepted": len(class_result.accepted),
            "rejected": len(class_result.rejected),
            "retention_rate": len(class_result.accepted) / len(base_dict.get("classes", [])) if base_dict.get("classes") else 0,
        },
        "relations": {
            "original": len(base_dict.get("relations", [])),
            "accepted": len(rel_result.accepted),
            "rejected": len(rel_result.rejected),
            "retention_rate": len(rel_result.accepted) / len(base_dict.get("relations", [])) if base_dict.get("relations") else 0,
        },
        "elapsed_seconds": round(elapsed, 2),
    }
    
    # 保存结果
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存去重后的 TBox
        tbox_path = output_path.parent / f"{output_path.stem}_tbox.json"
        tbox_path.write_text(
            json.dumps(tbox_dedup.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        
        # 保存去重详情
        details = {
            "statistics": stats,
            "rejected_classes": class_result.rejected,
            "rejected_relations": rel_result.rejected,
            "merge_map_classes": class_result.merge_map,
            "merge_map_relations": rel_result.merge_map,
        }
        details_path = output_path.parent / f"{output_path.stem}_details.json"
        details_path.write_text(
            json.dumps(details, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        
        print(f"  💾 已保存: {tbox_path.name}")
    
    print(f"  ✅ 完成 (耗时 {elapsed:.2f}s)")
    print(f"     类: {stats['classes']['original']} → {stats['classes']['accepted']} (保留率 {stats['classes']['retention_rate']:.1%})")
    print(f"     关系: {stats['relations']['original']} → {stats['relations']['accepted']} (保留率 {stats['relations']['retention_rate']:.1%})")
    
    return tbox_dedup, stats


def run_comparison_experiment(
    input_tbox_path: Path = None,
    output_dir: Path = None,
) -> Dict[str, Any]:
    """
    运行对比实验。
    
    Args:
        input_tbox_path: 输入的 TBox 文件路径（如果不提供则生成新的）
        output_dir: 输出目录
        
    Returns:
        实验结果汇总
    """
    print_header("向量去重效果对比实验")
    
    if output_dir is None:
        output_dir = Path("outputs/experiments/dedup_comparison")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 加载或生成 TBox
    if input_tbox_path and input_tbox_path.exists():
        print(f"📂 加载已有 TBox: {input_tbox_path}")
        tbox_data = json.loads(input_tbox_path.read_text(encoding="utf-8"))
        tbox_baseline = TBoxSchema(
            classes=[ClassDef(**c) for c in tbox_data.get("classes", [])],
            relations=[RelationDef(**r) for r in tbox_data.get("relations", [])],
            attributes=[AttributeDef(**a) for a in tbox_data.get("attributes", [])]
        )
    else:
        print("🔄 生成新的 TBox（使用演示数据）...")
        from kg.cq_pipeline import AttributeDef
        pipeline = CQLLMPipeline(output_dir=str(output_dir))
        
        # 生成 CQ
        cqs = pipeline.generate_cqs(DEMO_DOMAIN_DESC, n_cq=15)
        
        # 生成初始 TBox
        tbox_baseline = pipeline.cq_to_schema(cqs)
        
        # 保存 baseline
        baseline_path = output_dir / "baseline_tbox.json"
        baseline_path.write_text(
            json.dumps(tbox_baseline.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"  ✅ Baseline TBox 已保存: {baseline_path}")
    
    # 2. Baseline 统计
    print_header("Baseline 统计（无去重）")
    baseline_stats = calculate_tbox_stats(tbox_baseline)
    print(f"  类: {baseline_stats['num_classes']}")
    print(f"  关系: {baseline_stats['num_relations']}")
    print(f"  属性: {baseline_stats['num_attributes']}")
    print(f"  RR: {baseline_stats['RR']:.4f}")
    print(f"  IR: {baseline_stats['IR']:.4f}")
    print(f"  AR: {baseline_stats['AR']:.4f}")
    
    # 3. 不同阈值对比实验
    print_header("不同阈值去重对比")
    
    thresholds = [0.7, 0.75, 0.8]
    results = {
        "baseline": {
            "tbox": tbox_baseline,
            "stats": baseline_stats,
            "dedup_stats": None,
        }
    }
    
    for threshold in thresholds:
        key = f"threshold_{threshold}"
        output_prefix = output_dir / f"dedup_t{threshold}"
        
        tbox_dedup, dedup_stats = run_dedup_with_threshold(
            tbox_baseline,
            threshold,
            output_path=output_prefix
        )
        
        tbox_stats = calculate_tbox_stats(tbox_dedup)
        
        results[key] = {
            "tbox": tbox_dedup,
            "stats": tbox_stats,
            "dedup_stats": dedup_stats,
        }
    
    # 4. 生成对比报告
    print_header("实验结果汇总")
    
    comparison_table = []
    comparison_table.append(["配置", "类数量", "关系数", "属性数", "RR", "IR", "AR", "保留率(类)", "保留率(关系)"])
    comparison_table.append(["-" * 10] * 9)
    
    # Baseline
    baseline_row = [
        "Baseline (无去重)",
        baseline_stats['num_classes'],
        baseline_stats['num_relations'],
        baseline_stats['num_attributes'],
        f"{baseline_stats['RR']:.4f}",
        f"{baseline_stats['IR']:.4f}",
        f"{baseline_stats['AR']:.4f}",
        "100.0%",
        "100.0%",
    ]
    comparison_table.append(baseline_row)
    
    # 各阈值
    for threshold in thresholds:
        key = f"threshold_{threshold}"
        res = results[key]
        stats = res['stats']
        dedup_stats = res['dedup_stats']
        
        row = [
            f"去重 (t={threshold})",
            stats['num_classes'],
            stats['num_relations'],
            stats['num_attributes'],
            f"{stats['RR']:.4f}",
            f"{stats['IR']:.4f}",
            f"{stats['AR']:.4f}",
            f"{dedup_stats['classes']['retention_rate']:.1%}",
            f"{dedup_stats['relations']['retention_rate']:.1%}",
        ]
        comparison_table.append(row)
    
    # 打印表格
    for row in comparison_table:
        print("  ".join(str(cell).ljust(15) for cell in row))
    
    # 5. 保存完整报告
    report = {
        "experiment": "向量去重效果对比",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "baseline": {
            "num_classes": baseline_stats['num_classes'],
            "num_relations": baseline_stats['num_relations'],
            "num_attributes": baseline_stats['num_attributes'],
            "ontoqa": {
                "RR": baseline_stats['RR'],
                "IR": baseline_stats['IR'],
                "AR": baseline_stats['AR'],
            },
        },
        "variants": {},
    }
    
    for threshold in thresholds:
        key = f"threshold_{threshold}"
        res = results[key]
        report["variants"][key] = {
            "threshold": threshold,
            "tbox_size": {
                "num_classes": res['stats']['num_classes'],
                "num_relations": res['stats']['num_relations'],
                "num_attributes": res['stats']['num_attributes'],
            },
            "ontoqa": {
                "RR": res['stats']['RR'],
                "IR": res['stats']['IR'],
                "AR": res['stats']['AR'],
            },
            "dedup_effect": {
                "classes_retention": res['dedup_stats']['classes']['retention_rate'],
                "relations_retention": res['dedup_stats']['relations']['retention_rate'],
                "classes_rejected": res['dedup_stats']['classes']['rejected'],
                "relations_rejected": res['dedup_stats']['relations']['rejected'],
            },
            "elapsed_seconds": res['dedup_stats']['elapsed_seconds'],
        }
    
    report_path = output_dir / "comparison_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    print(f"\n📊 完整报告已保存: {report_path}")
    print(f"📁 所有结果保存在: {output_dir}")
    
    # 6. 分析建议
    print_header("实验分析与建议")
    
    print("📌 关键发现:")
    t07_res = results["threshold_0.7"]
    t075_res = results["threshold_0.75"]
    
    class_reduction_07 = (1 - t07_res['dedup_stats']['classes']['retention_rate']) * 100
    class_reduction_075 = (1 - t075_res['dedup_stats']['classes']['retention_rate']) * 100
    
    print(f"  1. 阈值 0.7 去除了 {class_reduction_07:.1f}% 的类，{(1-t07_res['dedup_stats']['relations']['retention_rate'])*100:.1f}% 的关系")
    print(f"  2. 阈值 0.75 去除了 {class_reduction_075:.1f}% 的类，{(1-t075_res['dedup_stats']['relations']['retention_rate'])*100:.1f}% 的关系")
    print(f"  3. 论文推荐阈值 0.7 在减少冗余和保留细粒度差异之间取得平衡")
    
    print("\n💡 论文撰写建议:")
    print("  - 在消融实验中对比 '有去重' vs '无去重' 的效果")
    print("  - 展示不同阈值对模式规模和质量的影响")
    print("  - 分析被去重的类/关系是否确实为同义或重复概念")
    print("  - 讨论向量去重如何减少人工审核工作量")
    
    return report


def main():
    parser = argparse.ArgumentParser(
        description="向量去重效果对比实验",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input-tbox",
        type=str,
        default=None,
        help="输入的 TBox JSON 文件路径（不提供则自动生成）"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="outputs/experiments/dedup_comparison",
        help="输出目录"
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="仅从已有结果生成报告（需要先运行过实验）"
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input_tbox) if args.input_tbox else None
    output_dir = Path(args.output_dir)
    
    if args.report_only:
        print("📄 从已有结果生成报告...")
        report_path = output_dir / "comparison_report.json"
        if not report_path.exists():
            print(f"❌ 报告文件不存在: {report_path}")
            print("   请先运行完整实验！")
            sys.exit(1)
        
        report = json.loads(report_path.read_text(encoding="utf-8"))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    
    try:
        report = run_comparison_experiment(
            input_tbox_path=input_path,
            output_dir=output_dir,
        )
        
        print("\n✅ 实验完成！")
        
    except Exception as e:
        print(f"\n❌ 实验失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
