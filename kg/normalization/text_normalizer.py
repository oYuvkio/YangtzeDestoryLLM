"""
统一文本归一化器

整合了之前分散在各个模块中的文本清理逻辑：
- SimpleEntityNormalizer (kg/entity_fusion.py): 基础文本清理、全角转半角
- EntityNormalizer (kg/utils/entity_linking.py): 别名映射
- BidirectionalFusion._normalize_text(): 正则表达式清理

提供统一的接口和多种归一化模式。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from .config import NormalizationConfig, NormalizationMode


class UnifiedTextNormalizer:
    """
    统一文本归一化器

    提供多种归一化模式，适用于不同场景：
    - standard: 标准模式，适用于大多数实体归一化
    - strict: 严格模式，仅做最小处理
    - fuzzy: 模糊模式，用于模糊匹配
    - value: 数值模式，用于提取和归一化数值

    Example:
        >>> normalizer = UnifiedTextNormalizer()
        >>> normalizer.normalize("  长江  ", mode="standard")
        '长江'
        >>> normalizer.normalize("２０２０年", mode="standard")
        '2020年'
        >>> normalizer.normalize("长江、黄河", mode="fuzzy")
        '长江黄河'
    """

    def __init__(self, config: Optional[NormalizationConfig] = None):
        """
        初始化归一化器

        Args:
            config: 归一化配置，如果为None则使用标准配置
        """
        self.config = config or NormalizationConfig.standard()

    def normalize(self, text: str, mode: Optional[str] = None) -> str:
        """
        归一化文本

        Args:
            text: 待归一化的文本
            mode: 归一化模式（"standard", "strict", "fuzzy", "value"）
                 如果为None，使用配置中的模式

        Returns:
            归一化后的文本
        """
        if not text:
            return text

        # 确定使用的模式
        if mode:
            norm_mode = NormalizationMode(mode)
        else:
            norm_mode = self.config.mode

        # 根据模式选择配置
        if norm_mode == NormalizationMode.STANDARD:
            config = NormalizationConfig.standard()
        elif norm_mode == NormalizationMode.STRICT:
            config = NormalizationConfig.strict()
        elif norm_mode == NormalizationMode.FUZZY:
            config = NormalizationConfig.fuzzy()
        elif norm_mode == NormalizationMode.VALUE:
            config = NormalizationConfig.value()
        else:
            config = self.config

        return self._normalize_with_config(text, config)

    def _normalize_with_config(self, text: str, config: NormalizationConfig) -> str:
        """
        使用指定配置归一化文本

        Args:
            text: 待归一化的文本
            config: 归一化配置

        Returns:
            归一化后的文本
        """
        result = text

        # 1. 去除首尾空白（所有模式都执行）
        result = result.strip()

        # 2. 自定义替换
        for old, new in config.custom_replacements.items():
            result = result.replace(old, new)

        # 3. 全角转半角
        if config.full_to_half:
            result = self._full_to_half(result)

        # 4. 去除全角空格（在统一空格之前处理）
        result = result.replace('　', '')

        # 5. 统一空格（多个空格合并为一个）
        result = re.sub(r'\s+', ' ', result)

        # 6. 去除所有空格
        if config.remove_spaces:
            result = result.replace(' ', '')

        # 7. 转小写
        if config.lowercase:
            result = result.lower()

        # 8. 去除标点符号
        if config.remove_punctuation:
            result = self._remove_punctuation(result, preserve_numbers=config.preserve_numbers)

        # 9. Unicode归一化（NFC形式）
        result = unicodedata.normalize('NFC', result)

        return result

    @staticmethod
    def _full_to_half(text: str) -> str:
        """
        全角字符转半角

        转换范围：
        - 全角数字（０-９）-> 半角数字（0-9）
        - 全角字母（Ａ-Ｚ，ａ-ｚ）-> 半角字母（A-Z，a-z）
        - 全角标点符号 -> 半角标点符号

        Args:
            text: 输入文本

        Returns:
            转换后的文本
        """
        result = []
        for char in text:
            code = ord(char)
            # 全角字符范围: 0xFF01-0xFF5E (！-～)
            # 对应半角范围: 0x0021-0x007E (!-~)
            if 0xFF01 <= code <= 0xFF5E:
                # 全角到半角的转换：减去0xFEE0
                result.append(chr(code - 0xFEE0))
            # 全角空格特殊处理
            elif code == 0x3000:
                result.append(' ')
            else:
                result.append(char)
        return ''.join(result)

    @staticmethod
    def _remove_punctuation(text: str, preserve_numbers: bool = True) -> str:
        """
        去除标点符号

        Args:
            text: 输入文本
            preserve_numbers: 是否保留数字

        Returns:
            去除标点后的文本
        """
        if preserve_numbers:
            # 保留中文字符、英文字母、数字
            pattern = r'[^\u4e00-\u9fa5a-zA-Z0-9]'
        else:
            # 仅保留中文字符和英文字母
            pattern = r'[^\u4e00-\u9fa5a-zA-Z]'

        return re.sub(pattern, '', text)

    def normalize_entity_name(self, name: str) -> str:
        """
        归一化实体名称（使用标准模式）

        这是最常用的归一化方法，用于实体名称的标准化。

        Args:
            name: 实体名称

        Returns:
            归一化后的实体名称
        """
        return self.normalize(name, mode="standard")

    def normalize_for_matching(self, text: str) -> str:
        """
        为匹配准备的归一化（使用模糊模式）

        用于实体匹配前的文本预处理，去除更多干扰信息。

        Args:
            text: 输入文本

        Returns:
            归一化后的文本
        """
        return self.normalize(text, mode="fuzzy")

    def extract_numbers(self, text: str) -> list[str]:
        """
        从文本中提取数字

        Args:
            text: 输入文本

        Returns:
            提取的数字列表
        """
        # 先全角转半角
        normalized = self._full_to_half(text)
        # 提取所有数字（包括小数）
        numbers = re.findall(r'\d+\.?\d*', normalized)
        return numbers

    def normalize_number(self, text: str) -> str:
        """
        归一化数值文本

        将文本中的数字统一为标准格式。

        Args:
            text: 包含数字的文本

        Returns:
            归一化后的文本
        """
        # 全角转半角
        result = self._full_to_half(text)
        # 去除数字中的逗号分隔符
        result = re.sub(r'(\d),(\d)', r'\1\2', result)
        return result

    def is_empty_after_normalization(self, text: str) -> bool:
        """
        检查文本归一化后是否为空

        Args:
            text: 输入文本

        Returns:
            归一化后是否为空
        """
        normalized = self.normalize(text)
        return not normalized or normalized.isspace()


# 便捷函数
def normalize_text(text: str, mode: str = "standard") -> str:
    """
    便捷函数：归一化文本

    Args:
        text: 待归一化的文本
        mode: 归一化模式

    Returns:
        归一化后的文本
    """
    normalizer = UnifiedTextNormalizer()
    return normalizer.normalize(text, mode=mode)


def normalize_entity_name(name: str) -> str:
    """
    便捷函数：归一化实体名称

    Args:
        name: 实体名称

    Returns:
        归一化后的实体名称
    """
    normalizer = UnifiedTextNormalizer()
    return normalizer.normalize_entity_name(name)


__all__ = [
    "UnifiedTextNormalizer",
    "normalize_text",
    "normalize_entity_name",
]
