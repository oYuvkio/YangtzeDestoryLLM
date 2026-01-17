"""
批量抽取模块

支持从 JSONL 文件批量抽取，并输出结果到 JSONL 文件。
支持 --text-source 参数，从外部文件获取完整文本。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import ModelConfig
from .model import ModelLoader
from .prompt import TaskType, TBoxSchema
from .service import ExtractionRequest, ExtractionService, convert_to_unified_format
from .utils import load_jsonl, pick_doc_id, pick_source_text

logger = logging.getLogger(__name__)


def setup_logger(
    log_file: Optional[str] = None,
    verbose: bool = False,
) -> logging.Logger:
    """设置日志"""
    log_format = "%(asctime)s | %(levelname)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    level = logging.DEBUG if verbose else logging.INFO
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
        force=True,
    )
    return logging.getLogger(__name__)


def load_tbox_schema(tbox_path: Path) -> Optional[TBoxSchema]:
    """加载 TBox Schema"""
    if not tbox_path.exists():
        return None
    
    try:
        data = json.loads(tbox_path.read_text(encoding="utf-8"))
        return TBoxSchema.from_tbox_json(data)
    except Exception as e:
        logger.warning(f"TBox 加载失败: {e}")
        return None


def load_existing_predictions(output_path: Path) -> Dict[str, Dict[str, Any]]:
    """加载已有预测结果"""
    if not output_path.exists():
        return {}
    
    predictions = {}
    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                doc_id = record.get("doc_id", "")
                if doc_id:
                    predictions[doc_id] = record
            except json.JSONDecodeError:
                continue
    return predictions


def load_text_lookup(
    text_source_path: Optional[Path],
    id_fields: Tuple[str, ...] = ("id", "doc_id"),
    text_field: str = "text",
) -> Dict[str, str]:
    """加载完整文本来源映射
    
    Args:
        text_source_path: 完整文本来源文件路径
        id_fields: doc_id 字段候选名
        text_field: 文本字段名
    
    Returns:
        doc_id -> text 的映射
    """
    if not text_source_path:
        return {}
    if not text_source_path.exists():
        raise FileNotFoundError(f"文本来源文件不存在: {text_source_path}")
    
    lookup: Dict[str, str] = {}
    with open(text_source_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            doc_id = ""
            for key in id_fields:
                value = item.get(key)
                if value:
                    doc_id = str(value)
                    break
            if not doc_id:
                continue
            
            text = item.get(text_field, "")
            if text:
                lookup[doc_id] = text
    
    return lookup


def resolve_source_text(
    sample: Dict[str, Any],
    doc_id: str,
    text_lookup: Dict[str, str],
    require_text_source: bool = False,
) -> Tuple[str, str]:
    """获取抽取文本，并返回来源标记
    
    Args:
        sample: 样本记录
        doc_id: 文档 ID
        text_lookup: 文本映射表
        require_text_source: 是否强制要求从 text_source 获取
    
    Returns:
        (text, source_tag)
        source_tag: text_source / missing_text_source / sample:<field> / empty
    """
    # 优先从 text_lookup 获取
    if text_lookup:
        if doc_id in text_lookup:
            return text_lookup[doc_id], "text_source"
        if require_text_source:
            return "", "missing_text_source"
    
    # 回退到样本自身字段
    text = pick_source_text(sample)
    if text:
        return text, "sample"
    
    return "", "empty"


def run_batch_extraction(
    test_file: Path,
    output_path: Path,
    task_type: str,
    model_config: ModelConfig,
    tbox_path: Optional[Path] = None,
    text_source_path: Optional[Path] = None,
    limit: Optional[int] = None,
    skip_existing: bool = False,
    verbose: bool = False,
    interval: float = 0.0,
) -> Dict[str, Any]:
    """运行批量抽取
    
    Args:
        test_file: 测试集文件路径（提供 doc_id 列表）
        output_path: 输出文件路径
        task_type: 任务类型 (ner/re/ee/ner+re/all)
        model_config: 模型配置
        tbox_path: TBox 文件路径
        text_source_path: 完整文本来源文件路径（用 doc_id 映射获取 text）
        limit: 最大处理数量
        skip_existing: 是否跳过已存在的预测
        verbose: 是否打印详细日志
        interval: 请求间隔（秒）
    
    Returns:
        运行统计信息
    """
    # 解析任务类型列表
    if task_type == "all":
        task_types = [TaskType.NER, TaskType.RE, TaskType.EE]
    elif task_type == "ner+re":
        task_types = [TaskType.NER, TaskType.RE]
    else:
        task_types = [TaskType(task_type)]
    
    logger.info(f"任务类型: {[t.value for t in task_types]}")
    # 加载测试集
    logger.info(f"加载测试集: {test_file}")
    samples = load_jsonl(test_file)
    if limit:
        samples = samples[:limit]
    logger.info(f"测试集样本数: {len(samples)}")
    
    # 加载完整文本映射
    text_lookup: Dict[str, str] = {}
    if text_source_path:
        logger.info(f"加载完整文本来源: {text_source_path}")
        text_lookup = load_text_lookup(text_source_path)
        logger.info(f"已加载 {len(text_lookup)} 条完整文本")
    
    # 加载 TBox
    schema = None
    if tbox_path:
        schema = load_tbox_schema(tbox_path)
        if schema:
            logger.info(f"TBox: 实体类型 {len(schema.entity_types)}, 关系 {len(schema.relation_types)}")
    
    # 加载已有预测
    existing_predictions = {}
    if skip_existing:
        existing_predictions = load_existing_predictions(output_path)
        logger.info(f"已有预测: {len(existing_predictions)} 条")
    
    # 加载模型
    logger.info("加载模型...")
    loader = ModelLoader(model_config)
    loader.load()
    
    # 创建服务
    service = ExtractionService(
        model_loader=loader,
        max_new_tokens=model_config.max_new_tokens,
        temperature=model_config.temperature,
        do_sample=model_config.do_sample,
        verbose=verbose,
    )
    
    # 运行抽取
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    logger.info("=" * 60)
    logger.info("开始抽取")
    logger.info("=" * 60)
    
    write_mode = "a" if skip_existing and output_path.exists() else "w"
    
    with open(output_path, write_mode, encoding="utf-8") as out_f:
        for idx, sample in enumerate(samples, start=1):
            doc_id = pick_doc_id(sample, f"doc_{idx}")
            
            # 获取文本（优先从 text_source 获取）
            source_text, source_tag = resolve_source_text(
                sample,
                doc_id,
                text_lookup,
                require_text_source=bool(text_source_path),
            )
            
            # 跳过空文本
            if not source_text:
                logger.warning(f"[{idx}/{len(samples)}] {doc_id}: 无有效文本({source_tag})，跳过")
                error_count += 1
                # 写入空结果
                record = {
                    "doc_id": doc_id,
                    "source_text": "",
                    "entities": [],
                    "events": [],
                    "triples": [],
                    "raw_output": "",
                    "error": f"no_text:{source_tag}",
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                out_f.flush()
                continue
            
            # 跳过已存在
            if skip_existing and doc_id in existing_predictions:
                skip_count += 1
                logger.info(f"[{idx}/{len(samples)}] {doc_id}: 跳过已存在")
                continue
            
            # 执行抽取（支持多任务）
            try:
                all_entities = []
                all_triples = []
                all_events = []
                all_raw_outputs = []
                total_latency = 0.0
                
                for t_type in task_types:
                    request = ExtractionRequest(
                        text=source_text,
                        task_type=t_type,
                        doc_id=doc_id,
                        schema=schema,
                    )
                    
                    response = service.extract(request)
                    all_raw_outputs.append(f"[{t_type.value}] {response.raw_output}")
                    total_latency += response.latency_ms
                    
                    if response.success:
                        parsed = response.parsed_result
                        if t_type == TaskType.NER:
                            all_entities.extend(parsed.get("entities", []))
                        elif t_type == TaskType.RE:
                            all_triples.extend(parsed.get("triples", []))
                        elif t_type == TaskType.EE:
                            all_events.extend(parsed.get("events", []))
                
                # 合并结果
                record = {
                    "doc_id": doc_id,
                    "source_text": source_text,
                    "entities": all_entities,
                    "triples": all_triples,
                    "events": all_events,
                    "raw_output": "\n".join(all_raw_outputs),
                    "latency_ms": total_latency,
                }
                
            except Exception as e:
                logger.error(f"[{idx}/{len(samples)}] {doc_id}: 抽取异常 - {e}")
                error_count += 1
                # 写入空结果
                record = {
                    "doc_id": doc_id,
                    "source_text": source_text,
                    "entities": [],
                    "events": [],
                    "triples": [],
                    "raw_output": "",
                    "error": str(e),
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                out_f.flush()
                continue
            
            # 写入结果
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_f.flush()
            
            success_count += 1
            entity_count = 0
            for group in all_entities:
                if not isinstance(group, dict):
                    continue
                for values in group.values():
                    if isinstance(values, list):
                        entity_count += len(values)
                    elif values:
                        entity_count += 1
            count_info = f"实体 {entity_count}, 三元组 {len(all_triples)}"
            if all_events:
                count_info += f", 事件 {len(all_events)}"
            logger.info(f"[{idx}/{len(samples)}] {doc_id}: {count_info}, 耗时 {total_latency:.0f}ms")
            
            # 间隔
            if interval > 0 and idx < len(samples):
                time.sleep(interval)
    
    # 保存元数据
    meta = {
        "timestamp": datetime.now().isoformat(),
        "model_path": model_config.model_path,
        "task_types": [t.value for t in task_types],
        "test_file": str(test_file),
        "text_source": str(text_source_path) if text_source_path else None,
        "tbox_file": str(tbox_path) if tbox_path else None,
        "total_samples": len(samples),
        "success_count": success_count,
        "skip_count": skip_count,
        "error_count": error_count,
        "output": str(output_path),
    }
    
    meta_path = output_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    
    logger.info("=" * 60)
    logger.info("抽取完成")
    logger.info("=" * 60)
    logger.info(f"总样本: {len(samples)}")
    logger.info(f"成功: {success_count}")
    logger.info(f"跳过: {skip_count}")
    logger.info(f"错误: {error_count}")
    logger.info(f"输出: {output_path}")
    logger.info(f"元数据: {meta_path}")
    
    return meta


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="YAYI-UIE 批量信息抽取",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    # 输入输出
    parser.add_argument(
        "--test-file", "-i",
        required=True,
        help="测试集文件路径 (JSONL)",
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="输出文件路径 (JSONL)",
    )
    parser.add_argument(
        "--tbox",
        default=None,
        help="TBox 文件路径 (JSON)",
    )
    parser.add_argument(
        "--text-source",
        default=None,
        help="完整文本来源文件 (JSONL)，用 id/doc_id 字段与 test-file 的 doc_id 映射获取 text",
    )
    
    # 任务配置
    parser.add_argument(
        "--task-type", "-t",
        choices=["ner", "re", "ee", "ner+re", "all"],
        default="re",
        help="任务类型: ner/re/ee 单任务，ner+re 实体+关系，all 全部任务 (默认: re)",
    )
    
    # 模型配置
    parser.add_argument(
        "--model-path",
        default="/hy-tmp/zjx/models/modelscope/wenge-research/yayi-uie",
        help="模型路径",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=8192,
        help="最大生成 token 数 (默认: 2048)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="采样温度 (默认: 0.0)",
    )
    
    # 运行配置
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最大处理数量",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="跳过已存在的预测",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.0,
        help="请求间隔秒数 (默认: 0)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="打印详细日志",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="调试模式",
    )
    
    args = parser.parse_args()
    
    # 设置日志
    log_file = None
    if args.debug:
        output_path = Path(args.output)
        log_file = str(output_path.with_suffix(".log"))
    setup_logger(log_file, args.verbose or args.debug)
    
    # 构建配置
    model_config = ModelConfig(
        model_path=args.model_path,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
    )
    
    # 运行抽取
    run_batch_extraction(
        test_file=Path(args.test_file),
        output_path=Path(args.output),
        task_type=args.task_type,
        model_config=model_config,
        tbox_path=Path(args.tbox) if args.tbox else None,
        text_source_path=Path(args.text_source) if args.text_source else None,
        limit=args.limit,
        skip_existing=args.skip_existing,
        verbose=args.verbose,
        interval=args.interval,
    )


if __name__ == "__main__":
    main()
