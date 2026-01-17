"""
统一实体和三元组格式定义

本模块定义了知识图谱中实体和三元组的统一表示格式，作为整个系统的单一数据源。
这些格式整合了之前分散在各个模块中的不同表示方式，提供了一致的接口和处理流程。

主要特性：
1. 类型安全：使用dataclass提供编译时类型检查
2. 可扩展：通过metadata字段支持自定义属性
3. 处理追踪：通过标志位追踪实体/三元组的处理状态
4. 向后兼容：提供转换工具支持旧格式

使用示例：
    >>> entity = UnifiedEntity(name="长江", type="River", cn_type="河流")
    >>> entity.aliases = ["扬子江", "大江"]
    >>> entity.normalized = True

    >>> triple = UnifiedTriple(
    ...     subject="长江", predicate="flows_through", object="武汉",
    ...     subject_type="River", object_type="City"
    ... )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class ProcessingStatus(Enum):
    """实体/三元组的处理状态"""
    RAW = "raw"                      # 原始提取，未处理
    NORMALIZED = "normalized"        # 已归一化
    ALIGNED = "aligned"              # 已对齐到TBox
    VERIFIED = "verified"            # 已验证
    REJECTED = "rejected"            # 已拒绝（质量不合格）


@dataclass
class UnifiedEntity:
    """
    统一实体表示

    整合了以下格式：
    - Node dataclass (kg/schema.py)
    - {"name": str, "type": str} 字典格式
    - 三元组中嵌入的实体信息
    - TBox schema中的实体类定义

    Attributes:
        name: 实体的规范名称（经过归一化后的标准名称）
        type: 实体类型的英文名称（与TBox对齐，如"River", "City"）
        cn_type: 实体类型的中文名称（可选，如"河流", "城市"）
        aliases: 实体的别名列表（如["扬子江", "大江"]）
        confidence: 实体提取的置信度（0.0-1.0）
        source_text: 原始文本中的实体提及（未归一化的原始形式）
        doc_id: 来源文档ID
        normalized: 是否已归一化
        aligned: 是否已对齐到TBox
        verified: 是否已通过验证
        status: 处理状态
        metadata: 扩展元数据字典，用于存储额外信息

    Example:
        >>> entity = UnifiedEntity(
        ...     name="长江",
        ...     type="River",
        ...     cn_type="河流",
        ...     aliases=["扬子江", "大江"],
        ...     source_text="扬子江",
        ...     doc_id="doc_001",
        ...     confidence=0.95
        ... )
    """
    # 核心字段（必需）
    name: str                          # 规范实体名称
    type: str                          # 英文类型名（来自TBox）

    # 元数据（可选）
    cn_type: Optional[str] = None      # 中文类型名
    aliases: List[str] = field(default_factory=list)  # 别名列表
    confidence: float = 1.0            # 置信度

    # 上下文信息（可选）
    source_text: Optional[str] = None  # 原始文本中的提及
    doc_id: Optional[str] = None       # 来源文档

    # 处理标志
    normalized: bool = False           # 是否已归一化
    aligned: bool = False              # 是否已对齐到TBox
    verified: bool = False             # 是否已验证
    status: ProcessingStatus = ProcessingStatus.RAW

    # 扩展性
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """验证字段有效性"""
        if not self.name:
            raise ValueError("Entity name cannot be empty")
        if not self.type:
            raise ValueError("Entity type cannot be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于序列化）"""
        return {
            "name": self.name,
            "type": self.type,
            "cn_type": self.cn_type,
            "aliases": self.aliases,
            "confidence": self.confidence,
            "source_text": self.source_text,
            "doc_id": self.doc_id,
            "normalized": self.normalized,
            "aligned": self.aligned,
            "verified": self.verified,
            "status": self.status.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UnifiedEntity:
        """从字典格式创建实体"""
        status = data.get("status", "raw")
        if isinstance(status, str):
            status = ProcessingStatus(status)

        return cls(
            name=data["name"],
            type=data["type"],
            cn_type=data.get("cn_type"),
            aliases=data.get("aliases", []),
            confidence=data.get("confidence", 1.0),
            source_text=data.get("source_text"),
            doc_id=data.get("doc_id"),
            normalized=data.get("normalized", False),
            aligned=data.get("aligned", False),
            verified=data.get("verified", False),
            status=status,
            metadata=data.get("metadata", {}),
        )

    def add_alias(self, alias: str):
        """添加别名"""
        if alias and alias not in self.aliases and alias != self.name:
            self.aliases.append(alias)

    def mark_normalized(self):
        """标记为已归一化"""
        self.normalized = True
        if self.status == ProcessingStatus.RAW:
            self.status = ProcessingStatus.NORMALIZED

    def mark_aligned(self):
        """标记为已对齐"""
        self.aligned = True
        if self.status in (ProcessingStatus.RAW, ProcessingStatus.NORMALIZED):
            self.status = ProcessingStatus.ALIGNED

    def mark_verified(self):
        """标记为已验证"""
        self.verified = True
        self.status = ProcessingStatus.VERIFIED

    def mark_rejected(self):
        """标记为已拒绝"""
        self.status = ProcessingStatus.REJECTED


@dataclass
class UnifiedTriple:
    """
    统一三元组表示

    整合了以下格式：
    - Edge dataclass (kg/schema.py)
    - {"subject": str, "predicate": str, "object": str, ...} 字典格式
    - 带类型和证据的完整三元组格式

    Attributes:
        subject: 主语实体名称
        predicate: 谓词/关系名称
        object: 宾语实体名称
        subject_type: 主语实体类型（英文）
        object_type: 宾语实体类型（英文）
        evidence: 支持该三元组的原文证据
        doc_id: 来源文档ID
        support: 支持度（该三元组在语料中出现的次数）
        confidence: 置信度（0.0-1.0）
        normalized: 是否已归一化
        direction_fixed: 是否已修正方向
        verified: 是否已验证
        status: 处理状态
        metadata: 扩展元数据字典

    Example:
        >>> triple = UnifiedTriple(
        ...     subject="长江",
        ...     predicate="flows_through",
        ...     object="武汉",
        ...     subject_type="River",
        ...     object_type="City",
        ...     evidence="长江流经武汉市",
        ...     doc_id="doc_001",
        ...     confidence=0.95
        ... )
    """
    # 核心三元组
    subject: str
    predicate: str
    object: str

    # 实体类型
    subject_type: str
    object_type: str

    # 证据和来源
    evidence: Optional[str] = None
    doc_id: Optional[str] = None

    # 处理元数据
    support: int = 1                   # 支持度（出现次数）
    confidence: float = 1.0            # 置信度

    # 处理标志
    normalized: bool = False           # 是否已归一化
    direction_fixed: bool = False      # 是否已修正方向
    verified: bool = False             # 是否已验证
    status: ProcessingStatus = ProcessingStatus.RAW

    # 扩展性
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """验证字段有效性"""
        if not self.subject:
            raise ValueError("Triple subject cannot be empty")
        if not self.predicate:
            raise ValueError("Triple predicate cannot be empty")
        if not self.object:
            raise ValueError("Triple object cannot be empty")
        if not self.subject_type:
            raise ValueError("Triple subject_type cannot be empty")
        if not self.object_type:
            raise ValueError("Triple object_type cannot be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")
        if self.support < 1:
            raise ValueError(f"Support must be at least 1, got {self.support}")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于序列化）"""
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "subject_type": self.subject_type,
            "object_type": self.object_type,
            "evidence": self.evidence,
            "doc_id": self.doc_id,
            "support": self.support,
            "confidence": self.confidence,
            "normalized": self.normalized,
            "direction_fixed": self.direction_fixed,
            "verified": self.verified,
            "status": self.status.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UnifiedTriple:
        """从字典格式创建三元组"""
        status = data.get("status", "raw")
        if isinstance(status, str):
            status = ProcessingStatus(status)

        return cls(
            subject=data["subject"],
            predicate=data["predicate"],
            object=data["object"],
            subject_type=data["subject_type"],
            object_type=data["object_type"],
            evidence=data.get("evidence"),
            doc_id=data.get("doc_id"),
            support=data.get("support", 1),
            confidence=data.get("confidence", 1.0),
            normalized=data.get("normalized", False),
            direction_fixed=data.get("direction_fixed", False),
            verified=data.get("verified", False),
            status=status,
            metadata=data.get("metadata", {}),
        )

    def get_key(self) -> tuple:
        """获取三元组的唯一标识（用于去重）"""
        return (self.subject, self.predicate, self.object)

    def mark_normalized(self):
        """标记为已归一化"""
        self.normalized = True
        if self.status == ProcessingStatus.RAW:
            self.status = ProcessingStatus.NORMALIZED

    def mark_direction_fixed(self):
        """标记为已修正方向"""
        self.direction_fixed = True

    def mark_verified(self):
        """标记为已验证"""
        self.verified = True
        self.status = ProcessingStatus.VERIFIED

    def mark_rejected(self):
        """标记为已拒绝"""
        self.status = ProcessingStatus.REJECTED

    def reverse(self) -> UnifiedTriple:
        """
        反转三元组方向

        Returns:
            新的三元组，主语和宾语互换
        """
        return UnifiedTriple(
            subject=self.object,
            predicate=self.predicate,
            object=self.subject,
            subject_type=self.object_type,
            object_type=self.subject_type,
            evidence=self.evidence,
            doc_id=self.doc_id,
            support=self.support,
            confidence=self.confidence,
            normalized=self.normalized,
            direction_fixed=True,  # 标记为已修正
            verified=self.verified,
            status=self.status,
            metadata=self.metadata.copy(),
        )


# 导出所有公共类和枚举
__all__ = [
    "UnifiedEntity",
    "UnifiedTriple",
    "ProcessingStatus",
]
