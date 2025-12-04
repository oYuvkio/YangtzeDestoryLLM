#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
P4 语料批量清洗工具 v4.0
================================================================================

专为「长江流域水旱灾害知识图谱」项目设计的高性能语料处理管线。

核心功能
--------
1. **多格式文档解析**
   - PDF：支持 PyPDF2（速度快）和 pdfplumber（表格识别强）双引擎
   - TXT：自动编码检测（UTF-8/GBK/GB2312/GB18030 等）
   - 可扩展架构：易于添加 DOCX、HTML 等新格式支持

2. **智能文本清洗**
   - 页眉页脚识别与移除（支持中英文多种格式）
   - 目录区域检测与跳过（状态机实现）
   - 参考文献截断（可配置）
   - 噪声模式过滤（URL、邮箱、基金信息等）
   - 全角/半角规范化

3. **语义感知切分**
   - 章节优先：识别多级标题结构，保持语义完整
   - 段落合并：智能合并短段落，避免碎片化
   - 长度控制：硬切超长文本时优先在句子边界切分
   - LLM 辅助（可选）：利用大模型进行语义理解和质量筛选

4. **元数据管理**
   - 自动提取：年份、省份、河流、来源类型
   - Sidecar 文件：每个分片附带 .meta.json 元数据
   - 索引生成：批量处理后生成完整索引文件

5. **工程特性**
   - 并行处理：多线程加速批量任务
   - 断点续跑：缓存机制支持任务中断后恢复
   - 进度追踪：实时显示处理进度
   - 优雅降级：LLM 调用失败时自动回退到规则切分

设计原则
--------
- **单一职责**：每个类只做一件事，职责边界清晰
- **开闭原则**：对扩展开放，对修改封闭
- **依赖注入**：通过构造函数注入依赖，便于测试和替换
- **防御性编程**：完善的输入校验和异常处理
- **可观测性**：详细的日志输出，便于问题定位

使用示例
--------
```bash
# 基础用法：处理目录下所有 PDF/TXT 文件
python3 tools/corpus_cleaner.py --input ./pdfs/ --output-dir ./corpus/

# 自定义切分参数
python3 tools/corpus_cleaner.py --input paper.pdf --min-chars 1000 --max-chars 3000

# 使用 pdfplumber 引擎，移除参考文献
python3 tools/corpus_cleaner.py --input ./docs/ --remove-references --pdf-engine pdfplumber

# 启用 LLM 语义切分（需要配额）
python3 tools/corpus_cleaner.py --input ./docs/ --llm-split \\
    --llm-provider zhipu --llm-model "GLM-4.5-Air"

# 试运行模式：只显示将要处理的文件
python3 tools/corpus_cleaner.py --input ./docs/ --dry-run
配置优先级
命令行参数 > 环境变量 > 配置文件 (cfg.yaml) > 默认值
环境变量
● LLM_PROVIDER: LLM 提供商 (zhipu/openai/gemini)
● LLM_MODEL_NAME: 模型名称
● LLM_API_KEY: API 密钥
● LLM_BASE_URL: 自定义 API 地址
● LLM_TEMPERATURE: 温度参数
作者: KG Team
版本: 4.0.0
许可: MIT
"""
from __future__ import annotations

# ==============================================================================
# 标准库导入
# ==============================================================================
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
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from functools import lru_cache, wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Final,
    Generator,
    Generic,
    Iterable,
    Iterator,
    List,
    Literal,
    Mapping,
    NamedTuple,
    Optional,
    Protocol,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
    runtime_checkable,
)
from contextlib import contextmanager
from io import StringIO

# ==============================================================================
# 第三方库导入（延迟导入以提高启动速度）
# ==============================================================================
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    yaml = None  # type: ignore
    YAML_AVAILABLE = False

# ==============================================================================
# 项目路径配置
# ==============================================================================
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ==============================================================================
# 项目模块延迟导入（避免循环依赖）
# ==============================================================================
# 使用延迟导入模式：模块级变量初始化为 None，在实际使用时才导入
_LLMFactory: Optional[type] = None


# 定义内部 LLM 错误类（确保不会被其他异常意外匹配）
class _InternalRateLimitError(Exception):
    """
    内部限流错误标记。
    用于明确标识 LLM API 返回的 429 错误，不会被其他异常误匹配。
    """
    pass


class _InternalAccountBlockedError(Exception):
    """
    内部账号封禁错误标记。
    用于明确标识 LLM API 返回的 401 错误，不会被其他异常误匹配。
    """
    pass


# 外部 LLM 模块的异常类引用（延迟导入后赋值）
_ExternalRateLimitError: Optional[Type[Exception]] = None
_ExternalAccountBlockedError: Optional[Type[Exception]] = None


def _ensure_llm_imports() -> None:
    """
    延迟导入 LLM 相关模块。

    这种模式的好处：
    1. 避免循环依赖
    2. 加快脚本启动速度（只有实际使用 LLM 功能时才导入）
    3. 在 LLM 模块不可用时仍能运行基础功能
    """
    global _LLMFactory, _ExternalRateLimitError, _ExternalAccountBlockedError

    if _LLMFactory is not None:
        return  # 已经导入过

    try:
        from kg.llm_core import LLMFactory, RateLimitError, AccountBlockedError
        _LLMFactory = LLMFactory
        _ExternalRateLimitError = RateLimitError
        _ExternalAccountBlockedError = AccountBlockedError
    except ImportError as e:
        logging.getLogger(__name__).warning(
            f"无法导入 LLM 模块，LLM 相关功能将不可用: {e}"
        )


def _is_rate_limit_error(exc: Exception) -> bool:
    """
    判断是否为限流错误 (429)。
    支持内部异常和外部 LLM 模块异常。
    """
    if isinstance(exc, _InternalRateLimitError):
        return True
    if _ExternalRateLimitError is not None and isinstance(exc, _ExternalRateLimitError):
        return True
    return False


def _is_account_blocked_error(exc: Exception) -> bool:
    """
    判断是否为账号封禁错误 (401)。
    支持内部异常和外部 LLM 模块异常。
    """
    if isinstance(exc, _InternalAccountBlockedError):
        return True
    if _ExternalAccountBlockedError is not None and isinstance(exc, _ExternalAccountBlockedError):
        return True
    return False


def _is_llm_critical_error(exc: Exception) -> bool:
    """判断是否为需要立即停止的 LLM 严重错误（429/401）"""
    return _is_rate_limit_error(exc) or _is_account_blocked_error(exc)


# ==============================================================================
# 类型变量定义
# ==============================================================================
T = TypeVar("T")
ConfigT = TypeVar("ConfigT", bound="BaseConfig")

# ==============================================================================
# 常量定义
# ==============================================================================


class Constants:
    """
    全局常量定义。

    将所有魔法数字和字符串集中管理，便于维护和修改。
    """

    # 版本信息
    VERSION: Final[str] = "4.0.0"
    TOOL_NAME: Final[str] = "P4 语料批量清洗工具"

    # 文件处理
    SUPPORTED_EXTENSIONS: Final[frozenset] = frozenset({".pdf", ".txt"})
    DEFAULT_ENCODINGS: Final[tuple] = (
        "utf-8", "gbk", "gb2312", "gb18030",
        "utf-16", "utf-16-le", "utf-16-be", "latin-1"
    )

    # 文本处理默认值
    DEFAULT_MIN_CHARS: Final[int] = 800
    DEFAULT_MAX_CHARS: Final[int] = 2500
    MIN_VALID_TEXT_LENGTH: Final[int] = 100
    MAX_LLM_INPUT_CHARS: Final[int] = 8000  # 单次 LLM 调用的最大输入字符数
    LLM_CHUNK_SIZE: Final[int] = 6000  # 分块大小（比 MAX 小一些，留给 prompt 空间）
    LLM_CHUNK_OVERLAP: Final[int] = 300  # 分块重叠字符数，保持语义连续性

    # 并行处理
    DEFAULT_MAX_WORKERS: Final[int] = 4

    # 缓存
    DEFAULT_CACHE_SAVE_INTERVAL: Final[int] = 10  # 每处理 10 个文件自动保存
    CACHE_FILE_NAME: Final[str] = ".corpus_cleaner_cache.jsonl"

    # 重试机制
    DEFAULT_MAX_RETRIES: Final[int] = 3
    DEFAULT_RETRY_DELAY: Final[float] = 2.0
    MAX_RETRY_DELAY: Final[float] = 60.0
    RETRY_BACKOFF_FACTOR: Final[float] = 2.0

    # MD5 哈希
    MD5_HASH_LENGTH: Final[int] = 12

    # 目录检测
    MAX_TOC_LINES: Final[int] = 100

    # 句子边界搜索范围
    SENTENCE_BOUNDARY_SEARCH_RANGE: Final[int] = 100

    # 日志滚动配置
    MAX_LOG_BYTES: Final[int] = 500 * 1024 * 1024  # 单个日志最大 500MB
    LOG_BACKUP_COUNT: Final[int] = 5  # 保留的历史日志文件数

# ==============================================================================
# 日志系统
# ==============================================================================


class LoggerFactory:
    """
    日志工厂类。

    提供统一的日志配置和管理，支持：
    - 控制台输出（带颜色）
    - 文件输出（可选）
    - 日志级别控制
    - 线程安全
    """

    _lock: ClassVar[threading.Lock] = threading.Lock()
    _initialized: ClassVar[bool] = False
    _logger: ClassVar[Optional[logging.Logger]] = None

    # ANSI 颜色代码
    COLORS: ClassVar[Dict[str, str]] = {
        "DEBUG": "\033[36m",     # 青色
        "INFO": "\033[32m",      # 绿色
        "WARNING": "\033[33m",   # 黄色
        "ERROR": "\033[31m",     # 红色
        "CRITICAL": "\033[35m",  # 紫色
        "RESET": "\033[0m",      # 重置
    }

    @classmethod
    def get_logger(
        cls,
        name: str = "corpus_cleaner",
        level: int = logging.INFO,
        log_file: Optional[Path] = None,
        use_colors: bool = True,
    ) -> logging.Logger:
        """
        获取或创建日志器。

        使用单例模式确保全局只有一个日志器实例。

        Args:
            name: 日志器名称
            level: 日志级别
            log_file: 可选的日志文件路径
            use_colors: 是否在控制台输出中使用颜色

        Returns:
            配置好的 Logger 实例
        """
        with cls._lock:
            if cls._initialized and cls._logger is not None:
                # 更新日志级别（允许动态调整）
                cls._logger.setLevel(level)
                
                # 如果有新的 log_file，检查是否已添加文件处理器
                if log_file:
                    has_file_handler = any(
                        isinstance(h, (logging.FileHandler, RotatingFileHandler)) 
                        for h in cls._logger.handlers
                    )
                    if not has_file_handler:
                        log_file.parent.mkdir(parents=True, exist_ok=True)
                        file_formatter = cls._create_formatter(use_colors=False)
                        file_handler = RotatingFileHandler(
                            log_file,
                            encoding="utf-8",
                            mode="a",
                            maxBytes=Constants.MAX_LOG_BYTES,
                            backupCount=Constants.LOG_BACKUP_COUNT,
                        )
                        file_handler.setFormatter(file_formatter)
                        file_handler.setLevel(level)
                        cls._logger.addHandler(file_handler)
                
                return cls._logger

            logger = logging.getLogger(name)
            logger.setLevel(level)
            logger.handlers.clear()  # 清除已有处理器

            # 创建格式化器
            console_formatter = cls._create_formatter(use_colors)
            file_formatter = cls._create_formatter(use_colors=False)

            # 控制台处理器
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(console_formatter)
            console_handler.setLevel(level)
            logger.addHandler(console_handler)

            # 文件处理器（可选）
            if log_file:
                log_file.parent.mkdir(parents=True, exist_ok=True)
                file_handler = RotatingFileHandler(
                    log_file,
                    encoding="utf-8",
                    mode="a",
                    maxBytes=Constants.MAX_LOG_BYTES,
                    backupCount=Constants.LOG_BACKUP_COUNT,
                )
                file_handler.setFormatter(file_formatter)
                file_handler.setLevel(level)
                logger.addHandler(file_handler)

            # 防止日志传播到根日志器
            logger.propagate = False

            cls._initialized = True
            cls._logger = logger

            return logger

    @classmethod
    def _create_formatter(cls, use_colors: bool = True) -> logging.Formatter:
        """创建日志格式化器"""
        if use_colors and sys.stdout.isatty():
            # 带颜色的格式
            format_str = (
                "%(asctime)s | %(levelname_colored)s | "
                "%(name)s | %(message)s"
            )

            class ColoredFormatter(logging.Formatter):
                def format(self, record: logging.LogRecord) -> str:
                    # 添加颜色
                    color = cls.COLORS.get(record.levelname, "")
                    reset = cls.COLORS["RESET"]
                    record.levelname_colored = f"{color}{record.levelname:<7}{reset}"
                    return super().format(record)

            return ColoredFormatter(format_str, datefmt="%Y-%m-%d %H:%M:%S")
        else:
            # 无颜色的格式
            format_str = (
                "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
            )
            return logging.Formatter(format_str, datefmt="%Y-%m-%d %H:%M:%S")

    @classmethod
    def reset(cls) -> None:
        """重置日志器（主要用于测试）"""
        with cls._lock:
            if cls._logger is not None:
                cls._logger.handlers.clear()
            cls._initialized = False
            cls._logger = None


# 创建默认日志器
logger = LoggerFactory.get_logger()

# ==============================================================================
# 异常定义
# ==============================================================================


class CorpusCleanerError(Exception):
    """语料清洗器基础异常"""
    pass


class ExtractionError(CorpusCleanerError):
    """文本提取失败"""
    pass


class CleaningError(CorpusCleanerError):
    """文本清洗失败"""
    pass


class SplittingError(CorpusCleanerError):
    """文本切分失败"""
    pass


class ConfigurationError(CorpusCleanerError):
    """配置错误"""
    pass


class UnsupportedFileTypeError(CorpusCleanerError):
    """不支持的文件类型"""

    def __init__(self, file_path: Path, message: Optional[str] = None):
        self.file_path = file_path
        self.message = message or f"不支持的文件类型: {file_path.suffix}"
        super().__init__(self.message)


class LLMError(CorpusCleanerError):
    """LLM 调用相关错误"""
    pass


class NetworkError(CorpusCleanerError):
    """
    网络相关错误。
    
    包括但不限于：
    - 网络超时
    - 连接失败
    - DNS 解析错误
    """
    pass


class CacheError(CorpusCleanerError):
    """缓存操作错误（读取/写入失败）"""
    pass


class FileSystemError(CorpusCleanerError):
    """
    文件系统操作错误。
    
    包括：
    - 磁盘空间不足
    - 文件权限问题
    - I/O 错误
    """
    pass

# ==============================================================================
# 枚举类型定义
# ==============================================================================


class FileType(Enum):
    """
    支持的文件类型枚举。

    使用枚举而非字符串可以：
    1. 提供类型安全
    2. 避免拼写错误
    3. 便于 IDE 自动补全
    """
    PDF = auto()
    TXT = auto()
    CAJ = auto()
    DOC = auto()
    DOCX = auto()
    HTML = auto()
    MARKDOWN = auto()
    UNKNOWN = auto()

    @classmethod
    def from_suffix(cls, suffix: str) -> "FileType":
        """
        根据文件后缀返回对应的文件类型。

        Args:
            suffix: 文件后缀（如 ".pdf"）

        Returns:
            对应的 FileType 枚举值
        """
        suffix_lower = suffix.lower()
        mapping: Dict[str, FileType] = {
            ".pdf": cls.PDF,
            ".txt": cls.TXT,
            ".text": cls.TXT,
            ".caj": cls.CAJ,
            ".doc": cls.DOC,
            ".docx": cls.DOCX,
            ".html": cls.HTML,
            ".htm": cls.HTML,
            ".md": cls.MARKDOWN,
            ".markdown": cls.MARKDOWN,
        }
        return mapping.get(suffix_lower, cls.UNKNOWN)

    @property
    def is_supported(self) -> bool:
        """检查文件类型是否被支持"""
        return self in {FileType.PDF, FileType.TXT}

    @property
    def description(self) -> str:
        """获取文件类型的中文描述"""
        descriptions = {
            FileType.PDF: "PDF 文档",
            FileType.TXT: "纯文本文件",
            FileType.CAJ: "CAJ 文件（需转换）",
            FileType.DOC: "Word 文档（需转换）",
            FileType.DOCX: "Word 文档（需转换）",
            FileType.HTML: "HTML 网页",
            FileType.MARKDOWN: "Markdown 文档",
            FileType.UNKNOWN: "未知格式",
        }
        return descriptions.get(self, "未知格式")


class TextQuality(Enum):
    """
    文本质量等级。

    用于评估和过滤语料质量。
    """
    EXCELLENT = "excellent"  # 优秀：格式规范，内容完整
    GOOD = "good"            # 良好：基本无噪声
    ACCEPTABLE = "acceptable"  # 可接受：有少量噪声但可读
    NOISY = "noisy"          # 有噪声：噪声较多但核心内容可识别
    GARBLED = "garbled"      # 乱码：严重损坏，不可用

    @property
    def is_usable(self) -> bool:
        """判断该质量等级的文本是否可用"""
        return self in {
            TextQuality.EXCELLENT,
            TextQuality.GOOD,
            TextQuality.ACCEPTABLE,
            TextQuality.NOISY
        }

    @property
    def score(self) -> int:
        """返回质量评分（0-4）"""
        scores = {
            TextQuality.EXCELLENT: 4,
            TextQuality.GOOD: 3,
            TextQuality.ACCEPTABLE: 2,
            TextQuality.NOISY: 1,
            TextQuality.GARBLED: 0,
        }
        return scores.get(self, 0)


class SourceType(Enum):
    """
    语料来源类型。

    用于分类和追踪语料来源，便于后续分析和质量控制。
    """
    LAW_REGULATION = "law_regulation"      # 法律法规
    EMERGENCY_PLAN = "emergency_plan"      # 应急预案
    GAZETTE_YEARBOOK = "gazette_yearbook"  # 公报、年鉴
    TECHNICAL_REPORT = "technical_report"  # 技术报告
    ACADEMIC_PAPER = "academic_paper"      # 学术论文
    NEWS_ARTICLE = "news_article"          # 新闻报道
    POPULAR_SCIENCE = "popular_science"    # 科普文章
    GOVERNMENT_DOC = "government_doc"      # 政府文件
    OTHER = "other"                        # 其他

    @property
    def description(self) -> str:
        """获取来源类型的中文描述"""
        descriptions = {
            SourceType.LAW_REGULATION: "法律法规",
            SourceType.EMERGENCY_PLAN: "应急预案",
            SourceType.GAZETTE_YEARBOOK: "公报年鉴",
            SourceType.TECHNICAL_REPORT: "技术报告",
            SourceType.ACADEMIC_PAPER: "学术论文",
            SourceType.NEWS_ARTICLE: "新闻报道",
            SourceType.POPULAR_SCIENCE: "科普文章",
            SourceType.GOVERNMENT_DOC: "政府文件",
            SourceType.OTHER: "其他",
        }
        return descriptions.get(self, "其他")


class ProcessingStatus(Enum):
    """处理状态枚举"""
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"
    PENDING = "pending"

# ==============================================================================
# 数据类定义
# ==============================================================================


@dataclass(frozen=True)
class TextStats:
    """
    文本统计信息（不可变）。

    使用 frozen=True 使其成为不可变对象，可以用作字典键。
    """
    total_chars: int
    chinese_chars: int
    english_chars: int
    digit_chars: int
    whitespace_chars: int
    punctuation_chars: int
    other_chars: int

    @property
    def chinese_ratio(self) -> float:
        """汉字占比"""
        return self.chinese_chars / self.total_chars if self.total_chars > 0 else 0.0

    @property
    def content_chars(self) -> int:
        """有效内容字符数（不含空白）"""
        return self.total_chars - self.whitespace_chars

    @classmethod
    def from_text(cls, text: str) -> "TextStats":
        """从文本计算统计信息"""
        if not text:
            return cls(0, 0, 0, 0, 0, 0, 0)

        chinese = 0
        english = 0
        digits = 0
        whitespace = 0
        punctuation = 0
        other = 0

        # 标点符号集合
        punct_chars = set('，。！？、；：""''（）【】《》——…·,.!?;:\'\"()[]<>-')

        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                chinese += 1
            elif char.isascii() and char.isalpha():
                english += 1
            elif char.isdigit():
                digits += 1
            elif char.isspace():
                whitespace += 1
            elif char in punct_chars:
                punctuation += 1
            else:
                other += 1

        return cls(
            total_chars=len(text),
            chinese_chars=chinese,
            english_chars=english,
            digit_chars=digits,
            whitespace_chars=whitespace,
            punctuation_chars=punctuation,
            other_chars=other,
        )


# 在 DocumentMeta 中添加字段
@dataclass
class DocumentMeta:
    """
    文档元数据。
    
    记录每个文档片段的来源、位置和关联信息。
    """
    source_file: str
    part_index: int
    total_parts: int
    char_count: int
    md5_hash: str

    # === 片段关联信息 ===
    prev_part_id: str = ""      # 前一个片段的 ID
    next_part_id: str = ""      # 后一个片段的 ID
    group_id: str = ""          # 同源文档组 ID

    # 其他元数据字段
    source_type: str = ""
    year: str = ""
    title: str = ""
    url: str = ""
    province: str = ""
    river: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

@dataclass
class ProcessingResult:
    """
    单个文件的处理结果。

    记录处理过程中的所有信息，便于后续分析和调试。
    """
    path: Path
    status: ProcessingStatus
    parts_count: int = 0
    message: str = ""
    error_type: str = ""
    error_traceback: str = ""
    output_paths: List[Path] = field(default_factory=list)
    meta_list: List[DocumentMeta] = field(default_factory=list)
    processing_time_seconds: float = 0.0

    @property
    def is_success(self) -> bool:
        """是否处理成功"""
        return self.status == ProcessingStatus.SUCCESS

    @property
    def is_failed(self) -> bool:
        """是否处理失败"""
        return self.status == ProcessingStatus.FAILED

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "path": str(self.path),
            "status": self.status.value,
            "parts_count": self.parts_count,
            "message": self.message,
            "error_type": self.error_type,
            "output_paths": [str(p) for p in self.output_paths],
            "processing_time_seconds": self.processing_time_seconds,
        }


@dataclass
class BatchResult:
    """
    批量处理结果汇总。

    提供整体处理统计和详细结果列表。
    """
    total_files: int = 0
    total_parts: int = 0
    success_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    duration_seconds: float = 0.0
    results: List[ProcessingResult] = field(default_factory=list)

    def add_result(self, result: ProcessingResult) -> None:
        """添加单个处理结果"""
        self.results.append(result)
        self.total_files += 1

        if result.status == ProcessingStatus.SUCCESS:
            self.success_count += 1
            self.total_parts += result.parts_count
        elif result.status == ProcessingStatus.SKIPPED:
            self.skipped_count += 1
        else:
            self.failed_count += 1

    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_files == 0:
            return 0.0
        return self.success_count / self.total_files

    @property
    def successful_results(self) -> List[ProcessingResult]:
        """成功的结果列表"""
        return [r for r in self.results if r.is_success]

    @property
    def failed_results(self) -> List[ProcessingResult]:
        """失败的结果列表"""
        return [r for r in self.results if r.is_failed]

    @property
    def skipped_results(self) -> List[ProcessingResult]:
        """跳过的结果列表"""
        return [r for r in self.results if r.status == ProcessingStatus.SKIPPED]

    def summary(self, verbose: bool = False) -> str:
        """
        生成处理结果摘要。

        Args:
            verbose: 是否包含详细信息

        Returns:
            格式化的摘要字符串
        """
        lines = [
            "",
            "=" * 70,
            f"  {Constants.TOOL_NAME} v{Constants.VERSION} - 处理完成",
            "=" * 70,
            "",
            f"  📊 总体统计",
            f"     • 处理文件数: {self.total_files}",
            f"     • 成功: {self.success_count} ({self.success_rate:.1%})",
            f"     • 跳过: {self.skipped_count}",
            f"     • 失败: {self.failed_count}",
            f"     • 生成分片: {self.total_parts}",
            f"     • 总耗时: {self.duration_seconds:.2f} 秒",
            "",
        ]

        if verbose and self.failed_results:
            lines.append("  ❌ 失败详情:")
            for r in self.failed_results[:10]:  # 最多显示 10 个
                lines.append(f"     • {r.path.name}: {r.message}")
            if len(self.failed_results) > 10:
                lines.append(
                    f"     ... 还有 {len(self.failed_results) - 10} 个失败")
            lines.append("")

        lines.append("=" * 70)

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "summary": {
                "total_files": self.total_files,
                "total_parts": self.total_parts,
                "success_count": self.success_count,
                "skipped_count": self.skipped_count,
                "failed_count": self.failed_count,
                "success_rate": f"{self.success_rate:.2%}",
                "duration_seconds": round(self.duration_seconds, 2),
            },
            "results": [r.to_dict() for r in self.results],
        }

# ==============================================================================
# 缓存管理
# ==============================================================================


class ProcessingCache:
    """
    处理进度缓存管理器。
    
    功能：
    1. **断点续运行**：记录已处理的文件，重启后跳过
    2. **进度持久化**：定期保存到磁盘，防止数据丢失
    3. **状态查询**：快速检查文件是否已处理
    4. **错误跟踪**：记录失败文件，支持重试
    
    缓存格式（JSONL）：
    ```json
    {"path": "file.pdf", "status": "success", "parts": 5, "timestamp": "2024-01-01 10:00:00"}
    {"path": "file2.pdf", "status": "failed", "error": "...", "timestamp": "..."}
    ```
    
    使用示例：
    ```python
    cache = ProcessingCache(output_dir / ".cache.jsonl")
    
    # 检查文件是否已处理
    if cache.is_processed(file_path, status="success"):
        print("already processed, skip")
        return
    
    # 处理文件...
    try:
        result = process_file(file_path)
        cache.mark_processed(file_path, "success", parts=10)
    except Exception as e:
        cache.mark_processed(file_path, "failed", error=str(e))
    
    # 定期保存
    cache.save()
    ```
    
    设计特点：
    - **线程安全**：使用锁保护共享状态
    - **延迟写入**：批量更新内存，定期 flush 到磁盘
    - **容错性**：缓存读取失败不影响主流程
    - **可观测性**：记录时间戳和详细统计
    """

    def __init__(
        self,
        cache_path: Path,
        auto_save_interval: int = Constants.DEFAULT_CACHE_SAVE_INTERVAL,
    ):
        """
        初始化缓存管理器。
        
        Args:
            cache_path: 缓存文件路径（JSONL 格式）
            auto_save_interval: 自动保存间隔（处理文件数）
        """
        self.cache_path = cache_path
        self.auto_save_interval = auto_save_interval
        
        # 缓存数据：path -> {status, parts, error, timestamp}
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._dirty = False  # 标记是否有未保存的更改
        self._operation_count = 0  # 操作计数
        
        # 加载已有缓存
        self._load()
    
    def _load(self) -> None:
        """
        从磁盘加载缓存。
        
        容错处理：
        - 文件不存在：创建空缓存
        - 格式错误：记录警告并跳过
        - JSON 解析失败：跳过损坏的行
        """
        if not self.cache_path.exists():
            logger.debug(f"缓存文件不存在，将创建新缓存: {self.cache_path}")
            return
        
        try:
            with self.cache_path.open("r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        entry = json.loads(line)
                        if "path" not in entry:
                            logger.warning(
                                f"缓存项缺少 'path' 字段（行 {line_num}），已跳过"
                            )
                            continue
                        
                        path = entry["path"]
                        self._cache[path] = {
                            "status": entry.get("status", "unknown"),
                            "parts": entry.get("parts", 0),
                            "error": entry.get("error", ""),
                            "timestamp": entry.get("timestamp", ""),
                        }
                    
                    except json.JSONDecodeError as e:
                        logger.warning(
                            f"解析缓存项失败（行 {line_num}）: {e}"
                        )
                        continue
            
            logger.info(
                f"已加载 {len(self._cache)} 条缓存记录从 {self.cache_path}"
            )
        
        except OSError as e:
            # 文件读取错误（权限、磁盘错误等）
            logger.error(f"读取缓存文件失败: {e}")
            logger.warning("将使用空缓存继续，但可能会重复处理文件")
        
        except Exception as e:
            # 其他未预见错误
            logger.exception(f"加载缓存时发生意外错误: {e}")
    
    def save(self, force: bool = False) -> bool:
        """
        保存缓存到磁盘。
        
        Args:
            force: 是否强制保存（忽略 dirty 标记）
        
        Returns:
            是否保存成功
        
        注意：
        - 使用原子写入（先写临时文件，再重命名）防止数据损坏
        - 失败时不清空内存缓存，下次依然可以重试
        """
        with self._lock:
            if not force and not self._dirty:
                logger.debug("缓存未变更，跳过保存")
                return True
            
            try:
                # 确保父目录存在
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 原子写入：先写临时文件
                temp_path = self.cache_path.with_suffix(".tmp")
                with temp_path.open("w", encoding="utf-8") as f:
                    for path, info in self._cache.items():
                        entry = {"path": path, **info}
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                
                # 原子替换
                temp_path.replace(self.cache_path)
                
                self._dirty = False
                logger.debug(f"已保存 {len(self._cache)} 条缓存记录到 {self.cache_path}")
                return True
            
            except OSError as e:
                logger.error(f"保存缓存失败（I/O 错误）: {e}")
                return False
            
            except Exception as e:
                logger.exception(f"保存缓存时发生意外错误: {e}")
                return False
    
    def is_processed(
        self,
        file_path: Union[Path, str],
        status: Optional[str] = None,
    ) -> bool:
        """
        检查文件是否已处理。
        
        Args:
            file_path: 文件路径
            status: 指定状态过滤（例如只检查 "success"）
        
        Returns:
            是否已处理
        
        示例：
        ```python
        # 检查是否已成功处理
        if cache.is_processed(path, status="success"):
            return
        
        # 检查是否曾经尝试处理（不论成败）
        if cache.is_processed(path):
            return
        ```
        """
        path_str = str(file_path)
        with self._lock:
            if path_str not in self._cache:
                return False
            
            if status is None:
                return True
            
            return self._cache[path_str].get("status") == status
    
    def mark_processed(
        self,
        file_path: Union[Path, str],
        status: str,
        parts: int = 0,
        error: str = "",
    ) -> None:
        """
        标记文件为已处理。
        
        Args:
            file_path: 文件路径
            status: 处理状态 ("success", "failed", "skipped")
            parts: 生成的片段数
            error: 错误信息（如果失败）
        """
        path_str = str(file_path)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        
        with self._lock:
            self._cache[path_str] = {
                "status": status,
                "parts": parts,
                "error": error,
                "timestamp": timestamp,
            }
            self._dirty = True
            self._operation_count += 1
            
            # 达到自动保存间隔
            if self._operation_count >= self.auto_save_interval:
                self.save()
                self._operation_count = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息。
        
        Returns:
            统计信息字典
        """
        with self._lock:
            total = len(self._cache)
            success = sum(1 for v in self._cache.values() if v["status"] == "success")
            failed = sum(1 for v in self._cache.values() if v["status"] == "failed")
            skipped = sum(1 for v in self._cache.values() if v["status"] == "skipped")
            
            return {
                "total": total,
                "success": success,
                "failed": failed,
                "skipped": skipped,
                "cache_path": str(self.cache_path),
            }
    
    def clear(self) -> None:
        """
        清空缓存（内存和磁盘）。
        
        警告：此操作不可逆！
        """
        with self._lock:
            self._cache.clear()
            self._dirty = True
            if self.cache_path.exists():
                try:
                    self.cache_path.unlink()
                    logger.info(f"已清空缓存: {self.cache_path}")
                except OSError as e:
                    logger.error(f"删除缓存文件失败: {e}")
    
    def __enter__(self) -> "ProcessingCache":
        """支持上下文管理器协议。"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出时自动保存缓存。"""
        self.save(force=True)
    
    def __len__(self) -> int:
        """返回缓存项数量。"""
        with self._lock:
            return len(self._cache)


# ==============================================================================
# 工具装饰器
# ==============================================================================


def retry_on_network_error(
    max_retries: int = Constants.DEFAULT_MAX_RETRIES,
    initial_delay: float = Constants.DEFAULT_RETRY_DELAY,
    backoff_factor: float = Constants.RETRY_BACKOFF_FACTOR,
    max_delay: float = Constants.MAX_RETRY_DELAY,
):
    """
    重试装饰器：仅针对网络错误进行重试。
    
    重要：
    - **429 限流错误不重试**：直接抛出，由上层处理
    - **账号封禁不重试**：直接抛出
    - **网络超时会重试**：这是瞬时错误，可以重试
    
    Args:
        max_retries: 最大重试次数（0 表示不重试）
        initial_delay: 初始延迟秒数
        backoff_factor: 退避因子
        max_delay: 最大延迟秒数
    
    使用示例：
    ```python
    @retry_on_network_error(max_retries=3, initial_delay=2.0)
    def call_llm_api(prompt: str) -> str:
        response = llm_backend.chat(prompt)
        return response
    ```
    
    重试策略：
    - 429 限流：立即抛出，不重试
    - 网络超时：指数退避重试
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception: Optional[Exception] = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                
                except Exception as e:
                    # 检查是否为 LLM 严重错误（429/401）
                    if _is_account_blocked_error(e):
                        # 账号封禁，不重试，直接抛出
                        logger.error(
                            f"账号被封禁或鉴权失败 (401): {func.__name__}"
                        )
                        raise _InternalAccountBlockedError(str(e)) from e
                    
                    if _is_rate_limit_error(e):
                        # 429 限流错误：不重试，直接抛出，交给上层处理
                        logger.error(
                            f"LLM 限流 (429)，立即停止: {func.__name__}"
                        )
                        raise _InternalRateLimitError(str(e)) from e
                    
                    # 网络错误（超时、连接失败等）可以重试
                    if isinstance(e, (OSError, IOError)):
                        last_exception = e
                        
                        if attempt >= max_retries:
                            logger.error(
                                f"网络错误，已达最大重试次数: {e}"
                            )
                            raise NetworkError(f"网络请求失败: {e}") from e
                        
                        delay = min(
                            initial_delay * (backoff_factor ** attempt),
                            max_delay
                        )
                        
                        logger.warning(
                            f"网络错误，第 {attempt + 1}/{max_retries} 次重试: {e}"
                        )
                        time.sleep(delay)
                        continue
                    
                    # 其他异常直接抛出
                    raise
            
            # 理论上不会走到这里
            if last_exception:
                raise last_exception
            raise RuntimeError(f"{func.__name__} 重试失败")
        
        return wrapper
    return decorator


# ==============================================================================
# 配置类定义
# ==============================================================================


@dataclass
class BaseConfig:
    """配置基类"""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls: Type[ConfigT], data: Dict[str, Any]) -> ConfigT:
        """从字典创建实例"""
        return cls(**{
            k: v for k, v in data.items()
            if k in {f.name for f in cls.__dataclass_fields__.values()}
        })


@dataclass
class CleanerConfig(BaseConfig):
    """
    文本清洗器配置。

    控制清洗行为的各项开关和参数。
    """
    # 移除选项
    remove_headers: bool = True
    remove_footers: bool = True
    remove_toc: bool = True
    remove_references: bool = False
    remove_noise: bool = True
    remove_watermarks: bool = True

    # 规范化选项
    normalize_whitespace: bool = True
    normalize_punctuation: bool = True
    fullwidth_to_halfwidth: bool = True

    # 高级选项
    max_consecutive_newlines: int = 2
    min_line_length: int = 0  # 删除过短的行（0 表示不删除）


@dataclass
class SplitterConfig(BaseConfig):
    """
    文本切分器配置。

    控制切分策略和长度限制。
    """
    min_chars: int = Constants.DEFAULT_MIN_CHARS
    max_chars: int = Constants.DEFAULT_MAX_CHARS
    prefer_section: bool = True
    merge_short: bool = True
    overlap_chars: int = 0  # 片段重叠字符数（用于保持上下文）

    def __post_init__(self) -> None:
        """参数校验"""
        if self.min_chars <= 0:
            raise ConfigurationError(f"min_chars 必须大于 0，当前值: {self.min_chars}")
        if self.max_chars <= self.min_chars:
            raise ConfigurationError(
                f"max_chars ({self.max_chars}) 必须大于 min_chars ({self.min_chars})"
            )
        if self.overlap_chars < 0:
            raise ConfigurationError(
                f"overlap_chars 不能为负数: {self.overlap_chars}")


@dataclass
class LLMConfig(BaseConfig):
    """
    LLM 配置。

    用于 LLM 语义切分和质量判定。
    """
    provider: str = "zhipu"
    model_name: str = "glm-4.5-flash"
    temperature: float = 0.0
    max_tokens: int = 4096
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    thinking_type: Optional[str] = None

    # 重试配置
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: float = 60.0

    def to_factory_dict(self) -> Dict[str, Any]:
        """
        转换为 LLMFactory 接受的字典格式。

        过滤掉 None 值和非必要字段。
        """
        result = {
            "provider": self.provider,
            "model_name": self.model_name,
            "temperature": self.temperature,
        }
        if self.api_key:
            result["api_key"] = self.api_key
        if self.base_url:
            result["base_url"] = self.base_url
        if self.thinking_type:
            result["thinking_type"] = self.thinking_type
        return result


@dataclass
class ProcessingConfig(BaseConfig):
    """
    处理流程整体配置。

    包含所有子模块配置和全局设置。
    """
    cleaner: CleanerConfig = field(default_factory=CleanerConfig)
    splitter: SplitterConfig = field(default_factory=SplitterConfig)
    llm: Optional[LLMConfig] = None

    # 全局设置
    pdf_engine: str = "auto"
    max_workers: int = Constants.DEFAULT_MAX_WORKERS
    use_llm_split: bool = False
    preserve_structure: bool = True

    # 缓存设置
    cache_enabled: bool = True
    cache_dir: Optional[Path] = None

    # 输出设置
    output_dir: Optional[Path] = None

# ==============================================================================
# 配置加载器
# ==============================================================================


class ConfigLoader:
    """
    配置加载器。

    支持从多个来源加载配置，按优先级合并：
    默认值 < 配置文件 < 环境变量 < 命令行参数

    设计特点：
    - 延迟加载：只在需要时才读取配置文件
    - 类型转换：自动将字符串转换为适当的类型
    - 错误处理：配置错误时提供清晰的错误信息
    """

    # 环境变量到配置路径的映射
    ENV_MAPPING: ClassVar[Dict[str, Tuple[str, ...]]] = {
        "LLM_PROVIDER": ("llm", "provider"),
        "LLM_MODEL_NAME": ("llm", "model_name"),
        "OPENAI_MODEL_API": ("llm", "model_name"),
        "LLM_TEMPERATURE": ("llm", "temperature"),
        "LLM_API_KEY": ("llm", "api_key"),
        "LLM_BASE_URL": ("llm", "base_url"),
        "OPENAI_BASE_URL": ("llm", "base_url"),
        "LLM_THINKING_TYPE": ("llm", "thinking_type"),
        "CORPUS_MIN_CHARS": ("splitter", "min_chars"),
        "CORPUS_MAX_CHARS": ("splitter", "max_chars"),
        "CORPUS_MAX_WORKERS": ("processing", "max_workers"),
    }

    def __init__(self, config_path: Optional[Path] = None):
        """
        初始化配置加载器。

        Args:
            config_path: 可选的 YAML 配置文件路径
        """
        self.config_path = config_path
        self._yaml_cache: Optional[Dict[str, Any]] = None
        self._load_attempted = False

    @property
    def yaml_config(self) -> Dict[str, Any]:
        """延迟加载 YAML 配置"""
        if not self._load_attempted:
            self._load_attempted = True
            if self.config_path and self.config_path.exists():
                self._yaml_cache = self._load_yaml_file(self.config_path)
            else:
                self._yaml_cache = {}
        return self._yaml_cache or {}

    @staticmethod
    def _load_yaml_file(path: Path) -> Dict[str, Any]:
        """
        加载 YAML 配置文件。

        Args:
            path: 文件路径

        Returns:
            解析后的字典，失败时返回空字典
        """
        if not YAML_AVAILABLE:
            logger.warning("未安装 PyYAML，无法加载配置文件")
            return {}

        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                logger.warning(f"配置文件格式无效: {path}")
                return {}
            logger.debug(f"已加载配置文件: {path}")
            return data
        except Exception as e:
            logger.warning(f"加载配置文件失败: {path}, 错误: {e}")
            return {}

    def _get_nested_value(
        self,
        data: Dict[str, Any],
        path: Tuple[str, ...],
        default: Any = None
    ) -> Any:
        """
        获取嵌套字典中的值。

        Args:
            data: 字典
            path: 键路径元组
            default: 默认值

        Returns:
            找到的值或默认值
        """
        current = data
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current if current is not None else default

    def _get_env_value(self, key: str, type_hint: type = str) -> Optional[Any]:
        """
        获取环境变量值并进行类型转换。

        Args:
            key: 环境变量名
            type_hint: 目标类型

        Returns:
            转换后的值，或 None
        """
        value = os.getenv(key)
        if value is None:
            return None

        try:
            if type_hint == bool:
                return value.lower() in ("true", "1", "yes", "on")
            elif type_hint == int:
                return int(value)
            elif type_hint == float:
                return float(value)
            else:
                return value
        except (ValueError, TypeError):
            logger.warning(
                f"环境变量 {key} 的值 '{value}' 无法转换为 {type_hint.__name__}")
            return None

    def resolve_value(
        self,
        cli_value: Any,
        env_key: Optional[str],
        yaml_path: Tuple[str, ...],
        default: Any,
        type_hint: type = str,
    ) -> Any:
        """
        按优先级解析配置值。

        优先级：CLI > 环境变量 > YAML 配置 > 默认值

        Args:
            cli_value: 命令行参数值
            env_key: 环境变量名
            yaml_path: YAML 配置路径
            default: 默认值
            type_hint: 目标类型

        Returns:
            解析后的配置值
        """
        # 1. 命令行参数优先
        if cli_value is not None:
            return cli_value

        # 2. 环境变量次之
        if env_key:
            env_value = self._get_env_value(env_key, type_hint)
            if env_value is not None:
                return env_value

        # 3. YAML 配置再次
        yaml_value = self._get_nested_value(self.yaml_config, yaml_path)
        if yaml_value is not None:
            return yaml_value

        # 4. 默认值
        return default

    def load_processing_config(self, args: argparse.Namespace) -> ProcessingConfig:
        """
        根据命令行参数加载完整处理配置。

        Args:
            args: 解析后的命令行参数

        Returns:
            完整的处理配置对象
        """
        # 清洗器配置
        cleaner_config = CleanerConfig(
            remove_headers=True,
            remove_footers=True,
            remove_toc=not getattr(args, "keep_toc", False),
            remove_references=getattr(args, "remove_references", False),
            remove_noise=True,
        )

        # 切分器配置
        min_chars = self.resolve_value(
            getattr(args, "min_chars", None),
            "CORPUS_MIN_CHARS",
            ("splitting", "min_chars"),
            Constants.DEFAULT_MIN_CHARS,
            int,
        )
        max_chars = self.resolve_value(
            getattr(args, "max_chars", None),
            "CORPUS_MAX_CHARS",
            ("splitting", "max_chars"),
            Constants.DEFAULT_MAX_CHARS,
            int,
        )
        splitter_config = SplitterConfig(
            min_chars=min_chars,
            max_chars=max_chars,
            prefer_section=not getattr(args, "no_section_split", False),
        )

        # LLM 配置（仅在启用时创建）
        llm_config = None
        if getattr(args, "llm_split", False):
            llm_config = LLMConfig(
                provider=self.resolve_value(
                    getattr(args, "llm_provider", None),
                    "LLM_PROVIDER",
                    ("llm", "provider"),
                    "zhipu",
                ),
                model_name=self.resolve_value(
                    getattr(args, "llm_model", None),
                    "LLM_MODEL_NAME",
                    ("llm", "model_name"),
                    "glm-4.5-flash",
                ),
                temperature=float(self.resolve_value(
                    getattr(args, "llm_temperature", None),
                    "LLM_TEMPERATURE",
                    ("llm", "temperature"),
                    0.0,
                    float,
                )),
                api_key=self.resolve_value(
                    getattr(args, "llm_api_key", None),
                    "LLM_API_KEY",
                    ("llm", "api_key"),
                    None,
                ),
                base_url=self.resolve_value(
                    getattr(args, "llm_base_url", None),
                    "LLM_BASE_URL",
                    ("llm", "base_url"),
                    None,
                ),
                thinking_type=self.resolve_value(
                    getattr(args, "llm_thinking", None),
                    "LLM_THINKING_TYPE",
                    ("llm", "thinking_type"),
                    None,
                ),
            )

        # 输出目录
        output_dir = Path(getattr(args, "output_dir",
                          "data/enhancing_onto_corpus_docs"))

        return ProcessingConfig(
            cleaner=cleaner_config,
            splitter=splitter_config,
            llm=llm_config,
            pdf_engine=getattr(args, "pdf_engine", "auto"),
            max_workers=self.resolve_value(
                getattr(args, "workers", None),
                "CORPUS_MAX_WORKERS",
                ("processing", "max_workers"),
                Constants.DEFAULT_MAX_WORKERS,
                int,
            ),
            use_llm_split=getattr(args, "llm_split", False),
            preserve_structure=not getattr(
                args, "no_preserve_structure", False),
            output_dir=output_dir,
        )

# ==============================================================================
# 文本提取器（策略模式）
# ==============================================================================


@runtime_checkable
class TextExtractor(Protocol):
    """
    文本提取器协议。

    定义所有文本提取器必须实现的接口。
    使用 Protocol 而非抽象基类，支持鸭子类型。
    """

    def extract(self, path: Path) -> str:
        """从文件提取文本"""
        ...

    def supports(self, file_type: FileType) -> bool:
        """检查是否支持指定文件类型"""
        ...


class BaseTextExtractor(ABC):
    """
    文本提取器抽象基类。

    提供通用功能和默认实现。
    """
    @abstractmethod
    def extract(self, path: Path) -> str:
        """从文件提取文本"""
        pass

    @abstractmethod
    def supports(self, file_type: FileType) -> bool:
        """检查是否支持指定文件类型"""
        pass

    def _validate_path(self, path: Path) -> None:
        """验证文件路径"""
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        if not path.is_file():
            raise ValueError(f"不是文件: {path}")


class PyPDF2Extractor(BaseTextExtractor):
    """
    基于 PyPDF2 的 PDF 文本提取器。

    特点：
    - 速度快，内存占用低
    - 兼容性好，支持大多数 PDF
    - 表格识别能力有限
    """
    _pypdf2_available: ClassVar[Optional[bool]] = None

    @classmethod
    def is_available(cls) -> bool:
        """检查 PyPDF2 是否可用"""
        if cls._pypdf2_available is None:
            try:
                import PyPDF2
                cls._pypdf2_available = True
            except ImportError:
                cls._pypdf2_available = False
        return cls._pypdf2_available

    def supports(self, file_type: FileType) -> bool:
        return file_type == FileType.PDF and self.is_available()

    def extract(self, path: Path) -> str:
        """
        从 PDF 文件提取文本。

        Args:
            path: PDF 文件路径

        Returns:
            提取的文本内容

        Raises:
            ImportError: 缺少 PyPDF2 库
            ExtractionError: 提取失败
        """
        self._validate_path(path)

        try:
            from PyPDF2 import PdfReader
        except ImportError:
            raise ImportError("请安装 PyPDF2: pip install PyPDF2")

        try:
            reader = PdfReader(str(path))
            pages = []

            for i, page in enumerate(reader.pages, 1):
                try:
                    text = page.extract_text() or ""
                    # 添加页面标记便于后续清洗
                    pages.append(f"[PAGE_{i}_START]\n{text}\n[PAGE_{i}_END]")
                except Exception as e:
                    logger.warning(f"提取第 {i} 页失败: {e}")
                    pages.append(f"[PAGE_{i}_START]\n[提取失败]\n[PAGE_{i}_END]")

            return "\n".join(pages)

        except Exception as e:
            raise ExtractionError(f"PyPDF2 解析失败: {path}, 错误: {e}") from e


class PDFPlumberExtractor(BaseTextExtractor):
    """
    基于 pdfplumber 的 PDF 文本提取器。

    特点：
    - 表格识别准确
    - 支持提取文本位置信息
    - 速度稍慢，内存占用较高
    """
    _pdfplumber_available: ClassVar[Optional[bool]] = None

    @classmethod
    def is_available(cls) -> bool:
        """检查 pdfplumber 是否可用"""
        if cls._pdfplumber_available is None:
            try:
                import pdfplumber
                cls._pdfplumber_available = True
            except ImportError:
                cls._pdfplumber_available = False
        return cls._pdfplumber_available

    def supports(self, file_type: FileType) -> bool:
        return file_type == FileType.PDF and self.is_available()

    def extract(self, path: Path) -> str:
        """
        从 PDF 文件提取文本，包括表格。

        Args:
            path: PDF 文件路径

        Returns:
            提取的文本内容
        """
        self._validate_path(path)

        try:
            import pdfplumber
        except ImportError:
            raise ImportError("请安装 pdfplumber: pip install pdfplumber")

        try:
            pages = []
            with pdfplumber.open(str(path)) as pdf:
                for i, page in enumerate(pdf.pages, 1):
                    try:
                        # 提取正文
                        text = page.extract_text() or ""

                        # 提取表格
                        table_text = self._extract_tables(page)

                        # 组合页面内容
                        page_content = f"[PAGE_{i}_START]\n{text}\n{table_text}[PAGE_{i}_END]"
                        pages.append(page_content)
                    except Exception as e:
                        logger.warning(f"提取第 {i} 页失败: {e}")
                        pages.append(
                            f"[PAGE_{i}_START]\n[提取失败]\n[PAGE_{i}_END]")

            return "\n".join(pages)

        except Exception as e:
            raise ExtractionError(f"pdfplumber 解析失败: {path}, 错误: {e}") from e

    def _extract_tables(self, page) -> str:
        """
        提取页面中的表格并格式化。

        将表格转换为 Markdown 风格的文本格式。
        """
        try:
            tables = page.extract_tables()
        except Exception:
            return ""

        if not tables:
            return ""

        table_texts = []
        for table_idx, table in enumerate(tables, 1):
            if not table:
                continue

            rows = []
            for row in table:
                # 处理 None 值和格式化单元格
                cells = [
                    str(cell).strip().replace("\n", " ") if cell else ""
                    for cell in row
                ]
                rows.append(" | ".join(cells))

            if rows:
                table_text = f"\n[TABLE_{table_idx}]\n" + \
                    "\n".join(rows) + f"\n[/TABLE_{table_idx}]\n"
                table_texts.append(table_text)

        return "".join(table_texts)


class TxtExtractor(BaseTextExtractor):
    """
    纯文本文件提取器。

    特点：
    - 自动编码检测
    - 支持多种编码格式
    - 优雅降级处理编码错误
    """

    def supports(self, file_type: FileType) -> bool:
        return file_type == FileType.TXT

    def extract(self, path: Path) -> str:
        """
        从文本文件提取内容，自动检测编码。

        Args:
            path: 文本文件路径

        Returns:
            文件内容
        """
        self._validate_path(path)

        # 尝试各种编码
        for encoding in Constants.DEFAULT_ENCODINGS:
            try:
                content = path.read_text(encoding=encoding)
                # 成功读取后验证内容
                if self._is_valid_text(content):
                    logger.debug(f"使用编码 {encoding} 成功读取: {path.name}")
                    return content
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception as e:
                logger.warning(f"读取文件时出错 ({encoding}): {e}")
                continue

        # 所有编码都失败，使用 utf-8 忽略错误模式
        logger.warning(f"无法确定编码，使用 UTF-8 忽略错误模式: {path}")
        return path.read_text(encoding="utf-8", errors="ignore")

    @staticmethod
    def _is_valid_text(text: str) -> bool:
        """
        检查文本是否有效（非乱码）。

        简单启发式：检查是否包含常见的乱码特征。
        """
        if not text:
            return False

        # 检查是否有过多的替换字符
        replacement_ratio = text.count('\ufffd') / len(text) if text else 0
        if replacement_ratio > 0.1:
            return False

        # 检查是否有足够的可打印字符
        printable_count = sum(
            1 for c in text if c.isprintable() or c.isspace())
        printable_ratio = printable_count / len(text) if text else 0

        return printable_ratio > 0.9


class ExtractorFactory:
    """
    文本提取器工厂。

    使用工厂模式根据文件类型和配置创建合适的提取器。

    设计特点：
    - 延迟初始化：只在需要时创建提取器
    - 自动降级：优先引擎不可用时自动选择备选
    - 可扩展：易于添加新的提取器
    """

    def __init__(self, pdf_engine: str = "auto"):
        """
        初始化工厂。

        Args:
            pdf_engine: PDF 引擎选择
                - "auto": 自动选择最佳可用引擎
                - "pypdf2": 强制使用 PyPDF2
                - "pdfplumber": 强制使用 pdfplumber
        """
        self.pdf_engine = pdf_engine
        self._extractors: Dict[FileType, BaseTextExtractor] = {}
        self._init_extractors()

    def _init_extractors(self) -> None:
        """初始化所有提取器"""
        # TXT 提取器
        self._extractors[FileType.TXT] = TxtExtractor()

        # PDF 提取器（根据配置选择）
        self._extractors[FileType.PDF] = self._create_pdf_extractor()

    def _create_pdf_extractor(self) -> BaseTextExtractor:
        """创建 PDF 提取器"""
        if self.pdf_engine == "pdfplumber":
            if PDFPlumberExtractor.is_available():
                return PDFPlumberExtractor()
            else:
                logger.warning("pdfplumber 不可用，回退到 PyPDF2")
                return PyPDF2Extractor()

        elif self.pdf_engine == "pypdf2":
            return PyPDF2Extractor()

        else:  # auto
            # 优先使用 pdfplumber
            if PDFPlumberExtractor.is_available():
                logger.debug("自动选择 pdfplumber 作为 PDF 引擎")
                return PDFPlumberExtractor()
            elif PyPDF2Extractor.is_available():
                logger.debug("自动选择 PyPDF2 作为 PDF 引擎")
                return PyPDF2Extractor()
            else:
                raise ImportError(
                    "未找到可用的 PDF 解析库。请安装 pdfplumber 或 PyPDF2:\n"
                    "  pip install pdfplumber\n"
                    "  或\n"
                    "  pip install PyPDF2"
                )

    def get_extractor(self, file_type: FileType) -> Optional[BaseTextExtractor]:
        """获取指定文件类型的提取器"""
        return self._extractors.get(file_type)

    def extract(self, path: Path) -> str:
        """
        提取文件文本的统一入口。

        Args:
            path: 文件路径

        Returns:
            提取的文本

        Raises:
            UnsupportedFileTypeError: 不支持的文件类型
            ExtractionError: 提取失败
        """
        file_type = FileType.from_suffix(path.suffix)

        # 检查是否需要手动转换
        if file_type == FileType.CAJ:
            raise UnsupportedFileTypeError(
                path,
                "CAJ 文件不支持直接解析。请使用 CAJViewer 转换为 PDF 后重试。"
            )

        if file_type in (FileType.DOC, FileType.DOCX):
            raise UnsupportedFileTypeError(
                path,
                "Word 文档请先转换为 PDF 或 TXT 格式。"
            )

        if file_type == FileType.UNKNOWN:
            raise UnsupportedFileTypeError(path)

        extractor = self.get_extractor(file_type)
        if not extractor:
            raise UnsupportedFileTypeError(
                path,
                f"找不到 {file_type.description} 的提取器"
            )

        return extractor.extract(path)

# ==============================================================================
# 文本清洗器
# ==============================================================================


class PatternRegistry:
    """
    正则表达式模式注册表。

    集中管理所有清洗相关的正则模式，便于维护和复用。
    所有模式都预编译以提高性能。
    """
    # 页眉页脚模式
    HEADER_FOOTER_PATTERNS: ClassVar[List[re.Pattern]] = [
        re.compile(r"第\s*\d+\s*页\s*[/／共]\s*\d+\s*页"),  # 第1页/共10页
        re.compile(r"第\s*\d+\s*页"),  # 第1页
        re.compile(r"[-—]\s*\d+\s*[-—]"),  # - 1 - 或 — 1 —
        re.compile(r"^\d{1,4}$"),  # 单独的页码
        re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]+$"),  # 圆圈数字
        re.compile(r"^\s*·\s*\d+\s*·\s*$"),  # ·1·
        re.compile(r"^Page\s+\d+\s*(of\s+\d+)?$", re.IGNORECASE),
        re.compile(r"^\d+\s*/\s*\d+$"),  # 1/10
    ]

    # 目录相关模式
    TOC_TITLE_PATTERNS: ClassVar[List[re.Pattern]] = [
        re.compile(r"^目\s*录\s*$"),
        re.compile(r"^CONTENTS?\s*$", re.IGNORECASE),
        re.compile(r"^TABLE\s+OF\s+CONTENTS?\s*$", re.IGNORECASE),
    ]

    TOC_ENTRY_PATTERNS: ClassVar[List[re.Pattern]] = [
        re.compile(r"^[\d一二三四五六七八九十]+[、.．]\s*.{2,40}\s*[\.…·]+\s*\d+\s*$"),
        re.compile(r"^第[一二三四五六七八九十\d]+[章节]\s*.{2,30}\s*[\.…·]+\s*\d+\s*$"),
    ]

    # 参考文献起始标志
    REFERENCE_START_PATTERNS: ClassVar[List[re.Pattern]] = [
        re.compile(r"^参\s*考\s*文\s*献\s*$", re.MULTILINE),
        re.compile(r"^References?\s*$", re.MULTILINE | re.IGNORECASE),
        re.compile(r"^REFERENCES?\s*$", re.MULTILINE),
        re.compile(r"^引用文献\s*$", re.MULTILINE),
        re.compile(r"^Bibliography\s*$", re.MULTILINE | re.IGNORECASE),
        re.compile(r"^文献\s*$", re.MULTILINE),
    ]

    # 噪声模式（需要删除的内容）
    NOISE_PATTERNS: ClassVar[List[re.Pattern]] = [
        # 页面标记
        re.compile(r"\[PAGE_\d+_(START|END)\]"),
        re.compile(r"\[TABLE_\d+\]|\[/TABLE_\d+\]"),
        re.compile(r"\[提取失败\]"),

        # 网址和联系方式
        re.compile(r"^\s*(?:https?://|www\.)[^\s]+\s*$", re.MULTILINE),
        re.compile(r"E-?mail\s*[:：]\s*[^\s]+", re.IGNORECASE),
        re.compile(r"(?:电话|Tel|Phone)\s*[:：]\s*[\d\-\s]+", re.IGNORECASE),
        re.compile(r"(?:传真|Fax)\s*[:：]\s*[\d\-\s]+", re.IGNORECASE),

        # 学术论文噪声
        re.compile(r"收稿日期\s*[:：]\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}"),
        re.compile(r"修回日期\s*[:：]\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}"),
        re.compile(r"基金项目\s*[:：].{10,150}"),
        re.compile(r"作者简介\s*[:：].{10,250}"),
        re.compile(r"通信作者\s*[:：].+"),
        re.compile(r"通讯作者\s*[:：].+"),
        re.compile(r"DOI\s*[:：]\s*\S+", re.IGNORECASE),
        re.compile(r"中图分类号\s*[:：]\s*\S+"),
        re.compile(r"文献标识码\s*[:：]\s*\S+"),
        re.compile(r"文章编号\s*[:：]\s*\S+"),

        # 版权信息
        re.compile(r"版权所有.*?翻印必究"),
        re.compile(r"©\s*\d{4}.*?保留所有权利", re.IGNORECASE),
        re.compile(r"All\s+Rights\s+Reserved", re.IGNORECASE),

        # 编辑部信息
        re.compile(r"本刊编辑部"),
        re.compile(r"投稿网址\s*[:：].*"),
        re.compile(r"编辑部地址\s*[:：].*"),
    ]

    # 章节标题模式（用于切分）
    SECTION_PATTERNS: ClassVar[List[re.Pattern]] = [
        # 一级标题
        re.compile(r"^第[一二三四五六七八九十百千\d]+[章篇部]\s*.+"),
        # 二级标题
        re.compile(r"^第[一二三四五六七八九十\d]+[节条款]\s*.+"),
        re.compile(r"^[一二三四五六七八九十]+[、.．]\s*.{2,50}$"),
        # 三级标题
        re.compile(r"^\d+[、.．]\s*.{2,50}$"),
        re.compile(r"^[（(][一二三四五六七八九十\d]+[)）]\s*.+"),
        # 四级标题
        re.compile(r"^\d+\.\d+\s+.{2,60}$"),
        re.compile(r"^\d+\.\d+\.\d+\s+.{2,60}$"),
        # 特殊章节
        re.compile(r"^摘\s*要\s*$"),
        re.compile(r"^Abstract\s*$", re.IGNORECASE),
        re.compile(r"^关键词\s*[:：]?", re.IGNORECASE),
        re.compile(r"^Keywords?\s*[:：]?", re.IGNORECASE),
        re.compile(r"^引\s*言\s*$"),
        re.compile(r"^前\s*言\s*$"),
        re.compile(r"^概\s*述\s*$"),
        re.compile(r"^背\s*景\s*$"),
        re.compile(r"^结\s*论\s*$"),
        re.compile(r"^结\s*语\s*$"),
        re.compile(r"^讨\s*论\s*$"),
        re.compile(r"^致\s*谢\s*$"),
        re.compile(r"^附\s*录\s*$"),
        re.compile(r"^Acknowledgment", re.IGNORECASE),
    ]


class TextCleaner:
    """
    文本清洗器。

    执行多层次的文本规范化和噪声移除。

    设计特点：
    - 流水线处理：按顺序执行多个清洗步骤
    - 可配置：通过配置对象控制各项行为
    - 高性能：正则表达式预编译
    """
    # Unicode 全角到半角的转换范围
    _FULLWIDTH_START: ClassVar[int] = 0xFF01
    _FULLWIDTH_END: ClassVar[int] = 0xFF5E
    _FULLWIDTH_OFFSET: ClassVar[int] = 0xFEE0
    _FULLWIDTH_SPACE: ClassVar[int] = 0x3000

    def __init__(self, config: Optional[CleanerConfig] = None):
        """
        初始化清洗器。

        Args:
            config: 清洗器配置，为 None 时使用默认配置
        """
        self.config = config or CleanerConfig()

    def clean(self, text: str) -> str:
        """
        执行完整的清洗流程。

        Args:
            text: 原始文本

        Returns:
            清洗后的文本
        """
        if not text or not text.strip():
            return ""

        # 1. 基础规范化
        text = self._normalize_basic(text)

        # 2. 去除页眉页脚
        if self.config.remove_headers or self.config.remove_footers:
            text = self._remove_headers_footers(text)

        # 3. 去除目录
        if self.config.remove_toc:
            text = self._remove_toc(text)

        # 4. 去除参考文献
        if self.config.remove_references:
            text = self._remove_references(text)

        # 5. 去除噪声模式
        if self.config.remove_noise:
            text = self._remove_noise(text)

        # 6. 最终规范化
        text = self._normalize_final(text)

        return text

    def _normalize_basic(self, text: str) -> str:
        """基础规范化：换行符、全角转半角"""
        # 统一换行符
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # 全角转半角
        if self.config.fullwidth_to_halfwidth:
            text = self._fullwidth_to_halfwidth(text)

        return text

    def _fullwidth_to_halfwidth(self, text: str) -> str:
        """
        全角字符转半角。

        转换范围：
        - 全角字母和数字 → 半角
        - 全角空格 → 半角空格
        """
        result = []
        for char in text:
            code = ord(char)
            if self._FULLWIDTH_START <= code <= self._FULLWIDTH_END:
                result.append(chr(code - self._FULLWIDTH_OFFSET))
            elif code == self._FULLWIDTH_SPACE:
                result.append(" ")
            else:
                result.append(char)
        return "".join(result)

    def _remove_headers_footers(self, text: str) -> str:
        """去除页眉页脚"""
        lines = text.split("\n")
        cleaned = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned.append(line)
                continue

            is_header_footer = any(
                p.match(stripped) for p in PatternRegistry.HEADER_FOOTER_PATTERNS
            )
            if not is_header_footer:
                cleaned.append(line)

        return "\n".join(cleaned)

    def _remove_toc(self, text: str) -> str:
        """
        去除目录部分。

        使用状态机检测目录区域的起止。
        """
        lines = text.split("\n")
        cleaned = []
        in_toc = False
        toc_line_count = 0

        for line in lines:
            stripped = line.strip()

            # 检测目录开始
            if not in_toc:
                is_toc_title = any(
                    p.match(stripped) for p in PatternRegistry.TOC_TITLE_PATTERNS
                )
                if is_toc_title:
                    in_toc = True
                    toc_line_count = 0
                    continue

            if in_toc:
                toc_line_count += 1

                # 检查是否仍在目录区域
                is_toc_entry = any(
                    p.match(stripped) for p in PatternRegistry.TOC_ENTRY_PATTERNS
                )

                # 目录结束条件
                if (
                    not is_toc_entry
                    and stripped
                    and len(stripped) > 50
                    and not stripped.endswith((".", "。", "…"))
                ):
                    # 遇到非目录格式的长文本行，可能是正文开始
                    in_toc = False
                    cleaned.append(line)
                elif toc_line_count > Constants.MAX_TOC_LINES:
                    # 超过最大目录行数，强制结束
                    in_toc = False
                # 否则跳过这行（仍在目录中）
            else:
                cleaned.append(line)

        return "\n".join(cleaned)

    def _remove_references(self, text: str) -> str:
        """去除参考文献部分"""
        for pattern in PatternRegistry.REFERENCE_START_PATTERNS:
            match = pattern.search(text)
            if match:
                # 找到参考文献开始位置，截断
                text = text[:match.start()].rstrip()
                break
        return text

    def _remove_noise(self, text: str) -> str:
        """去除各种噪声模式"""
        for pattern in PatternRegistry.NOISE_PATTERNS:
            text = pattern.sub("", text)
        return text

    def _normalize_final(self, text: str) -> str:
        """最终规范化"""
        if self.config.normalize_whitespace:
            # 压缩连续空白（保留换行）
            text = re.sub(r"[ \t]+", " ", text)
            # 压缩连续空行
            max_newlines = self.config.max_consecutive_newlines
            text = re.sub(rf"\n{{{max_newlines + 1},}}",
                          "\n" * max_newlines, text)

        # 去除每行首尾空白
        lines = [line.strip() for line in text.split("\n")]

        # 过滤过短的行（如果配置了）
        if self.config.min_line_length > 0:
            lines = [
                line for line in lines
                if not line or len(line) >= self.config.min_line_length
            ]

        text = "\n".join(lines)

        return text.strip()

# ==============================================================================
# 文本切分器
# ==============================================================================


class SmartSplitter:
    """
    智能文本切分器。

    支持多种切分策略：
    1. 章节优先：识别标题结构，按章节边界切分
    2. 段落感知：按空行分段，智能合并短段落
    3. 长度控制：硬切超长文本时优先在句子边界

    设计特点：
    - 递归处理：大章节会进一步按段落切分
    - 智能合并：自动合并过短的片段
    - 边界优化：尽量在句子边界切分
    """
    # 句子结束标点
    SENTENCE_ENDS: ClassVar[tuple] = (
        "。", "！", "？", "；", ".", "!", "?", ";", "\n")

    def __init__(self, config: Optional[SplitterConfig] = None):
        """
        初始化切分器。

        Args:
            config: 切分器配置
        """
        self.config = config or SplitterConfig()

    def split(self, text: str) -> List[str]:
        """
        执行文本切分。

        Args:
            text: 待切分文本

        Returns:
            切分后的文本片段列表
        """
        if not text or not text.strip():
            return []

        text = text.strip()

        # 文本过短，直接返回
        if len(text) < self.config.min_chars:
            return [text] if text else []

        # 文本在范围内，直接返回
        if len(text) <= self.config.max_chars:
            return [text]

        # 尝试按章节切分
        if self.config.prefer_section:
            sections = self._split_by_sections(text)
            if len(sections) > 1:
                # 对每个章节递归处理
                parts = []
                for section in sections:
                    parts.extend(self._ensure_length_limit(section))
                return self._merge_short_parts(parts)

        # 按段落和长度切分
        parts = self._split_by_paragraphs(text)
        return self._merge_short_parts(parts)

    def _split_by_sections(self, text: str) -> List[str]:
        """
        按章节标题切分文本。

        识别多级标题结构，在标题处进行切分。

        Args:
            text: 待切分文本

        Returns:
            按章节切分的片段列表
        """
        lines = text.split("\n")
        sections: List[str] = []
        current_section: List[str] = []

        for line in lines:
            stripped = line.strip()
            is_header = self._is_section_header(stripped)

            if is_header and current_section:
                # 保存当前章节，开始新章节
                section_text = "\n".join(current_section).strip()
                if section_text:
                    sections.append(section_text)
                current_section = [line]
            else:
                current_section.append(line)

        # 保存最后一个章节
        if current_section:
            section_text = "\n".join(current_section).strip()
            if section_text:
                sections.append(section_text)

        return sections

    def _is_section_header(self, text: str) -> bool:
        """检查是否是章节标题"""
        if not text or len(text) > 100:  # 标题不会太长
            return False
        return any(p.match(text) for p in PatternRegistry.SECTION_PATTERNS)

    def _split_by_paragraphs(self, text: str) -> List[str]:
        """
        按段落切分文本。

        使用空行作为段落分隔符，然后合并段落以满足长度要求。

        Args:
            text: 待切分文本

        Returns:
            切分后的片段列表
        """
        # 按空行分段
        paragraphs = [p.strip()
                      for p in re.split(r"\n\s*\n", text) if p.strip()]

        if not paragraphs:
            return []

        return self._merge_paragraphs(paragraphs)

    def _merge_paragraphs(self, paragraphs: List[str]) -> List[str]:
        """
        合并段落，控制每个片段的长度。

        Args:
            paragraphs: 段落列表

        Returns:
            合并后的片段列表
        """
        parts: List[str] = []
        buffer: List[str] = []
        buffer_len = 0

        for para in paragraphs:
            para_len = len(para)

            # 单个段落超长，需要硬切
            if para_len > self.config.max_chars:
                # 先保存缓冲区
                if buffer:
                    parts.append("\n\n".join(buffer))
                    buffer = []
                    buffer_len = 0
                # 硬切超长段落
                parts.extend(self._hard_split(para))
                continue

            # 计算加入当前段落后的长度（+2 是段落分隔符 "\n\n"）
            new_len = buffer_len + para_len + (2 if buffer else 0)

            if new_len > self.config.max_chars:
                # 超长了，需要决定是否保存缓冲区
                if buffer_len >= self.config.min_chars:
                    # 缓冲区已满足最小长度，保存并开始新缓冲区
                    parts.append("\n\n".join(buffer))
                    buffer = [para]
                    buffer_len = para_len
                else:
                    # 缓冲区太短，继续累加（可能会超过 max_chars）
                    buffer.append(para)
                    buffer_len = new_len
            else:
                buffer.append(para)
                buffer_len = new_len

        # 保存剩余缓冲区
        if buffer:
            parts.append("\n\n".join(buffer))

        return parts

    def _hard_split(self, text: str) -> List[str]:
        """
        硬切超长文本。

        尝试在句子边界切分，失败则按字符数切分。

        Args:
            text: 超长文本

        Returns:
            切分后的片段列表
        """
        parts: List[str] = []
        remaining = text

        while len(remaining) > self.config.max_chars:
            # 在最大长度附近寻找句子边界
            split_pos = self._find_sentence_boundary(
                remaining,
                self.config.max_chars
            )
            parts.append(remaining[:split_pos].strip())
            remaining = remaining[split_pos:].strip()

        if remaining:
            parts.append(remaining)

        return parts

    def _find_sentence_boundary(self, text: str, target_pos: int) -> int:
        """
        在目标位置附近寻找句子边界。

        搜索策略：
        1. 在目标位置前后一定范围内搜索
        2. 优先选择最接近目标位置的句子结束标点
        3. 找不到则直接在目标位置切分

        Args:
            text: 文本
            target_pos: 目标位置

        Returns:
            最佳切分位置
        """
        search_range = Constants.SENTENCE_BOUNDARY_SEARCH_RANGE
        search_start = max(0, target_pos - search_range)
        search_end = min(len(text), target_pos + search_range)

        # 优先在目标位置之前找
        best_pos = -1
        for end_char in self.SENTENCE_ENDS:
            # 在目标位置之前寻找
            pos = text.rfind(end_char, search_start, target_pos)
            if pos > best_pos:
                best_pos = pos

        if best_pos != -1:
            return best_pos + 1

        # 在目标位置之后找
        for end_char in self.SENTENCE_ENDS:
            pos = text.find(end_char, target_pos, search_end)
            if pos != -1:
                return pos + 1

        # 找不到句子边界，直接在目标位置切
        return target_pos

    def _ensure_length_limit(self, text: str) -> List[str]:
        """确保文本不超过最大长度"""
        text = text.strip()
        if not text:
            return []
        if len(text) <= self.config.max_chars:
            return [text]
        return self._split_by_paragraphs(text)

    def _merge_short_parts(self, parts: List[str]) -> List[str]:
        """
        合并过短的片段。

        遍历片段列表，将过短的片段与相邻片段合并。

        Args:
            parts: 片段列表

        Returns:
            合并后的片段列表
        """
        if len(parts) <= 1:
            return [p for p in parts if p.strip()]

        merged: List[str] = []
        i = 0

        while i < len(parts):
            current = parts[i].strip()
            if not current:
                i += 1
                continue

            # 如果当前部分过短，尝试与后续部分合并
            while (
                len(current) < self.config.min_chars
                and i + 1 < len(parts)
            ):
                next_part = parts[i + 1].strip()
                combined_len = len(current) + len(next_part) + 2

                if combined_len <= self.config.max_chars:
                    i += 1
                    current = current + "\n\n" + next_part
                else:
                    break

            merged.append(current)
            i += 1

        # 最后一个如果太短，与前一个合并
        if len(merged) >= 2:
            last = merged[-1]
            second_last = merged[-2]
            if len(last) < self.config.min_chars // 2:
                combined_len = len(second_last) + len(last) + 2
                if combined_len <= self.config.max_chars:
                    merged[-2] = second_last + "\n\n" + last
                    merged.pop()

        return [p for p in merged if p.strip()]

# ==============================================================================
# LLM 语义切分器
# ==============================================================================


class LLMSemanticSplitter:
    """
    基于 LLM 的语义感知切分器。
    利用大模型理解文本语义，实现：
    - 语义边界切分：在主题转换处切分，而非硬性字符数
    - 质量筛选：识别并过滤与目标领域无关的内容
    - 错误恢复：LLM 调用失败时自动回退到规则切分

    设计特点：
    - 延迟初始化：只在首次使用时创建 LLM 客户端
    - 优雅降级：出错时回退到规则切分
    - 结构化输出：使用 JSON 格式确保输出可解析
    """
    # 系统提示词
    SYSTEM_PROMPT: ClassVar[str] = """你是一名专业的中文语料处理助手，专门负责"长江流域水旱灾害知识图谱"项目的语料切分和筛选工作。
你的任务是：
1. 将长文本按语义边界切分成多个子段落
2. 判断每个子段落是否与水旱灾害领域相关
3. 输出结构化的切分结果
请注意：
● 保持语义完整性：不要在句子中间切断，尽量在主题转换处切分
● 保持上下文：每个子段落应该能独立理解
● 严格过滤：只保留与水旱灾害明确相关的内容
● 只输出 JSON，不要有任何额外文字"""

    def __init__(
        self,
        config: LLMConfig,
        min_chars: int = Constants.DEFAULT_MIN_CHARS,
        max_chars: int = Constants.DEFAULT_MAX_CHARS,
        fallback_splitter: Optional[SmartSplitter] = None,
        show_llm_output: bool = False,
    ):
        """
        初始化 LLM 语义切分器。

        Args:
            config: LLM 配置
            min_chars: 子段落最小字符数
            max_chars: 子段落最大字符数
            fallback_splitter: 失败时的回退切分器
            show_llm_output: 是否打印 LLM 调用信息（控制台，不写日志）
        """
        self.config = config
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.fallback_splitter = fallback_splitter or SmartSplitter(
            SplitterConfig(min_chars=min_chars, max_chars=max_chars)
        )
        self.show_llm_output = show_llm_output

        # LLM 后端（延迟初始化）
        self._llm_backend = None
        self._init_attempted = False

    @property
    def llm_backend(self):
        """
        延迟初始化 LLM 后端。

        只在首次访问时创建，避免不必要的资源消耗。
        """
        if self._llm_backend is None and not self._init_attempted:
            self._init_attempted = True
            _ensure_llm_imports()

            if _LLMFactory is None:
                if self.show_llm_output:
                    print("❌ LLM 模块不可用，请检查 kg/llm_core.py 是否存在")
                logger.warning(
                    f"LLM 后端初始化失败: LLM 模块不可用 (provider={self.config.provider}, model={self.config.model_name})"
                )
                return None

            try:
                self._llm_backend = _LLMFactory.create(
                    self.config.to_factory_dict())
                if self.show_llm_output:
                    print(f"✅ LLM 后端初始化成功: {self.config.provider}/{self.config.model_name}")
                logger.info(
                    f"LLM 后端初始化成功: provider={self.config.provider}, model={self.config.model_name}"
                )
            except Exception as e:
                if self.show_llm_output:
                    print(f"❌ LLM 后端初始化失败: {e}")
                logger.error(
                    f"LLM 后端初始化失败: provider={self.config.provider}, model={self.config.model_name}, error={e}"
                )

        return self._llm_backend

    def validate_backend(self) -> bool:
        """
        验证 LLM 后端是否可用。
        
        用于在程序启动时提前检测 LLM 后端状态，
        如果不可用则可以及早退出，避免处理文件时才发现问题。
        
        Returns:
            True 如果 LLM 后端已成功初始化，False 否则
        """
        # 触发延迟初始化
        backend = self.llm_backend
        return backend is not None

    @retry_on_network_error(max_retries=3, initial_delay=5.0)
    def split(self, text: str) -> List[str]:
        """
        使用 LLM 进行语义切分。

        Args:
            text: 待切分文本

        Returns:
            切分后保留的子段落列表
        
        注意：
        - 过长文本会自动分块处理，确保所有内容都经过 LLM
        - 429 错误直接抛出，不重试
        - 网络超时会自动重试
        """
        # 文本过短，直接返回
        if not text or len(text.strip()) < self.min_chars:
            logger.debug(f"文本过短({len(text.strip())} 字符)，跳过 LLM 切分")
            return [text.strip()] if text and text.strip() else []

        # 检查 LLM 是否可用
        if self.llm_backend is None:
            error_msg = (
                f"LLM 后端不可用，无法进行语义切分 "
                f"(provider={self.config.provider}, model={self.config.model_name})"
            )
            if self.show_llm_output:
                print(f"❌ {error_msg}")
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 检查是否需要分块处理
        max_input = Constants.LLM_CHUNK_SIZE
        if len(text) > max_input:
            return self._split_long_text(text)
        
        # 正常处理单块文本
        return self._process_single_chunk(text, chunk_index=0, total_chunks=1)

    def _split_into_chunks(self, text: str) -> List[str]:
        """
        将长文本分成多个块，带有重叠以保持语义连续性。
        
        Args:
            text: 待分块的文本
            
        Returns:
            分块后的文本列表
        """
        chunk_size = Constants.LLM_CHUNK_SIZE
        overlap = Constants.LLM_CHUNK_OVERLAP
        
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk = text[start:end]
            
            # 尝试在自然边界处切分（句号、换行符等）
            if end < len(text):
                # 向前查找最近的自然切分点
                for boundary in ['\n\n', '\n', '。', '！', '？', '。', '. ', '! ', '? ']:
                    last_boundary = chunk.rfind(boundary)
                    if last_boundary > chunk_size * 0.7:  # 至少保留 70% 内容
                        chunk = chunk[:last_boundary + len(boundary)]
                        end = start + len(chunk)
                        break
            
            chunks.append(chunk.strip())
            
            # 下一块从重叠位置开始
            start = end - overlap
            if start >= len(text):
                break
            # 避免最后一块太短
            if len(text) - start < self.min_chars:
                break
        
        return [c for c in chunks if c]  # 过滤空块

    def _split_long_text(self, text: str) -> List[str]:
        """
        分块处理长文本，确保所有内容都经过 LLM。
        
        Args:
            text: 过长的文本
            
        Returns:
            所有块处理后合并的结果
        """
        chunks = self._split_into_chunks(text)
        total_chunks = len(chunks)
        
        if self.show_llm_output:
            print(f"\n📄 文本过长 ({len(text)} 字符)，分成 {total_chunks} 块处理")
        logger.info(f"文本过长 ({len(text)} 字符)，分成 {total_chunks} 块处理")
        
        all_segments: List[str] = []
        
        for i, chunk in enumerate(chunks):
            if self.show_llm_output:
                print(f"\n🔄 处理第 {i+1}/{total_chunks} 块 ({len(chunk)} 字符)")
            logger.info(f"处理第 {i+1}/{total_chunks} 块 ({len(chunk)} 字符)")
            
            try:
                segments = self._process_single_chunk(chunk, chunk_index=i, total_chunks=total_chunks)
                all_segments.extend(segments)
            except (_InternalRateLimitError, _InternalAccountBlockedError):
                # 严重错误直接向上抛出
                raise
            except Exception as e:
                logger.warning(f"第 {i+1} 块处理失败: {e}")
                # 其他错误继续处理下一块
                continue
        
        # 去重（因为分块有重叠，可能有重复结果）
        unique_segments = self._deduplicate_segments(all_segments)
        
        if self.show_llm_output:
            print(f"\n✅ 分块处理完成: 共 {len(unique_segments)} 个有效段落")
        logger.info(f"分块处理完成: {total_chunks} 块 -> {len(unique_segments)} 个有效段落")
        
        return unique_segments

    def _deduplicate_segments(self, segments: List[str]) -> List[str]:
        """
        去除重复的段落（基于内容相似度）。
        
        Args:
            segments: 待去重的段落列表
            
        Returns:
            去重后的段落列表
        """
        if not segments:
            return []
        
        unique = []
        seen_texts = set()
        
        for seg in segments:
            # 简化文本用于比较（去除空白）
            normalized = ''.join(seg.split())
            
            # 检查是否为已有段落的子串或超串
            is_duplicate = False
            for seen in seen_texts:
                # 如果当前文本包含在已有文本中，或者非常相似
                if normalized in seen or seen in normalized:
                    is_duplicate = True
                    break
                # 简单的相似度检查：前100字符相同
                if len(normalized) > 100 and len(seen) > 100:
                    if normalized[:100] == seen[:100]:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                unique.append(seg)
                seen_texts.add(normalized)
        
        return unique

    def _process_single_chunk(self, text: str, chunk_index: int = 0, total_chunks: int = 1) -> List[str]:
        """
        处理单个文本块。
        
        Args:
            text: 待处理的文本块
            chunk_index: 当前块索引
            total_chunks: 总块数
            
        Returns:
            处理后的段落列表
        """
        # 在调用 LLM 之前打印信息
        if self.show_llm_output:
            chunk_info = f" [块 {chunk_index+1}/{total_chunks}]" if total_chunks > 1 else ""
            print(f"\n{'='*60}")
            print(f"🤖 LLM 调用信息{chunk_info}")
            print(f"{'='*60}")
            print(f"  • 厂商: {self.config.provider}")
            print(f"  • 模型: {self.config.model_name}")
            print(f"  • 温度: {self.config.temperature}")
            print(f"  • 输入长度: {len(text)} 字符")
            print(f"{'='*60}")
            print(f"🔄 正在调用 LLM...")
        
        # LLM 后端初始化成功，打印 API Key 信息
        if self.show_llm_output:
            # 尝试从 llm_backend 获取实际使用的 API Key
            actual_api_key = None
            if hasattr(self.llm_backend, 'api_key'):
                actual_api_key = self.llm_backend.api_key
            elif hasattr(self.llm_backend, 'client') and hasattr(self.llm_backend.client, 'api_key'):
                actual_api_key = self.llm_backend.client.api_key
            
            if actual_api_key:
                api_key_display = "***" + actual_api_key[-6:] if len(actual_api_key) > 6 else "已配置"
            elif self.config.api_key:
                api_key_display = "***" + self.config.api_key[-6:] if len(self.config.api_key) > 6 else "已配置"
            else:
                api_key_display = "未配置（使用环境变量）"
            
            print(f"  • API Key: {api_key_display}")

        # 构建用户提示词
        user_prompt = self._build_user_prompt(text)

        try:
            # 调用 LLM
            logger.info(
                f"LLM 调用开始 provider={self.config.provider}, model={self.config.model_name}, "
                f"temp={self.config.temperature}, text_len={len(text)}"
            )
            response = self.llm_backend.chat_messages(
                [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                json_mode=True,
                response_format={"type": "json_object"},
            )

            # 打印 LLM 输出（只打印到控制台，不写日志）
            if self.show_llm_output:
                print(f"\n✅ LLM 响应成功 ({len(response)} 字符):")
                print(f"{'~'*60}")
                # 截取显示，避免输出过长
                display_response = response[:1000] + "..." if len(response) > 1000 else response
                print(display_response)
                print(f"{'~'*60}\n")
            # 记录到日志（截断）
            truncated = response[:2000] + ("..." if len(response) > 2000 else "")
            logger.info(f"LLM 响应截断(最多2000字符): {truncated}")

            # 解析结果
            segments = self._parse_response(response)
            if segments:
                if self.show_llm_output:
                    print(f"✅ 切分结果: {len(segments)} 个有效段落")
                logger.info(f"✅ LLM 切分成功: {len(segments)} 个段落，原文长度 {len(text)} 字符")
                return segments

            logger.warning(f"⚠️ LLM 返回空结果 (text_len={len(text)})")
            if self.show_llm_output:
                print(f"⚠️ LLM 返回空结果")
            # 返回空列表，不回退到规则切分
            return []

        except Exception as e:
            # 打印错误信息
            if self.show_llm_output:
                print(f"\n❌ LLM 调用失败: {e}")
            logger.warning(f"❌ LLM 调用失败: {e}, text_len={len(text)}")

            # 429 限流：优雅退出（交给上层保存缓存并终止）
            if _is_rate_limit_error(e):
                logger.error("⚠️ LLM 调用遇到限流 (429)，立即停止")
                raise _InternalRateLimitError(str(e)) from e

            # 401 账号问题：立即停止
            if _is_account_blocked_error(e):
                logger.error("❌ LLM 账号被封禁 (401)")
                raise _InternalAccountBlockedError(str(e)) from e

            # 网络异常：让装饰器处理重试/退避
            if isinstance(e, (OSError, IOError)):
                raise

            # 解析/其他异常：记录日志并抛出
            logger.error(f"❌ LLM 语义切分失败: {e}")
            raise RuntimeError(f"LLM 语义切分失败: {e}") from e

        # 返回空列表（不回退到规则切分）
        return []

    def _build_user_prompt(self, text: str) -> str:
        """构建 LLM 用户提示词"""
        # 此时文本应该已经在上层分块处理过，不应超过最大限制
        # 作为安全保障，仍然检查并截断
        max_input = Constants.MAX_LLM_INPUT_CHARS
        if len(text) > max_input:
            logger.warning(f"文本单块仍超过最大限制 ({len(text)} > {max_input})，将被截断")
            text = text[:max_input]

        return f"""请对以下文本进行语义切分和筛选。
【切分要求】
● 将文本切分为多个子段落，每个子段落长度在 {self.min_chars} ~ {self.max_chars} 字之间
● 在主题转换、章节边界等语义断点处切分
● 保持每个子段落的语义完整性和可读性
【筛选标准】
只保留与以下主题相关的内容：
● 洪水、暴雨洪涝、山洪、城市内涝、干旱等水旱灾害
● 防汛抗旱、水利工程、应急响应等防灾减灾
● 灾害影响、人员伤亡、经济损失等
● 与长江流域相关的水文、气候信息
不保留的内容：
● 纯方法论、算法介绍
● 与水旱灾害无关的其他领域内容
● 乱码、碎片化的文本
【输出格式】
请严格按以下 JSON 格式输出：
{{
    "segments": [
        {{"text": "子段落1的完整内容...", "keep": true, "topic": "主题描述"}},
        {{"text": "子段落2的完整内容...", "keep": false, "reason": "剔除原因"}}
    ]
}}
【待处理文本】

{text}
---"""

    def _parse_response(self, response: str) -> List[str]:
        """
        解析 LLM 响应。

        Args:
            response: LLM 返回的 JSON 字符串

        Returns:
            保留的子段落列表
        """
        if not response:
            return []

        try:
            # 尝试解析 JSON
            data = json.loads(response)

            if not isinstance(data, dict):
                logger.warning(f"LLM 返回非字典格式: {type(data)}")
                return []

            segments = data.get("segments", [])
            if not isinstance(segments, list):
                logger.warning(f"segments 不是列表: {type(segments)}")
                return []

            # 提取保留的子段落
            kept: List[str] = []
            for seg in segments:
                if not isinstance(seg, dict):
                    continue

                text = seg.get("text", "").strip()
                keep = seg.get("keep", True)

                if keep and text:
                    # 验证长度
                    if len(text) >= self.min_chars // 2:  # 允许稍短一些
                        kept.append(text)

            return kept

        except json.JSONDecodeError as e:
            logger.warning(f"LLM 响应 JSON 解析失败: {e}")
            # 尝试从响应中提取文本
            return self._extract_text_fallback(response)

    def _extract_text_fallback(self, response: str) -> List[str]:
        """
        JSON 解析失败时的回退提取方法。

        尝试从响应中提取有效文本。
        """
        # 尝试找到 JSON 块
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                data = json.loads(json_match.group())
                segments = data.get("segments", [])
                return [
                    seg.get("text", "").strip()
                    for seg in segments
                    if isinstance(seg, dict) and seg.get("keep") and seg.get("text")
                ]
            except Exception:
                pass

        return []

# ==============================================================================
# 元数据提取与管理
# ==============================================================================


class MetadataExtractor:
    """
    元数据提取器。
    从文件名和文本内容中提取结构化元数据。

    支持提取：
    - 年份：从文件名或文本中识别 19xx/20xx 年份
    - 省份：识别中国省级行政区划名称
    - 河流：识别长江流域主要河流和湖泊
    - 来源类型：根据关键词推断文档类型
    """
    # 中国省级行政区划（按拼音排序）
    PROVINCES: ClassVar[tuple] = (
        "安徽", "北京", "重庆", "福建", "甘肃", "广东", "广西", "贵州",
        "海南", "河北", "河南", "黑龙江", "湖北", "湖南", "吉林", "江苏",
        "江西", "辽宁", "内蒙古", "宁夏", "青海", "山东", "山西", "陕西",
        "上海", "四川", "天津", "西藏", "新疆", "云南", "浙江",
        "香港", "澳门", "台湾",
    )

    # 长江流域主要河流和湖泊
    YANGTZE_RIVERS: ClassVar[tuple] = (
        # 干流
        "长江", "金沙江", "通天河", "沱沱河",
        # 主要支流
        "雅砻江", "岷江", "大渡河", "青衣江", "嘉陵江", "涪江", "渠江",
        "乌江", "沅江", "澧水", "湘江", "资水", "赣江", "抚河", "信江",
        "饶河", "修水", "汉江", "丹江", "唐白河", "清江",
        # 主要湖泊
        "洞庭湖", "鄱阳湖", "太湖", "巢湖", "洪湖", "洪泽湖",
        # 重要水利枢纽
        "三峡", "葛洲坝", "丹江口", "隔河岩", "水布垭", "向家坝", "溪洛渡",
    )

    # 年份匹配模式
    _YEAR_PATTERN: ClassVar[re.Pattern] = re.compile(r"(19[89]\d|20[0-2]\d)")

    # 来源类型关键词
    _SOURCE_TYPE_KEYWORDS: ClassVar[Dict[SourceType, List[str]]] = {
        SourceType.LAW_REGULATION: ["法", "条例", "规定", "办法", "细则"],
        SourceType.EMERGENCY_PLAN: ["预案", "应急", "防汛", "抗旱"],
        SourceType.GAZETTE_YEARBOOK: ["公报", "年鉴", "年报", "统计"],
        SourceType.TECHNICAL_REPORT: ["报告", "技术", "研究", "分析"],
        SourceType.ACADEMIC_PAPER: ["论文", "学报", "期刊", "硕士", "博士"],
        SourceType.NEWS_ARTICLE: ["新闻", "报道", "记者", "消息"],
        SourceType.GOVERNMENT_DOC: ["通知", "意见", "批复", "函"],
    }

    def __init__(
        self,
        default_source_type: str = "",
        default_url: str = "",
    ):
        """
        初始化元数据提取器。

        Args:
            default_source_type: 默认来源类型
            default_url: 默认 URL
        """
        self.default_source_type = default_source_type
        self.default_url = default_url

    def extract_from_filename(self, filename: str) -> Dict[str, str]:
        """
        从文件名提取元数据。

        Args:
            filename: 文件名（不含扩展名）

        Returns:
            提取的元数据字典
        """
        # 提取年份
        year_match = self._YEAR_PATTERN.search(filename)
        year = year_match.group(1) if year_match else ""

        # 提取省份
        province = self._extract_first_match(filename, self.PROVINCES)

        # 提取河流
        river = self._extract_first_match(filename, self.YANGTZE_RIVERS)

        # 推断来源类型
        source_type = self._infer_source_type(filename)

        return {
            "source_type": source_type or self.default_source_type,
            "year": year,
            "title": filename,
            "url": self.default_url,
            "province": province,
            "river": river,
        }

    def extract_from_text(self, text: str, max_chars: int = 1000) -> Dict[str, str]:
        """
        从文本内容提取补充元数据。

        只分析文本开头部分，通常包含标题和摘要。

        Args:
            text: 文本内容
            max_chars: 分析的最大字符数

        Returns:
            提取的元数据字典
        """
        sample = text[:max_chars] if text else ""
        meta: Dict[str, str] = {}

        # 提取年份
        year_match = self._YEAR_PATTERN.search(sample)
        if year_match:
            meta["year"] = year_match.group(1)

        # 提取省份和河流
        province = self._extract_first_match(sample, self.PROVINCES)
        if province:
            meta["province"] = province

        river = self._extract_first_match(sample, self.YANGTZE_RIVERS)
        if river:
            meta["river"] = river

        return meta

    @staticmethod
    def _extract_first_match(text: str, candidates: tuple) -> str:
        """从文本中提取第一个匹配的候选项"""
        for candidate in candidates:
            if candidate in text:
                return candidate
        return ""

    def _infer_source_type(self, text: str) -> str:
        """根据关键词推断来源类型"""
        for source_type, keywords in self._SOURCE_TYPE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return source_type.value
        return ""

    @staticmethod
    def compute_md5(text: str, length: int = Constants.MD5_HASH_LENGTH) -> str:
        """
        计算文本的 MD5 哈希值。

        Args:
            text: 文本内容
            length: 返回的哈希长度

        Returns:
            截断后的 MD5 哈希
        """
        return hashlib.md5(text.encode("utf-8")).hexdigest()[:length]

# ==============================================================================
# 输出管理器
# ==============================================================================


class OutputManager:
    """
    输出管理器。
    负责文件输出、目录结构管理和去重。

    特点：
    - 结构保留：可选保留原始目录结构
    - 去重机制：基于 MD5 哈希避免重复输出
    - 元数据：每个分片附带 .meta.json 文件
    - 索引生成：批量处理后生成完整索引
    """

    def __init__(
        self,
        output_dir: Path,
        preserve_structure: bool = True,
    ):
        """
        初始化输出管理器。

        Args:
            output_dir: 输出根目录
            preserve_structure: 是否保留原始目录结构
        """
        self.output_dir = output_dir
        self.preserve_structure = preserve_structure
        self._written_hashes: Set[str] = set()
        self._lock = threading.Lock()

        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build_output_name(
        self,
        stem: str,
        meta: Dict[str, str],
        part_index: int,
    ) -> str:
        """
        构建输出文件名。

        格式: {stem}_part{index}__{key1}-{val1}__{key2}-{val2}...

        Args:
            stem: 原始文件名主干
            meta: 元数据字典
            part_index: 分片索引

        Returns:
            构建的文件名（不含扩展名）
        """
        # 清理原始文件名中的非法字符
        safe_stem = re.sub(r'[\\/:*?"<>|\s]+', "_", stem)
        safe_stem = safe_stem[:50]  # 限制长度

        # 基础名称
        parts = [f"{safe_stem}_part{part_index:03d}"]

        # 添加关键元数据
        for key in ("year", "province", "river"):
            val = meta.get(key, "")
            if val:
                safe_val = re.sub(r'[\\/:*?"<>|\s]+', "_", val)[:20]
                parts.append(f"{key}_{safe_val}")

        return "__".join(parts)

    def write_parts(
        self,
        parts: List[str],
        source_file: str,
        rel_dir: Optional[Path] = None,
        meta_extra: Optional[Dict[str, str]] = None,
    ) -> List[Tuple[Path, DocumentMeta]]:
        """
        写入切分后的文本片段。

        Args:
            parts: 文本片段列表
            source_file: 原始文件名
            rel_dir: 相对目录路径（用于保留结构）
            meta_extra: 额外元数据

        Returns:
            (输出路径, 元数据) 的列表
        """
        # 确定目标目录
        target_dir = self.output_dir
        if self.preserve_structure and rel_dir:
            target_dir = self.output_dir / rel_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        written: List[Tuple[Path, DocumentMeta]] = []
        total = len(parts)
        stem = Path(source_file).stem
        meta_extra = meta_extra or {}

        # 同一源文件共享的 group_id，便于后续上下文拼接
        group_seed = f"{rel_dir}/{source_file}"
        group_id = MetadataExtractor.compute_md5(group_seed, length=12)

        # 预先计算所有片段的 md5，便于关联前后片段
        part_md5_list: List[str] = []
        for chunk in parts:
            part_md5_list.append(MetadataExtractor.compute_md5(chunk))

        for idx, chunk in enumerate(parts, start=1):
            chunk = chunk.strip()
            if not chunk:
                continue

            # 计算哈希并检查去重
            md5_hash = part_md5_list[idx - 1]

            with self._lock:
                if md5_hash in self._written_hashes:
                    logger.debug(f"跳过重复片段: {md5_hash[:8]}...")
                    continue
                self._written_hashes.add(md5_hash)

            # 前后片段 id（用于后续上下文拼接）
            prev_id = part_md5_list[idx - 2] if idx > 1 else ""
            next_id = part_md5_list[idx] if idx < total else ""

            # 构建元数据
            meta = DocumentMeta(
                source_file=source_file,
                part_index=idx,
                total_parts=total,
                char_count=len(chunk),
                md5_hash=md5_hash,
                prev_part_id=prev_id,
                next_part_id=next_id,
                group_id=group_id,
                source_type=meta_extra.get("source_type", ""),
                year=meta_extra.get("year", ""),
                title=meta_extra.get("title", ""),
                url=meta_extra.get("url", ""),
                province=meta_extra.get("province", ""),
                river=meta_extra.get("river", ""),
            )

            # 构建文件名
            name_base = self.build_output_name(stem, meta_extra, idx)

            # 写入文本文件
            text_path = target_dir / f"{name_base}.txt"
            text_path.write_text(chunk, encoding="utf-8")

            # 写入元数据文件
            meta_path = target_dir / f"{name_base}.meta.json"
            meta_path.write_text(meta.to_json(), encoding="utf-8")

            written.append((text_path, meta))
            logger.debug(f"写入: {text_path.name} ({len(chunk)} 字符)")

        return written

    def generate_index(self, result: BatchResult) -> Path:
        """
        生成处理结果索引文件。

        Args:
            result: 批量处理结果

        Returns:
            索引文件路径
        """
        index_path = self.output_dir / "_corpus_index.json"

        index_data = {
            "tool_name": Constants.TOOL_NAME,
            "tool_version": Constants.VERSION,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {
                "total_files": result.total_files,
                "total_parts": result.total_parts,
                "success_count": result.success_count,
                "skipped_count": result.skipped_count,
                "failed_count": result.failed_count,
                "duration_seconds": round(result.duration_seconds, 2),
            },
            "success": [
                {
                    "path": str(r.path),
                    "parts_count": r.parts_count,
                    "output_paths": [str(p) for p in r.output_paths],
                }
                for r in result.successful_results
            ],
            "skipped": [
                {"path": str(r.path), "message": r.message}
                for r in result.skipped_results
            ],
            "failed": [
                {
                    "path": str(r.path),
                    "message": r.message,
                    "error_type": r.error_type,
                }
                for r in result.failed_results
            ],
        }

        index_path.write_text(
            json.dumps(index_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info(f"索引已保存: {index_path}")
        return index_path

# ==============================================================================
# 文件处理器
# ==============================================================================


class FileProcessor:
    """
    单文件处理器。
    整合提取、清洗、切分流程，处理单个文件。

    处理流程：
    1. 文本提取
    2. 文本清洗
    3. 有效性检查
    4. 元数据提取
    5. 文本切分
    6. 结果输出
    """

    def __init__(
        self,
        extractor_factory: ExtractorFactory,
        cleaner: TextCleaner,
        splitter: SmartSplitter,
        llm_splitter: Optional[LLMSemanticSplitter] = None,
        meta_extractor: Optional[MetadataExtractor] = None,
        output_manager: Optional[OutputManager] = None,
        use_llm_split: bool = False,
    ):
        """
        初始化文件处理器。

        Args:
            extractor_factory: 文本提取器工厂
            cleaner: 文本清洗器
            splitter: 规则切分器
            llm_splitter: LLM 切分器（可选）
            meta_extractor: 元数据提取器
            output_manager: 输出管理器
            use_llm_split: 是否优先使用 LLM 切分
        """
        self.extractor_factory = extractor_factory
        self.cleaner = cleaner
        self.splitter = splitter
        self.llm_splitter = llm_splitter
        self.meta_extractor = meta_extractor or MetadataExtractor()
        self.output_manager = output_manager
        self.use_llm_split = use_llm_split

    def process(
        self,
        path: Path,
        rel_dir: Optional[Path] = None,
    ) -> ProcessingResult:
        """
        处理单个文件。

        Args:
            path: 文件路径
            rel_dir: 相对目录路径

        Returns:
            处理结果
        """
        start_time = time.time()

        try:
            # 1. 提取文本
            raw_text = self.extractor_factory.extract(path)
            logger.debug(f"提取文本: {path.name} ({len(raw_text)} 字符)")

            # 2. 清洗文本
            clean_text = self.cleaner.clean(raw_text)
            logger.debug(f"清洗后: {len(clean_text)} 字符")

            # 3. 检查有效内容
            if len(clean_text) < Constants.MIN_VALID_TEXT_LENGTH:
                return ProcessingResult(
                    path=path,
                    status=ProcessingStatus.SKIPPED,
                    message=f"清洗后文本过短（{len(clean_text)} 字符），可能是扫描版或空白文档",
                    processing_time_seconds=time.time() - start_time,
                )

            # 4. 提取元数据
            meta = self.meta_extractor.extract_from_filename(path.stem)
            text_meta = self.meta_extractor.extract_from_text(clean_text)
            # 合并（文件名优先，文本内容补充）
            for key, value in text_meta.items():
                if not meta.get(key):
                    meta[key] = value

            # 5. 切分
            parts = self._perform_split(clean_text)

            if not parts:
                return ProcessingResult(
                    path=path,
                    status=ProcessingStatus.SKIPPED,
                    message="切分后无有效片段",
                    processing_time_seconds=time.time() - start_time,
                )

            # 6. 输出
            output_paths: List[Path] = []
            meta_list: List[DocumentMeta] = []

            if self.output_manager:
                written = self.output_manager.write_parts(
                    parts,
                    str(path.name),
                    rel_dir=rel_dir,
                    meta_extra=meta,
                )
                output_paths = [w[0] for w in written]
                meta_list = [w[1] for w in written]

            return ProcessingResult(
                path=path,
                status=ProcessingStatus.SUCCESS,
                parts_count=len(parts),
                output_paths=output_paths,
                meta_list=meta_list,
                processing_time_seconds=time.time() - start_time,
            )

        except UnsupportedFileTypeError as e:
            return ProcessingResult(
                path=path,
                status=ProcessingStatus.SKIPPED,
                message=e.message,
                error_type=type(e).__name__,
                processing_time_seconds=time.time() - start_time,
            )

        except (_InternalRateLimitError, _InternalAccountBlockedError):
            # 重新抛出 LLM 严重错误，让上层处理
            raise

        except Exception as e:
            # 检查是否为外部 LLM 模块的限流/封禁错误
            if _is_llm_critical_error(e):
                raise
            
            logger.error(f"处理失败: {path}, 错误: {e}")
            return ProcessingResult(
                path=path,
                status=ProcessingStatus.FAILED,
                message=str(e),
                error_type=type(e).__name__,
                error_traceback=traceback.format_exc(),
                processing_time_seconds=time.time() - start_time,
            )

    def _perform_split(self, text: str) -> List[str]:
        """执行切分"""
        parts: List[str] = []

        # 优先尝试 LLM 切分
        if self.use_llm_split and self.llm_splitter:
            try:
                parts = self.llm_splitter.split(text)
            except (_InternalRateLimitError, _InternalAccountBlockedError):
                raise
            except Exception as e:
                # 检查是否为外部 LLM 错误
                if _is_llm_critical_error(e):
                    raise
                logger.warning(f"LLM 切分失败，回退到规则切分: {e}")

        # 回退或默认使用规则切分
        if not parts:
            parts = self.splitter.split(text)

        return parts

# ==============================================================================
# 批量处理器
# ==============================================================================


class BatchProcessor:
    """
    批量文件处理器。
    
    特点：
    - **并行处理**：使用线程池加速批量任务
    - **进度追踪**：实时显示处理进度
    - **错误恢复**：单个文件失败不影响其他文件
    - **优雅中断**：支持 Ctrl+C 中断后保存进度
    - **断点续运行**：自动跳过已成功处理的文件
    - **429 错误处理**：遇到限流后保存进度并退出
    
    使用示例：
    ```python
    processor = BatchProcessor(
        file_processor=file_proc,
        max_workers=4,
        cache=ProcessingCache(output_dir / ".cache.jsonl"),
    )
    result = processor.process(source_dir)
    ```
    """

    def __init__(
        self,
        file_processor: FileProcessor,
        max_workers: int = Constants.DEFAULT_MAX_WORKERS,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cache: Optional[ProcessingCache] = None,
        skip_processed: bool = True,
    ):
        """
        初始化批量处理器。

        Args:
            file_processor: 单文件处理器
            max_workers: 最大并行工作线程数
            progress_callback: 进度回调函数 (current, total, filename)
            cache: 处理缓存（支持断点续运行）
            skip_processed: 是否跳过已成功处理的文件
        """
        self.file_processor = file_processor
        self.max_workers = max_workers
        self.progress_callback = progress_callback
        self.cache = cache
        self.skip_processed = skip_processed
        self._interrupted = False
        self._rate_limit_hit = False  # 标记是否遇到 429 错误

    def collect_files(self, source: Path) -> List[Path]:
        """
        收集待处理文件。

        Args:
            source: 源路径（文件或目录）

        Returns:
            去重后的文件路径列表
        """
        if source.is_file():
            if source.suffix.lower() in Constants.SUPPORTED_EXTENSIONS:
                return [source]
            logger.warning(f"不支持的文件类型: {source}")
            return []

        seen: Set[Path] = set()
        files: List[Path] = []

        # 递归遍历目录
        for ext in Constants.SUPPORTED_EXTENSIONS:
            for pattern in (f"*{ext}", f"*{ext.upper()}", f"**/*{ext}", f"**/*{ext.upper()}"):
                for path in source.glob(pattern):
                    resolved = path.resolve()
                    if resolved.is_file() and resolved not in seen:
                        seen.add(resolved)
                        files.append(path)

        # 按路径排序，确保处理顺序一致
        files.sort()
        return files

    def process(
        self,
        source: Path,
        source_root: Optional[Path] = None,
        files: Optional[List[Path]] = None,
    ) -> BatchResult:
        """
        批量处理文件。

        Args:
            source: 源路径
            source_root: 用于计算相对路径的根目录
            files: 可选的文件列表，如果传入则直接使用，否则调用 collect_files

        Returns:
            批量处理结果
        """
        start_time = time.time()

        # 收集文件（如果外部未传入）
        if files is None:
            files = self.collect_files(source)
            if not files:
                logger.warning(f"未找到可处理的文件: {source}")
                return BatchResult()
            logger.info(f"收集到 {len(files)} 个待处理文件")
        else:
            if not files:
                logger.warning("传入的文件列表为空")
                return BatchResult()

        result = BatchResult()
        root = source_root or (source if source.is_dir() else source.parent)

        try:
            # 单线程或多线程处理
            if self.max_workers <= 1:
                self._process_sequential(files, root, result)
            else:
                self._process_parallel(files, root, result)
        except KeyboardInterrupt:
            logger.warning("用户中断处理")
            self._interrupted = True

        result.duration_seconds = time.time() - start_time
        return result

    def _process_sequential(
        self,
        files: List[Path],
        root: Path,
        result: BatchResult,
    ) -> None:
        """
        顺序处理文件。
        
        功能增强：
        1. 支持缓存检查，跳过已处理的文件
        2. 捕获 429 错误并保存进度
        3. 记录详细的处理状态
        """
        for i, path in enumerate(files):
            # 检查中断标志
            if self._interrupted or self._rate_limit_hit:
                break

            if self.progress_callback:
                self.progress_callback(i + 1, len(files), path.name)
            
            # 检查缓存：跳过已成功处理的文件
            if self.cache and self.skip_processed:
                if self.cache.is_processed(path, status="success"):
                    logger.debug(f"跳过已处理的文件: {path.name}")
                    result.add_result(ProcessingResult(
                        path=path,
                        status=ProcessingStatus.SKIPPED,
                        message="已在缓存中，跳过",
                    ))
                    continue

            try:
                rel_dir = self._get_relative_dir(path, root)
                proc_result = self.file_processor.process(path, rel_dir)
                result.add_result(proc_result)
                self._log_result(proc_result)
                
                # 更新缓存
                if self.cache:
                    if proc_result.status == ProcessingStatus.SUCCESS:
                        self.cache.mark_processed(
                            path, "success", parts=proc_result.parts_count
                        )
                    elif proc_result.status == ProcessingStatus.FAILED:
                        self.cache.mark_processed(
                            path, "failed", error=proc_result.message
                        )
                    elif proc_result.status == ProcessingStatus.SKIPPED:
                        self.cache.mark_processed(
                            path, "skipped", error=proc_result.message
                        )

            except (_InternalRateLimitError, _InternalAccountBlockedError) as e:
                # 429 限流/封禁错误：不写入缓存，直接停止
                logger.error(f"遇到 LLM 限流/封禁错误，立即停止处理: {e}")
                self._rate_limit_hit = True
                
                # 不将当前文件写入缓存（不标记为 failed）
                # 下次运行时可以重新处理这个文件
                
                # 保存已成功处理的缓存
                if self.cache:
                    self.cache.save(force=True)
                    logger.info(
                        f"已保存处理进度到缓存: {self.cache.cache_path}\n"
                        f"当前文件未写入缓存，下次运行时会重新处理"
                    )
                
                break
            
            except Exception as e:
                # 检查是否为外部 LLM 模块的限流/封禁错误
                if _is_llm_critical_error(e):
                    logger.error(f"遇到 LLM 限流/封禁错误，立即停止处理: {e}")
                    self._rate_limit_hit = True
                    if self.cache:
                        self.cache.save(force=True)
                        logger.info(
                            f"已保存处理进度到缓存: {self.cache.cache_path}\n"
                            f"当前文件未写入缓存，下次运行时会重新处理"
                        )
                    break
                
                # 其他异常：记录为处理失败，写入缓存，继续下一个文件
                logger.error(f"处理文件失败: {path.name}, 错误: {e}")
                result.add_result(ProcessingResult(
                    path=path,
                    status=ProcessingStatus.FAILED,
                    message=str(e),
                    error_type=type(e).__name__,
                    error_traceback=traceback.format_exc(),
                ))
                
                if self.cache:
                    self.cache.mark_processed(
                        path, "failed", error=str(e)
                    )

    def _process_parallel(
        self,
        files: List[Path],
        root: Path,
        result: BatchResult,
    ) -> None:
        """
        并行处理文件。
        
        功能增强：
        1. 支持缓存检查，跳过已处理的文件
        2. 捕莹 429 错误并立即停止所有任务
        3. 线程安全的缓存更新
        4. 优雅处理线程池关闭
        
        注意：
        - 并行处理时遇到 429 会立即取消所有剩余任务
        - 缓存更新是线程安全的（ProcessingCache 内部有锁）
        """
        # 预先过滤已处理的文件
        files_to_process: List[Path] = []
        for path in files:
            if self.cache and self.skip_processed:
                if self.cache.is_processed(path, status="success"):
                    logger.debug(f"跳过已处理的文件: {path.name}")
                    result.add_result(ProcessingResult(
                        path=path,
                        status=ProcessingStatus.SKIPPED,
                        message="已在缓存中，跳过",
                    ))
                    continue
            files_to_process.append(path)
        
        if not files_to_process:
            logger.info("所有文件已处理，无需重复执行")
            return
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交任务
            future_to_path: Dict[Future, Path] = {}
            for path in files_to_process:
                rel_dir = self._get_relative_dir(path, root)
                future = executor.submit(
                    self.file_processor.process, path, rel_dir
                )
                future_to_path[future] = path

            # 收集结果
            completed = 0
            for future in as_completed(future_to_path):
                # 检查是否应该中断
                if self._interrupted or self._rate_limit_hit:
                    logger.warning("检测到中断或限流，取消剩余任务...")
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                completed += 1
                path = future_to_path[future]

                if self.progress_callback:
                    self.progress_callback(completed, len(files_to_process), path.name)

                try:
                    proc_result = future.result()
                    result.add_result(proc_result)
                    self._log_result(proc_result)
                    
                    # 更新缓存（线程安全）
                    if self.cache:
                        if proc_result.status == ProcessingStatus.SUCCESS:
                            self.cache.mark_processed(
                                path, "success", parts=proc_result.parts_count
                            )
                        elif proc_result.status == ProcessingStatus.FAILED:
                            self.cache.mark_processed(
                                path, "failed", error=proc_result.message
                            )
                        elif proc_result.status == ProcessingStatus.SKIPPED:
                            self.cache.mark_processed(
                                path, "skipped", error=proc_result.message
                            )

                except (_InternalRateLimitError, _InternalAccountBlockedError) as e:
                    # 429 限流/封禁错误：不写入缓存，直接停止
                    logger.error(f"遇到 LLM 限流/封禁错误，立即停止处理: {e}")
                    self._rate_limit_hit = True
                    
                    # 不将当前文件写入缓存（不标记为 failed）
                    # 下次运行时可以重新处理这个文件
                    
                    # 保存已成功处理的缓存
                    if self.cache:
                        self.cache.save(force=True)
                        logger.info(
                            f"已保存处理进度到缓存: {self.cache.cache_path}\n"
                            f"当前文件未写入缓存，下次运行时会重新处理"
                        )
                    
                    # 取消剩余任务
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                except Exception as e:
                    # 检查是否为外部 LLM 模块的限流/封禁错误
                    if _is_llm_critical_error(e):
                        logger.error(f"遇到 LLM 限流/封禁错误，立即停止处理: {e}")
                        self._rate_limit_hit = True
                        if self.cache:
                            self.cache.save(force=True)
                            logger.info(
                                f"已保存处理进度到缓存: {self.cache.cache_path}\n"
                                f"当前文件未写入缓存，下次运行时会重新处理"
                            )
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    
                    # 其他异常：记录为处理失败，写入缓存，继续下一个文件
                    logger.error(f"处理文件失败: {path}, 错误: {e}")
                    result.add_result(ProcessingResult(
                        path=path,
                        status=ProcessingStatus.FAILED,
                        message=str(e),
                        error_type=type(e).__name__,
                        error_traceback=traceback.format_exc(),
                    ))
                    
                    if self.cache:
                        self.cache.mark_processed(
                            path, "failed", error=str(e)
                        )

    @staticmethod
    def _get_relative_dir(path: Path, root: Path) -> Optional[Path]:
        """获取相对目录路径"""
        try:
            return path.parent.relative_to(root)
        except ValueError:
            return None

    @staticmethod
    def _log_result(result: ProcessingResult) -> None:
        """记录处理结果"""
        if result.status == ProcessingStatus.SUCCESS:
            logger.info(f"[OK] {result.path.name}: {result.parts_count} 份")
        elif result.status == ProcessingStatus.SKIPPED:
            logger.info(f"[SKIP] {result.path.name}: {result.message}")
        else:
            logger.error(f"[FAIL] {result.path.name}: {result.message}")

# ==============================================================================
# 命令行接口
# ==============================================================================


def create_argument_parser() -> argparse.ArgumentParser:
    """
    创建命令行参数解析器。
    Returns:
        配置好的 ArgumentParser 实例
    """
    parser = argparse.ArgumentParser(
        prog="corpus_cleaner",
        description=f"{Constants.TOOL_NAME} v{Constants.VERSION} - 智能去噪、语义切分、多引擎支持",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例

基础用法：处理目录下所有 PDF/TXT 文件
python3 tools/corpus_cleaner.py --input ./pdfs/ --output-dir ./corpus/
处理单个文件，自定义切分参数
python3 tools/corpus_cleaner.py --input paper.pdf --min-chars 1000 --max-chars 3000
使用 pdfplumber 引擎，移除参考文献
python3 tools/corpus_cleaner.py --input ./docs/ --remove-references --pdf-engine pdfplumber
启用 LLM 语义切分（需要 API 配额）
python3 tools/corpus_cleaner.py --input ./docs/ --llm-split \\
    --llm-provider zhipu --llm-model "GLM-4.5-Air"
试运行模式
python3 tools/corpus_cleaner.py --input ./docs/ --dry-run --verbose
配置优先级

命令行参数 > 环境变量 > 配置文件 (cfg.yaml) > 默认值
环境变量

LLM_PROVIDER      - LLM 提供商 (zhipu/openai/gemini)
LLM_MODEL_NAME    - 模型名称
LLM_API_KEY       - API Key
LLM_BASE_URL      - 自定义 API 地址
LLM_TEMPERATURE   - 温度参数
        """,
    )
    # ===== 必需参数 =====
    parser.add_argument(
        "--input", "-i",
        required=True,
        type=str,
        help="输入文件或目录路径（支持 PDF/TXT）",
    )

    # ===== 输出选项 =====
    output_group = parser.add_argument_group("输出选项")
    output_group.add_argument(
        "--output-dir", "-o",
        type=str,
        default="data/enhancing_onto_corpus_docs",
        help="输出目录 (默认: data/enhancing_onto_corpus_docs)",
    )
    output_group.add_argument(
        "--no-preserve-structure",
        action="store_true",
        help="不保留原始目录结构，所有输出放在同一目录",
    )

    # ===== 切分选项 =====
    split_group = parser.add_argument_group("切分选项")
    split_group.add_argument(
        "--min-chars",
        type=int,
        default=None,
        help=f"切分后单份最小字符数 (默认: {Constants.DEFAULT_MIN_CHARS})",
    )
    split_group.add_argument(
        "--max-chars",
        type=int,
        default=None,
        help=f"切分后单份最大字符数 (默认: {Constants.DEFAULT_MAX_CHARS})",
    )
    split_group.add_argument(
        "--no-section-split",
        action="store_true",
        help="禁用章节智能切分，仅按长度切分",
    )

    # ===== 清洗选项 =====
    clean_group = parser.add_argument_group("清洗选项")
    clean_group.add_argument(
        "--remove-references",
        action="store_true",
        help="移除参考文献部分",
    )
    clean_group.add_argument(
        "--keep-toc",
        action="store_true",
        help="保留目录部分（默认移除）",
    )

    # ===== PDF 选项 =====
    pdf_group = parser.add_argument_group("PDF 解析选项")
    pdf_group.add_argument(
        "--pdf-engine",
        choices=["auto", "pypdf2", "pdfplumber"],
        default="auto",
        help="PDF 解析引擎 (默认: auto，优先尝试 pdfplumber)",
    )

    # ===== LLM 选项 =====
    llm_group = parser.add_argument_group("LLM 选项（语义切分）")
    llm_group.add_argument(
        "--llm-split",
        action="store_true",
        help="启用 LLM 语义切分+筛选（成本更高，需配额）",
    )
    llm_group.add_argument(
        "--llm-provider",
        type=str,
        default=None,
        help="LLM 提供商 (zhipu/openai/gemini)",
    )
    llm_group.add_argument(
        "--llm-model",
        type=str,
        default=None,
        help="LLM 模型名称",
    )
    llm_group.add_argument(
        "--llm-temperature",
        type=float,
        default=None,
        help="LLM 温度参数 (默认: 0.0，更稳定)",
    )
    llm_group.add_argument(
        "--llm-api-key",
        type=str,
        default=None,
        help="LLM API Key（推荐使用环境变量 LLM_API_KEY）",
    )
    llm_group.add_argument(
        "--llm-base-url",
        type=str,
        default=None,
        help="LLM API Base URL（用于自部署接口）",
    )
    llm_group.add_argument(
        "--llm-thinking",
        choices=["enabled", "disabled"],
        default=None,
        help="LLM 深度思考模式（仅 zhipu 有效）",
    )

    # ===== 元数据选项 =====
    meta_group = parser.add_argument_group("元数据选项")
    meta_group.add_argument(
        "--source-type",
        type=str,
        default="",
        help="来源类型 (law_regulation/emergency_plan/gazette_yearbook/...)",
    )
    meta_group.add_argument(
        "--default-url",
        type=str,
        default="",
        help="默认来源 URL",
    )

    # ===== 运行选项 =====
    run_group = parser.add_argument_group("运行选项")
    run_group.add_argument(
        "--workers", "-w",
        type=int,
        default=None,
        help=f"并行处理线程数 (默认: {Constants.DEFAULT_MAX_WORKERS})",
    )
    run_group.add_argument(
        "--cfg",
        type=str,
        default="configs/cfg.yaml",
        help="配置文件路径 (默认: configs/cfg.yaml)",
    )
    run_group.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细日志",
    )
    run_group.add_argument(
        "--dry-run",
        action="store_true",
        help="试运行，只显示将要处理的文件，不实际处理",
    )
    run_group.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="最多处理文件数（用于测试）",
    )
    run_group.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="日志文件路径（可以是目录，会自动生成文件名）",
    )
    run_group.add_argument(
        "--show-llm-output",
        action="store_true",
        help="在控制台打印 LLM 调用信息和输出（不写入日志）",
    )
    run_group.add_argument(
        "--no-cache",
        action="store_true",
        help="禁用缓存，不支持断点续运行",
    )
    run_group.add_argument(
        "--clear-cache",
        action="store_true",
        help="清空缓存，重新处理所有文件",
    )
    run_group.add_argument(
        "--clear-output",
        action="store_true",
        help="处理前清空输出目录（慎用，会删除 output-dir 下现有文件）",
    )

    return parser


def print_banner(
    config: ProcessingConfig,
    files_count: int,
    output_dir: Path,
) -> None:
    """打印启动横幅"""
    banner = f"""
{'=' * 70}
  {Constants.TOOL_NAME} v{Constants.VERSION}
{'=' * 70}
  📁 待处理文件: {files_count} 个
  📂 输出目录: {output_dir}
  📏 字符范围: {config.splitter.min_chars} - {config.splitter.max_chars}
  🔧 PDF 引擎: {config.pdf_engine}
  👷 并行线程: {config.max_workers}
"""
    if config.use_llm_split and config.llm:
        banner += f"  🤖 LLM 切分: ON | {config.llm.provider}/{config.llm.model_name}\n"
    else:
        banner += "  🤖 LLM 切分: OFF\n"

    banner += f"\n{'=' * 70}"
    print(banner)


def _resolve_log_file_path(log_path_str: str) -> Path:
    """
    解析日志文件路径，确保多次运行能追加到同一个文件。
    
    支持的输入格式：
    - 完整文件路径: ./logs/app.log -> 直接使用
    - 无后缀路径: ./logs/app -> 自动添加 .log 后缀
    - 目录路径: ./logs/ -> 在目录下创建 corpus_cleaner.log
    
    Args:
        log_path_str: 用户输入的日志路径字符串
        
    Returns:
        解析后的日志文件 Path 对象
    """
    log_path = Path(log_path_str)
    
    # 情况 1: 已存在的目录
    if log_path.exists() and log_path.is_dir():
        log_file = log_path / "corpus_cleaner.log"
        return log_file
    
    # 情况 2: 路径以 / 或 \\ 结尾，明确是目录
    if log_path_str.endswith('/') or log_path_str.endswith('\\'):
        log_path.mkdir(parents=True, exist_ok=True)
        log_file = log_path / "corpus_cleaner.log"
        return log_file
    
    # 情况 3: 没有文件后缀，当作文件名处理，自动添加 .log
    if not log_path.suffix:
        log_file = log_path.with_suffix('.log')
        log_file.parent.mkdir(parents=True, exist_ok=True)
        return log_file
    
    # 情况 4: 有后缀名，直接使用
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path


def run_cli() -> int:
    """
    运行命令行接口。
    Returns:
        退出码 (0=成功, 1=失败, 130=用户中断)
    """
    # 解析命令行参数
    parser = create_argument_parser()
    args = parser.parse_args()

    # 配置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_file: Optional[Path] = None
    if args.log_file:
        log_file = _resolve_log_file_path(args.log_file)
    
    # 重置日志器（确保每次运行都使用正确的配置）
    LoggerFactory.reset()
    global logger
    logger = LoggerFactory.get_logger(level=log_level, log_file=log_file)
    
    if log_file:
        print(f"📝 日志文件: {log_file}")
        logger.info(f"日志将写入: {log_file}")

    try:
        # 加载配置
        cfg_path = Path(args.cfg) if args.cfg else None
        config_loader = ConfigLoader(cfg_path)
        config = config_loader.load_processing_config(args)

        # 验证输入路径
        input_path = Path(args.input)
        if not input_path.exists():
            logger.error(f"输入路径不存在: {input_path}")
            return 1

        output_dir = config.output_dir or Path(args.output_dir)
        
        # 创建缓存（支持断点续运行）
        cache: Optional[ProcessingCache] = None
        if not args.no_cache:
            cache_path = output_dir / Constants.CACHE_FILE_NAME
            cache = ProcessingCache(cache_path)
            
            # 清空缓存（如果请求）
            if args.clear_cache:
                logger.info("清空缓存，将重新处理所有文件...")
                cache.clear()
            else:
                # 显示缓存统计
                stats = cache.get_stats()
                if stats["total"] > 0:
                    logger.info(
                        f"加载缓存: {stats['success']} 成功, "
                        f"{stats['failed']} 失败, {stats['skipped']} 跳过"
                    )

        # 如需清空输出目录
        if args.clear_output and output_dir.exists():
            import shutil
            shutil.rmtree(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"已清空输出目录: {output_dir}")

        # 创建组件
        extractor_factory = ExtractorFactory(pdf_engine=config.pdf_engine)
        cleaner = TextCleaner(config.cleaner)
        splitter = SmartSplitter(config.splitter)

        llm_splitter = None
        if config.use_llm_split and config.llm:
            # 如果启用了 show_llm_output，强制使用单线程以避免输出混乱
            show_llm_output = args.show_llm_output
            if show_llm_output and config.max_workers > 1:
                print("⚠️  启用 --show-llm-output 时自动切换到单线程模式 (--workers 1)")
                config.max_workers = 1
            
            llm_splitter = LLMSemanticSplitter(
                config=config.llm,
                min_chars=config.splitter.min_chars,
                max_chars=config.splitter.max_chars,
                fallback_splitter=splitter,
                show_llm_output=show_llm_output,
            )
            
            # 启用 LLM 切分时，立即验证后端是否可用
            # 如果不可用，直接退出程序，不允许回退到规则切分
            print("\n🔍 正在验证 LLM 后端...")
            if not llm_splitter.validate_backend():
                error_msg = (
                    f"\n❌ LLM 后端初始化失败\n"
                    f"   厂商: {config.llm.provider}\n"
                    f"   模型: {config.llm.model_name}\n\n"
                    f"您启用了 --llm-split 参数，要求使用 LLM 进行语义切分。\n"
                    f"但 LLM 后端不可用，无法继续执行。\n\n"
                    f"请检查：\n"
                    f"  1. kg/llm_core.py 模块是否存在\n"
                    f"  2. API Key 是否正确配置\n"
                    f"  3. 环境变量 ZHIPUAI_API_KEY / OPENAI_API_KEY 是否设置\n\n"
                    f"如果想使用规则切分，请移除 --llm-split 参数\n"
                )
                print(error_msg)
                logger.error("LLM 后端初始化失败，程序退出")
                return 1
            print("✅ LLM 后端验证通过\n")

        meta_extractor = MetadataExtractor(
            default_source_type=args.source_type,
            default_url=args.default_url,
        )

        output_manager = OutputManager(
            output_dir=output_dir,
            preserve_structure=config.preserve_structure,
        )

        file_processor = FileProcessor(
            extractor_factory=extractor_factory,
            cleaner=cleaner,
            splitter=splitter,
            llm_splitter=llm_splitter,
            meta_extractor=meta_extractor,
            output_manager=output_manager,
            use_llm_split=config.use_llm_split,
        )

        # 创建进度回调
        def progress_callback(current: int, total: int, filename: str) -> None:
            percent = (current / total) * 100
            if args.show_llm_output:
                # show_llm_output 模式下使用换行打印，避免覆盖 LLM 输出
                print(f"\n⏳ 进度: [{current}/{total}] {percent:5.1f}% | {filename}")
            else:
                # 正常模式使用回车符实现进度覆盖
                print(
                    f"\r⏳ 进度: [{current}/{total}] {percent:5.1f}% | {filename[:40]:<40}",
                    end="",
                    flush=True,
                )

        batch_processor = BatchProcessor(
            file_processor=file_processor,
            max_workers=config.max_workers,
            progress_callback=progress_callback,
            cache=cache,
            skip_processed=not args.clear_cache,  # 如果清空缓存，不跳过
        )

        # 收集文件
        files = batch_processor.collect_files(input_path)
        if args.max_files:
            files = files[:args.max_files]

        if not files:
            logger.warning(f"未找到可处理的文件: {input_path}")
            return 0

        # 打印启动信息
        print_banner(config, len(files), output_dir)

        # 试运行模式
        if args.dry_run:
            print("\n📋 [试运行模式] 将要处理的文件:\n")
            for i, f in enumerate(files, 1):
                print(f"  {i:3d}. {f}")
            print(f"\n共 {len(files)} 个文件")
            return 0

        # 执行处理（传入已截取的文件列表）
        result = batch_processor.process(
            source=input_path,
            source_root=input_path if input_path.is_dir() else input_path.parent,
            files=files,
        )

        # 清除进度条
        print()
        
        # 最终保存缓存
        if cache:
            cache.save(force=True)
            logger.info(f"处理结束，缓存已保存: {cache.cache_path}")

        # 生成索引
        output_manager.generate_index(result)

        # 打印结果摘要
        print(result.summary(verbose=args.verbose))
        
        # 检查是否遇到 429 错误
        if batch_processor._rate_limit_hit:
            logger.warning(
                "\n⚠️  检测到 LLM 限流错误 (429)\n"
                "处理进度已保存，可稍后重新运行命令继续处理。\n"
                "建议：\n"
                "  1. 等待几分钟后重试\n"
                "  2. 检查 API 配额是否充足\n"
                "  3. 减少并行线程数 (--workers 1)\n"
                "  4. 禁用 LLM 切分（移除 --llm-split 参数）"
            )
            return 2  # 使用特定退出码表示限流

        return 0 if result.failed_count == 0 else 1

    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断处理")
        # 保存缓存
        if 'cache' in locals() and cache:
            cache.save(force=True)
            logger.info(f"已保存处理进度到: {cache.cache_path}")
        return 130
    
    except (_InternalRateLimitError, _InternalAccountBlockedError) as e:
        # LLM 严重错误：保存进度并退出
        print("\n")
        is_rate_limit = isinstance(e, _InternalRateLimitError)
        error_type = "LLM 限流错误 (429)" if is_rate_limit else "账号错误 (401)"
        
        if is_rate_limit:
            logger.error(
                f"\n❌ {error_type}: {e}\n\n"
                "该错误通常表示 API 配额不足。\n\n"
                "已保存操作：\n"
                "  ✔ 所有已成功切分的文件已写入输出目录\n"
                "  ✔ 处理进度已保存到缓存\n"
                "  ✖ 当前文件未标记为已处理（下次会重新处理）\n\n"
                "建议操作：\n"
                "  1. 等待 API 配额恢复\n"
                "  2. 重新运行相同命令继续处理\n"
                "  3. 已处理的文件会自动跳过"
            )
            exit_code = 2
        else:
            logger.error(
                f"\n❌ {error_type}: {e}\n\n"
                "该错误通常表示：\n"
                "  - API Key 无效或已过期\n"
                "  - 账号被封禁\n"
                "  - 权限不足\n\n"
                "已保存操作：\n"
                "  ✔ 所有已成功切分的文件已写入输出目录\n"
                "  ✔ 处理进度已保存到缓存\n\n"
                "建议操作：\n"
                "  1. 检查 API Key 是否正确\n"
                "  2. 确认账号状态正常\n"
                "  3. 检查环境变量配置"
            )
            exit_code = 3
        
        if 'cache' in locals() and cache:
            cache.save(force=True)
            logger.info(f"缓存已保存: {cache.cache_path}")
        return exit_code

    except ConfigurationError as e:
        logger.error(f"配置错误: {e}")
        return 1
    
    except FileSystemError as e:
        print("\n")
        logger.error(
            f"文件系统错误: {e}\n"
            "请检查：\n"
            "  1. 磁盘空间是否充足\n"
            "  2. 输出目录是否有写入权限\n"
            "  3. 文件路径是否合法"
        )
        if 'cache' in locals() and cache:
            cache.save(force=True)
            logger.info(f"已保存处理进度到: {cache.cache_path}")
        return 1
    
    except NetworkError as e:
        print("\n")
        logger.error(
            f"网络错误: {e}\n"
            "请检查：\n"
            "  1. 网络连接是否正常\n"
            "  2. LLM API 地址是否可访问\n"
            "  3. 防火墙设置是否阻挡请求"
        )
        if 'cache' in locals() and cache:
            cache.save(force=True)
            logger.info(f"已保存处理进度到: {cache.cache_path}")
        return 1

    except Exception as e:
        # 其他未预见错误：保存缓存后退出
        print("\n")
        logger.exception(f"处理过程中发生错误: {e}")
        
        # 保存缓存
        if 'cache' in locals() and cache:
            cache.save(force=True)
            logger.info(f"已保存处理进度到: {cache.cache_path}")
        
        logger.error(
            "\n如果问题持续，请尝试：\n"
            "  1. 使用 --verbose 参数查看详细日志\n"
            "  2. 检查输入文件是否损坏\n"
            "  3. 减少并行线程数 (--workers 1)\n"
            "  4. 已处理的文件已保存，可重新运行继续"
        )
        return 1

# ==============================================================================
# 工具函数
# ==============================================================================


@dataclass
class Segment:
    """
    语料片段数据结构。
    用于轻量级过滤流程中的数据传递。
    """
    id: str
    text: str
    rel_path: str
    char_count: int
    filter_decision: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


def collect_segments_from_directory(
    root: Path,
    min_chars: int = 80,
    max_chars: int = 3000,
) -> List[Segment]:
    """
    从目录中收集文本片段。
    Args:
        root: 根目录
        min_chars: 最小字符数
        max_chars: 最大字符数

    Returns:
        片段列表
    """
    segments: List[Segment] = []
    txt_files = list(root.glob("**/*.txt"))

    for txt_path in txt_files:
        # 跳过元数据文件和索引文件
        if txt_path.name.endswith(".meta.json"):
            continue
        if txt_path.name.startswith("_"):
            continue

        try:
            text = txt_path.read_text(encoding="utf-8").strip()

            # 长度过滤
            if len(text) < min_chars or len(text) > max_chars:
                continue

            # 生成唯一 ID
            rel_path = str(txt_path.relative_to(root))
            seg_id = hashlib.md5(
                f"{rel_path}:{text[:100]}".encode()
            ).hexdigest()[:16]

            segments.append(Segment(
                id=seg_id,
                text=text,
                rel_path=rel_path,
                char_count=len(text),
            ))

        except Exception as e:
            logger.warning(f"读取文件失败: {txt_path}, 错误: {e}")

    logger.info(f"从 {root} 收集到 {len(segments)} 个片段")
    return segments


def save_segments_jsonl(segments: List[Segment], output_path: Path) -> None:
    """
    保存片段列表为 JSONL 格式。
    Args:
        segments: 片段列表
        output_path: 输出路径
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        for seg in segments:
            f.write(json.dumps(seg.to_dict(), ensure_ascii=False) + "\n")

    logger.info(f"保存 {len(segments)} 条片段到 {output_path}")

# ==============================================================================
# 主入口
# ==============================================================================


def main() -> int:
    """
    主入口函数。
    Returns:
        退出码
    """
    return run_cli()


if __name__ == "__main__":
    sys.exit(main())
