#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
P5 上下文感知抽取工具
================================================================================

为 P5 事件与三元组抽取提供上下文加载和文本构建功能。

核心功能
--------
1. **片段加载**：从过滤后的 JSONL 文件加载片段
2. **上下文补充**：根据片段关联信息加载前后文
3. **抽取文本构建**：组装用于 LLM 抽取的完整文本
4. **批量处理**：支持大规模语料的高效处理

设计原则
--------
- 懒加载：按需加载上下文，减少内存占用
- 容错性：单个片段加载失败不影响整体流程
- 可配置：上下文长度、格式可灵活调整

使用示例
--------
```python
from scripts.p5_extraction_utils import (
    load_segments_with_context,
    build_extraction_text,
    SegmentContextEnricher,
)

# 加载带上下文的片段
segments = load_segments_with_context(
    jsonl_path=Path("data/filtered/light_pool.jsonl"),
    corpus_root=Path("data/corpus"),
    context_chars=500,
)

# 构建抽取文本
for seg in segments:
    text = build_extraction_text(seg, include_context=True)
    # 调用 LLM 进行抽取...
```

作者: KG Team
版本: 1.0.0
"""
from __future__ import annotations

import json
import logging
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

# ==============================================================================
# 日志配置
# ==============================================================================

logger = logging.getLogger(__name__)


# ==============================================================================
# 常量定义
# ==============================================================================


class ExtractionConstants:
    """抽取相关常量"""
    
    # 上下文配置
    DEFAULT_CONTEXT_CHARS: int = 500
    MAX_TOTAL_CHARS: int = 4000
    
    # 文本标记
    MARKER_CONTEXT_BEFORE: str = "【前文参考】"
    MARKER_MAIN_TEXT: str = "【待抽取文本】"
    MARKER_CONTEXT_AFTER: str = "【后文参考】"
    
    # 段落分隔
    SECTION_SEPARATOR: str = "\n\n"


# ==============================================================================
# 数据结构
# ==============================================================================


@dataclass
class EnrichedSegment:
    """
    增强的片段数据结构。
    
    在原始片段基础上，增加了上下文信息和抽取相关元数据。
    
    Attributes:
        id: 片段唯一标识符
        text: 主文本内容
        rel_path: 相对路径
        char_count: 字符数
        source_file: 源文件名
        prev_part_id: 前一片段 ID
        next_part_id: 后一片段 ID
        group_id: 同源文档组 ID
        context_before: 前文上下文
        context_after: 后文上下文
        filter_labels: 过滤标签
        extraction_ready: 是否准备好抽取
    """
    
    id: str
    text: str
    rel_path: str = ""
    char_count: int = 0
    source_file: str = ""
    prev_part_id: str = ""
    next_part_id: str = ""
    group_id: str = ""
    context_before: str = ""
    context_after: str = ""
    filter_labels: Dict[str, Any] = field(default_factory=dict)
    extraction_ready: bool = True
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnrichedSegment":
        """
        从字典创建实例。
        
        Args:
            data: 片段数据字典
            
        Returns:
            EnrichedSegment 实例
        """
        return cls(
            id=data.get("id", ""),
            text=data.get("text", ""),
            rel_path=data.get("rel_path", ""),
            char_count=data.get("char_count", len(data.get("text", ""))),
            source_file=data.get("source_file", ""),
            prev_part_id=data.get("prev_part_id", ""),
            next_part_id=data.get("next_part_id", ""),
            group_id=data.get("group_id", ""),
            context_before=data.get("context_before", ""),
            context_after=data.get("context_after", ""),
            filter_labels=data.get("filter_labels", {}),
            extraction_ready=True,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "text": self.text,
            "rel_path": self.rel_path,
            "char_count": self.char_count,
            "source_file": self.source_file,
            "prev_part_id": self.prev_part_id,
            "next_part_id": self.next_part_id,
            "group_id": self.group_id,
            "context_before": self.context_before,
            "context_after": self.context_after,
            "filter_labels": self.filter_labels,
            "extraction_ready": self.extraction_ready,
        }
    
    def has_context(self) -> bool:
        """检查是否有上下文"""
        return bool(self.context_before or self.context_after)
    
    def get_total_length(self) -> int:
        """获取包含上下文的总长度"""
        return len(self.text) + len(self.context_before) + len(self.context_after)


# ==============================================================================
# 上下文索引构建器
# ==============================================================================


class ContextIndex:
    """
    片段上下文索引。
    
    维护片段 ID 到文本内容的映射，支持高效的上下文查找。
    """
    
    def __init__(self):
        """初始化索引"""
        self._id_to_text: Dict[str, str] = {}
        self._id_to_path: Dict[str, Path] = {}
        self._group_members: Dict[str, List[str]] = {}  # group_id -> [segment_ids]
    
    def add_segment(
        self,
        seg_id: str,
        text: str,
        path: Optional[Path] = None,
        group_id: str = "",
    ) -> None:
        """
        添加片段到索引。
        
        Args:
            seg_id: 片段 ID
            text: 文本内容
            path: 文件路径（可选）
            group_id: 组 ID（可选）
        """
        self._id_to_text[seg_id] = text
        if path:
            self._id_to_path[seg_id] = path
        if group_id:
            if group_id not in self._group_members:
                self._group_members[group_id] = []
            self._group_members[group_id].append(seg_id)
    
    def get_text(self, seg_id: str) -> Optional[str]:
        """
        获取片段文本。
        
        Args:
            seg_id: 片段 ID
            
        Returns:
            文本内容，不存在返回 None
        """
        return self._id_to_text.get(seg_id)
    
    def get_group_segments(self, group_id: str) -> List[str]:
        """
        获取同组的所有片段 ID。
        
        Args:
            group_id: 组 ID
            
        Returns:
            片段 ID 列表
        """
        return self._group_members.get(group_id, [])
    
    def contains(self, seg_id: str) -> bool:
        """检查是否包含片段"""
        return seg_id in self._id_to_text
    
    def __len__(self) -> int:
        """索引大小"""
        return len(self._id_to_text)


# ==============================================================================
# 上下文增强器
# ==============================================================================


class SegmentContextEnricher:
    """
    片段上下文增强器。
    
    负责为片段加载和填充上下文信息。
    
    Attributes:
        corpus_root: 语料根目录
        context_chars: 上下文截取字符数
        index: 上下文索引
    """
    
    def __init__(
        self,
        corpus_root: Optional[Path] = None,
        context_chars: int = ExtractionConstants.DEFAULT_CONTEXT_CHARS,
    ):
        """
        初始化增强器。
        
        Args:
            corpus_root: 语料根目录（用于从文件加载）
            context_chars: 上下文截取字符数
        """
        self.corpus_root = corpus_root
        self.context_chars = context_chars
        self.index = ContextIndex()
        self._load_failures: Set[str] = set()
    
    def build_index_from_segments(
        self,
        segments: List[Dict[str, Any]],
    ) -> None:
        """
        从片段列表构建索引。
        
        Args:
            segments: 片段字典列表
        """
        for seg in segments:
            seg_id = seg.get("id", "")
            if not seg_id:
                continue
            
            self.index.add_segment(
                seg_id=seg_id,
                text=seg.get("text", ""),
                group_id=seg.get("group_id", ""),
            )
        
        logger.info(f"构建上下文索引: {len(self.index)} 条")
    
    def build_index_from_corpus(
        self,
        corpus_root: Path,
        pattern: str = "**/*.txt",
    ) -> None:
        """
        从语料目录构建索引。
        
        Args:
            corpus_root: 语料根目录
            pattern: 文件匹配模式
        """
        self.corpus_root = corpus_root
        count = 0
        
        for txt_path in corpus_root.glob(pattern):
            if txt_path.name.endswith(".meta.json"):
                continue
            if txt_path.name.startswith(("_", ".")):
                continue
            
            try:
                text = txt_path.read_text(encoding="utf-8").strip()
                if not text:
                    continue
                
                # 尝试加载元数据获取 ID
                meta_path = txt_path.with_suffix(".meta.json")
                seg_id = ""
                group_id = ""
                
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                        seg_id = meta.get("md5_hash", "")
                        group_id = meta.get("group_id", "")
                    except Exception:
                        pass
                
                # 无 ID 则生成
                if not seg_id:
                    rel_path = str(txt_path.relative_to(corpus_root))
                    seg_id = hashlib.md5(
                        f"{rel_path}:{text[:100]}".encode()
                    ).hexdigest()[:16]
                
                self.index.add_segment(
                    seg_id=seg_id,
                    text=text,
                    path=txt_path,
                    group_id=group_id,
                )
                count += 1
                
            except Exception as e:
                logger.warning(f"加载文件失败 {txt_path}: {e}")
        
        logger.info(f"从语料目录构建索引: {count} 条")
    
    def enrich(self, segment: Dict[str, Any]) -> EnrichedSegment:
        """
        增强单个片段的上下文。
        
        Args:
            segment: 原始片段字典
            
        Returns:
            增强后的片段
        """
        enriched = EnrichedSegment.from_dict(segment)
        
        # 如果已有上下文，直接返回
        if enriched.has_context():
            return enriched
        
        # 加载前文
        if enriched.prev_part_id:
            prev_text = self._load_text(enriched.prev_part_id)
            if prev_text:
                enriched.context_before = prev_text[-self.context_chars:]
        
        # 加载后文
        if enriched.next_part_id:
            next_text = self._load_text(enriched.next_part_id)
            if next_text:
                enriched.context_after = next_text[:self.context_chars]
        
        return enriched
    
    def enrich_batch(
        self,
        segments: List[Dict[str, Any]],
        build_index: bool = True,
    ) -> List[EnrichedSegment]:
        """
        批量增强片段上下文。
        
        Args:
            segments: 片段列表
            build_index: 是否先构建索引
            
        Returns:
            增强后的片段列表
        """
        if build_index:
            self.build_index_from_segments(segments)
        
        enriched = []
        for seg in segments:
            try:
                enriched.append(self.enrich(seg))
            except Exception as e:
                logger.warning(f"增强片段失败 {seg.get('id', 'unknown')}: {e}")
                # 失败时仍保留原始片段
                enriched.append(EnrichedSegment.from_dict(seg))
        
        return enriched
    
    def _load_text(self, seg_id: str) -> Optional[str]:
        """
        加载片段文本。
        
        优先从索引加载，失败后尝试从文件加载。
        
        Args:
            seg_id: 片段 ID
            
        Returns:
            文本内容
        """
        # 避免重复尝试加载失败的片段
        if seg_id in self._load_failures:
            return None
        
        # 从索引加载
        text = self.index.get_text(seg_id)
        if text:
            return text
        
        # 尝试从文件加载（如果有语料目录）
        if self.corpus_root:
            text = self._load_from_file(seg_id)
            if text:
                self.index.add_segment(seg_id, text)
                return text
        
        self._load_failures.add(seg_id)
        return None
    
    def _load_from_file(self, seg_id: str) -> Optional[str]:
        """
        从文件系统加载片段文本。
        
        遍历语料目录，查找匹配的元数据文件。
        
        Args:
            seg_id: 片段 ID（通常是 MD5 哈希）
            
        Returns:
            文本内容
        """
        if not self.corpus_root or not self.corpus_root.exists():
            return None
        
        # 遍历元数据文件查找匹配
        for meta_path in self.corpus_root.rglob("*.meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("md5_hash") == seg_id:
                    txt_path = meta_path.with_suffix("")  # 去掉 .meta.json
                    txt_path = txt_path.with_suffix(".txt")
                    if txt_path.exists():
                        return txt_path.read_text(encoding="utf-8").strip()
            except Exception:
                continue
        
        return None


# ==============================================================================
# 抽取文本构建
# ==============================================================================


def build_extraction_text(
    segment: Union[Dict[str, Any], EnrichedSegment],
    include_context: bool = True,
    max_total_chars: int = ExtractionConstants.MAX_TOTAL_CHARS,
    context_ratio: float = 0.3,
) -> str:
    """
    构建用于 P5 抽取的文本。
    
    将主文本和上下文组装成结构化格式，便于 LLM 理解抽取边界。
    
    Args:
        segment: 片段数据（字典或 EnrichedSegment）
        include_context: 是否包含上下文
        max_total_chars: 最大总字符数
        context_ratio: 上下文占比（用于分配前后文空间）
        
    Returns:
        用于抽取的结构化文本
        
    Example:
        >>> seg = {"text": "1998年长江发生特大洪水...", "context_before": "..."}
        >>> text = build_extraction_text(seg)
        >>> # 【前文参考】
        >>> # ...
        >>> # 【待抽取文本】
        >>> # 1998年长江发生特大洪水...
    """
    # 统一转换为字典
    if isinstance(segment, EnrichedSegment):
        seg_data = segment.to_dict()
    else:
        seg_data = segment
    
    main_text = seg_data.get("text", "").strip()
    
    # 不包含上下文时，直接返回主文本
    if not include_context:
        return _truncate_text(main_text, max_total_chars)
    
    context_before = seg_data.get("context_before", "").strip()
    context_after = seg_data.get("context_after", "").strip()
    
    # 计算空间分配
    main_len = len(main_text)
    
    # 主文本超长时，优先保证主文本
    if main_len >= max_total_chars:
        return _truncate_text(main_text, max_total_chars)
    
    # 剩余空间分配给上下文
    remaining = max_total_chars - main_len
    context_budget = int(remaining * context_ratio)
    
    # 平均分配给前后文
    half_budget = context_budget // 2
    before_budget = half_budget if context_before else 0
    after_budget = half_budget if context_after else 0
    
    # 如果只有一边有上下文，分配全部预算
    if context_before and not context_after:
        before_budget = context_budget
    elif context_after and not context_before:
        after_budget = context_budget
    
    # 截取上下文
    before_part = context_before[-before_budget:] if context_before else ""
    after_part = context_after[:after_budget] if context_after else ""
    
    # 组装结构化文本
    parts = []
    
    if before_part:
        parts.append(
            f"{ExtractionConstants.MARKER_CONTEXT_BEFORE}\n{before_part}"
        )
    
    parts.append(
        f"{ExtractionConstants.MARKER_MAIN_TEXT}\n{main_text}"
    )
    
    if after_part:
        parts.append(
            f"{ExtractionConstants.MARKER_CONTEXT_AFTER}\n{after_part}"
        )
    
    return ExtractionConstants.SECTION_SEPARATOR.join(parts)


def build_extraction_text_simple(
    segment: Union[Dict[str, Any], EnrichedSegment],
    max_chars: int = ExtractionConstants.MAX_TOTAL_CHARS,
) -> str:
    """
    构建简单的抽取文本（无上下文标记）。
    
    直接拼接前文、主文本、后文，用于不需要区分边界的场景。
    
    Args:
        segment: 片段数据
        max_chars: 最大字符数
        
    Returns:
        拼接后的文本
    """
    if isinstance(segment, EnrichedSegment):
        seg_data = segment.to_dict()
    else:
        seg_data = segment
    
    parts = []
    
    context_before = seg_data.get("context_before", "")
    if context_before:
        parts.append(context_before)
    
    parts.append(seg_data.get("text", ""))
    
    context_after = seg_data.get("context_after", "")
    if context_after:
        parts.append(context_after)
    
    full_text = "\n".join(parts)
    return _truncate_text(full_text, max_chars)


def _truncate_text(text: str, max_chars: int) -> str:
    """
    截断文本到指定长度。
    
    尽量在句子边界截断，避免截断到句子中间。
    
    Args:
        text: 原始文本
        max_chars: 最大字符数
        
    Returns:
        截断后的文本
    """
    if len(text) <= max_chars:
        return text
    
    # 在最大长度附近寻找句子结束符
    truncated = text[:max_chars]
    
    # 常见句子结束符
    end_markers = ["。", "！", "？", "；", "\n", ".", "!", "?"]
    
    # 从末尾向前查找
    best_pos = -1
    for i in range(len(truncated) - 1, max(0, len(truncated) - 100), -1):
        if truncated[i] in end_markers:
            best_pos = i + 1
            break
    
    if best_pos > 0:
        return truncated[:best_pos]
    
    return truncated


# ==============================================================================
# 高级加载函数
# ==============================================================================


def load_segments_with_context(
    jsonl_path: Path,
    corpus_root: Optional[Path] = None,
    context_chars: int = ExtractionConstants.DEFAULT_CONTEXT_CHARS,
    max_segments: Optional[int] = None,
) -> List[EnrichedSegment]:
    """
    加载过滤后的片段，并补充上下文。
    
    从 light_pool.jsonl 加载片段，根据片段关联信息补充前后文上下文。
    
    Args:
        jsonl_path: 过滤后的 JSONL 文件路径
        corpus_root: 原始语料根目录（用于加载缺失的上下文）
        context_chars: 上下文截取字符数
        max_segments: 最大加载数量（用于测试）
        
    Returns:
        包含上下文的增强片段列表
        
    Raises:
        FileNotFoundError: JSONL 文件不存在
        
    Example:
        >>> segments = load_segments_with_context(
        ...     Path("data/filtered/light_pool.jsonl"),
        ...     Path("data/corpus"),
        ... )
        >>> len(segments)
        1234
    """
    if not jsonl_path.exists():
        raise FileNotFoundError(f"JSONL 文件不存在: {jsonl_path}")
    
    # 第一遍：加载所有片段
    raw_segments: List[Dict[str, Any]] = []
    
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                seg_data = json.loads(line)
                raw_segments.append(seg_data)
                
                if max_segments and len(raw_segments) >= max_segments:
                    break
                    
            except json.JSONDecodeError as e:
                logger.warning(f"行 {line_num} JSON 解析失败: {e}")
    
    logger.info(f"加载片段 {len(raw_segments)} 条: {jsonl_path}")
    
    # 创建增强器并处理
    enricher = SegmentContextEnricher(
        corpus_root=corpus_root,
        context_chars=context_chars,
    )
    
    # 批量增强
    enriched = enricher.enrich_batch(raw_segments, build_index=True)
    
    # 统计上下文覆盖率
    with_context = sum(1 for seg in enriched if seg.has_context())
    logger.info(
        f"上下文覆盖: {with_context}/{len(enriched)} "
        f"({with_context/len(enriched)*100:.1f}%)"
    )
    
    return enriched


def iterate_segments_with_context(
    jsonl_path: Path,
    corpus_root: Optional[Path] = None,
    context_chars: int = ExtractionConstants.DEFAULT_CONTEXT_CHARS,
    batch_size: int = 100,
) -> Iterator[List[EnrichedSegment]]:
    """
    迭代加载片段（适用于大文件）。
    
    分批加载和增强片段，减少内存占用。
    
    Args:
        jsonl_path: JSONL 文件路径
        corpus_root: 语料根目录
        context_chars: 上下文字符数
        batch_size: 批次大小
        
    Yields:
        增强后的片段批次
    """
    if not jsonl_path.exists():
        raise FileNotFoundError(f"JSONL 文件不存在: {jsonl_path}")
    
    enricher = SegmentContextEnricher(
        corpus_root=corpus_root,
        context_chars=context_chars,
    )
    
    # 如果有语料目录，预先构建索引
    if corpus_root and corpus_root.exists():
        enricher.build_index_from_corpus(corpus_root)
    
    batch: List[Dict[str, Any]] = []
    
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            try:
                seg_data = json.loads(line)
                batch.append(seg_data)
                
                if len(batch) >= batch_size:
                    yield enricher.enrich_batch(batch, build_index=False)
                    batch = []
                    
            except json.JSONDecodeError:
                continue
    
    # 处理剩余批次
    if batch:
        yield enricher.enrich_batch(batch, build_index=False)


# ==============================================================================
# 工具函数
# ==============================================================================


def get_context_stats(segments: List[EnrichedSegment]) -> Dict[str, Any]:
    """
    统计上下文覆盖情况。
    
    Args:
        segments: 增强片段列表
        
    Returns:
        统计信息字典
    """
    total = len(segments)
    with_before = sum(1 for s in segments if s.context_before)
    with_after = sum(1 for s in segments if s.context_after)
    with_both = sum(1 for s in segments if s.context_before and s.context_after)
    with_any = sum(1 for s in segments if s.has_context())
    
    avg_before_len = (
        sum(len(s.context_before) for s in segments) / total if total else 0
    )
    avg_after_len = (
        sum(len(s.context_after) for s in segments) / total if total else 0
    )
    
    return {
        "total_segments": total,
        "with_context_before": with_before,
        "with_context_after": with_after,
        "with_both_contexts": with_both,
        "with_any_context": with_any,
        "coverage_rate": with_any / total if total else 0,
        "avg_context_before_length": avg_before_len,
        "avg_context_after_length": avg_after_len,
    }


def filter_by_context_quality(
    segments: List[EnrichedSegment],
    require_context: bool = False,
    min_main_length: int = 100,
) -> List[EnrichedSegment]:
    """
    按上下文质量过滤片段。
    
    Args:
        segments: 片段列表
        require_context: 是否要求必须有上下文
        min_main_length: 主文本最小长度
        
    Returns:
        过滤后的片段列表
    """
    filtered = []
    
    for seg in segments:
        # 主文本长度检查
        if len(seg.text) < min_main_length:
            continue
        
        # 上下文要求检查
        if require_context and not seg.has_context():
            continue
        
        filtered.append(seg)
    
    return filtered


# ==============================================================================
# 命令行入口（测试用）
# ==============================================================================


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="P5 上下文感知抽取工具测试"
    )
    parser.add_argument(
        "--jsonl",
        required=True,
        help="过滤后的 JSONL 文件路径",
    )
    parser.add_argument(
        "--corpus",
        default=None,
        help="原始语料目录",
    )
    parser.add_argument(
        "--context-chars",
        type=int,
        default=500,
        help="上下文字符数",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=10,
        help="最大加载数量",
    )
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    
    # 加载片段
    corpus_root = Path(args.corpus) if args.corpus else None
    segments = load_segments_with_context(
        Path(args.jsonl),
        corpus_root=corpus_root,
        context_chars=args.context_chars,
        max_segments=args.max,
    )
    
    # 打印统计
    stats = get_context_stats(segments)
    print("\n上下文统计:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # 打印示例
    if segments:
        print("\n示例片段:")
        seg = segments[0]
        text = build_extraction_text(seg)
        print("-" * 60)
        print(text[:1000])
        print("-" * 60)
