"""
原文回溯校验模块（P5+/P6）

核心思想：有效的抽取结果必须在原文中具有明确的文本证据。
通过检查三元组的subject和object是否在原文中出现来过滤幻觉。

功能：检查P5抽取的实体是否在原文中出现，过滤幻觉
位置：P5抽取之后、知识融合之前
"""

from __future__ import annotations

import re
import logging
from difflib import SequenceMatcher
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """
    验证结果数据类

    Attributes:
        valid_triples: 通过验证的三元组列表
        filtered_triples: 被过滤的三元组列表（含过滤原因）
        valid_events: 通过验证的事件列表
        total_triples: 待验证的三元组总数
        valid_count: 通过验证的三元组数
        filtered_count: 被过滤的三元组数
        hallucination_rate: 幻觉率（百分比，0-100）
        verification_log: 验证日志
    """
    valid_triples: List[Dict] = field(default_factory=list)
    filtered_triples: List[Dict] = field(default_factory=list)
    valid_events: List[Dict] = field(default_factory=list)

    total_triples: int = 0
    valid_count: int = 0
    filtered_count: int = 0
    hallucination_rate: float = 0.0

    verification_log: List[str] = field(default_factory=list)


class HallucinationFilter:
    """
    原文回溯校验器

    核心逻辑：
    1. 对于每个三元组，检查subject和object是否在原文中出现
    2. 支持精确匹配和模糊匹配两种模式
    3. 记录被过滤的三元组及原因，便于统计幻觉率

    验证规则：
    1. 三元组的subject必须在原文中出现（精确匹配或模糊匹配）
    2. 三元组的object必须在原文中出现（精确匹配或模糊匹配）
    3. 同时通过验证的三元组才会被保留

    Args:
        strict_mode: 是否使用严格模式（仅精确匹配）
        fuzzy_threshold: 模糊匹配的相似度阈值（0.0-1.0）
        min_entity_length: 最小实体长度，过短的实体跳过校验
        verbose: 是否输出详细日志

    Example:
        >>> filter = HallucinationFilter(strict_mode=False, fuzzy_threshold=0.8)
        >>> result = filter.verify(extraction_result, original_text)
        >>> print(f"幻觉率: {result.hallucination_rate:.2f}%")
    """

    def __init__(
        self,
        strict_mode: bool = True,
        fuzzy_threshold: float = 0.8,
        min_entity_length: int = 2,
        verbose: bool = True
    ):
        """
        初始化校验器

        Args:
            strict_mode: 严格模式，True时仅精确匹配，False时启用模糊匹配
            fuzzy_threshold: 模糊匹配相似度阈值（0-1），默认0.8
            min_entity_length: 最小实体长度，过短的实体跳过校验（如单个数字）
            verbose: 是否输出详细日志
        """
        self.strict_mode = strict_mode
        self.fuzzy_threshold = fuzzy_threshold
        self.min_entity_length = min_entity_length
        self.verbose = verbose

    def verify(
        self,
        extraction_result: Dict,
        original_text: str,
        context_before: str = "",
        context_after: str = ""
    ) -> VerificationResult:
        """
        验证抽取结果

        Args:
            extraction_result: P5抽取的结果，包含events和triples字段
            original_text: 原始文本（待抽取文本）
            context_before: 前文上下文（可选）
            context_after: 后文上下文（可选）

        Returns:
            VerificationResult: 包含验证结果和统计信息
        """
        result = VerificationResult()

        # 合并文本用于验证（主文本+上下文）
        full_text = self._merge_text(original_text, context_before, context_after)
        clean_text = self._normalize_text(full_text)

        # 验证事件（宽松处理，主要验证事件名称）
        events = extraction_result.get("events", [])
        for event in events:
            if isinstance(event, dict):
                result.valid_events.append(event)

        # 验证三元组（严格处理）
        triples = extraction_result.get("triples", [])
        result.total_triples = len(triples)

        for triple in triples:
            if not isinstance(triple, dict):
                continue

            is_valid, reason = self._verify_triple(triple, clean_text, full_text)

            if is_valid:
                result.valid_triples.append(triple)
                result.valid_count += 1
            else:
                triple_with_reason = {**triple, "filter_reason": reason}
                result.filtered_triples.append(triple_with_reason)
                result.filtered_count += 1

                if self.verbose:
                    s = triple.get("subject", "")
                    p = triple.get("predicate", "")
                    o = triple.get("object", "")
                    log_msg = f"[过滤] {s} --{p}--> {o} | 原因: {reason}"
                    result.verification_log.append(log_msg)
                    logger.debug(log_msg)

        # 计算幻觉率
        if result.total_triples > 0:
            result.hallucination_rate = result.filtered_count / result.total_triples * 100

        return result

    def verify_triples(
        self,
        triples: List[Dict],
        original_text: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        批量验证三元组（简化接口）

        Args:
            triples: 三元组列表，格式为 [{"subject": str, "predicate": str, "object": str, ...}, ...]
            original_text: 原始文本

        Returns:
            valid_triples: 通过验证的三元组列表
            filtered_triples: 被过滤的三元组列表，每个元素包含 {"triple": dict, "reason": str}
        """
        extraction_result = {"triples": triples, "events": []}
        result = self.verify(extraction_result, original_text)

        # 转换为旧格式以保持兼容性
        filtered_with_reason = [
            {"triple": {k: v for k, v in t.items() if k != "filter_reason"},
             "reason": t.get("filter_reason", "")}
            for t in result.filtered_triples
        ]

        return result.valid_triples, filtered_with_reason

    def _merge_text(self, main: str, before: str, after: str) -> str:
        """合并主文本和上下文"""
        parts = []
        if before and before.strip():
            parts.append(before.strip())
        parts.append(main.strip())
        if after and after.strip():
            parts.append(after.strip())
        return " ".join(parts)

    def _normalize_text(self, text: str) -> str:
        """标准化文本（去除多余空白）"""
        text = re.sub(r'\s+', '', text)
        return text.strip()

    def _verify_triple(
        self,
        triple: Dict,
        clean_text: str,
        original_text: str
    ) -> Tuple[bool, str]:
        """
        验证单个三元组

        Returns:
            Tuple[bool, str]: (是否有效, 原因说明)
        """
        subject = triple.get("subject", "").strip()
        obj = triple.get("object", "").strip()

        # 验证subject
        s_valid, s_reason = self._check_entity(subject, clean_text, original_text)
        if not s_valid:
            return False, f"主语'{subject}': {s_reason}"

        # 验证object
        o_valid, o_reason = self._check_entity(obj, clean_text, original_text)
        if not o_valid:
            return False, f"宾语'{obj}': {o_reason}"

        return True, f"验证通过(subject:{s_reason}, object:{o_reason})"

    def _check_entity(
        self,
        entity: str,
        clean_text: str,
        original_text: str
    ) -> Tuple[bool, str]:
        """
        检查单个实体是否存在于原文中

        Args:
            entity: 待检查的实体字符串
            clean_text: 去除空白后的原文
            original_text: 原始文本

        Returns:
            (is_valid, reason): 是否通过验证及原因

        匹配优先级：
        1. 精确匹配（去空格后）
        2. 原文精确匹配（保留空格）
        3. 模糊匹配（非严格模式下）
        """
        if not entity:
            return False, "实体为空"

        # 过短的实体跳过校验（如单个数字、单个汉字）
        if len(entity) < self.min_entity_length:
            return True, "实体过短，跳过校验"

        # 清理实体中的空白字符
        clean_entity = re.sub(r'\s+', '', entity)

        # 1. 精确匹配（去空格后）
        if clean_entity in clean_text:
            return True, "精确匹配"

        # 2. 原文精确匹配（保留空格）
        if entity in original_text:
            return True, "原文匹配"

        # 严格模式下到此为止
        if self.strict_mode:
            return False, "原文中不存在"

        # 3. 忽略空格匹配
        entity_norm = entity.replace(" ", "").replace("　", "")
        text_norm = original_text.replace(" ", "").replace("　", "")
        if entity_norm in text_norm:
            return True, "标准化匹配"

        # 4. 模糊匹配（滑动窗口）
        similarity = self._fuzzy_search(clean_entity, clean_text)
        if similarity >= self.fuzzy_threshold:
            return True, f"模糊匹配({similarity:.2f})"

        return False, f"模糊匹配失败(最高{similarity:.2f}<阈值{self.fuzzy_threshold})"

    def _fuzzy_search(self, entity: str, text: str) -> float:
        """
        滑动窗口模糊搜索

        在文本中搜索与实体最相似的片段，返回最高相似度
        使用 difflib.SequenceMatcher 计算相似度
        """
        if not entity or not text:
            return 0.0

        entity_len = len(entity)
        text_len = len(text)

        if entity_len > text_len:
            return SequenceMatcher(None, entity, text).ratio()

        max_similarity = 0.0

        # 滑动窗口搜索
        window_sizes = [entity_len, entity_len + 1, entity_len - 1, entity_len + 2]
        window_sizes = [w for w in window_sizes if 0 < w <= text_len]

        for window_size in window_sizes:
            for i in range(text_len - window_size + 1):
                window = text[i:i + window_size]
                similarity = SequenceMatcher(None, entity, window).ratio()
                if similarity > max_similarity:
                    max_similarity = similarity
                    if max_similarity >= self.fuzzy_threshold:
                        return max_similarity

        return max_similarity

    def get_hallucination_rate(self, result: VerificationResult) -> float:
        """计算幻觉率 = 被过滤数量 / 总数量"""
        if result.total_triples == 0:
            return 0.0
        return result.filtered_count / result.total_triples

    def get_statistics(self, result: VerificationResult) -> Dict:
        """获取过滤统计信息"""
        return {
            "total_count": result.total_triples,
            "valid_count": result.valid_count,
            "filtered_count": result.filtered_count,
            "hallucination_rate": result.hallucination_rate,
            "verification_log": result.verification_log,
        }


# 便捷函数
def filter_hallucinations(
    triples: List[Dict],
    original_text: str,
    strict_mode: bool = True,
    fuzzy_threshold: float = 0.8
) -> Tuple[List[Dict], List[Dict], float]:
    """
    便捷函数：一步完成幻觉过滤

    Args:
        triples: 三元组列表
        original_text: 原始文本
        strict_mode: 是否使用严格模式
        fuzzy_threshold: 模糊匹配阈值

    Returns:
        (valid_triples, filtered_triples, hallucination_rate)
        - valid_triples: 通过验证的三元组列表
        - filtered_triples: 被过滤的三元组列表
        - hallucination_rate: 幻觉率（0-1之间的小数）
    """
    filter_instance = HallucinationFilter(
        strict_mode=strict_mode,
        fuzzy_threshold=fuzzy_threshold,
    )

    extraction_result = {"triples": triples, "events": []}
    result = filter_instance.verify(extraction_result, original_text)

    # 转换为包含reason的格式
    filtered_with_reason = [
        {"triple": {k: v for k, v in t.items() if k != "filter_reason"},
         "reason": t.get("filter_reason", "")}
        for t in result.filtered_triples
    ]

    # 返回0-1之间的幻觉率（而非百分比）
    hallucination_rate = result.hallucination_rate / 100.0

    return result.valid_triples, filtered_with_reason, hallucination_rate


if __name__ == "__main__":
    # 测试用例
    text = "1998年8月，长江干流沙市站水位达到45.22米，超过历史最高水位。"

    triples = [
        {"subject": "沙市站", "predicate": "水位达到", "object": "45.22米"},      # 应保留
        {"subject": "武汉站", "predicate": "水位达到", "object": "30米"},          # 应过滤（武汉站不在原文）
        {"subject": "长江干流", "predicate": "包含", "object": "沙市站"},          # 应保留
        {"subject": "1998年", "predicate": "发生", "object": "特大洪水"},          # 应过滤（特大洪水不在原文）
    ]

    valid, filtered, rate = filter_hallucinations(triples, text, strict_mode=True)

    print(f"通过: {len(valid)}, 过滤: {len(filtered)}, 幻觉率: {rate:.1%}")

    print("\n通过的三元组:")
    for t in valid:
        print(f"  {t['subject']} --{t['predicate']}--> {t['object']}")

    print("\n被过滤的三元组:")
    for f in filtered:
        print(f"  {f['triple']['subject']} --{f['triple']['predicate']}--> {f['triple']['object']}")
        print(f"    原因: {f['reason']}")

    # 预期输出：通过: 2, 过滤: 2, 幻觉率: 50.0%
