"""
P2-P6 完整执行脚本

使用方法：
    python scripts/run_p2_to_p6.py --corpus_dir data/corpus --output_dir outputs/kg_final

流程：
    - CQ 模式：P2 → P3 → P4 → P4+ → P5 → P6
    - Hybrid 模式：专家骨架 + 语料聚类 → 支持度/置信度筛选 → P5 → P6
"""

import json
import argparse
import logging
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

import yaml

# 兼容直接运行脚本时的导入路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.logging_utils import init_logging

logger = logging.getLogger(__name__)


def load_config(cfg_path: str) -> Dict[str, Any]:
    """加载配置文件，失败时返回空字典。"""
    path = Path(cfg_path)
    if not path.exists():
        logger.warning("配置文件不存在: %s，使用默认配置", path)
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("配置文件读取失败: %s，错误: %s", path, exc)
        return {}


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

    if corpus_dir.is_file() and corpus_dir.suffix.lower() == ".jsonl":
        try:
            with corpus_dir.open("r", encoding="utf-8") as f:
                for idx, line in enumerate(f, start=1):
                    if not line.strip():
                        continue
                    try:
                        doc = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    doc_id = doc.get("doc_id") or doc.get("id") or f"jsonl_{idx}"
                    text = doc.get("text") or doc.get("source_text") or doc.get("content") or doc.get("paragraph") or ""
                    if not text or len(text.strip()) < 50:
                        continue

                    segment = {
                        "id": str(doc_id),
                        "text": str(text).strip(),
                        "source": str(corpus_dir),
                        "context_before": doc.get("context_before", "") or "",
                        "context_after": doc.get("context_after", "") or "",
                    }
                    segments.append(segment)

                    if max_segments and len(segments) >= max_segments:
                        return segments
        except Exception as exc:
            logger.warning("读取 JSONL 失败: %s, 错误: %s", corpus_dir, exc)
        return segments

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


def _safe_segment_id(segment_id: str) -> str:
    """生成安全的文件名片段，避免特殊字符导致路径问题。"""
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", segment_id.strip())
    return cleaned or "segment"


def run_p5_p6_extraction(pipeline, tbox_final, corpus_dir: Path, output_dir: Path,
                         use_cot: bool = True,
                         strict_filter: bool = True,
                         fuzzy_threshold: float = 0.8,
                         strict_schema: bool = True,
                         resume_extraction: bool = False,
                         max_segments: Optional[int] = None):
    """
    P5 + P6: CoT约束抽取 + 原文回溯校验 + 知识融合

    参数说明：
    - use_cot: 是否使用思维链Prompt（推荐True）
    - strict_filter: 严格模式只使用精确匹配（推荐True）
    - fuzzy_threshold: 模糊匹配阈值（0.8 = 80%相似度）
    - strict_schema: 是否严格执行 Schema 约束
    - resume_extraction: 是否断点续跑（跳过已抽取样本）
    - max_segments: 最多处理多少个片段（测试用）

    注意事项：
    - P5会自动进行原文回溯校验，过滤幻觉
    - P6会进行实体归一化和关系去重
    - 每个片段的抽取结果保存在 extractions/ 子目录
    - 最终融合结果保存在 final_triples.json
    """
    logger.info("=" * 50)
    logger.info("[P5+P6] 开始知识抽取与融合...")

    from kg.extraction_output import build_extraction_record

    # 创建抽取结果目录
    extraction_dir = output_dir / "extractions"
    extraction_dir.mkdir(parents=True, exist_ok=True)
    extraction_jsonl = output_dir / "extractions.jsonl"

    # 加载语料片段
    segments = load_corpus_segments(corpus_dir, max_segments=max_segments)
    logger.info(f"[P5+P6] 加载了 {len(segments)} 个文本片段")

    # 收集所有抽取结果
    all_events = []
    all_triples = []
    all_filtered = []
    all_schema_filtered = []

    total_hallucination_count = 0
    total_triple_count = 0

    processed_ids: set[str] = set()
    if resume_extraction and extraction_jsonl.exists():
        with extraction_jsonl.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                doc_id = str(record.get("doc_id", "")).strip()
                if doc_id and not record.get("error"):
                    processed_ids.add(doc_id)
        logger.info("断点续跑启用，已抽取样本数: %d", len(processed_ids))

    with extraction_jsonl.open("a", encoding="utf-8") as out_f:
        for idx, segment in enumerate(segments, start=1):
            logger.info(f"[P5] 处理片段 {idx}/{len(segments)}: {segment['id']}")
            if resume_extraction and str(segment["id"]) in processed_ids:
                logger.info("[P5] 跳过已抽取样本: %s", segment["id"])
                continue

            safe_id = _safe_segment_id(segment["id"])
            try:
                # 使用完整的抽取+融合方法
                result = pipeline.extract_and_fuse(
                    paragraph=segment["text"],
                    schema=tbox_final,
                    context_before=segment.get("context_before", ""),
                    context_after=segment.get("context_after", ""),
                    save_path=extraction_dir / f"{safe_id}.json",
                    use_cot=use_cot,
                    strict_filter=strict_filter,
                    fuzzy_threshold=fuzzy_threshold,
                    strict_schema=strict_schema,
                )

                # 为结果添加来源信息
                for event in result.get("events", []):
                    event["_source_segment"] = segment["id"]
                for triple in result.get("triples", []):
                    triple["_source_segment"] = segment["id"]

                all_events.extend(result.get("events", []))
                all_triples.extend(result.get("triples", []))
                all_filtered.extend(result.get("filtered_triples", []))
                all_schema_filtered.extend(result.get("schema_filtered_triples", []))

                # 统计幻觉率
                stats = result.get("stats", {})
                total_triple_count += stats.get("total_triples", 0)
                total_hallucination_count += stats.get("filtered_triples", 0)

                record = build_extraction_record(
                    doc_id=str(segment["id"]),
                    source_text=segment["text"],
                    extraction_result=result,
                    use_cot=use_cot,
                    use_verify=True,
                )
                if "fusion_stats" in result:
                    record["fusion_stats"] = result.get("fusion_stats")
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                out_f.flush()
            except Exception as e:
                logger.error(f"[P5] 处理失败: {segment['id']}, 错误: {e}")
                error_record = build_extraction_record(
                    doc_id=str(segment["id"]),
                    source_text=segment.get("text", ""),
                    extraction_result=None,
                    use_cot=use_cot,
                    use_verify=True,
                    error=str(e),
                )
                out_f.write(json.dumps(error_record, ensure_ascii=False) + "\n")
                out_f.flush()
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
        "schema_filtered_triples": all_schema_filtered,
        "statistics": {
            "total_segments": len(segments),
            "total_events": len(all_events),
            "total_triples_before_fusion": len(all_triples),
            "total_triples_after_fusion": len(final_triples),
            "total_filtered_triples": len(all_filtered),
            "total_schema_filtered_triples": len(all_schema_filtered),
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
    logger.info(f"  - Schema 过滤: {len(all_schema_filtered)} 条")
    logger.info(f"  - 总体幻觉率: {overall_hallucination_rate:.2f}%")
    logger.info(f"  - 融合缩减率: {fusion_stats.get('reduction_rate', 0):.1%}")

    return final_result


def main():
    parser = argparse.ArgumentParser(description="P2-P6 知识图谱构建流水线")

    # 必需参数
    parser.add_argument("--corpus_dir", "--corpus", type=str, required=True,
                        help="语料库目录路径")
    parser.add_argument("--output_dir", type=str, default="outputs/kg_final",
                        help="输出目录路径")
    parser.add_argument("--cfg", type=str, default="configs/cfg.yaml",
                        help="配置文件路径（用于读取 llm/base_url 等配置）")
    parser.add_argument("--log-file", type=str, default="",
                        help="日志文件路径（启用后同时输出到控制台和文件）")

    # 可选参数 - 输入文件
    parser.add_argument("--cq_file", type=str, default=None,
                        help="已有的CQ文件路径（如果有）")
    parser.add_argument("--tbox_file", "--tbox", type=str, default=None,
                        help="已有的TBox文件路径（跳过P2-P4）")
    parser.add_argument("--tbox_mode", type=str, default="hybrid",
                        choices=["cq", "hybrid"], help="TBox 构建方式（默认 hybrid）")
    parser.add_argument("--expert_skeleton", type=str, default="data/expert_skeleton.json",
                        help="专家骨架文件路径（hybrid 模式使用）")
    parser.add_argument("--ontology_corpus", type=str, default=None,
                        help="本体构建语料路径（hybrid 模式使用，默认使用 corpus_dir）")
    parser.add_argument("--ontology_max_docs", type=int, default=None,
                        help="本体构建最多处理文档数（hybrid 模式使用）")
    parser.add_argument("--ontology_progress", type=str, default="",
                        help="本体构建词汇挖掘进度文件路径（JSONL）")
    parser.add_argument("--ontology_resume", action="store_true",
                        help="本体构建断点续跑（跳过 progress 中已有样本）")

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
    schema_group = parser.add_mutually_exclusive_group()
    schema_group.add_argument("--strict-schema", action="store_true", dest="strict_schema",
                              default=True, help="严格执行 Schema 约束（默认开启）")
    schema_group.add_argument("--no-strict-schema", action="store_false", dest="strict_schema",
                              help="关闭严格 Schema 约束（仅标记不剔除）")
    parser.add_argument("--max_segments", type=int, default=None,
                        help="最多处理片段数（测试用）")
    parser.add_argument("--resume-extraction", action="store_true",
                        help="断点续跑抽取（跳过 extractions.jsonl 中已成功的 doc_id）")

    # 可选参数 - 跳过某些阶段
    parser.add_argument("--skip_p2", action="store_true",
                        help="跳过P2（需要提供--tbox_file）")
    parser.add_argument("--skip_p3", action="store_true",
                        help="跳过P3")
    parser.add_argument("--skip_p4", action="store_true",
                        help="跳过P4")
    parser.add_argument("--only_extraction", action="store_true",
                        help="只运行P5+P6（需要提供--tbox_file）")
    parser.add_argument("--only_tbox", action="store_true",
                        help="只运行TBox构建，不执行抽取")

    args = parser.parse_args()

    # 路径处理
    corpus_dir = Path(args.corpus_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not corpus_dir.exists():
        raise ValueError(f"语料库目录不存在: {corpus_dir}")

    # 初始化Pipeline
    from kg.cq_pipeline import CQLLMPipeline, TBoxSchema, ClassDef, RelationDef, AttributeDef

    cfg = load_config(args.cfg)
    cfg_logging = cfg.get("logging", {}) if isinstance(cfg, dict) else {}
    if args.log_file:
        cfg_logging = dict(cfg_logging) if isinstance(cfg_logging, dict) else {}
        cfg_logging["file"] = args.log_file
    init_logging(cfg_logging)
    llm_config = cfg.get("llm", {}) if isinstance(cfg, dict) else {}
    if llm_config:
        logger.info("使用 cfg.yaml 中的 llm 配置初始化 Pipeline")
    else:
        logger.warning("未读取到 llm 配置，将使用默认 LLM 配置")

    pipeline = CQLLMPipeline(llm_config=llm_config, output_dir=str(output_dir))

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
            strict_schema=args.strict_schema,
            resume_extraction=args.resume_extraction,
            max_segments=args.max_segments,
        )
        return

    # ========== 情况2: 完整流程 ==========
    if args.tbox_mode == "hybrid":
        if args.tbox_file:
            logger.info(f"[Hybrid] 跳过构建，加载已有TBox: {args.tbox_file}")
            with Path(args.tbox_file).open("r", encoding="utf-8") as f:
                tbox_data = json.load(f)
        else:
            from kg.hybrid_ontology import HybridOntologyBuilder
            ontology_corpus = args.ontology_corpus or str(corpus_dir)
            hybrid_out_dir = output_dir / "hybrid_ontology"
            progress_path = args.ontology_progress or str(hybrid_out_dir / "vocab_mining.jsonl")
            builder = HybridOntologyBuilder(llm_config=pipeline.llm_config)
            tbox_data = builder.build(
                corpus_path=ontology_corpus,
                expert_skeleton_path=args.expert_skeleton,
                output_dir=str(hybrid_out_dir),
                max_docs=args.ontology_max_docs,
                progress_path=progress_path,
                resume=args.ontology_resume,
            )
            logger.info(f"[Hybrid] 本体构建完成，输出目录: {hybrid_out_dir}")

        tbox_final = TBoxSchema(
            classes=[ClassDef(**c) for c in tbox_data.get("classes", [])],
            relations=[RelationDef(**r) for r in tbox_data.get("relations", [])],
            attributes=[AttributeDef(**a) for a in tbox_data.get("attributes", [])],
        )
    else:
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

    if args.only_tbox:
        tbox_path = output_dir / "tbox_final.json"
        with tbox_path.open("w", encoding="utf-8") as f:
            json.dump(tbox_final.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"[TBox] 构建完成，仅输出 TBox: {tbox_path}")
        return

    # P5 + P6: 抽取与融合
    run_p5_p6_extraction(
        pipeline, tbox_final, corpus_dir, output_dir,
        use_cot=args.use_cot,
        strict_filter=args.strict_filter,
        fuzzy_threshold=args.fuzzy_threshold,
        strict_schema=args.strict_schema,
        resume_extraction=args.resume_extraction,
        max_segments=args.max_segments,
    )

    logger.info("=" * 60)
    logger.info("全部完成!")
    logger.info(f"结果保存在: {output_dir}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
