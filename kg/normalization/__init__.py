"""
统一归一化模块

本包提供了知识图谱中实体和三元组的统一归一化功能，整合了之前分散在各个模块中的
不同归一化逻辑。

主要组件：
- UnifiedTextNormalizer: 文本归一化器，提供多种归一化模式
- UnifiedEntityMatcher: 实体匹配器，支持精确匹配、模糊匹配、同义词匹配
- TypeRegistry: 类型注册表，管理实体类型的规范化和层次结构
- NormalizationConfig: 归一化配置

使用示例：
    >>> from kg.normalization import UnifiedTextNormalizer, UnifiedEntityMatcher
    >>> normalizer = UnifiedTextNormalizer()
    >>> text = normalizer.normalize("  长江  ", mode="standard")
    >>> matcher = UnifiedEntityMatcher()
    >>> is_match, confidence, reason = matcher.match(entity1, entity2)
"""

from .text_normalizer import UnifiedTextNormalizer, NormalizationMode
from .entity_matcher import UnifiedEntityMatcher, MatchResult
from .type_registry import TypeRegistry
from .config import NormalizationConfig, MatchingConfig

__all__ = [
    "UnifiedTextNormalizer",
    "NormalizationMode",
    "UnifiedEntityMatcher",
    "MatchResult",
    "TypeRegistry",
    "NormalizationConfig",
    "MatchingConfig",
]
