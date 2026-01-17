"""
归一化配置模块

定义了归一化和匹配过程中使用的各种配置参数。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum


class NormalizationMode(Enum):
    """文本归一化模式"""
    STANDARD = "standard"      # 标准模式：去除空格、转小写、全角转半角
    STRICT = "strict"          # 严格模式：仅去除首尾空白
    FUZZY = "fuzzy"            # 模糊模式：去除所有标点符号
    VALUE = "value"            # 数值模式：提取数值信息


class MatchingStrategy(Enum):
    """实体匹配策略"""
    EXACT = "exact"            # 精确匹配
    NORMALIZED = "normalized"  # 归一化后匹配
    SYNONYM = "synonym"        # 同义词匹配
    FUZZY = "fuzzy"            # 模糊匹配（基于编辑距离或相似度）


@dataclass
class NormalizationConfig:
    """
    文本归一化配置

    Attributes:
        mode: 归一化模式
        remove_spaces: 是否去除所有空格
        lowercase: 是否转换为小写
        full_to_half: 是否全角转半角
        remove_punctuation: 是否去除标点符号
        preserve_numbers: 是否保留数字
        custom_replacements: 自定义替换规则
    """
    mode: NormalizationMode = NormalizationMode.STANDARD
    remove_spaces: bool = True
    lowercase: bool = False  # 中文实体通常不需要转小写
    full_to_half: bool = True
    remove_punctuation: bool = False
    preserve_numbers: bool = True
    custom_replacements: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def standard(cls) -> NormalizationConfig:
        """标准配置：去除空格、全角转半角"""
        return cls(
            mode=NormalizationMode.STANDARD,
            remove_spaces=True,
            lowercase=False,
            full_to_half=True,
            remove_punctuation=False,
        )

    @classmethod
    def strict(cls) -> NormalizationConfig:
        """严格配置：仅去除首尾空白"""
        return cls(
            mode=NormalizationMode.STRICT,
            remove_spaces=False,
            lowercase=False,
            full_to_half=False,
            remove_punctuation=False,
        )

    @classmethod
    def fuzzy(cls) -> NormalizationConfig:
        """模糊配置：去除所有标点和空格"""
        return cls(
            mode=NormalizationMode.FUZZY,
            remove_spaces=True,
            lowercase=False,
            full_to_half=True,
            remove_punctuation=True,
        )

    @classmethod
    def value(cls) -> NormalizationConfig:
        """数值配置：提取数值信息"""
        return cls(
            mode=NormalizationMode.VALUE,
            remove_spaces=True,
            lowercase=False,
            full_to_half=True,
            remove_punctuation=False,
            preserve_numbers=True,
        )


@dataclass
class MatchingConfig:
    """
    实体匹配配置

    Attributes:
        strategies: 匹配策略列表（按优先级排序）
        fuzzy_threshold: 模糊匹配阈值（0.0-1.0）
        use_type_constraint: 是否使用类型约束（只匹配相同类型的实体）
        case_sensitive: 是否区分大小写
        normalization_config: 归一化配置
        synonym_dict: 同义词字典
        alias_dict: 别名字典
    """
    strategies: List[MatchingStrategy] = field(default_factory=lambda: [
        MatchingStrategy.EXACT,
        MatchingStrategy.NORMALIZED,
        MatchingStrategy.SYNONYM,
        MatchingStrategy.FUZZY,
    ])
    fuzzy_threshold: float = 0.8
    use_type_constraint: bool = True
    case_sensitive: bool = False
    normalization_config: NormalizationConfig = field(default_factory=NormalizationConfig.standard)
    synonym_dict: Dict[str, Set[str]] = field(default_factory=dict)
    alias_dict: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """验证配置有效性"""
        if not 0.0 <= self.fuzzy_threshold <= 1.0:
            raise ValueError(f"fuzzy_threshold must be between 0.0 and 1.0, got {self.fuzzy_threshold}")

    @classmethod
    def default(cls) -> MatchingConfig:
        """默认配置"""
        return cls()

    @classmethod
    def strict(cls) -> MatchingConfig:
        """严格配置：仅精确匹配"""
        return cls(
            strategies=[MatchingStrategy.EXACT],
            use_type_constraint=True,
            case_sensitive=True,
        )

    @classmethod
    def relaxed(cls) -> MatchingConfig:
        """宽松配置：使用所有匹配策略，降低阈值"""
        return cls(
            strategies=[
                MatchingStrategy.EXACT,
                MatchingStrategy.NORMALIZED,
                MatchingStrategy.SYNONYM,
                MatchingStrategy.FUZZY,
            ],
            fuzzy_threshold=0.7,
            use_type_constraint=False,
            case_sensitive=False,
        )


@dataclass
class TypeConfig:
    """
    类型系统配置

    Attributes:
        type_hierarchy: 类型层次结构（子类型 -> 父类型）
        type_aliases: 类型别名（别名 -> 规范类型）
        cn_to_en: 中文类型到英文类型的映射
        en_to_cn: 英文类型到中文类型的映射
        valid_types: 有效类型集合
    """
    type_hierarchy: Dict[str, str] = field(default_factory=dict)
    type_aliases: Dict[str, str] = field(default_factory=dict)
    cn_to_en: Dict[str, str] = field(default_factory=dict)
    en_to_cn: Dict[str, str] = field(default_factory=dict)
    valid_types: Set[str] = field(default_factory=set)

    def add_type(self, en_name: str, cn_name: Optional[str] = None, parent: Optional[str] = None):
        """添加类型定义"""
        self.valid_types.add(en_name)
        if cn_name:
            self.cn_to_en[cn_name] = en_name
            self.en_to_cn[en_name] = cn_name
        if parent:
            self.type_hierarchy[en_name] = parent

    def add_alias(self, alias: str, canonical: str):
        """添加类型别名"""
        self.type_aliases[alias] = canonical


__all__ = [
    "NormalizationMode",
    "MatchingStrategy",
    "NormalizationConfig",
    "MatchingConfig",
    "TypeConfig",
]
