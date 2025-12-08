#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
轻量级语料过滤器 v2.0
================================================================================

专为「长江流域水旱灾害知识图谱」项目设计的语料质量过滤工具。

功能概述
--------
对已切分的语料片段进行两阶段过滤：
1. **粗规则过滤**：基于统计特征快速剔除明显无效内容
   - 汉字占比检查
   - 异常字符比例检查
   - 领域关键词命中检查
2. **LLM 质量判定**：调用大模型进行语义级别的相关性判断
   - 水旱灾害领域相关性
   - 长江流域关联度
   - 文本质量评估
   - KG 抽取价值判断

设计特点
--------
- **断点续跑**：完善的缓存机制，支持任务中断后恢复
- **增量处理**：自动跳过已处理的片段
- **优雅降级**：LLM 调用失败时保存进度并优雅退出
- **实时输出**：边处理边写入，避免最后才发现问题
- **进度可视化**：清晰的处理进度和统计信息

使用示例
--------
```bash
# 基础用法
python tools/filter_corpus_light.py \
    --root data/corpus_for_kg/handled_all_kg_corpus \
    --out data/corpus_for_kg/p5_corpus_filtered/light_pool.jsonl

# 使用特定 LLM 配置
python tools/filter_corpus_light.py \
    --root ./handled_corpus \
    --out ./filtered/light_pool.jsonl \
    --llm-provider zhipu --llm-model "GLM-4.5-Air" \
    --sleep-secs 1.0

# 仅测试前 10 个文件
python tools/filter_corpus_light.py \
    --root ./handled_corpus \
    --max-files 10 --verbose
作者: KG Team
版本: 2.0.0
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Final,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager

import yaml

# ==============================================================================
# 项目路径配置
# ==============================================================================

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ==============================================================================
# 项目模块导入
# ==============================================================================

try:
    from kg.llm_core import LLMFactory, RateLimitError, AccountBlockedError

    LLM_AVAILABLE = True
except ImportError as e:
    LLMFactory = None  # type: ignore[assignment]
    RateLimitError = Exception  # type: ignore[assignment]
    AccountBlockedError = Exception  # type: ignore[assignment]
    LLM_AVAILABLE = False
    print(f"警告: 无法导入 LLM 模块: {e}")

try:
    from kg.prompts import (
        EVAL_SEGMENT_FILTER_SYSTEM,
        EVAL_SEGMENT_FILTER_USER_TEMPLATE,
    )

    PROMPTS_AVAILABLE = True
except ImportError:
    PROMPTS_AVAILABLE = False
    # 使用内置的默认提示词
    EVAL_SEGMENT_FILTER_SYSTEM = ""
    EVAL_SEGMENT_FILTER_USER_TEMPLATE = ""

# 导入标题标记清理函数
try:
    from tools.corpus_cleaner import clean_special_tags
    CLEANER_AVAILABLE = True
except ImportError:
    CLEANER_AVAILABLE = False
    # 回退实现
    def clean_special_tags(text: str) -> str:
        """Fallback: 简单清理标题标记"""
        import re
        text = re.sub(r'\[[一二三四五六]级标题\]\s*', '', text)
        text = re.sub(r'\[/?(表格|代码块)\]', '', text)
        text = re.sub(r'\[图片:\s*[^\]]*\]', '', text)
        return text.strip()

# ==============================================================================
# 常量定义
# ==============================================================================


class Constants:
    """全局常量。
    
    集中管理过滤器的所有可配置参数默认值。
    """

    VERSION: Final[str] = "2.0.0"
    TOOL_NAME: Final[str] = "轻量级语料过滤器"

    # 默认过滤参数
    DEFAULT_MIN_CHARS: Final[int] = 80
    DEFAULT_MAX_CHARS: Final[int] = 3000
    DEFAULT_MIN_CN_RATIO: Final[float] = 0.3
    DEFAULT_MAX_WEIRD_RATIO: Final[float] = 0.15
    DEFAULT_MIN_KEEP_CHARS: Final[int] = 200  # 保留片段最小长度，避免上下文过碎

    # 缓存与批处理
    DEFAULT_FLUSH_INTERVAL: Final[int] = 50
    DEFAULT_SLEEP_SECONDS: Final[float] = 0.0

    # 哈希长度
    SEGMENT_ID_LENGTH: Final[int] = 16
    
    # 上下文配置
    DEFAULT_CONTEXT_CHARS: Final[int] = 500  # 默认上下文截取字符数


# ==============================================================================
# 日志配置
# ==============================================================================


class LoggerFactory:
    """日志工厂"""

    _lock: ClassVar[threading.Lock] = threading.Lock()
    _logger: ClassVar[Optional[logging.Logger]] = None

    @classmethod
    def get_logger(
        cls,
        name: str = "corpus_filter",
        level: int = logging.INFO,
        log_file: Optional[Path] = None,
    ) -> logging.Logger:
        """获取或创建日志器"""
        with cls._lock:
            if cls._logger is not None:
                cls._logger.setLevel(level)
                return cls._logger

            logger = logging.getLogger(name)
            logger.setLevel(level)
            logger.handlers.clear()

            # 格式化器
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)-7s | %(message)s",
                datefmt="%H:%M:%S",
            )

            # 控制台处理器
            console = logging.StreamHandler(sys.stdout)
            console.setFormatter(formatter)
            logger.addHandler(console)

            # 文件处理器（可选）
            if log_file:
                log_file.parent.mkdir(parents=True, exist_ok=True)
                file_handler = logging.FileHandler(log_file, encoding="utf-8")
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)

            logger.propagate = False
            cls._logger = logger
            return logger


logger = LoggerFactory.get_logger()

# ==============================================================================
# 异常定义
# ==============================================================================


class FilterError(Exception):
    """过滤器基础异常"""

    pass


class CacheError(FilterError):
    """缓存操作异常"""

    pass


class LLMFilterError(FilterError):
    """LLM 过滤异常"""

    pass


# ==============================================================================
# 数据结构定义
# ==============================================================================


class FilterDecision(Enum):
    """过滤决策枚举"""

    KEEP = "keep"
    DROP_COARSE = "drop_coarse"  # 粗规则过滤掉
    DROP_LLM = "drop_llm"  # LLM 判定过滤掉
    ERROR = "error"  # 处理出错
    PENDING = "pending"  # 待处理


@dataclass
class Segment:
    """
    语料片段数据结构。

    Attributes:
        id: 唯一标识符（基于内容哈希）
        text: 文本内容
        rel_path: 相对于语料根目录的路径
        char_count: 字符数
        source_file: 来源文件名
        filter_decision: 过滤决策结果
        filter_labels: LLM 返回的标签信息
        filter_reason: 过滤原因说明
        process_time: 处理耗时（秒）
    """

    id: str
    text: str
    rel_path: str
    char_count: int
    source_file: str = ""
    prev_part_id: str = ""   # 前一片段 ID（来自 meta）
    next_part_id: str = ""   # 后一片段 ID（来自 meta）
    group_id: str = ""       # 同源文档组 ID（来自 meta）
    context_before: str = ""  # 预留上下文
    context_after: str = ""   # 预留上下文
    filter_decision: Optional[str] = None
    filter_labels: Dict[str, Any] = field(default_factory=dict)
    filter_reason: str = ""
    process_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，包含上下文"""
        d = asdict(self)
        # 确保上下文字段存在
        d.setdefault("context_before", "")
        d.setdefault("context_after", "")
        d.setdefault("prev_part_id", "")
        d.setdefault("next_part_id", "")
        d.setdefault("group_id", "")
        return d

    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Segment":
        """从字典创建实例"""
        return cls(
            id=data.get("id", ""),
            text=data.get("text", ""),
            rel_path=data.get("rel_path", ""),
            char_count=data.get("char_count", 0),
            source_file=data.get("source_file", ""),
            prev_part_id=data.get("prev_part_id", ""),
            next_part_id=data.get("next_part_id", ""),
            group_id=data.get("group_id", ""),
            context_before=data.get("context_before", ""),
            context_after=data.get("context_after", ""),
            filter_decision=data.get("filter_decision"),
            filter_labels=data.get("filter_labels", {}),
            filter_reason=data.get("filter_reason", ""),
            process_time=data.get("process_time", 0.0),
        )


@dataclass
class FilterStats:
    """
    过滤统计信息。
    """

    total_collected: int = 0
    passed_coarse: int = 0
    dropped_coarse: int = 0
    passed_llm: int = 0
    dropped_llm: int = 0
    errors: int = 0
    from_cache: int = 0
    llm_calls: int = 0
    total_time: float = 0.0

    @property
    def total_kept(self) -> int:
        """最终保留数量"""
        return self.passed_llm

    @property
    def total_dropped(self) -> int:
        """最终丢弃数量"""
        return self.dropped_coarse + self.dropped_llm

    @property
    def keep_rate(self) -> float:
        """保留率"""
        total = self.passed_coarse  # 进入 LLM 判定的数量
        if total == 0:
            return 0.0
        return self.passed_llm / total

    def summary(self) -> str:
        """生成统计摘要"""
        lines = [
            "",
            "=" * 60,
            f"  {Constants.TOOL_NAME} v{Constants.VERSION} - 过滤完成",
            "=" * 60,
            "",
            "  📊 统计信息",
            f"     • 收集片段: {self.total_collected}",
            f"     • 粗规则通过: {self.passed_coarse} (丢弃 {self.dropped_coarse})",
            f"     • LLM 判定通过: {self.passed_llm} (丢弃 {self.dropped_llm})",
            f"     • 最终保留率: {self.keep_rate:.1%}",
            "",
            "  ⚙️ 处理详情",
            f"     • 缓存命中: {self.from_cache}",
            f"     • LLM 调用: {self.llm_calls}",
            f"     • 处理错误: {self.errors}",
            f"     • 总耗时: {self.total_time:.1f} 秒",
            "",
            "=" * 60,
        ]
        return "\n".join(lines)


@dataclass
class FilterConfig:
    """
    过滤器配置。
    """

    # 长度过滤
    min_chars: int = Constants.DEFAULT_MIN_CHARS
    max_chars: int = Constants.DEFAULT_MAX_CHARS

    # 粗规则过滤
    min_cn_ratio: float = Constants.DEFAULT_MIN_CN_RATIO
    max_weird_ratio: float = Constants.DEFAULT_MAX_WEIRD_RATIO
    require_keyword: bool = True

    # LLM 配置
    llm_provider: str = "zhipu"
    llm_model: str = "glm-4.5-flash"
    llm_temperature: float = 0.0
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_thinking_type: Optional[str] = None
    llm_timeout: float = 60.0  # 传递给硬超时的参考

    # 处理配置
    sleep_seconds: float = Constants.DEFAULT_SLEEP_SECONDS
    flush_interval: int = Constants.DEFAULT_FLUSH_INTERVAL
    max_workers: int = 1  # LLM 调用通常串行更稳定
    skip_llm: bool = False  # 跳过 LLM 判定（仅做粗规则过滤）
    min_keep_chars: int = Constants.DEFAULT_MIN_KEEP_CHARS  # 保留片段最小长度，避免上下文过碎

    def to_llm_config(self) -> Dict[str, Any]:
        """转换为 LLMFactory 配置"""
        config: Dict[str, Any] = {
            "provider": self.llm_provider,
            "model_name": self.llm_model,
            "temperature": self.llm_temperature,
        }
        # 与 llm_core 对齐：只读取环境变量中的 OPENAI_API_KEY/OPENAI_BASE_URL
        if self.llm_base_url:
            config["base_url"] = self.llm_base_url
        if self.llm_thinking_type:
            config["thinking_type"] = self.llm_thinking_type
        return config


# ==============================================================================
# 领域知识定义
# ==============================================================================


class DomainKnowledge:
    """
    水旱灾害领域知识库。

    集中管理领域相关的关键词、模式等，便于维护和扩展。
    """

    # 灾害类型关键词
    DISASTER_TYPES: ClassVar[Set[str]] = {
        "洪水",
        "洪涝",
        "暴雨",
        "山洪",
        "内涝",
        "渍涝",
        "溃堤",
        "决口",
        "干旱",
        "旱灾",
        "旱情",
        "枯水",
        "缺水",
        "水荒",
        "台风",
        "风暴潮",
        "堰塞湖",
        "泥石流",
        "滑坡",
        "崩塌",
    }

    # 防灾减灾关键词
    DISASTER_PREVENTION: ClassVar[Set[str]] = {
        "防汛",
        "抗旱",
        "防洪",
        "排涝",
        "抢险",
        "救灾",
        "减灾",
        "水利",
        "水库",
        "堤防",
        "堤坝",
        "水闸",
        "泵站",
        "涵闸",
        "蓄滞洪区",
        "分洪",
        "滞洪",
        "行洪",
        "泄洪",
        "应急响应",
        "应急预案",
        "预警",
        "警戒",
        "转移",
        "安置",
        "巡堤",
        "查险",
        "抢护",
        "封堵",
        "加固",
    }

    # 影响与损失关键词
    IMPACT_KEYWORDS: ClassVar[Set[str]] = {
        "受灾",
        "灾情",
        "险情",
        "灾害",
        "灾损",
        "淹没",
        "受淹",
        "积水",
        "浸泡",
        "倒塌",
        "损毁",
        "冲毁",
        "垮塌",
        "死亡",
        "失踪",
        "伤亡",
        "转移",
        "经济损失",
        "直接损失",
        "农作物",
        "农田",
    }

    # 长江流域地理关键词
    YANGTZE_GEOGRAPHY: ClassVar[Set[str]] = {
        # 干流
        "长江",
        "金沙江",
        "川江",
        "荆江",
        "扬子江",
        # 主要支流
        "汉江",
        "嘉陵江",
        "岷江",
        "乌江",
        "湘江",
        "赣江",
        "沅江",
        "雅砻江",
        "大渡河",
        "清江",
        "沮漳河",
        # 湖泊
        "洞庭湖",
        "鄱阳湖",
        "太湖",
        "巢湖",
        "洪湖",
        # 水利枢纽
        "三峡",
        "葛洲坝",
        "丹江口",
        "隔河岩",
        # 区域
        "长江流域",
        "长江中下游",
        "长江上游",
        "沿江",
        "江汉平原",
    }

    # 省份（长江流域相关）
    YANGTZE_PROVINCES: ClassVar[Set[str]] = {
        "四川",
        "重庆",
        "湖北",
        "湖南",
        "江西",
        "安徽",
        "江苏",
        "上海",
        "云南",
        "贵州",
        "青海",
        "西藏",
    }

    @classmethod
    def get_all_keywords(cls) -> Set[str]:
        """获取所有领域关键词"""
        return (
            cls.DISASTER_TYPES
            | cls.DISASTER_PREVENTION
            | cls.IMPACT_KEYWORDS
            | cls.YANGTZE_GEOGRAPHY
            | cls.YANGTZE_PROVINCES
        )

    @classmethod
    def get_core_keywords(cls) -> Set[str]:
        """获取核心关键词（用于严格匹配）"""
        return cls.DISASTER_TYPES | cls.DISASTER_PREVENTION | cls.YANGTZE_GEOGRAPHY

    @classmethod
    def count_keyword_hits(cls, text: str) -> Dict[str, int]:
        """
        统计各类关键词命中数量。

        Args:
            text: 待检查文本

        Returns:
            各类别命中数量的字典
        """
        return {
            "disaster_types": sum(1 for kw in cls.DISASTER_TYPES if kw in text),
            "prevention": sum(1 for kw in cls.DISASTER_PREVENTION if kw in text),
            "impact": sum(1 for kw in cls.IMPACT_KEYWORDS if kw in text),
            "geography": sum(1 for kw in cls.YANGTZE_GEOGRAPHY if kw in text),
            "provinces": sum(1 for kw in cls.YANGTZE_PROVINCES if kw in text),
        }


# ==============================================================================
# 粗规则过滤器
# ==============================================================================


class CoarseFilter:
    """
    粗规则过滤器。

    基于统计特征快速过滤明显无效的文本片段。
    """

    # 异常字符模式（非常见中英文字符）
    WEIRD_CHAR_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"[^\u4e00-\u9fff"  # 常用汉字
        r"\u3400-\u4dbf"  # 扩展 A
        r"a-zA-Z0-9"  # 英文字母和数字
        r"\s"  # 空白字符
        r"，。！？、；：\"\"''（）【】《》"  # 中文标点
        r",.!?;:'\"\(\)\[\]<>"  # 英文标点
        r"\-—…·•●○◆■□△▽"  # 常见符号
        r"①②③④⑤⑥⑦⑧⑨⑩"  # 圆圈数字
        r"°%‰℃㎡㎞"  # 单位符号
        r"／＋＝×÷"  # 数学符号
        r"]"
    )

    # 乱码特征模式
    GARBLED_PATTERNS: ClassVar[List[re.Pattern]] = [
        re.compile(r"[\ufffd]{3,}"),  # 连续替换字符
        re.compile(r"[�]{2,}"),  # 连续问号替换
        re.compile(r"(?:[^\u4e00-\u9fff\s]{10,})"),  # 连续非汉字非空白
    ]

    def __init__(self, config: FilterConfig):
        """
        初始化过滤器。

        Args:
            config: 过滤器配置
        """
        self.config = config
        self._keywords = DomainKnowledge.get_core_keywords()

    def filter(self, segment: Segment) -> Tuple[bool, str]:
        """
        对片段进行粗规则过滤。

        Args:
            segment: 待过滤片段

        Returns:
            (是否通过, 原因说明)
        """
        text = segment.text

        # 1. 长度检查
        if len(text) < self.config.min_chars:
            return False, f"text_too_short:{len(text)}<{self.config.min_chars}"

        if len(text) > self.config.max_chars:
            return False, f"text_too_long:{len(text)}>{self.config.max_chars}"

        # 2. 汉字占比检查
        cn_ratio = self._calculate_cn_ratio(text)
        if cn_ratio < self.config.min_cn_ratio:
            return False, f"cn_ratio_low:{cn_ratio:.2f}<{self.config.min_cn_ratio}"

        # 3. 异常字符检查
        weird_ratio = self._calculate_weird_ratio(text)
        if weird_ratio > self.config.max_weird_ratio:
            return (
                False,
                f"weird_ratio_high:{weird_ratio:.2f}>{self.config.max_weird_ratio}",
            )

        # 4. 乱码检查
        if self._is_garbled(text):
            return False, "garbled_detected"

        # 5. 关键词检查
        if self.config.require_keyword:
            if not self._has_domain_keyword(text):
                return False, "no_domain_keyword"

        return True, "passed"

    def _calculate_cn_ratio(self, text: str) -> float:
        """计算汉字占比"""
        if not text:
            return 0.0
        cn_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        return cn_chars / len(text)

    def _calculate_weird_ratio(self, text: str) -> float:
        """计算异常字符占比"""
        if not text:
            return 0.0
        weird_chars = self.WEIRD_CHAR_PATTERN.findall(text)
        return len(weird_chars) / len(text)

    def _is_garbled(self, text: str) -> bool:
        """检查是否为乱码文本"""
        for pattern in self.GARBLED_PATTERNS:
            if pattern.search(text):
                return True
        return False

    def _has_domain_keyword(self, text: str) -> bool:
        """检查是否包含领域关键词"""
        return any(kw in text for kw in self._keywords)


# ==============================================================================
# LLM 质量判定器
# ==============================================================================


class LLMJudge:
    """
    LLM 质量判定器。

    调用大模型对片段进行语义级别的质量和相关性判定。
    """

    # 默认系统提示词
    DEFAULT_SYSTEM_PROMPT: ClassVar[str] = """
你是一名"长江流域水旱灾害知识图谱构建助手"。你的任务是对输入的中文段落进行质量和相关性评估，判断它是否适合用于知识图谱的构建。

请严格评估，只输出 JSON，不要输出其他内容。
""".strip()

    # 默认用户提示词模板
    DEFAULT_USER_TEMPLATE: ClassVar[str] = """
请评估以下文本片段是否适合用于"长江流域水旱灾害知识图谱"的构建。

【评估维度】

is_water_disaster_domain: 是否与水旱灾害领域相关 (true/false)
is_yangtze_related: 是否与长江流域相关 (true/false)
text_quality: 文本质量 ("good"/"noisy"/"garbled")
contains_event_or_rule: 是否包含可抽取的事件或规则 (true/false)
kg_potential: KG 抽取价值 (0/1/2, 0=无价值, 2=高价值)
cleanliness: 文本清洁度 (0/1/2, 0=严重乱码, 2=规范)
【判定规则】
只有满足以下所有条件才设置 keep_for_eval=true：

is_water_disaster_domain = true
text_quality != "garbled"
cleanliness >= 1
【输出格式】
{"keep_for_eval": true/false, "reason": "简短原因", "labels": {...}}

[待评估文本]
{segment_text}
""".strip()

    def __init__(self, config: FilterConfig):
        """
        初始化 LLM 判定器。

        Args:
            config: 过滤器配置
        """
        self.config = config
        self._backend = None
        self._init_attempted = False

        # 使用项目提示词或默认提示词
        if PROMPTS_AVAILABLE and EVAL_SEGMENT_FILTER_SYSTEM:
            self._system_prompt = EVAL_SEGMENT_FILTER_SYSTEM
            self._user_template = EVAL_SEGMENT_FILTER_USER_TEMPLATE
        else:
            self._system_prompt = self.DEFAULT_SYSTEM_PROMPT
            self._user_template = self.DEFAULT_USER_TEMPLATE

    @property
    def backend(self):
        """延迟初始化 LLM 后端"""
        if self._backend is None and not self._init_attempted:
            self._init_attempted = True

            if not LLM_AVAILABLE or LLMFactory is None:
                logger.warning("LLM 模块不可用")
                return None

            try:
                llm_config = self.config.to_llm_config()
                self._backend = LLMFactory.create(llm_config)
                logger.info(
                    f"LLM 初始化成功: {self.config.llm_provider}/{self.config.llm_model}"
                )
            except Exception as e:
                logger.error(f"LLM 初始化失败: {e}")

        return self._backend

    def judge(self, segment: Segment) -> Dict[str, Any]:
        """
        对片段进行 LLM 质量判定。

        Args:
            segment: 待判定片段

        Returns:
            判定结果字典，包含 keep_for_eval, reason, labels 等字段
        """
        if self.backend is None:
            return {
                "keep_for_eval": True,  # 无 LLM 时默认保留
                "reason": "llm_unavailable",
                "labels": {},
            }

        # 构建提示词
        user_prompt = self._user_template.replace(
            "{segment_text}",
            segment.text[:3000],  # 限制长度避免超 token
        )

        try:
            response = self._call_llm_with_timeout(
                [
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )

            return self._parse_response(response)

        except RateLimitError:
            raise  # 向上传递，让调用者处理
        except AccountBlockedError:
            raise  # 向上传递
        except Exception as e:
            logger.warning(f"LLM 调用异常 ({segment.id}): {e}")
            return {
                "keep_for_eval": False,
                "reason": f"llm_error:{type(e).__name__}",
                "labels": {},
            }

    def _call_llm_with_timeout(self, messages: List[Dict[str, str]]) -> str:
        """
        在硬超时保护下调用 LLM，避免底层客户端卡死。
        """
        hard_timeout = max(int(self.config.llm_timeout if hasattr(self.config, "llm_timeout") else 60) + 30, 90)

        def _invoke() -> str:
            return self.backend.chat_messages(messages, json_mode=True)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_invoke)
            try:
                return future.result(timeout=hard_timeout)
            except FuturesTimeoutError:
                future.cancel()
                raise TimeoutError(f"LLM 调用超时 ({hard_timeout}s)") from None

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 响应"""
        if not response:
            return {
                "keep_for_eval": False,
                "reason": "llm_empty_response",
                "labels": {},
            }

        try:
            result = json.loads(response)
            if not isinstance(result, dict):
                raise ValueError("response is not a dict")

            # 确保必要字段存在
            if "keep_for_eval" not in result:
                result["keep_for_eval"] = False
            if "reason" not in result:
                result["reason"] = ""
            if "labels" not in result:
                result["labels"] = {}

            return result

        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}")
            return {
                "keep_for_eval": False,
                "reason": "json_parse_error",
                "labels": {},
                "raw_response": response[:500],
            }


# ==============================================================================
# 缓存管理器
# ==============================================================================


class FilterCache:
    """
    过滤结果缓存管理器。支持增量更新和断点续跑。
    """

    def __init__(self, cache_path: Path):
        """
        初始化缓存管理器。

        Args:
            cache_path: 缓存文件路径
        """
        self.cache_path = cache_path
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._dirty = False

        self._load()

    def _load(self) -> None:
        """加载缓存文件"""
        if not self.cache_path.exists():
            logger.debug(f"缓存文件不存在，将创建新缓存: {self.cache_path}")
            return

        try:
            with self.cache_path.open("r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        seg_id = item.get("id") or item.get("segment_id")
                        if seg_id:
                            self._cache[seg_id] = item
                    except json.JSONDecodeError:
                        logger.warning(f"缓存行 {line_num} 解析失败，跳过")

            logger.info(f"加载缓存 {len(self._cache)} 条: {self.cache_path}")

        except Exception as e:
            logger.warning(f"加载缓存失败: {e}")

    def save(self) -> None:
        """保存缓存到文件"""
        with self._lock:
            if not self._dirty:
                return

            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)

                with self.cache_path.open("w", encoding="utf-8") as f:
                    for item in self._cache.values():
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")

                self._dirty = False
                logger.debug(f"保存缓存 {len(self._cache)} 条")

            except Exception as e:
                logger.error(f"保存缓存失败: {e}")

    def get(self, segment_id: str) -> Optional[Dict[str, Any]]:
        """获取缓存的判定结果"""
        with self._lock:
            return self._cache.get(segment_id)

    def set(self, segment_id: str, decision: Dict[str, Any]) -> None:
        """设置判定结果"""
        with self._lock:
            decision["id"] = segment_id
            self._cache[segment_id] = decision
            self._dirty = True

    def contains(self, segment_id: str) -> bool:
        """检查是否存在缓存"""
        with self._lock:
            return segment_id in self._cache

    def __len__(self) -> int:
        """缓存条目数量"""
        return len(self._cache)


# ==============================================================================
# 输出管理器
# ==============================================================================


class OutputManager:
    """
    输出文件管理器。

    支持增量写入和断点续跑。
    """

    def __init__(self, output_path: Path):
        """
        初始化输出管理器。

        Args:
            output_path: 输出文件路径
        """
        self.output_path = output_path
        self._written_ids: Set[str] = set()
        self._lock = threading.Lock()
        self._file_handle = None

        self._load_existing()

    def _load_existing(self) -> None:
        """加载已写入的记录 ID"""
        if not self.output_path.exists():
            return

        try:
            with self.output_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        seg_id = item.get("id")
                        if seg_id:
                            self._written_ids.add(seg_id)
                    except json.JSONDecodeError:
                        pass

            logger.info(f"已有输出 {len(self._written_ids)} 条: {self.output_path}")

        except Exception as e:
            logger.warning(f"加载已有输出失败: {e}")

    def is_written(self, segment_id: str) -> bool:
        """检查是否已写入"""
        with self._lock:
            return segment_id in self._written_ids

    def write(self, segment: Segment) -> bool:
        """
        写入保留的片段。

        Args:
            segment: 要写入的片段

        Returns:
            是否成功写入（已存在则返回 False）
        """
        with self._lock:
            if segment.id in self._written_ids:
                return False

            try:
                self.output_path.parent.mkdir(parents=True, exist_ok=True)

                with self.output_path.open("a", encoding="utf-8") as f:
                    f.write(segment.to_json() + "\n")

                self._written_ids.add(segment.id)
                # 写出后立即刷新缓存，确保断点续跑
                try:
                    cache = getattr(segment, "_cache_ref", None)
                    if cache:
                        cache.save()
                except Exception:
                    pass
                return True

            except Exception as e:
                logger.error(f"写入失败: {e}")
                return False

    def count(self) -> int:
        """已写入数量"""
        with self._lock:
            return len(self._written_ids)


# ==============================================================================
# 上下文加载器
# ==============================================================================


class ContextLoader:
    """
    上下文加载器。
    
    根据片段的关联信息加载前后文，为 P5 抽取提供更丰富的上下文。
    """
    
    def __init__(self, corpus_root: Path, context_chars: int = 500):
        """
        初始化上下文加载器。
        
        Args:
            corpus_root: 语料根目录
            context_chars: 上下文截取字符数
        """
        self.corpus_root = corpus_root
        self.context_chars = context_chars
        self._segment_cache: Dict[str, Segment] = {}
        self._id_to_path: Dict[str, Path] = {}
        
    def build_index(self, segments: List[Segment]) -> None:
        """
        构建片段 ID 到路径的索引。
        
        Args:
            segments: 片段列表
        """
        for seg in segments:
            self._segment_cache[seg.id] = seg
            # 从 rel_path 推断完整路径
            full_path = self.corpus_root / seg.rel_path
            self._id_to_path[seg.id] = full_path
            
    def load_context(self, segment: Segment) -> Segment:
        """
        为片段加载上下文。
        
        Args:
            segment: 当前片段
            
        Returns:
            添加了上下文的片段
        """
        # 加载前文
        if segment.prev_part_id:
            prev_text = self._load_segment_text(segment.prev_part_id)
            if prev_text:
                # 取末尾 N 个字符作为前文
                segment.context_before = prev_text[-self.context_chars:]
        
        # 加载后文
        if segment.next_part_id:
            next_text = self._load_segment_text(segment.next_part_id)
            if next_text:
                # 取开头 N 个字符作为后文
                segment.context_after = next_text[:self.context_chars]
                
        return segment
    
    def _load_segment_text(self, seg_id: str) -> Optional[str]:
        """
        根据 ID 加载片段文本。
        
        Args:
            seg_id: 片段 ID
            
        Returns:
            片段文本，加载失败返回 None
        """
        # 先从缓存查找
        if seg_id in self._segment_cache:
            return self._segment_cache[seg_id].text
            
        # 尝试从文件加载
        if seg_id in self._id_to_path:
            path = self._id_to_path[seg_id]
            if path.exists():
                try:
                    return path.read_text(encoding="utf-8")
                except Exception:
                    pass
        return None
    
    def get_full_context(
        self, 
        segment: Segment, 
        include_self: bool = True
    ) -> str:
        """
        获取完整的上下文文本（前文 + 当前 + 后文）。
        
        Args:
            segment: 当前片段
            include_self: 是否包含当前片段
            
        Returns:
            拼接后的完整文本
        """
        parts = []
        
        if segment.context_before:
            parts.append(f"[前文]\n{segment.context_before}\n")
            
        if include_self:
            parts.append(f"[当前段落]\n{segment.text}\n")
            
        if segment.context_after:
            parts.append(f"[后文]\n{segment.context_after}\n")
            
        return "\n".join(parts)


# ==============================================================================
# 语料收集器
# ==============================================================================


class SegmentCollector:
    """
    语料片段收集器。

    从目录中收集和加载文本片段。
    """

    # 跳过的文件模式
    SKIP_PATTERNS: ClassVar[List[str]] = [
        "*.meta.json",
        "_*",
        ".*",
    ]

    def __init__(
        self,
        root: Path,
        min_chars: int = Constants.DEFAULT_MIN_CHARS,
        max_chars: int = Constants.DEFAULT_MAX_CHARS,
    ):
        """
        初始化收集器。

        Args:
            root: 语料根目录
            min_chars: 最小字符数
            max_chars: 最大字符数
        """
        self.root = root
        self.min_chars = min_chars
        self.max_chars = max_chars

    def collect(self, max_files: Optional[int] = None) -> List[Segment]:
        """
        收集所有符合条件的片段。

        Args:
            max_files: 最大文件数限制

        Returns:
            片段列表
        """
        segments: List[Segment] = []
        txt_files = self._find_txt_files()

        if max_files:
            txt_files = txt_files[:max_files]

        for txt_path in txt_files:
            segment = self._load_segment(txt_path)
            if segment:
                # 长度预过滤
                if self.min_chars <= segment.char_count <= self.max_chars:
                    segments.append(segment)

        logger.info(f"收集片段 {len(segments)} 条 (来自 {len(txt_files)} 个文件)")
        return segments

    def _find_txt_files(self) -> List[Path]:
        """查找所有 txt 文件"""
        files: List[Path] = []

        for txt_path in sorted(self.root.rglob("*.txt")):
            # 跳过特殊文件
            if self._should_skip(txt_path):
                continue
            files.append(txt_path)

        return files

    def _should_skip(self, path: Path) -> bool:
        """检查是否应跳过该文件"""
        name = path.name

        # 元数据文件
        if name.endswith(".meta.json"):
            return True

        # 隐藏文件或特殊文件
        if name.startswith(("_", ".")):
            return True

        return False

    def _load_segment(self, path: Path) -> Optional[Segment]:
        """加载单个片段（包含元数据）"""
        try:
            raw_text = path.read_text(encoding="utf-8").strip()
            if not raw_text:
                return None

            # 清理标题标记等特殊格式，获取纯净文本
            text = clean_special_tags(raw_text)

            # 计算相对路径
            try:
                rel_path = str(path.relative_to(self.root))
            except ValueError:
                rel_path = path.name

            # 尝试加载同名元数据
            meta_path = path.with_suffix(".meta.json")
            meta: Dict[str, Any] = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}

            # 生成 ID（优先元数据中的 md5_hash）
            seg_id = meta.get("md5_hash") or self._generate_id(rel_path, text)

            return Segment(
                id=seg_id,
                text=text,
                rel_path=rel_path,
                char_count=len(text),
                source_file=meta.get("source_file", path.name),
                prev_part_id=meta.get("prev_part_id", ""),
                next_part_id=meta.get("next_part_id", ""),
                group_id=meta.get("group_id", ""),
            )

        except Exception as e:
            logger.warning(f"加载文件失败 {path}: {e}")
            return None

    @staticmethod
    def _generate_id(rel_path: str, text: str) -> str:
        """生成片段唯一 ID"""
        content = f"{rel_path}:{text[:100]}"
        return hashlib.md5(content.encode()).hexdigest()[: Constants.SEGMENT_ID_LENGTH]


# ==============================================================================
# 核心过滤管道
# ==============================================================================


class FilterPipeline:
    """
    语料过滤管道。

    整合粗规则过滤和 LLM 判定，提供完整的过滤流程。
    """

    def __init__(
        self,
        config: FilterConfig,
        cache: FilterCache,
        output: OutputManager,
        context_loader: Optional[ContextLoader] = None,  # 新增
    ):
        """
        初始化过滤管道。

        Args:
            config: 过滤器配置
            cache: 缓存管理器
            output: 输出管理器
        """
        self.config = config
        self.cache = cache
        self.output = output

        self.coarse_filter = CoarseFilter(config)
        self.llm_judge = LLMJudge(config) if not config.skip_llm else None
        self.context_loader = context_loader  # 新增上下文加载器
        self.stats = FilterStats()

    def process_all(
        self,
        segments: List[Segment],
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> List[Segment]:
        """
        处理所有片段。

        Args:
            segments: 待处理片段列表
            progress_callback: 进度回调函数 (current, total, message)

        Returns:
            保留的片段列表
        """
        start_time = time.time()
        self.stats.total_collected = len(segments)
        kept: List[Segment] = []
        pending: Optional[Segment] = None  # 用于合并过短片段
        processed_count = 0

        try:
            for i, segment in enumerate(segments):
                # 进度回调
                if progress_callback:
                    progress_callback(i + 1, len(segments), segment.id[:8])

                # 处理单个片段
                result = self._process_one(segment)
                processed_count += 1

                # 记录保留的片段
                if result:
                    # 补充上下文
                    if self.context_loader:
                        result = self.context_loader.load_context(result)

                    # 若启用最小长度要求，尝试与上一段合并，避免上下文过碎
                    if (
                        self.config.min_keep_chars
                        and pending is not None
                        and pending.rel_path == result.rel_path
                        and len(pending.text) + len(result.text) < self.config.min_keep_chars
                    ):
                        pending.text = pending.text.rstrip() + "\n\n" + result.text.strip()
                    else:
                        if pending:
                            kept.append(pending)
                            self.output.write(pending)
                        pending = result

                # 定期保存缓存
                if processed_count % self.config.flush_interval == 0:
                    self.cache.save()
                    logger.debug(
                        f"进度: {processed_count}/{len(segments)}, "
                        f"保留: {len(kept) + (1 if pending else 0)}"
                    )

                # 休眠控制
                if self.config.sleep_seconds > 0:
                    time.sleep(self.config.sleep_seconds)

        except (RateLimitError, AccountBlockedError) as e:
            logger.warning(f"LLM 限流/封禁，保存进度后退出: {e}")
            self.cache.save()
            raise

        except KeyboardInterrupt:
            logger.warning("用户中断，保存进度...")
            self.cache.save()
            raise

        finally:
            # 收尾写入最后 pending
            if pending:
                kept.append(pending)
                self.output.write(pending)
            # 确保保存
            self.cache.save()
            self.stats.total_time = time.time() - start_time

        return kept

    def _process_one(self, segment: Segment) -> Optional[Segment]:
        """
        处理单个片段。

        Args:
            segment: 待处理片段

        Returns:
            保留则返回更新后的片段，否则返回 None
        """
        start_time = time.time()

        # 检查是否已写入输出
        if self.output.is_written(segment.id):
            self.stats.from_cache += 1
            self.stats.passed_llm += 1
            self.stats.passed_coarse += 1
            return None  # 已经写入，不重复返回

        # 阶段 1: 粗规则过滤
        passed, reason = self.coarse_filter.filter(segment)
        if not passed:
            segment.filter_decision = FilterDecision.DROP_COARSE.value
            segment.filter_reason = reason
            self.stats.dropped_coarse += 1
            logger.debug(f"[COARSE] DROP {segment.id}: {reason}")
            return None

        self.stats.passed_coarse += 1

        # 阶段 2: LLM 判定
        if self.config.skip_llm:
            # 跳过 LLM，直接保留
            segment.filter_decision = FilterDecision.KEEP.value
            segment.filter_reason = "coarse_only"
            segment.process_time = time.time() - start_time
            self.stats.passed_llm += 1
            return segment

        # 检查缓存
        cached = self.cache.get(segment.id)
        if cached is not None:
            self.stats.from_cache += 1
            keep = self._apply_cached_decision(segment, cached)
            if keep:
                return segment
            return None

        # 调用 LLM
        self.stats.llm_calls += 1
        if self.llm_judge is None:
            decision = {
                "keep_for_eval": True,
                "reason": "llm_skipped",
                "labels": {},
            }
        else:
            decision = self.llm_judge.judge(segment)

        # 保存到缓存
        self.cache.set(segment.id, decision)
        # 给 OutputManager 的写入提供 cache 引用（便于写入时同步 flush）
        segment._cache_ref = self.cache  # type: ignore[attr-defined]

        # 应用决策
        keep = self._apply_decision(segment, decision)
        segment.process_time = time.time() - start_time

        if keep:
            return segment

        return None

    def _apply_cached_decision(
        self,
        segment: Segment,
        cached: Dict[str, Any],
    ) -> bool:
        """应用缓存的决策"""
        keep = self._check_keep(cached)

        segment.filter_labels = cached.get("labels", {})
        segment.filter_reason = cached.get("reason", "cached")

        if keep:
            segment.filter_decision = FilterDecision.KEEP.value
            self.stats.passed_llm += 1
        else:
            segment.filter_decision = FilterDecision.DROP_LLM.value
            self.stats.dropped_llm += 1

        return keep

    def _apply_decision(
        self,
        segment: Segment,
        decision: Dict[str, Any],
    ) -> bool:
        """应用 LLM 决策"""
        keep = self._check_keep(decision)

        segment.filter_labels = decision.get("labels", {})
        segment.filter_reason = decision.get("reason", "")

        if keep:
            segment.filter_decision = FilterDecision.KEEP.value
            self.stats.passed_llm += 1
            logger.debug(f"[LLM] KEEP {segment.id}")
        else:
            segment.filter_decision = FilterDecision.DROP_LLM.value
            self.stats.dropped_llm += 1
            logger.debug(f"[LLM] DROP {segment.id}: {segment.filter_reason}")

        return keep

    def _check_keep(self, decision: Dict[str, Any]) -> bool:
        """
        检查是否应保留。

        轻量过滤规则（相对宽松）：
        - is_water_disaster_domain = true
        - text_quality != "garbled"
        - cleanliness >= 1（如果有该字段）
        """
        # 直接检查 keep_for_eval
        if decision.get("keep_for_eval") is True:
            return True
        if decision.get("keep_for_eval") is False:
            return False

        # 回退到标签检查
        labels = decision.get("labels", {})

        # 必须是水旱灾害领域
        if not labels.get("is_water_disaster_domain"):
            return False

        # 不能是乱码
        if labels.get("text_quality") == "garbled":
            return False

        # 清洁度检查
        cleanliness = labels.get("cleanliness")
        if cleanliness is not None:
            try:
                if int(cleanliness) < 1:
                    return False
            except (ValueError, TypeError):
                pass

        return True

    def _write_kept(self, segment: Segment) -> None:
        """写入保留的片段，包含上下文信息"""
        # 加载上下文
        if self.context_loader:
            segment = self.context_loader.load_context(segment)

        if self.output.write(segment):
            logger.debug(f"[OUTPUT] {segment.id}")


# ==============================================================================
# 配置加载器
# ==============================================================================


class ConfigLoader:
    """配置加载器"""

    @staticmethod
    def load_from_yaml(path: Path) -> Dict[str, Any]:
        """加载 YAML 配置文件"""
        if not path.exists():
            return {}

        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"加载配置文件失败: {e}")
            return {}

    @classmethod
    def build_config(cls, args: argparse.Namespace) -> FilterConfig:
        """
        从命令行参数和配置文件构建配置。

        优先级: 命令行 > 环境变量 > 配置文件 > 默认值
        """
        # 加载配置文件
        cfg: Dict[str, Any] = {}
        if args.cfg:
            cfg = cls.load_from_yaml(Path(args.cfg))

        cfg_filter = cfg.get("filtering", {}).get("light", {})
        cfg_llm = cfg.get("llm", {})

        def pick(*vals, default=None):
            for v in vals:
                if v not in (None, ""):
                    return v
            return default

        return FilterConfig(
            # 长度过滤
            min_chars=int(
                pick(
                    args.min_chars,
                    cfg_filter.get("min_chars"),
                    Constants.DEFAULT_MIN_CHARS,
                )
            ),
            max_chars=int(
                pick(
                    args.max_chars,
                    cfg_filter.get("max_chars"),
                    Constants.DEFAULT_MAX_CHARS,
                )
            ),
            # 粗规则过滤
            min_cn_ratio=float(
                pick(
                    args.min_cn_ratio,
                    cfg_filter.get("min_cn_ratio"),
                    Constants.DEFAULT_MIN_CN_RATIO,
                )
            ),
            max_weird_ratio=float(
                pick(
                    args.max_weird_ratio,
                    cfg_filter.get("max_weird_ratio"),
                    Constants.DEFAULT_MAX_WEIRD_RATIO,
                )
            ),
            require_keyword=not args.no_keyword_filter,
            # LLM 配置
            llm_provider=pick(
                args.llm_provider,
                os.getenv("LLM_PROVIDER"),
                cfg_llm.get("provider"),
                "zhipu",
            ),
            llm_model=pick(
                args.llm_model,
                os.getenv("LLM_MODEL_NAME"),
                cfg_llm.get("model_name"),
                "glm-4.5-flash",
            ),
            llm_temperature=float(
                pick(
                    args.llm_temperature,
                    os.getenv("LLM_TEMPERATURE"),
                    cfg_llm.get("temperature"),
                    0.0,
                )
            ),
            llm_api_key=pick(
                args.llm_api_key,
                os.getenv("LLM_API_KEY"),
                None,  # 不从配置文件读取 key
            ),
            llm_base_url=pick(
                cfg_llm.get("base_url"),
                os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL"),
            ),
            llm_thinking_type=pick(
                args.llm_thinking,
                os.getenv("LLM_THINKING_TYPE"),
                cfg_llm.get("thinking_type"),
            ),
            llm_timeout=float(
                pick(
                    cfg_llm.get("timeout"),
                    60.0,
                )
            ),
            # 处理配置
            sleep_seconds=float(pick(args.sleep_secs, 0.0)),
            flush_interval=int(
                pick(args.flush_every, Constants.DEFAULT_FLUSH_INTERVAL)
            ),
            skip_llm=args.skip_llm if hasattr(args, "skip_llm") else False,
        )


# ==============================================================================
# 命令行接口
# ==============================================================================


def create_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog="filter_corpus_light",
        description=f"{Constants.TOOL_NAME} v{Constants.VERSION} - 快速剔除无效语料",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""

使用示例
基础用法
python tools/filter_corpus_light.py \
  --root data/corpus_for_kg/handled_all_kg_corpus \
  --out data/corpus_for_kg/p5_corpus_filtered/light_pool.jsonl

使用特定 LLM
python tools/filter_corpus_light.py \
  --root ./handled_corpus \
  --llm-provider zhipu --llm-model "GLM-4.5-Air"

仅粗规则过滤（不调用 LLM）
python tools/filter_corpus_light.py \
  --root ./handled_corpus \
  --skip-llm

测试模式
python tools/filter_corpus_light.py \
  --root ./handled_corpus \
  --max-files 10 --verbose
""",
    )

    # 输入输出
    io_group = parser.add_argument_group("输入输出")
    io_group.add_argument(
        "--root",
        "-r",
        required=True,
        help="源语料根目录",
    )
    io_group.add_argument(
        "--out",
        "-o",
        default="data/corpus_for_kg/p5_corpus_filtered/light_pool.jsonl",
        help="过滤后输出文件路径",
    )
    io_group.add_argument(
        "--filter-cache",
        default=None,
        help="LLM 过滤缓存文件路径（默认与输出同目录）",
    )

    # 过滤参数
    filter_group = parser.add_argument_group("过滤参数")
    filter_group.add_argument(
        "--min-chars",
        type=int,
        default=None,
        help=f"最小字符数（默认: {Constants.DEFAULT_MIN_CHARS}）",
    )
    filter_group.add_argument(
        "--max-chars",
        type=int,
        default=None,
        help=f"最大字符数（默认: {Constants.DEFAULT_MAX_CHARS}）",
    )
    filter_group.add_argument(
        "--min-cn-ratio",
        type=float,
        default=None,
        help=f"最小汉字占比（默认: {Constants.DEFAULT_MIN_CN_RATIO}）",
    )
    filter_group.add_argument(
        "--max-weird-ratio",
        type=float,
        default=None,
        help=f"最大异常字符比例（默认: {Constants.DEFAULT_MAX_WEIRD_RATIO}）",
    )
    filter_group.add_argument(
        "--no-keyword-filter",
        action="store_true",
        help="不强制要求命中领域关键词",
    )

    # LLM 参数
    llm_group = parser.add_argument_group("LLM 参数")
    llm_group.add_argument(
        "--llm-provider",
        default=None,
        help="LLM 提供商 (zhipu/openai/gemini)",
    )
    llm_group.add_argument(
        "--llm-model",
        default=None,
        help="LLM 模型名称",
    )
    llm_group.add_argument(
        "--llm-temperature",
        type=float,
        default=None,
        help="LLM 温度参数",
    )
    llm_group.add_argument(
        "--llm-api-key",
        default=None,
        help="LLM API Key（推荐使用环境变量）",
    )
    llm_group.add_argument(
        "--llm-thinking",
        choices=["enabled", "disabled"],
        default=None,
        help="LLM 深度思考模式（仅 zhipu）",
    )
    llm_group.add_argument(
        "--skip-llm",
        action="store_true",
        help="跳过 LLM 判定，仅做粗规则过滤",
    )

    # 运行参数
    run_group = parser.add_argument_group("运行参数")
    run_group.add_argument(
        "--cfg",
        default="configs/cfg.yaml",
        help="配置文件路径",
    )
    run_group.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="最多处理文件数（用于测试）",
    )
    run_group.add_argument(
        "--sleep-secs",
        type=float,
        default=0.0,
        help="每次 LLM 调用后休眠秒数",
    )
    run_group.add_argument(
        "--flush-every",
        type=int,
        default=Constants.DEFAULT_FLUSH_INTERVAL,
        help="缓存刷新间隔",
    )
    run_group.add_argument(
        "--refilter",
        action="store_true",
        help="忽略缓存，强制重新过滤",
    )
    run_group.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="显示详细日志",
    )
    run_group.add_argument(
        "--log-file",
        default=None,
        help="日志文件路径",
    )

    return parser


def print_banner(
    config: FilterConfig,
    segment_count: int,
    root: Path,
    out: Path,
) -> None:
    """打印启动横幅"""
    banner = f"""
{'=' * 70}
{Constants.TOOL_NAME} v{Constants.VERSION}
{'=' * 70}

📂 源目录: {root}
📄 输出文件: {out}
📊 待处理片段: {segment_count} 个

⚙️ 过滤参数:
• 长度范围: {config.min_chars} - {config.max_chars} 字符
• 汉字占比: >= {config.min_cn_ratio:.0%}
• 关键词过滤: {'是' if config.require_keyword else '否'}
"""
    if config.skip_llm:
        banner += "• LLM 判定: 跳过（仅粗规则）\n"
    else:
        banner += f"• LLM: {config.llm_provider}/{config.llm_model}\n"

    banner += f"\n{'=' * 70}"
    print(banner)


def main() -> int:
    """主函数"""
    parser = create_argument_parser()
    args = parser.parse_args()

    # 配置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_file = Path(args.log_file) if args.log_file else None
    global logger
    logger = LoggerFactory.get_logger(level=log_level, log_file=log_file)

    try:
        # 验证输入
        root = Path(args.root)
        if not root.exists():
            logger.error(f"源目录不存在: {root}")
            return 1

        out_path = Path(args.out)
        cache_path = (
            Path(args.filter_cache)
            if args.filter_cache
            else out_path.parent / "_light_filter_cache.jsonl"
        )

        # 加载配置
        config = ConfigLoader.build_config(args)

        # 收集片段
        logger.info(f"扫描源目录: {root}")
        collector = SegmentCollector(
            root,
            min_chars=config.min_chars,
            max_chars=config.max_chars,
        )
        segments = collector.collect(max_files=args.max_files)

        if not segments:
            logger.warning("未找到符合条件的片段")
            return 0

        # 打印启动信息
        print_banner(config, len(segments), root, out_path)

        # 初始化组件
        if args.refilter:
            # 强制重新过滤：删除缓存
            if cache_path.exists():
                cache_path.unlink()
                logger.info("已删除旧缓存，强制重新过滤")

        cache = FilterCache(cache_path)
        output = OutputManager(out_path)
        # 构建上下文加载器，便于后续拼接前后文
        context_loader = ContextLoader(root)
        context_loader.build_index(segments)
        pipeline = FilterPipeline(config, cache, output, context_loader=context_loader)

        # 进度回调
        def progress_callback(current: int, total: int, seg_id: str) -> None:
            percent = (current / total) * 100
            print(
                f"\r⏳ [{current}/{total}] {percent:5.1f}% | {seg_id} | 保留: {output.count()}",
                end="",
                flush=True,
            )

        # 执行过滤
        _ = pipeline.process_all(segments, progress_callback)

        # 清除进度条
        print()

        # 打印统计
        print(pipeline.stats.summary())

        return 0

    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断，进度已保存")
        return 130

    except (RateLimitError, AccountBlockedError) as e:
        logger.error(f"LLM 限流/封禁: {e}")
        logger.info("进度已保存，可稍后重试继续")
        return 2

    except Exception as e:
        logger.exception(f"处理出错: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
