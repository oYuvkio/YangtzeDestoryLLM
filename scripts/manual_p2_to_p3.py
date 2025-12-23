#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动 P2+P3 流程：从 Web 端生成的 P2 TBox 开始，应用去重生成 P3。

使用方法：
1. 使用 prompts_for_web/P2_with_hierarchy.md 中的 Prompt 在 Web 端生成 P2 TBox
2. 将生成的 JSON 保存为文件（如 outputs/manual/p2_tbox_with_hierarchy.json）
3. 运行本脚本进行去重和规范化：
   
   PYTHONPATH=. python scripts/manual_p2_to_p3.py \
     --p2-file outputs/manual/p2_tbox_with_hierarchy.json \
     --output-dir outputs/manual \
     --dedup-threshold 0.7

输出：
- p3_tbox_dedup.json: 去重后的 TBox（带 parent 字段）
- dedup_report.json: 去重详情报告
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from kg.cq_pipeline import TBoxSchema, ClassDef, RelationDef, AttributeDef
from kg.utils.deduplication import EmbeddingDeduplicator
from kg.utils.schema_alignment import SchemaAligner

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def load_p2_tbox(p2_file: Path) -> TBoxSchema:
    """加载 P2 TBox JSON 文件"""
    logger.info(f"📂 加载 P2 TBox: {p2_file}")
    data = json.loads(p2_file.read_text(encoding="utf-8"))
    
    tbox = TBoxSchema(
        classes=[ClassDef(**c) for c in data.get("classes", [])],
        relations=[RelationDef(**r) for r in data.get("relations", [])],
        attributes=[AttributeDef(**a) for a in data.get("attributes", [])],
    )
    
    logger.info(f"  ✅ 加载成功: {len(tbox.classes)} 个类, {len(tbox.relations)} 个关系, {len(tbox.attributes)} 个属性")
    
    # 检查 parent 字段
    classes_with_parent = sum(1 for c in tbox.classes if c.parent)
    logger.info(f"  🔗 继承关系: {classes_with_parent}/{len(tbox.classes)} 个类有父类")
    
    return tbox


def apply_deduplication(
    tbox: TBoxSchema, 
    threshold: float = 0.7,
    output_dir: Path = None
) -> TBoxSchema:
    """应用向量去重"""
    logger.info(f"🔄 开始去重（阈值={threshold}）...")
    
    deduplicator = EmbeddingDeduplicator(threshold=threshold)
    base_dict = tbox.to_dict()
    
    # 去重类
    candidate_classes = base_dict.get("classes", [])
    class_result = deduplicator.deduplicate_classes([], candidate_classes)
    logger.info(f"  📦 类去重: {len(candidate_classes)} → {len(class_result.accepted)} (拒绝 {len(class_result.rejected)})")
    
    # 去重关系
    candidate_rels = base_dict.get("relations", [])
    rel_result = deduplicator.deduplicate_relations([], candidate_rels)
    logger.info(f"  🔗 关系去重: {len(candidate_rels)} → {len(rel_result.accepted)} (拒绝 {len(rel_result.rejected)})")
    
    # 构建去重后的 TBox
    dedup_tbox = TBoxSchema(
        classes=[ClassDef(**c) for c in class_result.accepted],
        relations=[RelationDef(**r) for r in rel_result.accepted],
        attributes=tbox.attributes,  # 属性通常不去重
    )
    
    # 保存去重报告
    if output_dir:
        report = {
            "class_dedup": {
                "original": len(candidate_classes),
                "accepted": len(class_result.accepted),
                "rejected": len(class_result.rejected),
                "rejected_items": [
                    {"name": r.get("name"), "reason": "相似度过高"}
                    for r in class_result.rejected
                ]
            },
            "relation_dedup": {
                "original": len(candidate_rels),
                "accepted": len(rel_result.accepted),
                "rejected": len(rel_result.rejected),
                "rejected_items": [
                    {"name": r.get("name"), "reason": "相似度过高"}
                    for r in rel_result.rejected
                ]
            }
        }
        
        report_path = output_dir / "dedup_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"  📊 去重报告: {report_path}")
    
    logger.info(f"  ✅ 去重完成")
    return dedup_tbox


def main():
    parser = argparse.ArgumentParser(description="手动 P2+P3 流程：去重和规范化")
    parser.add_argument("--p2-file", type=str, required=True, help="P2 TBox JSON 文件路径")
    parser.add_argument("--output-dir", type=str, default="outputs/manual", help="输出目录")
    parser.add_argument("--dedup-threshold", type=float, default=0.7, help="去重阈值")
    
    args = parser.parse_args()
    
    p2_file = Path(args.p2_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("=" * 80)
    logger.info("手动 P2→P3 流程（带继承关系）")
    logger.info("=" * 80)
    
    # 1. 加载 P2 TBox
    p2_tbox = load_p2_tbox(p2_file)
    
    # 2. 应用去重
    p3_tbox = apply_deduplication(p2_tbox, args.dedup_threshold, output_dir)
    
    # 3. 保存 P3 TBox
    p3_file = output_dir / "p3_tbox_dedup.json"
    p3_file.write_text(
        json.dumps(p3_tbox.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    logger.info(f"✅ P3 TBox 已保存: {p3_file}")
    
    # 4. 统计信息
    logger.info("")
    logger.info("📊 最终统计:")
    logger.info(f"  类: {len(p3_tbox.classes)} 个")
    logger.info(f"  关系: {len(p3_tbox.relations)} 个")
    logger.info(f"  属性: {len(p3_tbox.attributes)} 个")
    
    classes_with_parent = sum(1 for c in p3_tbox.classes if c.parent)
    logger.info(f"  继承关系: {classes_with_parent}/{len(p3_tbox.classes)} 个类有父类")
    
    if classes_with_parent > 0:
        ir = classes_with_parent / len(p3_tbox.classes)
        logger.info(f"  🎯 继承丰富度 (IR): {ir:.4f}")
    else:
        logger.warning("  ⚠️  警告: 没有检测到继承关系！请确保 P2 TBox 中包含 parent 字段")
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("✅ 完成！下一步可以使用此 TBox 运行 P4 增强")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
