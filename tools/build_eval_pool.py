"""从处理后的语料目录中抽取评估子集（Eval Pool），并按类别划分 Dev/Test。

目标：
- 从四类语料中抽若干段落（默认约 300 段，每段 150~400 字），覆盖主要概念（洪水/干旱/致灾因子/影响/应对）。
- 分类来源（约配置）：
  * law_plan（法案&预案&制度） ~60
  * gazette_yearbook（公报&年鉴） ~80
  * case_paper（案例&论文） ~100
  * news_popular（科普&新闻） ~60
- 输出：
  * data/p5_eval_pool/pool.jsonl （全部样本）
  * data/p5_eval_pool/dev.jsonl   （分层抽样 60%）
  * data/p5_eval_pool/test.jsonl  （分层抽样 40%）

使用示例：
python tools/build_eval_pool.py \
  --root data/corpus_for_kg/handled_used_kg_corpus \
  --out-dir data/p5_eval_pool \
  --min-chars 150 --max-chars 400 \
  --target law_plan=60 gazette_yearbook=80 case_paper=100 news_popular=60
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import re
import signal
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, Final, List, Mapping, Optional, Tuple, Iterable

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
# LLM 模块延迟导入
# ==============================================================================
_LLMFactory = None
_RateLimitError = None
_AccountBlockedError = None
_ServiceUnavailableError = None


def _ensure_llm_imports() -> None:
    """延迟导入 LLM 模块，避免循环依赖并加快启动速度"""
    global _LLMFactory, _RateLimitError, _AccountBlockedError, _ServiceUnavailableError
    if _LLMFactory is not None:
        return
    try:
        from kg.llm_core import (
            LLMFactory, RateLimitError, AccountBlockedError, ServiceUnavailableError
        )
        _LLMFactory = LLMFactory
        _RateLimitError = RateLimitError
        _AccountBlockedError = AccountBlockedError
        _ServiceUnavailableError = ServiceUnavailableError
    except ImportError as e:
        logger.warning(f"无法导入 LLM 模块: {e}")
        raise


try:
    from kg.prompts import (
        EVAL_SEGMENT_FILTER_SYSTEM,
        EVAL_SEGMENT_FILTER_USER_TEMPLATE,
    )
except ImportError:
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
        """简单清理标题标记"""
        text = re.sub(r'\[[一二三四五六]级标题\]\s*', '', text)
        text = re.sub(r'\[/?(表格|代码块)\]', '', text)
        text = re.sub(r'\[图片:\s*[^\]]*\]', '', text)
        return text.strip()


# ==============================================================================
# 自定义异常
# ==============================================================================
class LLMConfigError(Exception):
    """
    LLM 配置级错误（如模型名错误、API Key 无效、返回空响应等）。
    这类错误应该立即停止，不写入缓存。
    """
    pass


class LLMRetryExhaustedError(Exception):
    """
    LLM 重试耗尽错误（限流、网络问题等经过多次重试后仍失败）。
    这类错误不写入缓存，退出程序交给人工处理。
    """
    pass


class LLMParseError(Exception):
    """
    LLM 返回结果解析失败（返回了内容但无法解析为有效 JSON）。
    这类错误可以重试，不写入缓存。
    """
    pass


# ==============================================================================
# 常量定义
# ==============================================================================
class Constants:
    """全局常量定义"""
    VERSION: Final[str] = "2.0.0"
    TOOL_NAME: Final[str] = "P5 Eval Pool 构建工具"

    # 默认参数
    DEFAULT_MIN_CHARS: Final[int] = 150
    DEFAULT_MAX_CHARS: Final[int] = 2000
    DEFAULT_DEV_RATIO: Final[float] = 0.6
    DEFAULT_MIN_CN_RATIO: Final[float] = 0.3
    DEFAULT_MAX_WEIRD_RATIO: Final[float] = 0.3

    # LLM 调用
    DEFAULT_MAX_TOKENS: Final[int] = 8192
    DEFAULT_MAX_RETRIES: Final[int] = 3
    DEFAULT_RETRY_DELAY: Final[float] = 2.0
    RETRY_BACKOFF_FACTOR: Final[float] = 2.0
    MAX_RETRY_DELAY: Final[float] = 60.0

    # 缓存
    CACHE_FLUSH_INTERVAL: Final[int] = 10
    CACHE_FILE_NAME: Final[str] = "_eval_filter_cache.jsonl"

    # 默认目标分布 (按 source_type)
    DEFAULT_TARGET: Final[Dict[str, int]] = {
        "law_plan": 60,
        "gazette_yearbook": 80,
        "case_paper": 100,
        "news_popular": 60,
    }

    # 默认目标分布 (按 topic_label)
    DEFAULT_TARGET_TOPIC: Final[Dict[str, int]] = {
        "disaster_event": 150,
        "measure_response": 180,
        "background_analysis": 50,
        "institution_regulation": 50,
        "impact_assessment": 10,
    }


# ==============================================================================
# 日志系统
# ==============================================================================
def setup_logger(
    name: str = "eval_pool",
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    """配置并返回 logger"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8", mode="a")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


logger = setup_logger()


# ==============================================================================
# 分类映射与关键词
# ==============================================================================
CategoryMap: Final[Dict[str, str]] = {
    "法案": "law_plan",
    "预案": "law_plan",
    "制度": "law_plan",
    "应急预案": "law_plan",
    "公报": "gazette_yearbook",
    "年鉴": "gazette_yearbook",
    "年报": "gazette_yearbook",
    "案例": "case_paper",
    "论文": "case_paper",
    "科普": "news_popular",
    "新闻": "news_popular",
}

DIR_CATEGORY_MAP: Final[Dict[str, str]] = {
    "法案&预案&制度类": "law_plan",
    "流域公报&年鉴": "gazette_yearbook",
    "灾害案例 & 论文": "case_paper",
    "科普 & 新闻": "news_popular",
}

KEYWORDS_CORE: Final[List[str]] = [
    "长江", "流域", "洪水", "干旱", "水旱",
    "防汛", "抗旱", "蓄滞洪区", "应急响应", "防洪", "枯水",
]
KEYWORDS_LAW: Final[List[str]] = ["防汛", "抗旱", "应急", "预案", "响应"]


# ==============================================================================
# 数据类定义
# ==============================================================================
@dataclass
class EvalConfig:
    """评估池构建配置"""
    root: Path
    out_dir: Path
    min_chars: int = Constants.DEFAULT_MIN_CHARS
    max_chars: int = Constants.DEFAULT_MAX_CHARS
    dev_ratio: float = Constants.DEFAULT_DEV_RATIO
    min_cn_ratio: float = Constants.DEFAULT_MIN_CN_RATIO
    max_weird_ratio: float = Constants.DEFAULT_MAX_WEIRD_RATIO
    require_keyword: bool = True
    target: Dict[str, int] = field(default_factory=lambda: dict(Constants.DEFAULT_TARGET))

    # LLM 配置
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_temperature: float = 0.0
    llm_max_tokens: int = Constants.DEFAULT_MAX_TOKENS
    llm_max_retries: int = Constants.DEFAULT_MAX_RETRIES

    # 运行模式
    no_filter: bool = False
    refilter: bool = False
    filter_cache_path: Optional[Path] = None
    seed: Optional[int] = None

    @property
    def cache_path(self) -> Path:
        """LLM 过滤缓存文件路径"""
        return self.filter_cache_path or (self.out_dir / Constants.CACHE_FILE_NAME)


@dataclass
class Segment:
    """语料片段"""
    id: str
    source_type: str
    doc_title: str
    year: Optional[int]
    text: str
    rel_path: str
    filter_decision: Optional[Dict[str, Any]] = None
    # 时空元数据（从 LLM 筛选结果中提取）
    extracted_time: Optional[str] = None
    extracted_location: Optional[str] = None
    extracted_issuer: Optional[str] = None
    temporal_detail: Optional[int] = None
    spatial_detail: Optional[int] = None
    issuer_detail: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    def update_spatiotemporal_from_decision(self) -> None:
        """从 filter_decision 中提取并更新时空主体元数据"""
        if not self.filter_decision or not isinstance(self.filter_decision, dict):
            return
        labels = self.filter_decision.get("labels", {})
        if not labels:
            return
        # 提取时间/空间/主体信息
        self.extracted_time = labels.get("extracted_time") or None
        self.extracted_location = labels.get("extracted_location") or None
        self.extracted_issuer = labels.get("extracted_issuer") or None
        # 提取详细程度评分
        try:
            self.temporal_detail = int(labels.get("temporal_detail", 0))
        except (ValueError, TypeError):
            self.temporal_detail = 0
        try:
            self.spatial_detail = int(labels.get("spatial_detail", 0))
        except (ValueError, TypeError):
            self.spatial_detail = 0
        try:
            self.issuer_detail = int(labels.get("issuer_detail", 0))
        except (ValueError, TypeError):
            self.issuer_detail = 0


@dataclass
class FilterStats:
    """过滤统计信息"""
    total: int = 0
    processed: int = 0
    kept: int = 0
    dropped: int = 0
    from_cache: int = 0
    llm_errors: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    def summary(self) -> str:
        rate = (self.kept / self.processed * 100) if self.processed > 0 else 0
        return (
            f"处理 {self.processed}/{self.total} | "
            f"保留 {self.kept} ({rate:.1f}%) | "
            f"丢弃 {self.dropped} | "
            f"缓存命中 {self.from_cache} | "
            f"错误 {self.llm_errors} | "
            f"耗时 {self.elapsed:.1f}s"
        )


def cn_ratio(text: str) -> float:
    if not text:
        return 0.0
    cn = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cn / len(text)


def weird_ratio(text: str) -> float:
    if not text:
        return 0.0
    allowed = set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ，。！？；：、“”‘’（）()《》<>-———…·%/\\ \n\r\t")
    weird = sum(1 for ch in text if ch not in allowed and not ("\u4e00" <= ch <= "\u9fff"))
    return weird / len(text)


def has_keywords(text: str, keywords: Iterable[str]) -> bool:
    return any(k in text for k in keywords)


def coarse_filter_segment(
    seg: Segment,
    *,
    min_cn_ratio: float = 0.3,
    max_weird_ratio: float = 0.3,
    require_keyword: bool = True,
) -> Tuple[bool, str]:
    """
    规则级粗过滤：先挡掉明显乱码/无关文本，减少 LLM 调用。
    """
    cn_r = cn_ratio(seg.text)
    if cn_r < min_cn_ratio:
        return False, f"cn_ratio<{min_cn_ratio:.2f}"
    w_r = weird_ratio(seg.text)
    if w_r > max_weird_ratio:
        return False, f"weird_ratio>{max_weird_ratio:.2f}"
    if require_keyword:
        kws = KEYWORDS_CORE + (KEYWORDS_LAW if seg.source_type == "law_plan" else [])
        if not has_keywords(seg.text, kws):
            return False, "no_keyword"
    return True, "ok"


def _normalize_source_type(raw: str) -> Optional[str]:
    """将 meta 中的 source_type 或中文标签规范化到英文枚举。"""
    if not raw:
        return None
    if raw in DIR_CATEGORY_MAP.values():
        return raw
    for k, v in CategoryMap.items():
        if k in raw:
            return v
    return None


def detect_source_type(path: Path, *, root: Optional[Path] = None, meta: Optional[Mapping[str, Any]] = None) -> str:
    """
    优先使用目录/侧边 meta 的信息判定 source_type，最后再回落到关键词。
    """
    if meta:
        meta_src = _normalize_source_type(str(meta.get("source_type", "")).strip())
        if meta_src:
            return meta_src

    # 先看顶层目录（人工整理的分类最可信）
    if root:
        try:
            rel = path.relative_to(root)
            top = rel.parts[0] if rel.parts else ""
            if top in DIR_CATEGORY_MAP:
                return DIR_CATEGORY_MAP[top]
        except ValueError:
            pass  # 不在同一根目录下时跳过

    # 回退到文件名/父目录关键词匹配
    names = [path.name] + [p.name for p in path.parents]
    for name in names:
        for k, v in CategoryMap.items():
            if k in name:
                return v
    return "unknown"


def detect_year_from_name(name: str) -> Optional[int]:
    """从文件名中提取年份"""
    m = re.search(r"(19|20)\d{2}", name)
    return int(m.group(0)) if m else None


def split_paragraphs(text: str, min_chars: int, max_chars: int) -> List[str]:
    """
    按空行分段后合并，控制长度在 [min_chars, max_chars]；过长则硬切。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    parts: List[str] = []
    buf: List[str] = []
    buf_len = 0

    def flush():
        nonlocal buf, buf_len
        if buf:
            parts.append("\n\n".join(buf).strip())
            buf = []
            buf_len = 0

    for para in paras:
        if len(para) > max_chars:
            flush()
            for i in range(0, len(para), max_chars):
                parts.append(para[i:i + max_chars].strip())
            continue
        if buf_len + len(para) + 2 <= max_chars:
            buf.append(para)
            buf_len += len(para) + 2
        else:
            if buf_len >= min_chars:
                flush()
                buf.append(para)
                buf_len = len(para)
            else:
                buf.append(para)
                buf_len += len(para) + 2
    flush()
    if len(parts) >= 2 and len(parts[-1]) < min_chars:
        parts[-2] = parts[-2] + "\n\n" + parts[-1]
        parts.pop()
    return parts


# ==============================================================================
# 缓存管理器
# ==============================================================================
class FilterCache:
    """
    过滤缓存管理器，支持断点续跑和增量保存。

    设计特点：
    - 线程安全
    - 增量写入：每次 LLM 调用后立即追加保存
    - 定期 flush：防止程序中断丢失数据
    """

    def __init__(self, cache_path: Path):
        self.path = cache_path
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._pending_writes: List[Dict[str, Any]] = []
        self._file_handle: Optional[Any] = None
        self._load()

    def _load(self) -> None:
        """从磁盘加载缓存"""
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        seg_id = item.get("id")
                        if seg_id:
                            self._cache[seg_id] = item
                    except json.JSONDecodeError:
                        continue
            logger.info(f"加载缓存 {len(self._cache)} 条记录: {self.path}")
        except Exception as e:
            logger.warning(f"缓存加载失败: {e}")

    def get(self, seg_id: str) -> Optional[Dict[str, Any]]:
        """获取缓存结果"""
        return self._cache.get(seg_id)

    def contains(self, seg_id: str) -> bool:
        """检查是否存在"""
        return seg_id in self._cache

    def put(self, seg_id: str, decision: Dict[str, Any]) -> None:
        """添加缓存并立即追加写入文件"""
        self._cache[seg_id] = decision
        self._append_to_file(seg_id, decision)

    def _append_to_file(self, seg_id: str, decision: Dict[str, Any]) -> None:
        """追加写入文件（增量保存）"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {"id": seg_id, **decision}
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
        except Exception as e:
            logger.warning(f"缓存写入失败: {e}")

    def save_full(self) -> None:
        """全量保存（用于重建缓存）"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            for seg_id, decision in self._cache.items():
                row = {"id": seg_id, **decision}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        logger.info(f"全量保存缓存 {len(self._cache)} 条记录")

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        if self.path.exists():
            self.path.unlink()

    def __len__(self) -> int:
        return len(self._cache)


# ==============================================================================
# LLM 调用器（带重试机制）
# ==============================================================================
class LLMSegmentJudge:
    """
    LLM 段落评估器，带重试机制和进度显示。
    """

    def __init__(
        self,
        llm_config: Dict[str, Any],
        max_retries: int = Constants.DEFAULT_MAX_RETRIES,
        max_tokens: int = Constants.DEFAULT_MAX_TOKENS,
    ):
        self.llm_config = llm_config
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self._backend = None

    @property
    def backend(self):
        """延迟初始化 LLM 客户端"""
        if self._backend is None:
            _ensure_llm_imports()
            # 确保配置中包含 max_tokens
            config = dict(self.llm_config)
            if "max_tokens" not in config:
                config["max_tokens"] = self.max_tokens
            self._backend = _LLMFactory.create(config)
            logger.info(f"LLM 后端初始化: {config.get('model_name', 'default')}")
        return self._backend

    def judge(self, seg: Segment) -> Dict[str, Any]:
        """
        调用 LLM 评估段落质量与相关性。

        带有指数退避重试机制，支持临时性错误恢复。
        """
        user_prompt = EVAL_SEGMENT_FILTER_USER_TEMPLATE.replace(
            "{segment_text}", seg.text[:3000]  # 限制长度避免超 token
        )

        delay = Constants.DEFAULT_RETRY_DELAY
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                resp = self.backend.chat_messages(
                    [
                        {"role": "system", "content": EVAL_SEGMENT_FILTER_SYSTEM},
                        {"role": "user", "content": user_prompt},
                    ],
                    json_mode=True,
                )
                return self._parse_response(resp, seg.id)

            except Exception as e:
                last_error = e
                err_str = str(e).lower()

                # 严重错误：账号封禁、限流，直接抛出
                if _AccountBlockedError and isinstance(e, _AccountBlockedError):
                    logger.error(f"账号封禁，终止处理: {e}")
                    raise
                if _RateLimitError and isinstance(e, _RateLimitError):
                    logger.error(f"触发限流，终止处理: {e}")
                    raise
                if "401" in err_str or "unauthorized" in err_str:
                    raise
                if "429" in err_str or "rate" in err_str:
                    raise

                # 可重试错误：网络、超时、5xx、4xx
                if attempt < self.max_retries:
                    logger.warning(
                        f"LLM 调用失败 ({seg.id})[重试 {attempt+1}/{self.max_retries}]: {e}"
                    )
                    time.sleep(delay)
                    delay = min(delay * Constants.RETRY_BACKOFF_FACTOR, Constants.MAX_RETRY_DELAY)
                else:
                    logger.error(f"LLM 调用最终失败 ({seg.id}): {e}")

        # 所有重试均失败
        return {
            "keep_for_eval": False,
            "reason": f"llm_error: {str(last_error)[:100]}",
            "labels": {},
        }

    def _parse_response(self, resp: str, seg_id: str) -> Dict[str, Any]:
        """解析 LLM 响应"""
        if not resp:
            return {
                "keep_for_eval": False,
                "reason": "llm_empty_response",
                "labels": {},
            }
        try:
            parsed = json.loads(resp)
            if not isinstance(parsed, dict):
                raise ValueError("not a dict")
            return parsed
        except json.JSONDecodeError as e:
            logger.debug(f"解析 LLM 响应失败 ({seg_id}): {e}")
            return {
                "keep_for_eval": False,
                "reason": "llm_parse_error",
                "raw": resp[:500],
                "labels": {},
            }


# 向后兼容的函数接口
def load_filter_cache(path: Path) -> Dict[str, dict]:
    """加载缓存（向后兼容）"""
    cache = FilterCache(path)
    return dict(cache._cache)


def save_filter_cache(cache_dict: Dict[str, dict], path: Path) -> None:
    """保存缓存（向后兼容）"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for seg_id, item in cache_dict.items():
            row = {"id": seg_id, **item}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def judge_segment(seg: Segment, backend, max_retries: int = 3) -> Dict[str, Any]:
    """
    调用 LLM 按提示词评估段落质量与相关性。
    
    返回有效的 JSON dict，否则抛出异常：
    - LLMConfigError: 配置错误（空响应、模型不存在等）
    - LLMParseError: 返回内容无法解析
    - LLMRetryExhaustedError: 重试耗尽后仍失败
    
    注意：只有返回有效结果时才应写入缓存，异常情况不写缓存。
    """
    user_prompt = EVAL_SEGMENT_FILTER_USER_TEMPLATE.replace(
        "{segment_text}", seg.text[:3000]
    )

    delay = Constants.DEFAULT_RETRY_DELAY
    last_error = None
    parse_failures = 0  # JSON 解析失败次数

    for attempt in range(max_retries + 1):
        try:
            resp = backend.chat_messages(
                [
                    {"role": "system", "content": EVAL_SEGMENT_FILTER_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                json_mode=True,
            )

            if not resp:
                # 空响应通常意味着配置错误（如模型名错误），抛出异常立即停止
                raise LLMConfigError(
                    f"LLM 返回空响应，请检查模型名和 API Key 配置是否正确 (segment_id={seg.id})"
                )

            try:
                parsed = json.loads(resp)
                if not isinstance(parsed, dict):
                    raise ValueError("not a dict")
                # 验证返回结果是否包含必要字段
                if "keep_for_eval" not in parsed and "labels" not in parsed:
                    raise ValueError("missing required fields")
                return parsed
            except (json.JSONDecodeError, ValueError) as e:
                parse_failures += 1
                if attempt < max_retries:
                    logger.warning(
                        f"LLM 返回解析失败 ({seg.id})[{attempt+1}/{max_retries}]: {e}, 响应: {resp[:200]}..."
                    )
                    time.sleep(delay)
                    delay = min(delay * Constants.RETRY_BACKOFF_FACTOR, Constants.MAX_RETRY_DELAY)
                    continue
                else:
                    raise LLMParseError(
                        f"LLM 返回无法解析为有效 JSON (segment_id={seg.id}): {resp[:200]}"
                    )

        except (LLMConfigError, LLMParseError):
            # 配置错误和解析错误直接向上抛出
            raise
        except Exception as e:
            last_error = e
            err_str = str(e).lower()

            # 配置级错误：直接抛出，不重试
            if _AccountBlockedError and isinstance(e, _AccountBlockedError):
                raise LLMConfigError(f"账号被封禁: {e}")
            if "401" in err_str or "unauthorized" in err_str:
                raise LLMConfigError(f"API Key 无效或账户异常: {e}")
            if "404" in err_str and "model" in err_str:
                raise LLMConfigError(f"模型不存在: {e}")
            
            # 限流错误：重试，但最终仍失败则抛出
            is_rate_limit = (
                (_RateLimitError and isinstance(e, _RateLimitError)) or
                "429" in err_str or "rate" in err_str or "limit" in err_str
            )
            
            # 可重试错误
            if attempt < max_retries:
                retry_msg = "限流" if is_rate_limit else "网络/服务错误"
                logger.warning(
                    f"LLM 调用失败 ({seg.id})[{retry_msg}, 重试 {attempt+1}/{max_retries}]: {e}"
                )
                # 限流时等待更长时间
                wait_time = delay * 3 if is_rate_limit else delay
                time.sleep(wait_time)
                delay = min(delay * Constants.RETRY_BACKOFF_FACTOR, Constants.MAX_RETRY_DELAY)
            else:
                logger.error(f"LLM 调用最终失败 ({seg.id}): {e}")

    # 重试耗尽，抛出异常
    raise LLMRetryExhaustedError(
        f"LLM 调用经过 {max_retries+1} 次尝试后仍失败 (segment_id={seg.id}): {last_error}"
    )


def _get_score(decision: dict, key: str) -> int:
    labels = decision.get("labels", {}) if isinstance(decision, dict) else {}
    val = labels.get(key)
    try:
        return int(val)
    except Exception:
        return -1


def keep_by_eval_rule(decision: dict, strict_completeness: bool = True) -> bool:
    """
    严格规则（最新版本，按类型区分完备性要求）：
    
    必须满足以下条件：
    1) is_water_disaster_domain = true
    2) text_quality != "garbled" 且 cleanliness >= 1
    3) contains_event_or_rule = true 且 kg_potential >= 1
    4) relevance_yangtze >= 1
    5) 信息完备性（按 topic_label 类型区分）：
       - disaster_event / impact_assessment：temporal >= 1 且 spatial >= 1
       - institution_regulation：temporal >= 1 或 issuer >= 1
       - measure_response：temporal >= 1 或 spatial >= 1 或 issuer >= 1
       - background_analysis / other：temporal >= 1 或 spatial >= 1
    
    Args:
        decision: LLM 返回的判定结果字典
        strict_completeness: 是否强制要求信息完备性（默认 True）
    
    Returns:
        bool: 是否保留该片段
    """
    labels = decision.get("labels", {}) if isinstance(decision, dict) else {}
    
    # 1. 领域相关性
    domain = labels.get("is_water_disaster_domain")
    if not domain:
        return False
    
    # 2. 文本质量
    text_quality = labels.get("text_quality")
    if text_quality == "garbled":
        return False
    cleanliness = _get_score(decision, "cleanliness")
    if cleanliness < 1:
        return False
    
    # 3. 事件/规则内容 & KG 潜力
    contains_event = labels.get("contains_event_or_rule", False)
    kg_potential = _get_score(decision, "kg_potential")
    if not contains_event or kg_potential < 1:
        return False
    
    # 4. 长江相关性
    relevance = _get_score(decision, "relevance_yangtze")
    if relevance < 1:
        return False
    
    # 5. 信息完备性（按类型区分）
    if strict_completeness:
        temporal = _get_score(decision, "temporal_detail")
        spatial = _get_score(decision, "spatial_detail")
        issuer = _get_score(decision, "issuer_detail")
        topic_label = labels.get("topic_label", "")
        source_guess = labels.get("source_guess", "")
        
        # 全部为 0 直接拒绝
        if temporal < 1 and spatial < 1 and issuer < 1:
            return False
        
        # 按类型区分完备性要求
        if topic_label in ("disaster_event", "impact_assessment"):
            # 灾害事件/影响评估：必须有时间+地点
            if temporal < 1 or spatial < 1:
                return False
        elif topic_label == "institution_regulation" or source_guess == "law_plan":
            # 制度/法规类：需要时间或发布主体
            if temporal < 1 and issuer < 1:
                return False
        elif topic_label == "measure_response":
            # 措施响应类：至少有一项明确
            if temporal < 1 and spatial < 1 and issuer < 1:
                return False
        else:
            # background_analysis 或 other：需要时间或空间
            if temporal < 1 and spatial < 1:
                return False
    
    return True


def filter_segments_with_llm(
    segments: List[Segment],
    llm_config: Dict[str, Any],
    cache_path: Path,
    refilter: bool = False,
    max_retries: int = Constants.DEFAULT_MAX_RETRIES,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> List[Segment]:
    """
    使用 LLM 过滤段落；支持基于缓存的断点续跑。

    改进：
    - 使用 FilterCache 类进行增量保存
    - 支持进度回调
    - 信号处理保证中断时保存进度
    """
    _ensure_llm_imports()

    # 初始化 LLM 后端，确保包含 max_tokens
    config = dict(llm_config)
    if "max_tokens" not in config:
        config["max_tokens"] = Constants.DEFAULT_MAX_TOKENS
    backend = _LLMFactory.create(config)

    # 初始化缓存
    if refilter and cache_path.exists():
        cache_path.unlink()
        logger.info("强制重新过滤，已清除旧缓存")
    cache = FilterCache(cache_path)

    # 统计信息
    stats = FilterStats(total=len(segments))
    kept: List[Segment] = []

    # 信号处理：保证中断时保存进度
    interrupted = False

    def signal_handler(signum, frame):
        nonlocal interrupted
        interrupted = True
        logger.warning("\n收到中断信号，正在保存进度...")

    old_handler = signal.signal(signal.SIGINT, signal_handler)

    try:
        for i, seg in enumerate(segments):
            if interrupted:
                logger.info(f"已中断，处理了 {stats.processed}/{stats.total} 条")
                break

            stats.processed += 1

            # 检查缓存
            if not refilter and cache.contains(seg.id):
                decision = cache.get(seg.id)
                stats.from_cache += 1
            else:
                # 调用 LLM（只有成功获得有效结果才写入缓存）
                try:
                    decision = judge_segment(seg, backend, max_retries=max_retries)
                    # 成功获得有效结果，写入缓存
                    cache.put(seg.id, decision)
                except LLMConfigError as e:
                    # 配置级错误：立即停止，不写入缓存
                    logger.error(f"\n\u274c 配置错误，立即停止: {e}")
                    logger.error("提示: 请检查 --llm-model 或 cfg.yaml 中的模型名配置是否正确")
                    raise  # 重新抛出，终止处理
                except LLMParseError as e:
                    # 解析错误：不写缓存，终止处理
                    logger.error(f"\n\u274c LLM 返回无法解析: {e}")
                    logger.error("提示: LLM 返回了内容但无法解析为有效 JSON，请检查 Prompt 或更换模型")
                    raise
                except LLMRetryExhaustedError as e:
                    # 重试耗尽：不写缓存，终止处理交人工处理
                    logger.error(f"\n\u274c 重试耗尽: {e}")
                    logger.error("提示: 可能是限流/网络问题，请稍后重试或更换 API Key")
                    raise

            seg.filter_decision = decision
            # 从 decision 中提取时空元数据
            seg.update_spatiotemporal_from_decision()
            
            if keep_by_eval_rule(decision):
                kept.append(seg)
                stats.kept += 1
            else:
                stats.dropped += 1

            # 进度回调
            if progress_callback:
                progress_callback(stats.processed, stats.total, seg.id)
            elif stats.processed % 10 == 0 or stats.processed == stats.total:
                logger.info(stats.summary())

    finally:
        signal.signal(signal.SIGINT, old_handler)

    logger.info(f"过滤完成: {stats.summary()}")
    return kept


def collect_segments(root: Path, min_chars: int, max_chars: int) -> List[Segment]:
    segments: List[Segment] = []
    for fp in root.rglob("*.txt"):
        if fp.name.endswith(".meta.txt") or fp.name.endswith(".meta.json"):
            continue
        meta: Dict[str, Any] = {}
        meta_path = fp.with_suffix(".meta.json")
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                logger.debug(f"侧边 meta 解析失败，忽略: {meta_path}")

        src_type = detect_source_type(fp, root=root, meta=meta)
        year = meta.get("year") or detect_year_from_name(fp.name)
        title = meta.get("title") or fp.stem
        rel_path = fp.relative_to(root).as_posix()
        raw_text = fp.read_text(encoding="utf-8", errors="ignore")
        # 清理标题标记等特殊格式，获取纯净文本
        text = clean_special_tags(raw_text)
        parts = split_paragraphs(text, min_chars, max_chars)
        for idx, p in enumerate(parts, start=1):
            if len(p) < min_chars:
                continue
            hash_suffix = hashlib.md5(p.encode("utf-8")).hexdigest()[:8]
            seg_id = f"{src_type}_{fp.stem}_para_{idx}_{hash_suffix}"
            segments.append(Segment(
                id=seg_id,
                source_type=src_type,
                doc_title=title,
                year=year,
                text=p,
                rel_path=rel_path,
            ))
    return segments


def load_segments_from_jsonl(jsonl_path: Path, min_chars: int, max_chars: int) -> List[Segment]:
    """
    从 filter_corpus_light.py 的 JSONL 输出加载片段。
    
    字段映射:
        filter_corpus_light.Segment -> build_eval_pool.Segment
        - id -> id
        - text -> text
        - rel_path -> rel_path
        - source_type -> source_type
        - title -> doc_title
        - year -> year
        - filter_labels -> filter_decision (包装为兼容格式)
    
    Args:
        jsonl_path: JSONL 文件路径
        min_chars: 最小字符数过滤
        max_chars: 最大字符数过滤
    
    Returns:
        转换后的 Segment 列表
    """
    segments: List[Segment] = []
    if not jsonl_path.exists():
        logger.error(f"JSONL 文件不存在: {jsonl_path}")
        return segments
    
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"JSONL 第 {line_num} 行解析失败: {e}")
                continue
            
            text = data.get("text", "")
            # 长度过滤
            if len(text) < min_chars or len(text) > max_chars:
                continue
            
            # 字段映射
            seg_id = data.get("id", "")
            source_type = data.get("source_type", "unknown")
            doc_title = data.get("title", data.get("doc_title", ""))
            rel_path = data.get("rel_path", "")
            
            # 年份处理（filter_corpus_light 输出为字符串）
            year_raw = data.get("year", "")
            year: Optional[int] = None
            if year_raw:
                try:
                    year = int(year_raw)
                except (ValueError, TypeError):
                    pass
            
            # 如果 filter_corpus_light 已经做过 LLM 判定，保留其结果
            # 将 filter_labels 包装到 filter_decision 中，以便后续可以获取 topic_label
            existing_labels = data.get("filter_labels", {})
            existing_decision = data.get("filter_decision", "")
            
            # 构建 filter_decision，包含 labels 信息
            filter_decision_data = {
                "keep_for_eval": existing_decision == "keep",
                "labels": existing_labels,
            }
            
            segments.append(Segment(
                id=seg_id,
                source_type=source_type,
                doc_title=doc_title,
                year=year,
                text=text,
                rel_path=rel_path,
                filter_decision=filter_decision_data,
            ))
    
    logger.info(f"从 JSONL 加载 {len(segments)} 条片段（长度范围 {min_chars}~{max_chars}）")
    return segments


def _get_topic(seg: Segment) -> str:
    """从 filter_decision 或 filter_labels 中获取 topic_label"""
    # 优先从 filter_decision.labels 获取
    if seg.filter_decision and isinstance(seg.filter_decision, dict):
        labels = seg.filter_decision.get("labels", {})
        topic = labels.get("topic_label") or labels.get("main_topic")
        if topic:
            return str(topic)
    return "unknown"


def _get_stratify_value(seg: Segment, stratify_by: str) -> str:
    """根据分层字段获取分层值"""
    if stratify_by == "topic_label":
        return _get_topic(seg)
    else:  # source_type
        return seg.source_type or "unknown"


def sample_by_category(
    segments: List[Segment],
    target: Dict[str, int],
    stratify_by: str = "source_type",
) -> List[Segment]:
    """
    分层随机采样。
    
    Args:
        segments: 待采样的片段列表
        target: 各类别抽取目标，如 {"disaster_event": 150, ...}
        stratify_by: 分层字段，"source_type" 或 "topic_label"
    """
    # 按分层字段分组
    by_cat: Dict[str, List[Segment]] = {}
    for seg in segments:
        cat_value = _get_stratify_value(seg, stratify_by)
        by_cat.setdefault(cat_value, []).append(seg)
    
    # 打印各类别实际数量
    logger.info(f"按 {stratify_by} 分层，各类别数量:")
    for cat, segs_list in sorted(by_cat.items(), key=lambda x: -len(x[1])):
        logger.info(f"  {cat}: {len(segs_list)}")

    sampled: List[Segment] = []
    for cat, num in target.items():
        pool = by_cat.get(cat, [])
        if not pool:
            logger.warning(f"类别 '{cat}' 无数据，跳过")
            continue
        random.shuffle(pool)
        
        # 如果按 topic_label 分层，则不再做二级 topic 轮询
        if stratify_by == "topic_label":
            picked = pool[:num]
        else:
            # 按 source_type 分层时，尽量覆盖不同 topic_label
            topic_buckets: Dict[str, List[Segment]] = {}
            for s in pool:
                topic_buckets.setdefault(_get_topic(s), []).append(s)
            for lst in topic_buckets.values():
                random.shuffle(lst)

            picked: List[Segment] = []
            topics = list(topic_buckets.keys())
            # 轮询 topic，保证覆盖
            while len(picked) < num and topics:
                topics = [t for t in topics if topic_buckets.get(t)]
                if not topics:
                    break
                for t in list(topics):
                    if len(picked) >= num:
                        break
                    if topic_buckets[t]:
                        picked.append(topic_buckets[t].pop())
            # 兜底：如仍不足，直接补齐
            if len(picked) < num:
                remaining = [s for lst in topic_buckets.values() for s in lst]
                random.shuffle(remaining)
                picked.extend(remaining[: max(0, num - len(picked))])

        sampled.extend(picked)
        logger.info(f"  {cat}: 目标 {num}, 实际抽取 {len(picked)}")
    
    return sampled


def split_dev_test(
    sampled: List[Segment],
    dev_ratio: float = 0.6,
    stratify_by: str = "source_type",
) -> Tuple[List[Segment], List[Segment]]:
    """
    在每个类别组内随机划分 Dev/Test，保持分布。
    
    Args:
        sampled: 已采样的片段列表
        dev_ratio: Dev 集比例
        stratify_by: 分层字段，"source_type" 或 "topic_label"
    """
    by_cat: Dict[str, List[Segment]] = {}
    for seg in sampled:
        cat_value = _get_stratify_value(seg, stratify_by)
        by_cat.setdefault(cat_value, []).append(seg)

    dev, test = [], []
    for cat, segs in by_cat.items():
        random.shuffle(segs)
        cutoff = int(len(segs) * dev_ratio)
        dev.extend(segs[:cutoff])
        test.extend(segs[cutoff:])
    return dev, test


def save_jsonl(objs: List[Segment], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for obj in objs:
            f.write(json.dumps(asdict(obj), ensure_ascii=False) + "\n")


def parse_target(target_args: List[str]) -> Dict[str, int]:
    """
    解析 --target 形如 law_plan=60 的列表。
    """
    target: Dict[str, int] = {}
    for item in target_args:
        if "=" in item:
            k, v = item.split("=", 1)
            if v.isdigit():
                target[k] = int(v)
    return target


def main() -> int:
    """
    主入口函数。

    返回:
        0: 成功
        1: 配置错误
        2: LLM 错误
        130: 用户中断
    """
    parser = argparse.ArgumentParser(
        description=f"{Constants.TOOL_NAME} v{Constants.VERSION}：构建 P5 Eval Pool，并按类别分层切分 Dev/Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # 配置文件
    parser.add_argument("--cfg", default="configs/cfg.yaml", help="配置文件路径，命令行参数优先级更高")
    # 路径参数
    parser.add_argument("--root", default=None, help="源语料根目录（与 --input-jsonl 二选一）")
    parser.add_argument("--input-jsonl", default=None, 
                        help="从 filter_corpus_light.py 的 JSONL 输出读取（与 --root 二选一）")
    parser.add_argument("--out-dir", default=None, help="输出目录")
    # 分段参数
    parser.add_argument("--min-chars", type=int, default=None, help=f"段落最小字符数，默认 {Constants.DEFAULT_MIN_CHARS}")
    parser.add_argument("--max-chars", type=int, default=None, help=f"段落最大字符数，默认 {Constants.DEFAULT_MAX_CHARS}")
    # 抽样参数
    parser.add_argument("--target", nargs="+", default=None,
                        help="各类别抽取目标，如 law_plan=60 gazette_yearbook=80")
    parser.add_argument("--stratify-by", choices=["source_type", "topic_label"], default="source_type",
                        help="分层字段：source_type(按数据来源) 或 topic_label(按主题类型)，默认 source_type")
    parser.add_argument("--dev-ratio", type=float, default=None,
                        help=f"Dev 集比例，默认 {Constants.DEFAULT_DEV_RATIO}")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，用于复现结果")
    # 过滤参数
    parser.add_argument("--no-filter", action="store_true", help="跳过 LLM 质量过滤")
    parser.add_argument("--refilter", action="store_true", help="忽略缓存，强制重新过滤")
    parser.add_argument("--filter-cache", default=None, help="LLM 过滤缓存文件路径")
    # LLM 参数
    parser.add_argument("--llm-provider", default=None, help="LLM provider")
    parser.add_argument("--llm-model", default=None, help="LLM 模型名")
    parser.add_argument("--llm-temperature", type=float, default=None, help="LLM 温度")
    parser.add_argument("--llm-max-tokens", type=int, default=None,
                        help=f"LLM max_tokens，默认 {Constants.DEFAULT_MAX_TOKENS}")
    # 粗过滤参数
    parser.add_argument("--min-cn-ratio", type=float, default=None,
                        help=f"汉字占比阈值，默认 {Constants.DEFAULT_MIN_CN_RATIO}")
    parser.add_argument("--max-weird-ratio", type=float, default=None,
                        help=f"异常字符比例阈值，默认 {Constants.DEFAULT_MAX_WEIRD_RATIO}")
    parser.add_argument("--no-keyword-filter", action="store_true", help="不强制关键词命中")
    # 日志参数
    parser.add_argument("--log-file", default=None, help="日志文件路径")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    # 配置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_file = Path(args.log_file) if args.log_file else None
    global logger
    logger = setup_logger(level=log_level, log_file=log_file)

    # 加载配置文件
    cfg: Dict[str, Any] = {}
    if args.cfg:
        cfg_path = Path(args.cfg)
        if cfg_path.exists() and YAML_AVAILABLE:
            try:
                cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
                logger.debug(f"加载配置文件: {cfg_path}")
            except Exception as e:
                logger.warning(f"配置文件解析失败: {e}")

    # 参数优先级处理函数
    def pick(*vals, default=None):
        for v in vals:
            if v is not None and v != "":
                return v
        return default

    # 解析配置
    cfg_paths = cfg.get("paths", {}) if isinstance(cfg, dict) else {}
    cfg_filter = cfg.get("filtering", {}).get("eval", {}) if isinstance(cfg, dict) else {}
    cfg_evalpool = cfg.get("eval_pool", {}) if isinstance(cfg, dict) else {}
    cfg_llm = cfg.get("llm", {}) if isinstance(cfg, dict) else {}

    # 核心路径
    input_jsonl = Path(args.input_jsonl) if args.input_jsonl else None
    root = Path(pick(args.root, cfg_paths.get("corpus_full"), "data/corpus_for_kg/handled_used_kg_corpus")) if not input_jsonl else None
    out_dir = Path(pick(args.out_dir, cfg_paths.get("eval_pool_dir"), "data/p5_eval_pool"))

    # 输入源校验
    if input_jsonl:
        if not input_jsonl.exists():
            logger.error(f"JSONL 文件不存在: {input_jsonl}")
            return 1
        logger.info(f"输入模式: 从 JSONL 读取 ({input_jsonl})")
    else:
        if not root or not root.exists():
            logger.error(f"源目录不存在: {root}")
            return 1
        logger.info(f"输入模式: 从目录扫描 ({root})")

    # 抽样目标与分层字段
    # 优先级：命令行 > cfg.yaml > 默认值
    stratify_by = pick(
        args.stratify_by if args.stratify_by != "source_type" else None,  # 命令行显式指定时优先
        cfg_evalpool.get("stratify_by"),
        "source_type"  # 默认值
    )
    # 如果命令行显式指定了 --stratify-by，优先使用命令行值
    if args.stratify_by and args.stratify_by != "source_type":
        stratify_by = args.stratify_by
    
    # 根据分层字段选择目标配置
    if args.target:
        # 命令行显式指定优先
        target = parse_target(args.target)
    else:
        # 从 cfg.yaml 读取对应分层字段的目标配置
        if stratify_by == "topic_label":
            target_cfg = cfg_evalpool.get("target_topic_label") or cfg_evalpool.get("target") or {}
            default_target = Constants.DEFAULT_TARGET_TOPIC
        else:
            target_cfg = cfg_evalpool.get("target_source_type") or cfg_evalpool.get("target") or {}
            default_target = Constants.DEFAULT_TARGET
        
        if target_cfg:
            target = {k: int(v) for k, v in target_cfg.items()}
        else:
            target = dict(default_target)
    
    logger.info(f"分层策略: {stratify_by}, 目标配置: {target}")

    # 分段参数
    min_chars = pick(args.min_chars, cfg_filter.get("min_chars"), Constants.DEFAULT_MIN_CHARS)
    max_chars = pick(args.max_chars, cfg_filter.get("max_chars"), Constants.DEFAULT_MAX_CHARS)

    # Dev/Test 比例 - 修复：确保有默认值
    dev_ratio = pick(
        args.dev_ratio,
        cfg_evalpool.get("dev_ratio"),
        Constants.DEFAULT_DEV_RATIO
    )

    # 粗过滤参数
    min_cn = pick(args.min_cn_ratio, cfg_filter.get("min_cn_ratio"), Constants.DEFAULT_MIN_CN_RATIO)
    max_weird = pick(args.max_weird_ratio, cfg_filter.get("max_weird_ratio"), Constants.DEFAULT_MAX_WEIRD_RATIO)
    use_kw = not args.no_keyword_filter

    # 随机种子
    seed = pick(args.seed, cfg_evalpool.get("seed"), None)
    if seed is not None:
        random.seed(seed)
        logger.info(f"设置随机种子: {seed}")

    # ========== 执行流程 ==========
    logger.info("=" * 60)
    logger.info(f"{Constants.TOOL_NAME} v{Constants.VERSION}")
    logger.info("=" * 60)

    # 1. 收集段落
    if input_jsonl:
        logger.info(f"从 JSONL 加载: {input_jsonl}")
        segs = load_segments_from_jsonl(input_jsonl, min_chars, max_chars)
    else:
        logger.info(f"扫描源目录: {root}")
        segs = collect_segments(root, min_chars, max_chars)
    logger.info(f"收集段落 {len(segs)} 条")

    if not segs:
        logger.warning("未找到任何段落，请检查源目录")
        return 1

    # 2. 粗过滤
    kept_coarse: List[Segment] = []
    dropped = 0
    for s in segs:
        ok, reason = coarse_filter_segment(
            s,
            min_cn_ratio=min_cn,
            max_weird_ratio=max_weird,
            require_keyword=use_kw,
        )
        if ok:
            kept_coarse.append(s)
        else:
            dropped += 1
    segs = kept_coarse
    logger.info(f"粗过滤后 {len(segs)} 条（丢弃 {dropped} 条明显无关/乱码）")

    # 3. LLM 过滤
    try:
        if args.no_filter:
            filtered = segs
            logger.info(f"跳过 LLM 过滤，直接使用 {len(filtered)} 条")
        else:
            cache_path = Path(args.filter_cache) if args.filter_cache else out_dir / Constants.CACHE_FILE_NAME

            # 构建 LLM 配置
            llm_conf: Dict[str, Any] = {}
            # 基本参数
            llm_conf["temperature"] = pick(args.llm_temperature, cfg_llm.get("temperature"), 0.0)
            llm_conf["max_tokens"] = pick(args.llm_max_tokens, cfg_llm.get("max_tokens"), Constants.DEFAULT_MAX_TOKENS)
            # 思考模式（用于 LongCat-Flash-Thinking 等模型）
            llm_conf["enable_thinking"] = cfg_llm.get("enable_thinking", False)
            # 连接/鉴权相关
            base_url = pick(cfg_llm.get("base_url"))
            if base_url:
                llm_conf["base_url"] = base_url
            timeout = pick(cfg_llm.get("timeout"))
            if timeout is not None:
                llm_conf["timeout"] = timeout
            max_retries = pick(cfg_llm.get("max_retries"), Constants.DEFAULT_MAX_RETRIES)
            if max_retries is not None:
                llm_conf["max_retries"] = max_retries
            # 模型与 provider
            if args.llm_provider or cfg_llm.get("provider"):
                llm_conf["provider"] = pick(args.llm_provider, cfg_llm.get("provider"))
            if args.llm_model or cfg_llm.get("model_name"):
                llm_conf["model_name"] = pick(args.llm_model, cfg_llm.get("model_name"))

            logger.info(f"使用 LLM 过滤段落，缓存: {cache_path}")
            filtered = filter_segments_with_llm(
                segs,
                llm_conf,
                cache_path=cache_path,
                refilter=args.refilter,
            )
            logger.info(f"过滤后保留 {len(filtered)} 条（原始 {len(segs)}）")

    except KeyboardInterrupt:
        logger.warning("\n用户中断，进度已保存")
        return 130
    except LLMConfigError as e:
        # 配置级错误：不写缓存，立即停止
        logger.error(f"\n\u274c 配置错误: {e}")
        logger.error("提示: 请检查 --llm-model 或 cfg.yaml 中的模型名/API Key 配置")
        logger.error("未写入缓存，修正配置后重新运行即可")
        return 1
    except LLMParseError as e:
        # 解析错误：不写缓存
        logger.error(f"\n\u274c LLM 返回解析失败: {e}")
        logger.error("提示: LLM 返回了内容但无法解析为有效 JSON")
        logger.error("未写入缓存，请检查 Prompt 或更换模型后重试")
        return 1
    except LLMRetryExhaustedError as e:
        # 重试耗尽：不写缓存，退出交人工处理
        logger.error(f"\n\u274c LLM 调用重试耗尽: {e}")
        logger.error("提示: 可能是限流/网络问题，请稍后重试或更换 API Key")
        logger.error("未写入缓存，修复问题后从断点继续运行即可")
        return 2
    except Exception as e:
        err_str = str(e).lower()
        if "401" in err_str or "blocked" in err_str or "unauthorized" in err_str:
            logger.error(f"\u274c LLM 账号/Key 可能被封禁: {e}")
        elif "429" in err_str or "rate" in err_str:
            logger.error(f"\u26a0\ufe0f LLM 触发限流: {e}")
        else:
            logger.error(f"LLM 过滤失败: {e}")
        logger.info("进度已保存，可稍后重试继续")
        return 2

    # 4. 分层抽样
    logger.info(f"分层字段: {stratify_by}")
    sampled = sample_by_category(filtered, target, stratify_by=stratify_by)
    logger.info(f"按类别采样 {len(sampled)} 条（目标: {target}）")

    # 5. 划分 Dev/Test
    dev, test = split_dev_test(sampled, dev_ratio, stratify_by=stratify_by)
    logger.info(f"划分 Dev/Test -> Dev {len(dev)} | Test {len(test)} (ratio={dev_ratio})")

    # 6. 保存结果
    out_dir.mkdir(parents=True, exist_ok=True)
    save_jsonl(sampled, out_dir / "pool.jsonl")
    save_jsonl(dev, out_dir / "dev.jsonl")
    save_jsonl(test, out_dir / "test.jsonl")

    logger.info("=" * 60)
    logger.info(f"已保存到 {out_dir}")
    logger.info(f"  - pool.jsonl: {len(sampled)} 条")
    logger.info(f"  - dev.jsonl:  {len(dev)} 条")
    logger.info(f"  - test.jsonl: {len(test)} 条")
    logger.info(f"  分层字段: {stratify_by}")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
