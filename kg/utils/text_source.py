"""
文本来源加载与解析工具。

用于保证 Gold/Pred 使用完全一致的原文输入。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

logger = logging.getLogger(__name__)


def load_text_lookup(
    text_source_path: Optional[Path],
    *,
    id_fields: Iterable[str] = ("id", "doc_id"),
    text_field: str = "text",
) -> Dict[str, str]:
    """
    加载完整文本来源映射。

    Args:
        text_source_path: 完整文本来源文件路径
        id_fields: doc_id 字段候选名
        text_field: 文本字段名（默认 text）

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


def resolve_doc_id(sample: Dict[str, Any], index: int, *, prefix: str = "doc") -> str:
    """
    统一 doc_id 获取逻辑，保证 Gold/Pred 一致。
    """
    for key in ("doc_id", "id"):
        value = sample.get(key)
        if value:
            return str(value)
    return f"{prefix}_{index}"


def resolve_source_text(
    sample: Dict[str, Any],
    doc_id: str,
    text_lookup: Dict[str, str],
    *,
    require_text_source: bool,
    fallback_fields: Iterable[str] = ("source_text", "text", "content"),
) -> Tuple[str, str]:
    """
    获取抽取文本，并返回来源标记。

    Returns:
        (text, source_tag)
        source_tag 可能为: text_source / missing_text_source / sample:<field> / empty_source_text
    """
    if text_lookup:
        if doc_id in text_lookup:
            return text_lookup[doc_id], "text_source"
        if require_text_source:
            return "", "missing_text_source"

    for field in fallback_fields:
        text = sample.get(field, "")
        if text:
            return text, f"sample:{field}"

    return "", "empty_source_text"
