"""
统一实体匹配器

整合了之前分散在各个模块中的实体匹配逻辑，提供统一的匹配接口。

匹配策略（按优先级）：
1. 精确匹配：完全相同
2. 归一化匹配：归一化后相同
3. 同义词匹配：通过同义词字典匹配
4. 模糊匹配：基于编辑距离或相似度
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Set
from difflib import SequenceMatcher

from ..unified_formats import UnifiedEntity
from .config import MatchingConfig, MatchingStrategy
from .text_normalizer import UnifiedTextNormalizer


@dataclass
class MatchResult:
    """
    实体匹配结果

    Attributes:
        is_match: 是否匹配
        confidence: 匹配置信度（0.0-1.0）
        strategy: 使用的匹配策略
        reason: 匹配原因说明
    """
    is_match: bool
    confidence: float
    strategy: MatchingStrategy
    reason: str

    def __bool__(self) -> bool:
        """支持布尔判断"""
        return self.is_match


class UnifiedEntityMatcher:
    """
    统一实体匹配器

    提供多种匹配策略，支持精确匹配、归一化匹配、同义词匹配和模糊匹配。

    Example:
        >>> matcher = UnifiedEntityMatcher()
        >>> entity1 = UnifiedEntity(name="长江", type="River")
        >>> entity2 = UnifiedEntity(name="扬子江", type="River")
        >>> result = matcher.match(entity1, entity2)
        >>> if result:
        ...     print(f"匹配成功: {result.reason}")
    """

    def __init__(self, config: Optional[MatchingConfig] = None):
        """
        初始化匹配器

        Args:
            config: 匹配配置，如果为None则使用默认配置
        """
        self.config = config or MatchingConfig.default()
        self.normalizer = UnifiedTextNormalizer(self.config.normalization_config)

        # 构建反向同义词索引（从任意同义词到规范名称）
        self._synonym_index: Dict[str, str] = {}
        self._build_synonym_index()

    def _build_synonym_index(self):
        """构建同义词反向索引"""
        self._synonym_index.clear()

        # 从同义词字典构建
        for canonical, synonyms in self.config.synonym_dict.items():
            self._synonym_index[canonical] = canonical
            for syn in synonyms:
                self._synonym_index[syn] = canonical

        # 从别名字典构建
        for alias, canonical in self.config.alias_dict.items():
            self._synonym_index[alias] = canonical
            if canonical not in self._synonym_index:
                self._synonym_index[canonical] = canonical

    def match(
        self,
        entity1: UnifiedEntity,
        entity2: UnifiedEntity,
        mode: Optional[str] = None
    ) -> MatchResult:
        """
        匹配两个实体

        Args:
            entity1: 第一个实体
            entity2: 第二个实体
            mode: 匹配模式（"standard", "strict", "relaxed"）

        Returns:
            匹配结果
        """
        # 类型约束检查
        if self.config.use_type_constraint:
            if entity1.type != entity2.type:
                return MatchResult(
                    is_match=False,
                    confidence=0.0,
                    strategy=MatchingStrategy.EXACT,
                    reason=f"Type mismatch: {entity1.type} != {entity2.type}"
                )

        # 按优先级尝试各种匹配策略
        for strategy in self.config.strategies:
            result = self._match_with_strategy(entity1, entity2, strategy)
            if result.is_match:
                return result

        # 所有策略都失败
        return MatchResult(
            is_match=False,
            confidence=0.0,
            strategy=MatchingStrategy.EXACT,
            reason="No matching strategy succeeded"
        )

    def _match_with_strategy(
        self,
        entity1: UnifiedEntity,
        entity2: UnifiedEntity,
        strategy: MatchingStrategy
    ) -> MatchResult:
        """
        使用指定策略匹配实体

        Args:
            entity1: 第一个实体
            entity2: 第二个实体
            strategy: 匹配策略

        Returns:
            匹配结果
        """
        if strategy == MatchingStrategy.EXACT:
            return self._exact_match(entity1, entity2)
        elif strategy == MatchingStrategy.NORMALIZED:
            return self._normalized_match(entity1, entity2)
        elif strategy == MatchingStrategy.SYNONYM:
            return self._synonym_match(entity1, entity2)
        elif strategy == MatchingStrategy.FUZZY:
            return self._fuzzy_match(entity1, entity2)
        else:
            return MatchResult(
                is_match=False,
                confidence=0.0,
                strategy=strategy,
                reason=f"Unknown strategy: {strategy}"
            )

    def _exact_match(self, entity1: UnifiedEntity, entity2: UnifiedEntity) -> MatchResult:
        """精确匹配"""
        name1 = entity1.name
        name2 = entity2.name

        if not self.config.case_sensitive:
            name1 = name1.lower()
            name2 = name2.lower()

        if name1 == name2:
            return MatchResult(
                is_match=True,
                confidence=1.0,
                strategy=MatchingStrategy.EXACT,
                reason="Exact name match"
            )

        return MatchResult(
            is_match=False,
            confidence=0.0,
            strategy=MatchingStrategy.EXACT,
            reason="Names do not match exactly"
        )

    def _normalized_match(self, entity1: UnifiedEntity, entity2: UnifiedEntity) -> MatchResult:
        """归一化匹配"""
        norm1 = self.normalizer.normalize_entity_name(entity1.name)
        norm2 = self.normalizer.normalize_entity_name(entity2.name)

        if not self.config.case_sensitive:
            norm1 = norm1.lower()
            norm2 = norm2.lower()

        if norm1 == norm2:
            return MatchResult(
                is_match=True,
                confidence=0.95,
                strategy=MatchingStrategy.NORMALIZED,
                reason=f"Normalized match: '{entity1.name}' -> '{norm1}', '{entity2.name}' -> '{norm2}'"
            )

        return MatchResult(
            is_match=False,
            confidence=0.0,
            strategy=MatchingStrategy.NORMALIZED,
            reason="Normalized names do not match"
        )

    def _synonym_match(self, entity1: UnifiedEntity, entity2: UnifiedEntity) -> MatchResult:
        """同义词匹配"""
        # 检查是否通过同义词索引映射到同一规范名称
        canonical1 = self._get_canonical_name(entity1.name)
        canonical2 = self._get_canonical_name(entity2.name)

        if canonical1 and canonical2 and canonical1 == canonical2:
            return MatchResult(
                is_match=True,
                confidence=0.9,
                strategy=MatchingStrategy.SYNONYM,
                reason=f"Synonym match: both map to '{canonical1}'"
            )

        # 检查别名列表
        all_names1 = {entity1.name} | set(entity1.aliases)
        all_names2 = {entity2.name} | set(entity2.aliases)

        # 归一化所有名称
        norm_names1 = {self.normalizer.normalize_entity_name(n) for n in all_names1}
        norm_names2 = {self.normalizer.normalize_entity_name(n) for n in all_names2}

        # 检查是否有交集
        intersection = norm_names1 & norm_names2
        if intersection:
            return MatchResult(
                is_match=True,
                confidence=0.9,
                strategy=MatchingStrategy.SYNONYM,
                reason=f"Alias match: common names {intersection}"
            )

        return MatchResult(
            is_match=False,
            confidence=0.0,
            strategy=MatchingStrategy.SYNONYM,
            reason="No synonym match found"
        )

    def _fuzzy_match(self, entity1: UnifiedEntity, entity2: UnifiedEntity) -> MatchResult:
        """模糊匹配（基于编辑距离）"""
        # 归一化后进行模糊匹配
        norm1 = self.normalizer.normalize_for_matching(entity1.name)
        norm2 = self.normalizer.normalize_for_matching(entity2.name)

        if not norm1 or not norm2:
            return MatchResult(
                is_match=False,
                confidence=0.0,
                strategy=MatchingStrategy.FUZZY,
                reason="Empty name after normalization"
            )

        # 计算相似度
        similarity = self._calculate_similarity(norm1, norm2)

        if similarity >= self.config.fuzzy_threshold:
            return MatchResult(
                is_match=True,
                confidence=similarity,
                strategy=MatchingStrategy.FUZZY,
                reason=f"Fuzzy match: similarity {similarity:.2f} >= threshold {self.config.fuzzy_threshold}"
            )

        return MatchResult(
            is_match=False,
            confidence=similarity,
            strategy=MatchingStrategy.FUZZY,
            reason=f"Similarity {similarity:.2f} < threshold {self.config.fuzzy_threshold}"
        )

    def _get_canonical_name(self, name: str) -> Optional[str]:
        """获取规范名称"""
        # 先尝试精确匹配
        if name in self._synonym_index:
            return self._synonym_index[name]

        # 尝试归一化后匹配
        norm_name = self.normalizer.normalize_entity_name(name)
        if norm_name in self._synonym_index:
            return self._synonym_index[norm_name]

        return None

    @staticmethod
    def _calculate_similarity(str1: str, str2: str) -> float:
        """
        计算两个字符串的相似度

        使用SequenceMatcher计算相似度（基于最长公共子序列）

        Args:
            str1: 第一个字符串
            str2: 第二个字符串

        Returns:
            相似度（0.0-1.0）
        """
        return SequenceMatcher(None, str1, str2).ratio()

    def match_names(self, name1: str, name2: str, entity_type: Optional[str] = None) -> MatchResult:
        """
        匹配两个实体名称（便捷方法）

        Args:
            name1: 第一个实体名称
            name2: 第二个实体名称
            entity_type: 实体类型（可选）

        Returns:
            匹配结果
        """
        entity1 = UnifiedEntity(name=name1, type=entity_type or "Unknown")
        entity2 = UnifiedEntity(name=name2, type=entity_type or "Unknown")
        return self.match(entity1, entity2)

    def find_canonical(self, entity: UnifiedEntity) -> Optional[str]:
        """
        查找实体的规范名称

        Args:
            entity: 实体

        Returns:
            规范名称，如果找不到则返回None
        """
        return self._get_canonical_name(entity.name)

    def add_synonym(self, canonical: str, synonym: str):
        """
        添加同义词

        Args:
            canonical: 规范名称
            synonym: 同义词
        """
        if canonical not in self.config.synonym_dict:
            self.config.synonym_dict[canonical] = set()
        self.config.synonym_dict[canonical].add(synonym)
        self._build_synonym_index()

    def add_alias(self, alias: str, canonical: str):
        """
        添加别名

        Args:
            alias: 别名
            canonical: 规范名称
        """
        self.config.alias_dict[alias] = canonical
        self._build_synonym_index()


# 便捷函数
def match_entities(
    entity1: UnifiedEntity,
    entity2: UnifiedEntity,
    config: Optional[MatchingConfig] = None
) -> MatchResult:
    """
    便捷函数：匹配两个实体

    Args:
        entity1: 第一个实体
        entity2: 第二个实体
        config: 匹配配置

    Returns:
        匹配结果
    """
    matcher = UnifiedEntityMatcher(config)
    return matcher.match(entity1, entity2)


def match_names(
    name1: str,
    name2: str,
    entity_type: Optional[str] = None,
    config: Optional[MatchingConfig] = None
) -> MatchResult:
    """
    便捷函数：匹配两个实体名称

    Args:
        name1: 第一个实体名称
        name2: 第二个实体名称
        entity_type: 实体类型
        config: 匹配配置

    Returns:
        匹配结果
    """
    matcher = UnifiedEntityMatcher(config)
    return matcher.match_names(name1, name2, entity_type)


__all__ = [
    "UnifiedEntityMatcher",
    "MatchResult",
    "match_entities",
    "match_names",
]
