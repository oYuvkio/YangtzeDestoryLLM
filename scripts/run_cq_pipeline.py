"""
CQ 驱动的 TBox + KG 抽取全流程。

支持 P1-P5 各阶段独立或串联运行：
- P1: 领域描述 -> 生成 CQ（能力问题）
- P2: CQ -> 初始 TBox（类、关系、属性定义）
- P3: TBox 规范化（命名统一、去重、冲突检测）
- P4: TBox 增强（基于样本文本扩展模式）
- P5: 事件与三元组抽取（支持批量模式）

用法示例：
    # 完整流程
    python scripts/run_cq_pipeline.py --provider zhipu --model glm-4.5-flash
    
    # 从 P3 开始（使用已有 P2 输出）
    python scripts/run_cq_pipeline.py --start-step p3 --p2-file outputs/p2_tbox.json
    
    # 仅运行 P5 批量抽取
    python scripts/run_cq_pipeline.py --start-step p5 --p4-file outputs/p4_tbox.json \\
        --corpus-jsonl data/light_pool.jsonl --include-context

注意：
* 需要提前设置对应的 API KEY（OPENAI_API_KEY / ZHIPU_API_KEY / GEMINI_API_KEY）；
* 默认使用 summary 中的领域说明与 1998 洪水示例段落，可通过参数替换。
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from kg.cq_pipeline import (
    CQLLMPipeline,
    TBoxSchema,
    ClassDef,
    RelationDef,
    AttributeDef,
    DEMO_DOMAIN_DESC,
    DEMO_PARAGRAPH_1998,
)
from kg.utils.deduplication import EmbeddingDeduplicator
from kg.utils.conflict_detection import detect_schema_conflicts, summarize_conflicts
from kg.utils.entity_linking import normalize_extraction_result
from tools.logging_utils import init_logging

# ============================================================================
# 日志配置
# ============================================================================
logger = logging.getLogger(__name__)


# ============================================================================
# 辅助函数
# ============================================================================

def pick(*vals: Any, default: Any = None) -> Any:
    """
    从多个值中选择第一个有效值。
    
    Args:
        *vals: 候选值列表，按优先级排序
        default: 所有候选值无效时的默认值
        
    Returns:
        第一个非空、非 None 的值，或 default
    """
    for v in vals:
        if v not in (None, ""):
            return v
    return default


def read_text_if_provided(path: Optional[str], fallback: str) -> str:
    """
    若传入文件路径则读取文件内容，否则返回默认文本。
    
    Args:
        path: 可选的文件路径
        fallback: 路径为空时的默认文本
        
    Returns:
        文件内容或默认文本
    """
    if path:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"指定文件不存在: {path}")
        return file_path.read_text(encoding="utf-8")
    return fallback


def load_tbox_from_file(path: Path) -> TBoxSchema:
    """
    从 JSON 文件加载 TBox 模式。
    
    Args:
        path: TBox JSON 文件路径
        
    Returns:
        TBoxSchema 实例
        
    Raises:
        FileNotFoundError: 文件不存在
        json.JSONDecodeError: JSON 解析失败
    """
    if not path.exists():
        raise FileNotFoundError(f"TBox 文件不存在: {path}")
    
    data = json.loads(path.read_text(encoding="utf-8"))
    return TBoxSchema(
        classes=[ClassDef(**c) for c in data.get("classes", [])],
        relations=[RelationDef(**r) for r in data.get("relations", [])],
        attributes=[AttributeDef(**a) for a in data.get("attributes", [])],
    )


def load_cqs_from_file(path: Path) -> List:
    """
    从 JSON 文件加载 CQ 列表。
    
    支持两种格式：
    1. {"cqs": [...]}  带包装的格式
    2. [...]  直接的列表格式
    
    Args:
        path: CQ JSON 文件路径
        
    Returns:
        CQ 对象列表
    """
    if not path.exists():
        raise FileNotFoundError(f"CQ 文件不存在: {path}")
    
    from kg.cq_pipeline import CQ
    
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "cqs" in data:
        return [CQ(**c) for c in data["cqs"]]
    elif isinstance(data, list):
        return [CQ(**c) if isinstance(c, dict) else c for c in data]
    else:
        raise ValueError(f"无法识别的 CQ 文件格式: {path}")


# ============================================================================
# P5 批量抽取支持
# ============================================================================

def load_segments_for_p5(
    jsonl_path: Path,
    max_segments: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    从 JSONL 文件加载待抽取的片段。
    
    支持从 filter_corpus_light.py 输出的 light_pool.jsonl 格式：
    - id: 片段唯一标识
    - text: 主文本内容
    - source_file: 源文件名
    - context_before: 可选的前文上下文
    - context_after: 可选的后文上下文
    
    Args:
        jsonl_path: 过滤后的语料 JSONL 文件路径
        max_segments: 最大片段数限制，None 表示无限制
        
    Returns:
        片段字典列表
        
    Raises:
        FileNotFoundError: 文件不存在
    """
    if not jsonl_path.exists():
        raise FileNotFoundError(f"语料文件不存在: {jsonl_path}")
    
    segments = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                seg = json.loads(line)
                # 确保有基本字段
                if "text" not in seg:
                    logger.warning(f"第 {line_no} 行缺少 text 字段，跳过")
                    continue
                # 确保有 id
                if "id" not in seg:
                    seg["id"] = f"seg_{line_no}"
                segments.append(seg)
                if max_segments and len(segments) >= max_segments:
                    break
            except json.JSONDecodeError as e:
                logger.warning(f"第 {line_no} 行 JSON 解析失败: {e}")
                continue
    
    logger.info(f"加载了 {len(segments)} 个片段，来源: {jsonl_path}")
    return segments


def build_extraction_input(
    segment: Dict[str, Any],
    include_context: bool = True,
    max_chars: int = 4000,
    context_ratio: float = 0.3,
) -> str:
    """
    构建 P5 抽取的输入文本。
    
    支持拼接上下文以提供更丰富的语义信息。
    使用结构化标记区分不同部分：
    - 【前文参考】: 提供上文背景，但不作为抽取目标
    - 【待抽取文本】: 主要抽取内容
    - 【后文参考】: 提供下文背景，但不作为抽取目标
    
    Args:
        segment: 片段字典，包含 text 和可选的 context_before/context_after
        include_context: 是否包含上下文
        max_chars: 最大字符数限制
        context_ratio: 上下文占比（前后各占一半）
        
    Returns:
        格式化的输入文本
    """
    main_text = segment.get("text", "")
    if not main_text:
        return ""
    
    # 不包含上下文时，直接返回主文本
    if not include_context:
        return main_text[:max_chars]
    
    context_before = segment.get("context_before", "")
    context_after = segment.get("context_after", "")
    
    # 计算各部分的字符限制
    main_len = len(main_text)
    remaining = max_chars - main_len - 60  # 预留标记空间
    
    if remaining <= 0:
        # 主文本已超限，截断主文本
        return f"【待抽取文本】\n{main_text[:max_chars - 20]}"
    
    # 分配上下文空间
    context_budget = int(remaining * context_ratio)
    before_budget = context_budget // 2
    after_budget = context_budget // 2
    
    # 组装文本
    parts = []
    
    if context_before:
        # 取末尾部分（最接近主文本的）
        trimmed_before = context_before[-before_budget:] if len(context_before) > before_budget else context_before
        if trimmed_before:
            parts.append(f"【前文参考】\n{trimmed_before}")
    
    parts.append(f"【待抽取文本】\n{main_text}")
    
    if context_after:
        # 取开头部分（最接近主文本的）
        trimmed_after = context_after[:after_budget] if len(context_after) > after_budget else context_after
        if trimmed_after:
            parts.append(f"【后文参考】\n{trimmed_after}")
    
    full_text = "\n\n".join(parts)
    return full_text[:max_chars]


def run_p5_batch(
    pipeline: "CQLLMPipeline",
    tbox: TBoxSchema,
    segments: List[Dict[str, Any]],
    output_dir: Path,
    favor_existing_classes: bool = True,
    normalize_entities: bool = False,
    include_context: bool = True,
    save_interval: int = 10,
) -> Dict[str, Any]:
    """
    批量执行 P5 抽取。
    
    支持断点续跑：如果已存在结果文件，将跳过已处理的片段。
    定期保存汇总结果，防止中断丢失数据。
    
    Args:
        pipeline: CQ 管道实例
        tbox: TBox 模式
        segments: 待抽取片段列表
        output_dir: 输出目录
        favor_existing_classes: 优先使用已有类
        normalize_entities: 是否标准化实体
        include_context: 是否使用上下文
        save_interval: 保存汇总的间隔（每处理 N 个片段保存一次）
        
    Returns:
        汇总统计结果
    """
    all_events: List[Dict] = []
    all_triples: List[Dict] = []
    failed: List[Dict] = []
    
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "p5_batch_results.jsonl"
    
    # 检查已处理的片段（断点续跑）
    processed_ids: set = set()
    if results_path.exists():
        with results_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    seg_id = item.get("segment_id")
                    if seg_id:
                        processed_ids.add(seg_id)
                except json.JSONDecodeError:
                    continue
        print(f"  🔄 发现已处理 {len(processed_ids)} 个片段，继续之前的进度...")
    
    total = len(segments)
    processed_count = 0
    start_time = time.time()
    
    for i, seg in enumerate(segments):
        seg_id = seg.get("id", f"seg_{i}")
        
        # 跳过已处理
        if seg_id in processed_ids:
            continue
        
        # 构建输入文本
        input_text = build_extraction_input(seg, include_context)
        if not input_text:
            logger.warning(f"片段 {seg_id} 文本为空，跳过")
            continue
        
        try:
            # 执行抽取
            result = pipeline.extract_events(
                input_text,
                tbox,
                save_path=None,
                favor_existing_classes=favor_existing_classes,
            )
            
            # 实体标准化
            if normalize_entities:
                result = normalize_extraction_result(result)
            
            events = result.get("events", [])
            triples = result.get("triples", [])
            
            all_events.extend(events)
            all_triples.extend(triples)
            
            # 写入单条结果（追加模式）
            with results_path.open("a", encoding="utf-8") as f:
                record = {
                    "segment_id": seg_id,
                    "source_file": seg.get("source_file", ""),
                    "events": events,
                    "triples": triples,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            
            processed_count += 1
            print(f"  [{i+1}/{total}] {seg_id}: 事件 {len(events)}, 三元组 {len(triples)}")
            
        except Exception as e:
            logger.error(f"片段 {seg_id} 抽取失败: {e}")
            failed.append({
                "segment_id": seg_id,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            print(f"  [{i+1}/{total}] {seg_id}: ✗ 失败 - {e}")
        
        # 定期保存汇总
        if processed_count > 0 and processed_count % save_interval == 0:
            _save_p5_summary(output_dir, all_events, all_triples, failed)
            elapsed = time.time() - start_time
            rate = processed_count / elapsed if elapsed > 0 else 0
            print(f"  💾 已保存汇总 ({processed_count} 个, {rate:.2f} 个/秒)")
    
    # 最终保存
    _save_p5_summary(output_dir, all_events, all_triples, failed)
    
    elapsed = time.time() - start_time
    summary = {
        "total_segments": total,
        "processed_segments": processed_count,
        "skipped_segments": len(processed_ids),
        "total_events": len(all_events),
        "total_triples": len(all_triples),
        "failed_count": len(failed),
        "elapsed_seconds": round(elapsed, 2),
    }
    
    # 保存执行摘要
    summary_path = output_dir / "p5_batch_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    return summary


def _save_p5_summary(
    output_dir: Path,
    events: List[Dict],
    triples: List[Dict],
    failed: List[Dict],
) -> None:
    """
    保存 P5 批量抽取的汇总文件。
    
    Args:
        output_dir: 输出目录
        events: 所有抽取的事件
        triples: 所有抽取的三元组
        failed: 失败记录
    """
    # 事件汇总
    events_path = output_dir / "p5_all_events.json"
    events_path.write_text(
        json.dumps({"events": events, "count": len(events)}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    # 三元组汇总
    triples_path = output_dir / "p5_all_triples.json"
    triples_path.write_text(
        json.dumps({"triples": triples, "count": len(triples)}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    # 失败记录
    if failed:
        failed_path = output_dir / "p5_failed.json"
        failed_path.write_text(
            json.dumps(failed, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )


def main() -> None:
    """
    主入口函数。
    
    解析命令行参数，加载配置，按顺序执行 P1-P5 各阶段。
    """
    parser = argparse.ArgumentParser(
        description="CQ 驱动的长江灾害 KG 构建流程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 完整流程
  python scripts/run_cq_pipeline.py --provider zhipu --model glm-4.5-flash
  
  # 从 P5 开始批量抽取
  python scripts/run_cq_pipeline.py --start-step p5 --p4-file outputs/p4_tbox.json \\
      --corpus-jsonl data/light_pool.jsonl --include-context
        """
    )
    
    # ===== 基础参数 =====
    parser.add_argument("--cfg", default="configs/cfg.yaml",
                        help="配置文件路径（命令行优先级最高）")
    parser.add_argument("--output-dir", default=None,
                        help="结果保存目录（默认读 cfg.paths.output_dir）")
    parser.add_argument("--start-step", choices=["p1", "p2", "p3", "p4", "p5"], default="p1",
                        help="从哪个阶段开始运行（默认 p1）")
    parser.add_argument("--only-stage", action="store_true",
                        help="仅运行指定的单个阶段")
    
    # ===== LLM 参数 =====
    llm_group = parser.add_argument_group("LLM 配置")
    llm_group.add_argument("--provider", default=None,
                           choices=["openai", "zhipu", "gemini"],
                           help="LLM 提供商")
    llm_group.add_argument("--model", default=None,
                           help="模型名称")
    llm_group.add_argument("--temperature", type=float, default=None,
                           help="采样温度（JSON 模式建议 0.1）")
    llm_group.add_argument("--llm-api-key", default=None,
                           help="API Key（建议从环境变量注入）")
    llm_group.add_argument("--llm-base-url", default=None,
                           help="自定义 Base URL")
    
    # ===== P1 参数 =====
    p1_group = parser.add_argument_group("P1: CQ 生成")
    p1_group.add_argument("--domain-file", default=None,
                          help="领域描述文件路径")
    p1_group.add_argument("--n-cq", type=int, default=10,
                          help="生成 CQ 的数量")
    p1_group.add_argument("--cqs-file", default=None,
                          help="已有 CQ 文件路径")
    
    # ===== P2/P3 参数 =====
    schema_group = parser.add_argument_group("P2/P3: TBox 生成与规范化")
    schema_group.add_argument("--p2-file", default=None,
                              help="已有 P2 TBox 文件路径")
    schema_group.add_argument("--p3-file", default=None,
                              help="已有 P3 TBox 文件路径")
    schema_group.add_argument("--dedup-schema", action="store_true",
                              help="对类/关系做 embedding 去重")
    schema_group.add_argument("--dedup-threshold", type=float, default=None,
                              help="去重相似度阈值（默认 0.75）")
    
    # ===== P4 参数 =====
    p4_group = parser.add_argument_group("P4: TBox 增强")
    p4_group.add_argument("--p4-file", default=None,
                          help="已有 P4 TBox 文件路径（跳过 P4）")
    p4_group.add_argument("--p4-sample-file", default=None,
                          help="P4 用于增强的样本文本文件")
    p4_group.add_argument("--p4-n-samples", type=int, default=3,
                          help="P4 使用的样本数量")
    
    # ===== P5 参数 =====
    p5_group = parser.add_argument_group("P5: 事件与三元组抽取")
    p5_group.add_argument("--paragraph-file", default=None,
                          help="单个文本文件（单条模式）")
    p5_group.add_argument("--corpus-jsonl", default=None,
                          help="过滤后的语料 JSONL 文件（批量模式）")
    p5_group.add_argument("--max-segments", type=int, default=None,
                          help="批量模式最多处理的片段数")
    p5_group.add_argument("--include-context", action="store_true",
                          help="抽取时包含上下文")
    p5_group.add_argument("--favor-existing-classes", action="store_true",
                          help="优先使用已有类（保守模式）")
    p5_group.add_argument("--normalize-entities", action="store_true",
                          help="实体标准化（地点别名等）")
    p5_group.add_argument("--save-interval", type=int, default=10,
                          help="批量抽取时的保存间隔")
    
    args = parser.parse_args()
    
    # =========================================================================
    # 加载配置文件
    # =========================================================================
    cfg: Dict[str, Any] = {}
    if args.cfg:
        cfg_path = Path(args.cfg)
        if cfg_path.exists():
            try:
                cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
                logger.info(f"加载配置文件: {cfg_path}")
            except Exception as e:
                logger.warning(f"配置文件解析失败: {e}")
                cfg = {}
    
    # 提取配置子项
    cfg_llm = cfg.get("llm", {}) if isinstance(cfg, dict) else {}
    cfg_llm_stage = cfg.get("llm_per_stage", {}) if isinstance(cfg, dict) else {}
    cfg_paths = cfg.get("paths", {}) if isinstance(cfg, dict) else {}
    cfg_p5 = cfg.get("p5", {}) if isinstance(cfg, dict) else {}
    cfg_p4 = cfg.get("p4", {}) if isinstance(cfg, dict) else {}
    cfg_dedup = cfg.get("dedup_schema", {}) if isinstance(cfg, dict) else {}
    cfg_log = cfg.get("logging", {}) if isinstance(cfg, dict) else {}
    
    init_logging(cfg_log)
    
    # =========================================================================
    # LLM 配置工厂函数
    # =========================================================================
    def get_llm_config(stage: str = "") -> Dict[str, Any]:
        """
        获取指定阶段的 LLM 配置。
        
        优先级：CLI > cfg.llm_per_stage[stage] > cfg.llm > 默认值
        """
        stage_cfg = cfg_llm_stage.get(stage, {}) if isinstance(cfg_llm_stage, dict) else {}
        provider_val = pick(args.provider, stage_cfg.get("provider"), 
                           cfg_llm.get("provider"), default="zhipu")
        model_val = pick(
            args.model, 
            stage_cfg.get("model_name"),
            cfg_llm.get("model_name"),
            default="gpt-4o-mini" if provider_val == "openai" else "glm-4.5-flash"
        )
        return {
            "provider": provider_val,
            "model_name": model_val,
            "temperature": pick(args.temperature, stage_cfg.get("temperature"),
                               cfg_llm.get("temperature"), default=0.1),
            "base_url": pick(args.llm_base_url, stage_cfg.get("base_url"),
                            cfg_llm.get("base_url")),
            "api_key": args.llm_api_key,  # 仅从 CLI 读取
            "thinking_type": cfg_llm.get("thinking_type"),
            "enable_thinking": cfg_llm.get("enable_thinking", False),
        }
    
    def create_pipeline(stage: str) -> CQLLMPipeline:
        """创建指定阶段的 Pipeline 实例。"""
        llm_conf = get_llm_config(stage)
        print(f"[{stage.upper()}] LLM: {llm_conf['provider']}/{llm_conf['model_name']} "
              f"(temp={llm_conf['temperature']})")
        return CQLLMPipeline(llm_config=llm_conf, output_dir=str(out_dir))
    
    # =========================================================================
    # 解析其他配置
    # =========================================================================
    output_dir = pick(args.output_dir, cfg_paths.get("output_dir"), 
                      default="outputs/cq_pipeline/final")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    favor_existing = pick(args.favor_existing_classes, 
                          cfg_p5.get("favor_existing_classes"), default=True)
    dedup_schema_flag = pick(args.dedup_schema, 
                             cfg_dedup.get("enabled"), default=False)
    dedup_threshold = pick(args.dedup_threshold, 
                           cfg_dedup.get("threshold"), default=0.75)
    normalize_entities_flag = pick(args.normalize_entities, 
                                   cfg_p5.get("normalize_entities"), default=False)
    include_context_flag = pick(args.include_context,
                                cfg_p5.get("include_context"), default=False)
    
    # =========================================================================
    # 初始化全局变量（解决作用域问题）
    # =========================================================================
    cqs: Optional[List] = None
    tbox: Optional[TBoxSchema] = None
    pipeline: Optional[CQLLMPipeline] = None
    
    print(f"\n{'='*60}")
    print(f"CQ 驱动的长江灾害 KG 构建流程")
    print(f"{'='*60}")
    print(f"输出目录: {out_dir}")
    print(f"起始阶段: {args.start_step.upper()}")
    print(f"仅单阶段: {args.only_stage}")
    print(f"{'='*60}\n")

    # =========================================================================
    # P1: 生成 CQ（能力问题）
    # =========================================================================
    if args.start_step == "p1":
        print("\n" + "-"*60)
        print("Step P1: 生成 CQ ...")
        print("-"*60)
        
        pipeline = create_pipeline("p1")
        domain_desc = read_text_if_provided(args.domain_file, DEMO_DOMAIN_DESC)
        
        cqs = pipeline.generate_cqs(
            domain_desc, 
            n_cq=args.n_cq, 
            save_path=out_dir / "p1_cqs.json"
        )
        print(f"  ✓ 获得 {len(cqs)} 条 CQ，已保存到 {out_dir / 'p1_cqs.json'}")
        
        if args.only_stage:
            print("\n已完成 P1 阶段，退出。")
            return
    else:
        # 加载已有 CQ
        cqs_path = Path(args.cqs_file) if args.cqs_file else out_dir / "p1_cqs.json"
        if cqs_path.exists():
            cqs = load_cqs_from_file(cqs_path)
            print(f"[SKIP P1] 使用已有 CQ: {cqs_path} ({len(cqs)} 条)")
        elif args.start_step != "p5":  # P5 可以不需要 CQ
            raise FileNotFoundError(f"CQ 文件不存在: {cqs_path}")
    
    # =========================================================================
    # P2: CQ -> 初始 TBox
    # =========================================================================
    if args.start_step in ["p1", "p2"]:
        print("\n" + "-"*60)
        print("Step P2: CQ -> 初始 TBox ...")
        print("-"*60)
        
        if cqs is None:
            raise ValueError("P2 需要 CQ 输入，请先运行 P1 或指定 --cqs-file")
        
        pipeline = create_pipeline("p2")
        tbox = pipeline.cq_to_schema(cqs, save_path=out_dir / "p2_tbox_init.json")
        print(f"  ✓ 类 {len(tbox.classes)} 个，关系 {len(tbox.relations)} 条")
        
        # 可选去重
        if dedup_schema_flag:
            print(f"  去重中 (threshold={dedup_threshold}) ...")
            tbox = pipeline.deduplicate_tbox(tbox, threshold=float(dedup_threshold))
            pipeline._dump_json(tbox.to_dict(), out_dir / "p2_tbox_init_dedup.json")
            print(f"  ✓ 去重后：类 {len(tbox.classes)}，关系 {len(tbox.relations)}")
        
        if args.only_stage and args.start_step == "p2":
            print("\n已完成 P2 阶段，退出。")
            return
    else:
        # 加载已有 P2 TBox
        tbox_path = Path(args.p2_file) if args.p2_file else out_dir / "p2_tbox_init.json"
        if tbox_path.exists():
            tbox = load_tbox_from_file(tbox_path)
            print(f"[SKIP P2] 使用已有 TBox: {tbox_path}")
    
    # =========================================================================
    # P3: TBox 规范化
    # =========================================================================
    if args.start_step in ["p1", "p2", "p3"]:
        print("\n" + "-"*60)
        print("Step P3: 规范化 TBox ...")
        print("-"*60)
        
        if tbox is None:
            raise ValueError("P3 需要 TBox 输入，请先运行 P2 或指定 --p2-file")
        
        pipeline = create_pipeline("p3")
        p3_res = pipeline.refine_schema(tbox, save_path=out_dir / "p3_tbox_refinement.json")
        tbox = pipeline.normalize_tbox_with_p3(
            tbox, p3_res, save_path=out_dir / "p3_tbox_normalized.json"
        )
        print(f"  ✓ 规范化完成：类 {len(tbox.classes)}，关系 {len(tbox.relations)}，属性 {len(tbox.attributes)}")
        
        # 可选去重
        if dedup_schema_flag:
            print(f"  P3 后去重 (threshold={dedup_threshold}) ...")
            tbox = pipeline.deduplicate_tbox(tbox, threshold=float(dedup_threshold))
            pipeline._dump_json(tbox.to_dict(), out_dir / "p3_tbox_normalized_dedup.json")
            print(f"  ✓ 去重后：类 {len(tbox.classes)}，关系 {len(tbox.relations)}")
        
        # 冲突检测
        conflicts = detect_schema_conflicts(tbox.to_dict())
        if conflicts:
            conf_path = out_dir / "p3_conflicts.json"
            conf_path.write_text(
                json.dumps(conflicts, ensure_ascii=False, indent=2), 
                encoding="utf-8"
            )
            summary = summarize_conflicts(conflicts)
            print(f"  ⚠️ 发现 {len(conflicts)} 条潜在冲突: {summary}")
        else:
            print("  ✓ 未发现模式冲突")
        
        if args.only_stage and args.start_step == "p3":
            print("\n已完成 P3 阶段，退出。")
            return
    else:
        # 加载已有 P3 TBox
        tbox_path = Path(args.p3_file) if args.p3_file else out_dir / "p3_tbox_normalized.json"
        if tbox_path.exists():
            tbox = load_tbox_from_file(tbox_path)
            print(f"[SKIP P3] 使用已有 TBox: {tbox_path}")
    
    # =========================================================================
    # P4: TBox 增强（基于样本文本扩展模式）
    # =========================================================================
    if args.start_step in ["p1", "p2", "p3", "p4"]:
        # 检查是否有已有 P4 文件
        if args.p4_file:
            tbox = load_tbox_from_file(Path(args.p4_file))
            print(f"[LOAD P4] 使用已有增强 TBox: {args.p4_file}")
        else:
            print("\n" + "-"*60)
            print("Step P4: TBox 增强 ...")
            print("-"*60)
            
            if tbox is None:
                raise ValueError("P4 需要 TBox 输入，请先运行 P3 或指定 --p3-file")
            
            pipeline = create_pipeline("p4")
            
            # 加载样本文本用于增强
            sample_text = ""
            if args.p4_sample_file:
                sample_text = Path(args.p4_sample_file).read_text(encoding="utf-8")
            elif args.paragraph_file:
                sample_text = Path(args.paragraph_file).read_text(encoding="utf-8")
            else:
                sample_text = DEMO_PARAGRAPH_1998
            
            # 执行 P4 增强（如果 pipeline 支持）
            if hasattr(pipeline, 'enhance_schema'):
                tbox = pipeline.enhance_schema(
                    tbox, 
                    sample_text=sample_text,
                    n_samples=args.p4_n_samples,
                    save_path=out_dir / "p4_tbox_enhanced.json"
                )
                print(f"  ✓ 增强完成：类 {len(tbox.classes)}，关系 {len(tbox.relations)}")
            else:
                # 如果不支持 enhance_schema，直接保存当前 TBox
                logger.warning("Pipeline 不支持 enhance_schema 方法，跳过 P4 增强")
                pipeline._dump_json(tbox.to_dict(), out_dir / "p4_tbox_enhanced.json")
                print(f"  ✓ 保存当前 TBox（未增强）")
        
        # 冲突检测
        conflicts = detect_schema_conflicts(tbox.to_dict())
        if conflicts:
            conf_path = out_dir / "p4_conflicts.json"
            conf_path.write_text(
                json.dumps(conflicts, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            summary = summarize_conflicts(conflicts)
            print(f"  ⚠️ 发现 {len(conflicts)} 条潜在冲突: {summary}")
        else:
            print("  ✓ 未发现模式冲突")
        
        if args.only_stage and args.start_step == "p4":
            print("\n已完成 P4 阶段，退出。")
            return
    else:
        # 从 P5 开始，必须指定 P4 文件
        if args.p4_file:
            tbox = load_tbox_from_file(Path(args.p4_file))
            print(f"[LOAD P4] 使用已有增强 TBox: {args.p4_file}")
        elif tbox is None:
            # 尝试加载默认 P4 文件
            default_p4 = out_dir / "p4_tbox_enhanced.json"
            if default_p4.exists():
                tbox = load_tbox_from_file(default_p4)
                print(f"[LOAD P4] 使用默认 P4 TBox: {default_p4}")
            else:
                raise ValueError(
                    "P5 需要 TBox 输入。请指定 --p4-file 或先运行 P1-P4 阶段"
                )
    
    # =========================================================================
    # P5: 事件与三元组抽取
    # =========================================================================
    print("\n" + "-"*60)
    print("Step P5: 事件与三元组抽取 ...")
    print("-"*60)
    
    if tbox is None:
        raise ValueError("P5 需要 TBox 输入")
    
    # 创建 Pipeline（如果还没有）
    if pipeline is None:
        pipeline = create_pipeline("p5")
    
    # 判断批量模式还是单条模式
    if args.corpus_jsonl:
        # ===== 批量模式 =====
        print(f"  模式: 批量抽取")
        print(f"  语料文件: {args.corpus_jsonl}")
        print(f"  包含上下文: {include_context_flag}")
        
        # 加载片段
        segments = load_segments_for_p5(
            Path(args.corpus_jsonl),
            max_segments=args.max_segments
        )
        
        if not segments:
            print("  ⚠️ 未加载到任何片段")
            return
        
        print(f"  待处理片段数: {len(segments)}")
        
        # 执行批量抽取
        summary = run_p5_batch(
            pipeline=pipeline,
            tbox=tbox,
            segments=segments,
            output_dir=out_dir,
            favor_existing_classes=bool(favor_existing),
            normalize_entities=normalize_entities_flag,
            include_context=include_context_flag,
            save_interval=args.save_interval,
        )
        
        print(f"\n  ✓ 批量抽取完成:")
        print(f"    - 总片段数: {summary['total_segments']}")
        print(f"    - 处理片段: {summary['processed_segments']}")
        print(f"    - 跳过片段: {summary['skipped_segments']}")
        print(f"    - 抽取事件: {summary['total_events']}")
        print(f"    - 抽取三元组: {summary['total_triples']}")
        print(f"    - 失败数: {summary['failed_count']}")
        print(f"    - 耗时: {summary['elapsed_seconds']} 秒")
        
    else:
        # ===== 单条模式 =====
        print(f"  模式: 单条抽取")
        
        # 加载文本
        paragraph = read_text_if_provided(args.paragraph_file, DEMO_PARAGRAPH_1998)
        
        # 构建输入（如果需要上下文，可以扩展）
        if include_context_flag:
            input_text = build_extraction_input(
                {"text": paragraph},
                include_context=False  # 单条模式没有上下文
            )
        else:
            input_text = paragraph
        
        # 执行抽取
        p5_res = pipeline.extract_events(
            input_text, 
            tbox, 
            save_path=None, 
            favor_existing_classes=bool(favor_existing)
        )
        
        # 实体标准化
        if normalize_entities_flag:
            p5_res = normalize_extraction_result(p5_res)
        
        # 保存结果
        pipeline._dump_json(p5_res, out_dir / "p5_events.json")
        
        events = p5_res.get('events', [])
        triples = p5_res.get('triples', [])
        print(f"  ✓ 抽取事件 {len(events)} 个，三元组 {len(triples)} 条")
        print(f"    已保存到 {out_dir / 'p5_events.json'}")
    
    print(f"\n{'='*60}")
    print("流程完成!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
