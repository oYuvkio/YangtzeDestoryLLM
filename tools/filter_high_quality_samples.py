#!/usr/bin/env python3
"""
测试集质量筛选工具

根据 gold 和 pred 的评分筛选高质量样本作为测试集。
支持按实体、关系、事件各维度筛选，支持阈值过滤和 top-n 选取。

用法示例:
    python tools/filter_high_quality_samples.py \
        --gold data/gold.jsonl \
        --pred data/pred.jsonl \
        --out data/filtered_gold.jsonl \
        --top-n 500 \
        --entity-threshold 0.5 \
        --triple-threshold 0.3 \
        --event-threshold 0.3 \
        --sort-by avg \
        --export-scores scores.csv

    # 允许实体和事件为空
    python tools/filter_high_quality_samples.py \
        --gold data/gold.jsonl \
        --pred data/pred.jsonl \
        --out data/filtered_gold.jsonl \
        --allow-empty-entity --allow-empty-event

    # 使用 --args 传递 JSON 配置
    python tools/filter_high_quality_samples.py \
        --gold data/gold.jsonl \
        --pred data/pred.jsonl \
        --out data/filtered_gold.jsonl \
        --args '{"top_n": 500, "entity_threshold": 0.5}'

    # 使用 --args 从文件加载配置
    python tools/filter_high_quality_samples.py \
        --args @config.json
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 复用 abox_metrics 中的评估函数
from abox_metrics import (
    compute_entity_f1,
    compute_triple_f1,
    compute_event_f1,
)


@dataclass
class SampleScore:
    """单个样本的评分结果"""
    doc_id: str
    entity_f1: Optional[float]
    triple_f1: Optional[float]  # 使用 relaxed 模式
    event_f1: Optional[float]
    avg_f1: float
    passed: bool
    gold_record: Dict[str, Any]
    pred_record: Dict[str, Any]
    empty_dimensions: int = 0  # 空维度数量

    def to_csv_row(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "entity_f1": self.entity_f1 if self.entity_f1 is not None else "",
            "triple_f1": self.triple_f1 if self.triple_f1 is not None else "",
            "event_f1": self.event_f1 if self.event_f1 is not None else "",
            "avg_f1": round(self.avg_f1, 4),
            "empty_dimensions": self.empty_dimensions,
            "passed": self.passed,
        }


def count_empty_dimensions(gold_record: Dict[str, Any]) -> int:
    """
    统计 gold 记录中空维度的数量
    
    Returns:
        空维度数量 (0-3)
    """
    empty_count = 0
    
    # 检查实体
    entities = gold_record.get("entities", []) or []
    if not entities:
        empty_count += 1
    
    # 检查三元组
    triples = gold_record.get("triples", []) or gold_record.get("gold_triples", []) or []
    if not triples:
        empty_count += 1
    
    # 检查事件
    events = gold_record.get("events", []) or gold_record.get("gold_events", []) or []
    if not events:
        empty_count += 1
    
    return empty_count


def check_empty_dimensions_allowed(
    gold_record: Dict[str, Any],
    allow_empty_entity: bool = True,
    allow_empty_triple: bool = True,
    allow_empty_event: bool = True,
) -> bool:
    """
    检查样本的空维度是否符合允许规则
    
    Args:
        gold_record: Gold 标注记录
        allow_empty_entity: 是否允许实体为空
        allow_empty_triple: 是否允许三元组为空
        allow_empty_event: 是否允许事件为空
    
    Returns:
        True 如果符合空值允许规则，否则 False
    """
    # 检查实体
    if not allow_empty_entity:
        entities = gold_record.get("entities", []) or []
        if not entities:
            return False
    
    # 检查三元组
    if not allow_empty_triple:
        triples = gold_record.get("triples", []) or gold_record.get("gold_triples", []) or []
        if not triples:
            return False
    
    # 检查事件
    if not allow_empty_event:
        events = gold_record.get("events", []) or gold_record.get("gold_events", []) or []
        if not events:
            return False
    
    return True


def setup_logger(log_file: Optional[str] = None) -> logging.Logger:
    """配置日志"""
    log_format = "%(asctime)s | %(levelname)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
        force=True,
    )
    return logging.getLogger(__name__)


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    """加载 JSONL 文件"""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    items: List[Dict[str, Any]] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as e:
            logging.warning(f"JSON 解析失败: {e}")
            continue
    return items


def get_doc_id(record: Dict[str, Any]) -> str:
    """从记录中提取文档 ID"""
    # 尝试多种可能的 ID 字段
    for key in ["doc_id", "id", "document_id", "file_id", "source_id"]:
        if key in record and record[key]:
            return str(record[key])
    # 如果没有 ID 字段，使用记录的哈希值
    return str(hash(json.dumps(record, sort_keys=True, ensure_ascii=False)))


def compute_sample_scores(
    gold_record: Dict[str, Any],
    pred_record: Dict[str, Any],
    doc_id: str,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    计算单个样本的三个维度评分
    
    Returns:
        (entity_f1, triple_f1, event_f1) - 如果某维度无数据则返回 None
    """
    entity_f1: Optional[float] = None
    triple_f1: Optional[float] = None
    event_f1: Optional[float] = None
    
    # 计算实体 F1
    try:
        entity_metrics, entity_stats = compute_entity_f1(pred_record, gold_record)
        # 只有当 gold 或 pred 有实体时才计算
        if entity_stats.get("gold_count", 0) > 0 or entity_stats.get("pred_count", 0) > 0:
            entity_f1 = entity_metrics.f1
    except Exception as e:
        logging.debug(f"实体 F1 计算失败 ({doc_id}): {e}")
    
    # 计算关系 F1（使用 relaxed 模式）
    try:
        triple_metrics, _ = compute_triple_f1(pred_record, gold_record)
        relaxed_metrics = triple_metrics.get("relaxed")
        if relaxed_metrics:
            # 检查是否有三元组数据
            gold_triples = gold_record.get("triples", []) or gold_record.get("gold_triples", []) or []
            pred_triples = pred_record.get("triples", []) or []
            if len(gold_triples) > 0 or len(pred_triples) > 0:
                triple_f1 = relaxed_metrics.f1
    except Exception as e:
        logging.debug(f"关系 F1 计算失败 ({doc_id}): {e}")
    
    # 计算事件 F1
    try:
        event_metrics, _ = compute_event_f1(pred_record, gold_record)
        # 检查是否有事件数据
        gold_events = gold_record.get("events", []) or gold_record.get("gold_events", []) or []
        pred_events = pred_record.get("events", []) or []
        if len(gold_events) > 0 or len(pred_events) > 0:
            event_f1 = event_metrics.f1
    except Exception as e:
        logging.debug(f"事件 F1 计算失败 ({doc_id}): {e}")
    
    return entity_f1, triple_f1, event_f1


def calculate_avg_f1(
    entity_f1: Optional[float],
    triple_f1: Optional[float],
    event_f1: Optional[float],
    skip_missing: bool,
) -> float:
    """
    计算平均 F1
    
    Args:
        skip_missing: True 时缺失维度不参与计算，False 时缺失维度视为 1.0
    """
    scores = []
    
    if entity_f1 is not None:
        scores.append(entity_f1)
    elif not skip_missing:
        scores.append(1.0)
    
    if triple_f1 is not None:
        scores.append(triple_f1)
    elif not skip_missing:
        scores.append(1.0)
    
    if event_f1 is not None:
        scores.append(event_f1)
    elif not skip_missing:
        scores.append(1.0)
    
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def check_thresholds(
    entity_f1: Optional[float],
    triple_f1: Optional[float],
    event_f1: Optional[float],
    entity_threshold: float,
    triple_threshold: float,
    event_threshold: float,
    skip_missing: bool,
) -> bool:
    """
    检查是否满足所有阈值条件（AND 逻辑）
    
    Args:
        skip_missing: True 时缺失维度跳过检查，False 时缺失维度视为满分
    """
    # 实体阈值检查
    if entity_threshold > 0:
        if entity_f1 is not None:
            if entity_f1 < entity_threshold:
                return False
        elif not skip_missing:
            # 缺失时视为满分，满分 >= 阈值，通过
            pass
        # skip_missing=True 且缺失时，跳过此维度检查
    
    # 关系阈值检查
    if triple_threshold > 0:
        if triple_f1 is not None:
            if triple_f1 < triple_threshold:
                return False
        elif not skip_missing:
            pass
    
    # 事件阈值检查
    if event_threshold > 0:
        if event_f1 is not None:
            if event_f1 < event_threshold:
                return False
        elif not skip_missing:
            pass
    
    return True


def filter_high_quality_samples(
    gold_records: List[Dict[str, Any]],
    pred_records: List[Dict[str, Any]],
    entity_threshold: float = 0.0,
    triple_threshold: float = 0.0,
    event_threshold: float = 0.0,
    top_n: int = 0,
    sort_by: str = "avg",
    skip_missing: bool = True,
    max_empty_dimensions: int = 3,
    allow_empty_entity: bool = True,
    allow_empty_triple: bool = True,
    allow_empty_event: bool = True,
) -> Tuple[List[SampleScore], List[SampleScore]]:
    """
    筛选高质量样本
    
    Args:
        gold_records: Gold 标注列表
        pred_records: Pred 预测列表
        entity_threshold: 实体 F1 阈值
        triple_threshold: 关系 F1 阈值
        event_threshold: 事件 F1 阈值
        top_n: 筛选前 N 条（0 表示不限制）
        sort_by: 排序维度 (entity/triple/event/avg)
        skip_missing: 缺失维度是否跳过
        max_empty_dimensions: 允许的最大空维度数量 (0-3)，默认 3 表示不限制
        allow_empty_entity: 是否允许实体为空
        allow_empty_triple: 是否允许三元组为空
        allow_empty_event: 是否允许事件为空
    
    Returns:
        (all_scores, filtered_scores): 所有样本评分和筛选后的评分
    """
    logger = logging.getLogger(__name__)
    
    # 按 doc_id 建立索引
    gold_by_id: Dict[str, Dict[str, Any]] = {}
    for record in gold_records:
        doc_id = get_doc_id(record)
        gold_by_id[doc_id] = record
    
    pred_by_id: Dict[str, Dict[str, Any]] = {}
    for record in pred_records:
        doc_id = get_doc_id(record)
        pred_by_id[doc_id] = record
    
    # 找到共同的 doc_id
    common_ids = set(gold_by_id.keys()) & set(pred_by_id.keys())
    logger.info(f"Gold 样本数: {len(gold_by_id)}, Pred 样本数: {len(pred_by_id)}, 共同样本数: {len(common_ids)}")
    
    if not common_ids:
        logger.warning("没有找到匹配的样本！请检查 gold 和 pred 文件的 doc_id 是否一致")
        return [], []
    
    # 计算每个样本的评分
    all_scores: List[SampleScore] = []
    for doc_id in common_ids:
        gold_record = gold_by_id[doc_id]
        pred_record = pred_by_id[doc_id]
        
        entity_f1, triple_f1, event_f1 = compute_sample_scores(
            gold_record, pred_record, doc_id
        )
        
        avg_f1 = calculate_avg_f1(entity_f1, triple_f1, event_f1, skip_missing)
        
        passed = check_thresholds(
            entity_f1, triple_f1, event_f1,
            entity_threshold, triple_threshold, event_threshold,
            skip_missing,
        )
        
        # 统计空维度数量
        empty_dims = count_empty_dimensions(gold_record)
        
        score = SampleScore(
            doc_id=doc_id,
            entity_f1=entity_f1,
            triple_f1=triple_f1,
            event_f1=event_f1,
            avg_f1=avg_f1,
            passed=passed,
            gold_record=gold_record,
            pred_record=pred_record,
            empty_dimensions=empty_dims,
        )
        all_scores.append(score)
    
    # 筛选通过阈值的样本
    filtered_scores = [s for s in all_scores if s.passed]
    logger.info(f"通过阈值筛选的样本数: {len(filtered_scores)}/{len(all_scores)}")
    
    # 筛选空维度数量符合要求的样本
    if max_empty_dimensions < 3:
        before_count = len(filtered_scores)
        filtered_scores = [s for s in filtered_scores if s.empty_dimensions <= max_empty_dimensions]
        logger.info(f"空维度筛选 (max_empty={max_empty_dimensions}): {len(filtered_scores)}/{before_count}")
    
    # 按独立维度筛选空值
    if not (allow_empty_entity and allow_empty_triple and allow_empty_event):
        before_count = len(filtered_scores)
        filtered_scores = [
            s for s in filtered_scores
            if check_empty_dimensions_allowed(
                s.gold_record,
                allow_empty_entity=allow_empty_entity,
                allow_empty_triple=allow_empty_triple,
                allow_empty_event=allow_empty_event,
            )
        ]
        logger.info(
            f"独立空维度筛选 (entity={allow_empty_entity}, triple={allow_empty_triple}, event={allow_empty_event}): "
            f"{len(filtered_scores)}/{before_count}"
        )
    
    # 排序
    def get_sort_key(s: SampleScore) -> float:
        if sort_by == "entity":
            return s.entity_f1 if s.entity_f1 is not None else -1
        elif sort_by == "triple":
            return s.triple_f1 if s.triple_f1 is not None else -1
        elif sort_by == "event":
            return s.event_f1 if s.event_f1 is not None else -1
        else:  # avg
            return s.avg_f1
    
    filtered_scores.sort(key=get_sort_key, reverse=True)
    
    # 取 top-n
    if top_n > 0 and len(filtered_scores) > top_n:
        filtered_scores = filtered_scores[:top_n]
        logger.info(f"取 top-{top_n} 后的样本数: {len(filtered_scores)}")
    
    return all_scores, filtered_scores


def export_scores_csv(scores: List[SampleScore], output_path: str) -> None:
    """导出评分详情到 CSV"""
    # 确保输出目录存在
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    fieldnames = ["doc_id", "entity_f1", "triple_f1", "event_f1", "avg_f1", "empty_dimensions", "passed"]
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for score in scores:
            writer.writerow(score.to_csv_row())
    
    logging.info(f"评分详情已导出到: {output_path}")


def save_filtered_gold(scores: List[SampleScore], output_path: str) -> None:
    """保存筛选后的 gold 文件"""
    # 确保输出目录存在
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        for score in scores:
            f.write(json.dumps(score.gold_record, ensure_ascii=False) + "\n")
    
    logging.info(f"筛选后的 gold 文件已保存到: {output_path}")


def print_statistics(all_scores: List[SampleScore], filtered_scores: List[SampleScore]) -> None:
    """打印统计信息"""
    logger = logging.getLogger(__name__)
    
    def calc_stats(scores: List[SampleScore], field: str) -> Dict[str, float]:
        values = [getattr(s, field) for s in scores if getattr(s, field) is not None]
        if not values:
            return {"count": 0, "min": 0, "max": 0, "avg": 0}
        return {
            "count": len(values),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "avg": round(sum(values) / len(values), 4),
        }
    
    logger.info("=" * 60)
    logger.info("全部样本统计:")
    logger.info(f"  总数: {len(all_scores)}")
    for field in ["entity_f1", "triple_f1", "event_f1", "avg_f1"]:
        stats = calc_stats(all_scores, field)
        logger.info(f"  {field}: count={stats['count']}, min={stats['min']}, max={stats['max']}, avg={stats['avg']}")
    
    logger.info("-" * 60)
    logger.info("筛选后样本统计:")
    logger.info(f"  总数: {len(filtered_scores)}")
    for field in ["entity_f1", "triple_f1", "event_f1", "avg_f1"]:
        stats = calc_stats(filtered_scores, field)
        logger.info(f"  {field}: count={stats['count']}, min={stats['min']}, max={stats['max']}, avg={stats['avg']}")
    logger.info("=" * 60)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="测试集质量筛选工具 - 根据 gold/pred 评分筛选高质量样本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本用法：筛选评分前 500 条
  python tools/filter_high_quality_samples.py \\
      --gold data/gold.jsonl --pred data/pred.jsonl \\
      --out data/filtered_gold.jsonl --top-n 500

  # 设置阈值筛选
  python tools/filter_high_quality_samples.py \\
      --gold data/gold.jsonl --pred data/pred.jsonl \\
      --out data/filtered_gold.jsonl \\
      --entity-threshold 0.5 --triple-threshold 0.3 --event-threshold 0.3

  # 按实体 F1 排序，导出评分详情
  python tools/filter_high_quality_samples.py \\
      --gold data/gold.jsonl --pred data/pred.jsonl \\
      --out data/filtered_gold.jsonl \\
      --sort-by entity --export-scores scores.csv

  # 允许实体和事件为空，但三元组不能为空
  python tools/filter_high_quality_samples.py \\
      --gold data/gold.jsonl --pred data/pred.jsonl \\
      --out data/filtered_gold.jsonl \\
      --allow-empty-entity --allow-empty-event --no-allow-empty-triple

  # 使用 --args 传递 JSON 配置
  python tools/filter_high_quality_samples.py \\
      --args '{"gold": "data/gold.jsonl", "pred": "data/pred.jsonl", "out": "data/filtered.jsonl", "top_n": 500}'

  # 使用 --args 从文件加载配置 (以 @ 开头)
  python tools/filter_high_quality_samples.py --args @config.json
        """,
    )
    
    # --args 参数配置（可覆盖其他参数）
    parser.add_argument(
        "--args", type=str, default=None,
        help="JSON 格式的参数配置字符串，或以 @ 开头的 JSON 文件路径。支持的键：gold, pred, out, top_n, entity_threshold, triple_threshold, event_threshold, sort_by, skip_missing, max_empty_dimensions, allow_empty_entity, allow_empty_triple, allow_empty_event, export_scores, log_file"
    )
    
    # 必填参数（使用 --args 时可省略）
    parser.add_argument("--gold", default=None, help="Gold 文件路径 (JSONL)")
    parser.add_argument("--pred", default=None, help="Pred 文件路径 (JSONL)")
    parser.add_argument("--out", default=None, help="输出筛选后的 gold 文件路径")
    
    # 筛选参数
    parser.add_argument(
        "--top-n", type=int, default=0,
        help="筛选前 N 条（0 表示不限制，默认: 0）"
    )
    parser.add_argument(
        "--entity-threshold", type=float, default=0.0,
        help="实体 F1 阈值（默认: 0.0）"
    )
    parser.add_argument(
        "--triple-threshold", type=float, default=0.0,
        help="关系 F1 阈值（默认: 0.0）"
    )
    parser.add_argument(
        "--event-threshold", type=float, default=0.0,
        help="事件 F1 阈值（默认: 0.0）"
    )
    
    # 排序和缺失处理
    parser.add_argument(
        "--sort-by", choices=["entity", "triple", "event", "avg"], default="avg",
        help="排序维度（默认: avg）"
    )
    parser.add_argument(
        "--skip-missing", action="store_true", default=True,
        help="缺失维度跳过筛选（默认: True）"
    )
    parser.add_argument(
        "--no-skip-missing", action="store_false", dest="skip_missing",
        help="缺失维度视为满分（1.0）"
    )
    parser.add_argument(
        "--max-empty-dimensions", type=int, default=3, choices=[0, 1, 2, 3],
        help="允许的最大空维度数量 (0=三个维度都不能为空, 1=最多1个为空, 2=最多2个为空, 3=不限制，默认: 3)"
    )
    
    # 独立维度空值控制
    parser.add_argument(
        "--allow-empty-entity", action="store_true", default=True,
        help="允许实体为空（默认: True）"
    )
    parser.add_argument(
        "--no-allow-empty-entity", action="store_false", dest="allow_empty_entity",
        help="不允许实体为空"
    )
    parser.add_argument(
        "--allow-empty-triple", action="store_true", default=True,
        help="允许三元组为空（默认: True）"
    )
    parser.add_argument(
        "--no-allow-empty-triple", action="store_false", dest="allow_empty_triple",
        help="不允许三元组为空"
    )
    parser.add_argument(
        "--allow-empty-event", action="store_true", default=True,
        help="允许事件为空（默认: True）"
    )
    parser.add_argument(
        "--no-allow-empty-event", action="store_false", dest="allow_empty_event",
        help="不允许事件为空"
    )
    
    # 输出选项
    parser.add_argument(
        "--export-scores", type=str, default=None,
        help="导出评分详情 CSV 文件路径（可选）"
    )
    parser.add_argument(
        "--log-file", type=str, default=None,
        help="日志文件路径（可选）"
    )
    
    return parser.parse_args()


def merge_args_with_json(args: argparse.Namespace) -> argparse.Namespace:
    """
    合并 --args JSON 配置与命令行参数
    
    优先级: 命令行显式参数 > --args JSON 配置 > 默认值
    """
    if not args.args:
        return args
    
    # 解析 --args 参数
    args_str = args.args.strip()
    if args_str.startswith("@"):
        # 从文件加载
        config_path = Path(args_str[1:])
        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        json_config = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        # 直接解析 JSON 字符串
        json_config = json.loads(args_str)
    
    # 参数映射（JSON 键 -> argparse 属性名）
    key_mapping = {
        "gold": "gold",
        "pred": "pred",
        "out": "out",
        "top_n": "top_n",
        "entity_threshold": "entity_threshold",
        "triple_threshold": "triple_threshold",
        "event_threshold": "event_threshold",
        "sort_by": "sort_by",
        "skip_missing": "skip_missing",
        "max_empty_dimensions": "max_empty_dimensions",
        "allow_empty_entity": "allow_empty_entity",
        "allow_empty_triple": "allow_empty_triple",
        "allow_empty_event": "allow_empty_event",
        "export_scores": "export_scores",
        "log_file": "log_file",
    }
    
    # 合并配置（JSON 配置作为基础，命令行非 None 值覆盖）
    for json_key, attr_name in key_mapping.items():
        if json_key in json_config:
            json_value = json_config[json_key]
            current_value = getattr(args, attr_name, None)
            # 只有当命令行未显式设置时才使用 JSON 值
            # 对于布尔值和数值类型需要特殊处理
            if current_value is None or (
                attr_name in ["gold", "pred", "out", "export_scores", "log_file"] and current_value is None
            ):
                setattr(args, attr_name, json_value)
    
    return args


def main() -> None:
    args = parse_args()
    
    # 合并 --args JSON 配置
    args = merge_args_with_json(args)
    
    # 验证必填参数
    if not args.gold:
        raise ValueError("缺少必填参数: --gold（可通过 --args 提供）")
    if not args.pred:
        raise ValueError("缺少必填参数: --pred（可通过 --args 提供）")
    if not args.out:
        raise ValueError("缺少必填参数: --out（可通过 --args 提供）")
    
    logger = setup_logger(args.log_file)
    
    logger.info("开始加载数据...")
    logger.info(f"Gold 文件: {args.gold}")
    logger.info(f"Pred 文件: {args.pred}")
    
    # 加载数据
    gold_records = load_jsonl(args.gold)
    pred_records = load_jsonl(args.pred)
    
    logger.info(f"加载完成: Gold {len(gold_records)} 条, Pred {len(pred_records)} 条")
    
    # 筛选参数
    logger.info("筛选参数:")
    logger.info(f"  entity_threshold: {args.entity_threshold}")
    logger.info(f"  triple_threshold: {args.triple_threshold}")
    logger.info(f"  event_threshold: {args.event_threshold}")
    logger.info(f"  top_n: {args.top_n}")
    logger.info(f"  sort_by: {args.sort_by}")
    logger.info(f"  skip_missing: {args.skip_missing}")
    logger.info(f"  max_empty_dimensions: {args.max_empty_dimensions}")
    logger.info(f"  allow_empty_entity: {args.allow_empty_entity}")
    logger.info(f"  allow_empty_triple: {args.allow_empty_triple}")
    logger.info(f"  allow_empty_event: {args.allow_empty_event}")
    
    # 执行筛选
    all_scores, filtered_scores = filter_high_quality_samples(
        gold_records=gold_records,
        pred_records=pred_records,
        entity_threshold=args.entity_threshold,
        triple_threshold=args.triple_threshold,
        event_threshold=args.event_threshold,
        top_n=args.top_n,
        sort_by=args.sort_by,
        skip_missing=args.skip_missing,
        max_empty_dimensions=args.max_empty_dimensions,
        allow_empty_entity=args.allow_empty_entity,
        allow_empty_triple=args.allow_empty_triple,
        allow_empty_event=args.allow_empty_event,
    )
    
    # 打印统计信息
    print_statistics(all_scores, filtered_scores)
    
    # 保存结果
    if filtered_scores:
        save_filtered_gold(filtered_scores, args.out)
    else:
        logger.warning("没有样本通过筛选！")
    
    # 导出评分详情
    if args.export_scores:
        export_scores_csv(all_scores, args.export_scores)
    
    logger.info("完成！")


if __name__ == "__main__":
    main()
