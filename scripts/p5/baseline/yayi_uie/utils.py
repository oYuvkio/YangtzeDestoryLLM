"""
公共工具模块

提供文本处理、文件操作等通用功能。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def normalize_text(text: str, remove_punctuation: bool = True) -> str:
    """标准化文本
    
    Args:
        text: 原始文本
        remove_punctuation: 是否移除标点符号
    
    Returns:
        标准化后的文本
    """
    if not text:
        return ""
    
    text = str(text).strip().lower()
    text = re.sub(r"\s+", "", text)
    
    if remove_punctuation:
        # 移除中英文标点
        text = re.sub(r"[，。、""''：；（）【】《》/\\-,.!?;:\"'()\[\]{}]", "", text)
    
    return text


def normalize_text_light(text: str) -> str:
    """轻量级文本标准化（保留标点）
    
    Args:
        text: 原始文本
    
    Returns:
        标准化后的文本
    """
    if not text:
        return ""
    text = str(text).strip()
    text = re.sub(r'\s+', ' ', text)
    return text


def load_jsonl(file_path: Path) -> List[Dict[str, Any]]:
    """加载 JSONL 文件
    
    Args:
        file_path: 文件路径
    
    Returns:
        记录列表
    """
    items = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def save_jsonl(items: List[Dict[str, Any]], file_path: Path) -> None:
    """保存 JSONL 文件
    
    Args:
        items: 记录列表
        file_path: 文件路径
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def pick_doc_id(record: Dict[str, Any], default: str = "") -> str:
    """从记录中提取 doc_id
    
    Args:
        record: 记录字典
        default: 默认值
    
    Returns:
        doc_id 字符串
    """
    for key in ("doc_id", "docid", "id", "document_id"):
        value = record.get(key)
        if value not in [None, ""]:
            return str(value)
    return default


def pick_source_text(record: Dict[str, Any]) -> str:
    """从记录中提取源文本
    
    Args:
        record: 记录字典
    
    Returns:
        源文本字符串
    """
    for key in ("source_text", "text", "content", "body"):
        value = record.get(key)
        if value:
            return str(value)
    return ""


def compute_f1(pred_count: int, gold_count: int, matched: int) -> Dict[str, float]:
    """计算 Precision, Recall, F1
    
    Args:
        pred_count: 预测数量
        gold_count: 标注数量
        matched: 匹配数量
    
    Returns:
        包含 precision, recall, f1 的字典
    """
    precision = matched / pred_count if pred_count > 0 else 0.0
    recall = matched / gold_count if gold_count > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "pred_count": pred_count,
        "gold_count": gold_count,
        "matched": matched,
    }
