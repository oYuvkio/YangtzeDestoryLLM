"""
P2-P6 完整执行脚本

使用方法：
    python scripts/run_p2_to_p6.py --corpus_dir data/corpus --output_dir outputs/kg_final

流程：
    P2: CQ → 初始TBox
    P3: TBox规范化
    P4: 文献增强
    P4+: 统一向量去重
    P5: CoT约束抽取 + 原文回溯校验
    P6: 知识融合
"""

import json
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def load_cqs_from_file(cq_path: Path) -> List:
    """加载已有的CQ文件"""
    from kg.cq_pipeline import CQ

    with cq_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    cqs = []
    for item in data.get("cqs", []):
        cqs.append(CQ(
            id=str(item.get("id", len(cqs) + 1)),
            question=item.get("question", ""),
            category=item.get("category", ""),
        ))
    return cqs


def run_p2_initial_tbox(pipeline, cqs: List, output_dir: Path):
    """
    P2: 从CQ生成初始TBox

    注意事项：
    - 确保CQ覆盖各类灾害场景
    - 输出的TBox可能有冗余，将在P3清洗
    """
    logger.info("=" * 50)
    logger.info("[P2] 开始生成初始TBox...")

    tbox_init = pipeline.cq_to_schema(
        cqs,
        save_path=output_dir / "p2_tbox_init.json"
    )

    logger.info(f"[P2] 完成: 类 {len(tbox_init.classes)} 个, "
                f"关系 {len(tbox_init.relations)} 条, "
                f"属性 {len(tbox_init.attributes)} 个")

    return tbox_init


def run_p3_normalize(pipeline, tbox_init, output_dir: Path):
    """
    P3: TBox规范化

    注意事项：
    - 会合并语义相似的类（如 FloodEvent 和 FloodDisaster）
    - 会构建类层次结构
    - 检查 p3_tbox_refinement.json 中的 merged_class_aliases 是否合理
    """
    logger.info("=" * 50)
    logger.info("[P3] 开始TBox规范化...")

    # Step 1: 获取规范化建议
    p3_result = pipeline.refine_schema(
        tbox_init,
        save_path=output_dir / "p3_tbox_refinement.json"
    )

    # Step 2: 应用规范化
    tbox_normalized = pipeline.normalize_tbox_with_p3(
        tbox_init,
        p3_result,
        save_path=output_dir / "p3_tbox_normalized.json"
    )

    logger.info(f"[P3] 完成: 类 {len(tbox_normalized.classes)} 个, "
                f"关系 {len(tbox_normalized.relations)} 条")

    return tbox_normalized


def run_p4_enhance(pipeline, tbox_normalized, corpus_dir: Path, output_dir: Path,
                   min_support: int = 2, max_docs: Optional[int] = None):
    """
    P4: 文献驱动增强

    参数说明：
    - min_support: 概念至少在多少篇文献中出现才被采纳（默认2）
    - max_docs: 最多处理多少篇文献（None表示全部）

    注意事项：
    - 文献格式应为 .txt 文件
    - 建议先用少量文献测试（max_docs=5）
    - 检查 p4_suggestions.json 中的建议是否合理
    """
    logger.info("=" * 50)
    logger.info(f"[P4] 开始文献增强，语料目录: {corpus_dir}")

    tbox_augmented = pipeline.run_p4_over_corpus(
        base_schema=tbox_normalized,
        corpus_dir=str(corpus_dir),
        pattern="*.txt",
        max_docs=max_docs,
        min_support=min_support,
        allow_new_classes=True,  # 允许从文献中发现新类
        dedup_new=False,  # 这里不做去重，统一放到P4+
        save_suggestions_path=output_dir / "p4_suggestions.json",
        save_aug_tbox_path=output_dir / "p4_tbox_augmented.json",
    )

    logger.info(f"[P4] 完成: 类 {len(tbox_augmented.classes)} 个, "
                f"关系 {len(tbox_augmented.relations)} 条")

    return tbox_augmented


def run_p4_plus_dedup(pipeline, tbox_augmented, output_dir: Path,
                      class_threshold: float = 0.85,
                      relation_threshold: float = 0.80):
    """
    P4+: 统一向量去重（★ 新增步骤）

    参数说明：
    - class_threshold: 类相似度阈值（0.85 = 85%相似则合并）
    - relation_threshold: 关系相似度阈值

    注意事项：
    - 这是P4之后、P5之前的关键步骤
    - 阈值不要设太低，否则会误合并不同概念
    - 检查合并日志确认合并是否合理
    """
    logger.info("=" * 50)
    logger.info("[P4+] 开始统一向量去重...")

    # 使用现有的去重方法
    # 注意：这里使用较保守的阈值
    tbox_final = pipeline.deduplicate_tbox(
        tbox_augmented,
        threshold=class_threshold
    )

    # 保存最终TBox
    with (output_dir / "p4_tbox_final.json").open("w", encoding="utf-8") as f:
        json.dump(tbox_final.to_dict(), f, ensure_ascii=False, indent=2)

    logger.info(f"[P4+] 去重完成: 类 {len(tbox_augmented.classes)} -> {len(tbox_final.classes)}, "
                f"关系 {len(tbox_augmented.relations)} -> {len(tbox_final.relations)}")

    return tbox_final


def load_corpus_segments(corpus_dir: Path, pattern: str = "*.txt",
                         max_segments: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    加载语料库文本片段

    返回格式：
    [
        {
            "id": "文件名_序号",
            "text": "文本内容",
            "source": "文件路径",
            "context_before": "",  # 可选
            "context_after": "",   # 可选
        }
    ]
    """
    segments = []

    for fp in sorted(corpus_dir.glob(pattern)):
        try:
            text = fp.read_text(encoding="utf-8").strip()
            if not text:
                continue

            # 简单分段（按段落）
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

            for i, para in enumerate(paragraphs):
                if len(para) < 50:  # 跳过太短的段落
                    continue

                segment = {
                    "id": f"{fp.stem}_{i+1}",
                    "text": para,
                    "source": str(fp),
                    "context_before": paragraphs[i-1] if i > 0 else "",
                    "context_after": paragraphs[i+1] if i < len(paragraphs)-1 else "",
                }
                segments.append(segment)

                if max_segments and len(segments) >= max_segments:
                    return segments

        except Exception as e:
            logger.warning(f"读取文件失败: {fp}, 错误: {e}")
            continue

    return segments


def run_p5_p6_extraction(pipeline, tbox_final, corpus_dir: Path, output_dir: Path,
                         use_cot: bool = True,
                         strict_filter: bool = True,
                         fuzzy_threshold: float = 0.8,
                         max_segments: Optional[int] = None):
    """
    P5 + P6: CoT约束抽取 + 原文回溯校验 + 知识融合

    参数说明：
    - use_cot: 是否使用思维链Prompt（推荐True）
    - strict_filter: 严格模式只使用精确匹配（推荐True）
    - fuzzy_threshold: 模糊匹配阈值（0.8 = 80%相似度）
    - max_segments: 最多处理多少个片段（测试用）

    注意事项：
    - P5会自动进行原文回溯校验，过滤幻觉
    - P6会进行实体归一化和关系去重
    - 每个片段的抽取结果保存在 extractions/ 子目录
    - 最终融合结果保存在 final_triples.json
    """
    logger.info("=" * 50)
    logger.info("[P5+P6] 开始知识抽取与融合...")

    # 创建抽取结果目录
    extraction_dir = output_dir / "extractions"
    extraction_dir.mkdir(parents=True, exist_ok=True)

    # 加载语料片段
    segments = load_corpus_segments(corpus_dir, max_segments=max_segments)
    logger.info(f"[P5+P6] 加载了 {len(segments)} 个文本片段")

    # 收集所有抽取结果
    all_events = []
    all_triples = []
    all_filtered = []

    total_hallucination_count = 0
    total_triple_count = 0

    for idx, segment in enumerate(segments, start=1):
        logger.info(f"[P5] 处理片段 {idx}/{len(segments)}: {segment['id']}")

        try:
            # 使用完整的抽取+融合方法
            result = pipeline.extract_and_fuse(
                paragraph=segment["text"],
                schema=tbox_final,
                context_before=segment.get("context_before", ""),
                context_after=segment.get("context_after", ""),
                save_path=extraction_dir / f"{segment['id']}.json",
                use_cot=use_cot,
                strict_filter=strict_filter,
                fuzzy_threshold=fuzzy_threshold,
            )

            # 为结果添加来源信息
            for event in result.get("events", []):
                event["_source_segment"] = segment["id"]
            for triple in result.get("triples", []):
                triple["_source_segment"] = segment["id"]

            all_events.extend(result.get("events", []))
            all_triples.extend(result.get("triples", []))
            all_filtered.extend(result.get("filtered_triples", []))

            # 统计幻觉率
            stats = result.get("stats", {})
            total_triple_count += stats.get("total_triples", 0)
            total_hallucination_count += stats.get("filtered_triples", 0)

        except Exception as e:
            logger.error(f"[P5] 处理失败: {segment['id']}, 错误: {e}")
            continue

    # P6: 对所有结果进行最终融合
    logger.info("[P6] 进行最终知识融合...")

    from kg.entity_fusion import fuse_knowledge

    if all_triples:
        final_triples, fusion_stats = fuse_knowledge(all_triples)
    else:
        final_triples = []
        fusion_stats = {"entity_merges": 0, "reduction_rate": 0}

    # 计算总体幻觉率
    overall_hallucination_rate = (
        total_hallucination_count / total_triple_count * 100
        if total_triple_count > 0 else 0
    )

    # 保存最终结果
    final_result = {
        "events": all_events,
        "triples": final_triples,
        "filtered_triples": all_filtered,
        "statistics": {
            "total_segments": len(segments),
            "total_events": len(all_events),
            "total_triples_before_fusion": len(all_triples),
            "total_triples_after_fusion": len(final_triples),
            "total_filtered_triples": len(all_filtered),
            "overall_hallucination_rate": f"{overall_hallucination_rate:.2f}%",
            "fusion_reduction_rate": f"{fusion_stats.get('reduction_rate', 0):.1%}",
            "entity_merges": fusion_stats.get("entity_merges", 0),
        }
    }

    with (output_dir / "final_triples.json").open("w", encoding="utf-8") as f:
        json.dump(final_result, f, ensure_ascii=False, indent=2)

    logger.info("=" * 50)
    logger.info("[P5+P6] 完成!")
    logger.info(f"  - 处理片段: {len(segments)} 个")
    logger.info(f"  - 抽取事件: {len(all_events)} 个")
    logger.info(f"  - 有效三元组: {len(final_triples)} 条 (融合前 {len(all_triples)} 条)")
    logger.info(f"  - 过滤幻觉: {len(all_filtered)} 条")
    logger.info(f"  - 总体幻觉率: {overall_hallucination_rate:.2f}%")
    logger.info(f"  - 融合缩减率: {fusion_stats.get('reduction_rate', 0):.1%}")

    return final_result


def main():
    parser = argparse.ArgumentParser(description="P2-P6 知识图谱构建流水线")

    # 必需参数
    parser.add_argument("--corpus_dir", type=str, required=True,
                        help="语料库目录路径")
    parser.add_argument("--output_dir", type=str, default="outputs/kg_final",
                        help="输出目录路径")

    # 可选参数 - 输入文件
    parser.add_argument("--cq_file", type=str, default=None,
                        help="已有的CQ文件路径（如果有）")
    parser.add_argument("--tbox_file", type=str, default=None,
                        help="已有的TBox文件路径（跳过P2-P4）")

    # 可选参数 - P4配置
    parser.add_argument("--p4_min_support", type=int, default=2,
                        help="P4概念最小支持度")
    parser.add_argument("--p4_max_docs", type=int, default=None,
                        help="P4最多处理文献数")

    # 可选参数 - P5配置
    parser.add_argument("--use_cot", action="store_true", default=True,
                        help="使用CoT Prompt")
    parser.add_argument("--strict_filter", action="store_true", default=True,
                        help="使用严格过滤模式")
    parser.add_argument("--fuzzy_threshold", type=float, default=0.8,
                        help="模糊匹配阈值")
    parser.add_argument("--max_segments", type=int, default=None,
                        help="最多处理片段数（测试用）")

    # 可选参数 - 跳过某些阶段
    parser.add_argument("--skip_p2", action="store_true",
                        help="跳过P2（需要提供--tbox_file）")
    parser.add_argument("--skip_p3", action="store_true",
                        help="跳过P3")
    parser.add_argument("--skip_p4", action="store_true",
                        help="跳过P4")
    parser.add_argument("--only_extraction", action="store_true",
                        help="只运行P5+P6（需要提供--tbox_file）")

    args = parser.parse_args()

    # 路径处理
    corpus_dir = Path(args.corpus_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not corpus_dir.exists():
        raise ValueError(f"语料库目录不存在: {corpus_dir}")

    # 初始化Pipeline
    from kg.cq_pipeline import CQLLMPipeline, TBoxSchema, ClassDef, RelationDef, AttributeDef

    pipeline = CQLLMPipeline(output_dir=str(output_dir))

    logger.info("=" * 60)
    logger.info("长江流域水旱灾害知识图谱构建 - P2~P6 流水线")
    logger.info("=" * 60)
    logger.info(f"语料目录: {corpus_dir}")
    logger.info(f"输出目录: {output_dir}")

    # ========== 情况1: 只运行抽取 ==========
    if args.only_extraction:
        if not args.tbox_file:
            raise ValueError("--only_extraction 需要提供 --tbox_file")

        with Path(args.tbox_file).open("r", encoding="utf-8") as f:
            tbox_data = json.load(f)
        tbox_final = TBoxSchema(
            classes=[ClassDef(**c) for c in tbox_data.get("classes", [])],
            relations=[RelationDef(**r) for r in tbox_data.get("relations", [])],
            attributes=[AttributeDef(**a) for a in tbox_data.get("attributes", [])],
        )

        run_p5_p6_extraction(
            pipeline, tbox_final, corpus_dir, output_dir,
            use_cot=args.use_cot,
            strict_filter=args.strict_filter,
            fuzzy_threshold=args.fuzzy_threshold,
            max_segments=args.max_segments,
        )
        return

    # ========== 情况2: 完整流程 ==========

    # P2: 生成初始TBox
    if args.skip_p2 or args.tbox_file:
        if args.tbox_file:
            logger.info(f"[P2] 跳过，加载已有TBox: {args.tbox_file}")
            with Path(args.tbox_file).open("r", encoding="utf-8") as f:
                tbox_data = json.load(f)
            tbox_init = TBoxSchema(
                classes=[ClassDef(**c) for c in tbox_data.get("classes", [])],
                relations=[RelationDef(**r) for r in tbox_data.get("relations", [])],
                attributes=[AttributeDef(**a) for a in tbox_data.get("attributes", [])],
            )
        else:
            raise ValueError("跳过P2需要提供--tbox_file")
    else:
        # 加载CQ
        if args.cq_file:
            cqs = load_cqs_from_file(Path(args.cq_file))
        else:
            # 如果没有CQ文件，使用默认领域描述生成
            from kg.cq_pipeline import DEMO_DOMAIN_DESC
            cqs = pipeline.generate_cqs(DEMO_DOMAIN_DESC, n_cq=30,
                                        save_path=output_dir / "p1_cqs.json")

        tbox_init = run_p2_initial_tbox(pipeline, cqs, output_dir)

    # P3: TBox规范化
    if args.skip_p3:
        logger.info("[P3] 跳过")
        tbox_normalized = tbox_init
    else:
        tbox_normalized = run_p3_normalize(pipeline, tbox_init, output_dir)

    # P4: 文献增强
    if args.skip_p4:
        logger.info("[P4] 跳过")
        tbox_augmented = tbox_normalized
    else:
        tbox_augmented = run_p4_enhance(
            pipeline, tbox_normalized, corpus_dir, output_dir,
            min_support=args.p4_min_support,
            max_docs=args.p4_max_docs,
        )

    # P4+: 统一去重
    tbox_final = run_p4_plus_dedup(pipeline, tbox_augmented, output_dir)

    # P5 + P6: 抽取与融合
    run_p5_p6_extraction(
        pipeline, tbox_final, corpus_dir, output_dir,
        use_cot=args.use_cot,
        strict_filter=args.strict_filter,
        fuzzy_threshold=args.fuzzy_threshold,
        max_segments=args.max_segments,
    )

    logger.info("=" * 60)
    logger.info("全部完成!")
    logger.info(f"结果保存在: {output_dir}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
