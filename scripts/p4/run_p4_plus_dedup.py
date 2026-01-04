#!/usr/bin/env python3
"""
P4+ 统一向量去重脚本

对 P4 生成的多个 TBox 版本进行 embedding 相似度去重，
去除语义重复的类/关系定义，支持多阈值批量对比。

使用方式：
    python scripts/p4/run_p4_plus_dedup.py
    python scripts/p4/run_p4_plus_dedup.py --thresholds 0.7 0.75 0.8

输出：
    outputs/cq_pipeline/final/p4_tbox_*_dedup.json
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Set

# 添加项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kg.cq_pipeline import TBoxSchema, ClassDef, RelationDef, AttributeDef
from kg.utils.deduplication import EmbeddingDeduplicator

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def load_tbox(path: Path) -> TBoxSchema:
    """加载 TBox JSON 文件"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return TBoxSchema(
        classes=[ClassDef(**c) for c in data.get("classes", [])],
        relations=[RelationDef(**r) for r in data.get("relations", [])],
        attributes=[AttributeDef(**a) for a in data.get("attributes", [])]
    )


def save_tbox(tbox: TBoxSchema, path: Path):
    """保存 TBox 到 JSON 文件"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tbox.to_dict(), f, ensure_ascii=False, indent=2)


def count_tbox(tbox: TBoxSchema) -> Dict[str, int]:
    """统计 TBox 元素数量"""
    return {
        "classes": len(tbox.classes),
        "relations": len(tbox.relations),
        "attributes": len(tbox.attributes),
        "total": len(tbox.classes) + len(tbox.relations) + len(tbox.attributes)
    }


def remap_attributes(
    attributes: List[AttributeDef],
    merge_map: Dict[str, str],
    valid_classes: Set[str],
) -> Dict[str, Any]:
    """重映射属性 owner，清理去重后无效的属性。"""
    kept = 0
    remapped = 0
    removed = 0
    deduped = 0
    seen = set()
    new_attrs: List[AttributeDef] = []

    for attr in attributes:
        new_owner = merge_map.get(attr.owner, attr.owner)
        if new_owner not in valid_classes:
            removed += 1
            continue
        key = (new_owner, attr.name)
        if key in seen:
            deduped += 1
            continue
        seen.add(key)
        if new_owner != attr.owner:
            remapped += 1
        new_attrs.append(
            AttributeDef(
                owner=new_owner,
                name=attr.name,
                cn_name=attr.cn_name,
                value_type=attr.value_type,
            )
        )
        kept += 1

    return {
        "attributes": new_attrs,
        "stats": {
            "kept": kept,
            "remapped": remapped,
            "removed": removed,
            "deduped": deduped,
        },
    }


def run_dedup(
    input_path: Path,
    output_path: Path,
    deduper: EmbeddingDeduplicator,
) -> Dict[str, Any]:
    """
    对单个 TBox 执行去重

    Returns:
        统计信息字典
    """
    logger.info(f"处理: {input_path.name}")

    # 加载
    tbox_before = load_tbox(input_path)
    count_before = count_tbox(tbox_before)

    logger.info(f"  去重前: 类 {count_before['classes']}, 关系 {count_before['relations']}, 属性 {count_before['attributes']}")

    # 去重（类/关系）
    base_dict = tbox_before.to_dict()
    class_res = deduper.deduplicate_classes([], base_dict.get("classes", []))
    rel_res = deduper.deduplicate_relations([], base_dict.get("relations", []))
    classes = [ClassDef(**c) for c in class_res.accepted]
    relations = [RelationDef(**r) for r in rel_res.accepted]
    valid_classes = {c.name for c in classes}

    # 属性按类合并映射，避免 owner 指向无效类
    attr_remap = remap_attributes(
        tbox_before.attributes, class_res.merge_map, valid_classes
    )
    tbox_after = TBoxSchema(
        classes=classes,
        relations=relations,    
        attributes=attr_remap["attributes"],
    )

    count_after = count_tbox(tbox_after)

    logger.info(
        f"  去重后: 类 {count_after['classes']}, 关系 {count_after['relations']}, "
        f"属性 {count_after['attributes']}"
    )
    logger.info(
        "  属性处理: 保留 %(kept)s, 重映射 %(remapped)s, 移除 %(removed)s, 去重 %(deduped)s",
        attr_remap["stats"],
    )

    # 计算去重数量
    removed_classes = count_before['classes'] - count_after['classes']
    removed_relations = count_before['relations'] - count_after['relations']

    logger.info(f"  去除: 类 -{removed_classes}, 关系 -{removed_relations}")

    # 保存
    save_tbox(tbox_after, output_path)
    logger.info(f"  保存: {output_path.name}")

    return {
        "input": str(input_path),
        "output": str(output_path),
        "before": count_before,
        "after": count_after,
        "removed": {
            "classes": removed_classes,
            "relations": removed_relations
        },
        "attr_stats": attr_remap["stats"],
        "merge_map_size": len(class_res.merge_map),
    }


def main():
    parser = argparse.ArgumentParser(description="P4+ 统一向量去重")
    parser.add_argument("--threshold", type=float, default=0.75,
                        help="去重相似度阈值（默认 0.75）")
    parser.add_argument("--thresholds", nargs="+", type=float, default=None,
                        help="多阈值列表，传入后会覆盖 --threshold")
    parser.add_argument("--input-dir", type=Path,
                        default=Path("outputs/cq_pipeline/final"),
                        help="输入目录")
    parser.add_argument("--versions", nargs="+",
                        default=["s2_allow0", "s2_allow1", "s3_allow0", "s3_allow1"],
                        help="要处理的版本列表")

    args = parser.parse_args()

    input_dir = args.input_dir
    versions = args.versions
    thresholds = args.thresholds or [args.threshold]

    logger.info("=" * 60)
    logger.info("P4+ 统一向量去重")
    logger.info("=" * 60)
    logger.info(f"输入目录: {input_dir}")
    logger.info(f"去重阈值: {thresholds}")
    logger.info(f"处理版本: {versions}")
    logger.info("=" * 60)

    results = []

    def format_threshold(value: float) -> str:
        return f"t{value:.2f}".replace(".", "p")

    for threshold in thresholds:
        logger.info("-" * 60)
        logger.info(f"开始处理阈值: {threshold}")
        deduper = EmbeddingDeduplicator(threshold=threshold)
        threshold_tag = format_threshold(threshold)

        for version in versions:
            # 查找输入文件
            pattern = f"p4_tbox_augmented_{version}*.json"
            candidates = sorted(input_dir.glob(pattern), reverse=True)

            # 过滤掉已去重的文件
            candidates = [c for c in candidates if "_dedup" not in c.name]

            if not candidates:
                logger.warning(f"未找到版本 {version} 的文件，跳过")
                continue

            input_path = candidates[0]  # 使用最新的

            # 构建输出文件名
            output_name = input_path.stem.replace("_augmented_", "_dedup_")
            output_name = f"{output_name}_{threshold_tag}.json"
            output_path = input_dir / output_name

            try:
                result = run_dedup(input_path, output_path, deduper)
                result["threshold"] = threshold
                results.append(result)
            except Exception as e:
                logger.error(f"处理 {version} 失败: {e}")
                continue

            logger.info("")

    # 生成汇总报告
    logger.info("=" * 60)
    logger.info("去重完成汇总")
    logger.info("=" * 60)

    print(f"\n{'阈值':<6} {'版本':<15} {'去重前':>12} {'去重后':>12} {'去除类':>8} {'去除关系':>8}")
    print("-" * 68)

    for r in results:
        threshold = r.get("threshold", 0.0)
        version = Path(r['input']).stem.replace("p4_tbox_augmented_", "").split("_")[0:2]
        version = "_".join(version)
        before = r['before']['total']
        after = r['after']['total']
        rm_c = r['removed']['classes']
        rm_r = r['removed']['relations']
        print(f"{threshold:<6.2f} {version:<15} {before:>12} {after:>12} {rm_c:>8} {rm_r:>8}")

    print("-" * 68)

    # 保存报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "thresholds": thresholds,
        "results": results
    }

    report_path = input_dir / "p4_dedup_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(f"\n报告已保存: {report_path}")

    # 输出文件列表
    logger.info("\n生成的去重文件:")
    for r in results:
        logger.info(f"  - {Path(r['output']).name}")


if __name__ == "__main__":
    main()
