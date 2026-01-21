# 文件路径: kg/llm_core.py
"""
统一的 LLM 调用模块，基于 OpenAI 兼容接口。

配置方式：
- API Key: 放在 .env 文件中
  - OPENAI_API_KEYS: 多个 Key 用逗号分隔，支持自动轮换
  - OPENAI_API_KEY: 单个 Key（向后兼容）
- 其他配置: 放在 cfg.yaml 的 llm 块中 (base_url, model_name, temperature 等)

支持的第三方 API：
- OpenAI 原生 API
- LongCat API（自动补全 /openai/v1，禁用 response_format）
- 其他 OpenAI 兼容 API（如 Gemini 代理等）

特性：
- 多 Key 轮换：遇到 429 限流自动切换到下一个可用 Key
- 智能冷却：记录 Key 限流时间，冷却后自动恢复
- 线程安全：支持多线程并发调用
"""
from typing import Any, Dict, List, Optional, Tuple
import json
import os
import re
import time
import logging
import logging.handlers
import threading
from dotenv import load_dotenv

load_dotenv()

# 日志配置
# =============================================================================
# 模块级 logger，默认使用模块名作为 logger 名称
logger = logging.getLogger(__name__)


class _FlushingRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """每次写入都立即刷新的 RotatingFileHandler"""
    
    def emit(self, record: logging.LogRecord) -> None:
        """写入日志记录后立即刷新"""
        super().emit(record)
        self.flush()


def configure_logger(
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    propagate: bool = True,
) -> logging.Logger:
    """
    配置 llm_core 模块的日志。
    
    如果调用方已经配置了根 logger,设置 propagate=True 就可以自动继承。
    如果需要独立输出到文件，可以指定 log_file。
    
    Args:
        log_file: 日志文件路径（可选）
        level: 日志级别
        propagate: 是否传播到父 logger
        
    Returns:
        配置后的 logger
    """
    logger.setLevel(level)
    logger.propagate = propagate
    
    if log_file:
        import logging.handlers
        import pathlib
        
        log_path = pathlib.Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 使用即时刷新的文件处理器
        file_handler = _FlushingRotatingFileHandler(
            log_path,
            encoding="utf-8",
            mode="a",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3,
        )
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    
    return logger


def set_logger(external_logger: logging.Logger) -> None:
    """
    使用外部传入的 logger。
    
    这允许调用方统一管理日志配置。
    
    Args:
        external_logger: 外部配置好的 logger
    """
    global logger
    logger = external_logger

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore


# =============================================================================
# 异常类
# =============================================================================
class RateLimitError(Exception):
    """触发限流（429）"""


class AccountBlockedError(Exception):
    """认证失败（401）"""


class ServiceUnavailableError(Exception):
    """服务不可用（5xx）"""


class EndpointNotFoundError(Exception):
    """端点不存在（404）- 通常是 base_url 配置错误"""


class AllKeysExhaustedError(Exception):
    """所有 API Key 均已耗尽配额"""


# =============================================================================
# API Key 管理器
# =============================================================================
class APIKeyManager:
    """
    API Key 管理器：智能轮换多个 Key，遇到限流自动切换。

    设计理念
    --------
    1. **加载多 Key**：从 OPENAI_API_KEYS 读取（逗号分隔），向后兼容 OPENAI_API_KEY
    2. **智能轮换**：遇到 429 边标记边切换，不耗尽不停止
    3. **冷却恢复**：记录限流时间，超过冷却期后自动恢复
    4. **线程安全**：使用锁保护共享状态

    使用示例
    --------
    ```python
    manager = APIKeyManager()
    key = manager.get_current_key()  # 获取当前 Key
    manager.mark_rate_limited()       # 遇到 429 时标记
    key = manager.get_current_key()  # 自动切换到下一个
    ```
    """

    # 默认冷却时间（60 秒）
    DEFAULT_COOLDOWN_SECONDS: int = 60

    def __init__(self, cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS):
        """
        初始化 API Key 管理器。

        Args:
            cooldown_seconds: Key 限流后的冷却时间（秒）
        """
        self._lock = threading.Lock()
        self._cooldown_seconds = cooldown_seconds

        # 加载所有 Key
        self._keys: List[str] = self._load_keys()
        if not self._keys:
            raise ValueError(
                "❌ 未找到 API Key，请在 .env 中配置\n"
                "   OPENAI_API_KEYS=key1,key2,key3  (多 Key 用逗号分隔)\n"
                "   或 OPENAI_API_KEY=your_key     (单 Key)"
            )

        # 当前使用的 Key 索引
        self._current_index: int = 0

        # 记录每个 Key 的限流时间戳（0 表示未限流）
        self._rate_limited_until: Dict[int, float] = {}

        logger.info(
            f"API Key 管理器初始化: 共 {len(self._keys)} 个 Key, "
            f"冷却时间 {cooldown_seconds}s"
        )

    def _load_keys(self) -> List[str]:
        """
        从环境变量加载 API Keys。

        优先级：OPENAI_API_KEYS > OPENAI_API_KEY

        Returns:
            Key 列表（去重、去空）
        """
        keys: List[str] = []

        # 优先从 OPENAI_API_KEYS 加载（多 Key）
        keys_str = os.getenv("OPENAI_API_KEYS", "")
        if keys_str:
            for key in keys_str.split(","):
                key = key.strip()
                if key and key not in keys:
                    keys.append(key)

        # 向后兼容：如果没有 OPENAI_API_KEYS，尝试 OPENAI_API_KEY
        if not keys:
            single_key = os.getenv("OPENAI_API_KEY", "").strip()
            if single_key:
                keys.append(single_key)

        return keys

    def get_current_key(self) -> str:
        """
        获取当前可用的 API Key。

        如果当前 Key 处于冷却中，自动切换到下一个。

        Returns:
            可用的 API Key

        Raises:
            AllKeysExhaustedError: 所有 Key 均在冷却中
        """
        with self._lock:
            now = time.time()
            tried = 0

            while tried < len(self._keys):
                # 检查当前 Key 是否已冷却
                limited_until = self._rate_limited_until.get(self._current_index, 0)

                if limited_until <= now:
                    # 已冷却或未限流，可以使用
                    if limited_until > 0:
                        # 清除冷却标记
                        del self._rate_limited_until[self._current_index]
                        logger.info(
                            f"API Key #{self._current_index + 1} 已冷却完成，恢复使用"
                        )
                    return self._keys[self._current_index]

                # 当前 Key 仍在冷却，尝试下一个
                self._current_index = (self._current_index + 1) % len(self._keys)
                tried += 1

            # 所有 Key 都在冷却中
            min_wait = min(
                self._rate_limited_until.get(i, 0) - now
                for i in range(len(self._keys))
            )
            raise AllKeysExhaustedError(
                f"所有 {len(self._keys)} 个 API Key 均在冷却中，"
                f"最短等待 {max(0, min_wait):.0f} 秒"
            )

    def mark_rate_limited(self, key: Optional[str] = None) -> bool:
        """
        标记当前 Key 为限流状态，并切换到下一个。

        Args:
            key: 要标记的 Key（可选，默认为当前 Key）

        Returns:
            True 如果成功切换到新 Key，False 如果所有 Key 都已限流
        """
        with self._lock:
            # 确定要标记的 Key 索引
            if key:
                try:
                    idx = self._keys.index(key)
                except ValueError:
                    idx = self._current_index
            else:
                idx = self._current_index

            # 记录限流时间
            now = time.time()
            self._rate_limited_until[idx] = now + self._cooldown_seconds

            key_preview = self._keys[idx][:8] + "..."
            logger.warning(
                f"API Key #{idx + 1} ({key_preview}) 遇到 429 限流，"
                f"冷却 {self._cooldown_seconds}s"
            )

            # 尝试切换到下一个可用 Key
            for _ in range(len(self._keys)):
                self._current_index = (self._current_index + 1) % len(self._keys)
                if self._rate_limited_until.get(self._current_index, 0) <= now:
                    new_preview = self._keys[self._current_index][:8] + "..."
                    logger.info(
                        f"已切换到 API Key #{self._current_index + 1} ({new_preview})"
                    )
                    return True

            # 所有 Key 都已限流
            logger.error(
                f"所有 {len(self._keys)} 个 API Key 均已限流，"
                f"请等待 {self._cooldown_seconds}s 后重试"
            )
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        获取所有 Key 的状态。

        Returns:
            状态字典，包含每个 Key 的可用性和冷却时间
        """
        with self._lock:
            now = time.time()
            status = {
                "total_keys": len(self._keys),
                "current_index": self._current_index,
                "keys": []
            }

            for i, key in enumerate(self._keys):
                limited_until = self._rate_limited_until.get(i, 0)
                remaining = max(0, limited_until - now)
                status["keys"].append({
                    "index": i + 1,
                    "preview": key[:8] + "...",
                    "is_current": i == self._current_index,
                    "is_available": limited_until <= now,
                    "cooldown_remaining": round(remaining, 1) if remaining > 0 else 0,
                })

            return status

    @property
    def available_count(self) -> int:
        """当前可用的 Key 数量"""
        with self._lock:
            now = time.time()
            return sum(
                1 for i in range(len(self._keys))
                if self._rate_limited_until.get(i, 0) <= now
            )

    @property
    def total_count(self) -> int:
        """总 Key 数量"""
        return len(self._keys)


# 全局单例（延迟初始化）
_global_key_manager: Optional[APIKeyManager] = None
_global_key_manager_lock = threading.Lock()


def get_key_manager(cooldown_seconds: int = 60) -> APIKeyManager:
    """
    获取全局 API Key 管理器单例。

    Args:
        cooldown_seconds: Key 冷却时间（仅首次创建时有效）

    Returns:
        APIKeyManager 实例
    """
    global _global_key_manager
    if _global_key_manager is None:
        with _global_key_manager_lock:
            if _global_key_manager is None:
                _global_key_manager = APIKeyManager(cooldown_seconds)
    return _global_key_manager


# =============================================================================
# 已知的第三方 API 配置
# =============================================================================
# 不支持 response_format 参数的 API 提供商（小写匹配）
_PROVIDERS_NO_RESPONSE_FORMAT = {
    "longcat",      # LongCat API
    "gemini",       # Gemini 代理
    "deepseek",     # DeepSeek（部分模型）
    "runanytime",   # RunAnytime 代理
}

# 需要自动补全路径的 API 提供商
_PROVIDER_URL_FIXES = {
    "longcat.chat": "/openai/v1",  # LongCat: api.longcat.chat -> api.longcat.chat/openai/v1
    "runanytime.hxi.me": "/v1",    # RunAnytime: runanytime.hxi.me -> runanytime.hxi.me/v1
}


# =============================================================================
# LLM 客户端
# =============================================================================
class LLMClient:
    """
    统一的 LLM 客户端，基于 OpenAI 兼容接口。
    
    特性：
    - 多 Key 轮换：遇到 429 限流自动切换到下一个可用 Key
    - 自动识别第三方 API 并适配（如 LongCat、Gemini 代理）
    - 自动修正 base_url（如 LongCat 需要补全 /openai/v1）
    - 自动禁用不支持的参数（如 response_format）
    - 完整的错误处理和日志记录
    - 支持上下文管理器，自动关闭连接
    
    使用方式：
        llm = LLMClient(config)  # config 来自 cfg.yaml 的 llm 块
        response = llm.chat("你好")
        llm.close()  # 使用完毕后关闭
        
        # 或者使用上下文管理器
        with LLMClient(config) as llm:
            response = llm.chat("你好")
    """

    def __init__(self, config: dict, key_manager: Optional[APIKeyManager] = None):
        """
        初始化 LLM 客户端。
        
        Args:
	            config: LLM 配置字典，包含以下字段：
	                - base_url: API 基础地址（必需）
	                - model_name: 模型名称（必需）
	                - temperature: 温度参数（默认 0.1）
	                - max_retries: 最大重试次数（默认 3）
	                - top_p: Top-P 参数（可选）
	                - timeout: 超时时间秒（默认 60）
	                - max_tokens: 最大生成 token 数（可选；仅在显式配置时才传给 API）
	                - request_mode: 请求方式（sdk/post/auto，默认 sdk）
	                - disable_response_format: 是否强制禁用 response_format（默认 false）
            key_manager: API Key 管理器（可选，默认使用全局单例）
        
        Raises:
            ImportError: 使用 sdk 但未安装 openai 库
            ValueError: 缺少必要配置
        """
        # ===== API Key 管理器 =====
        self._key_manager = key_manager or get_key_manager()
        self._current_api_key: str = self._key_manager.get_current_key()

        # ===== 请求方式配置 =====
        raw_request_mode = (
            config.get("request_mode")
            or os.getenv("LLM_REQUEST_MODE")
            or "sdk"
        )
        raw_request_mode = str(raw_request_mode).lower()
        if raw_request_mode not in {"sdk", "post", "auto"}:
            logger.warning(f"未知 request_mode={raw_request_mode}，将回退为 sdk")
            raw_request_mode = "sdk"
        self.request_mode = raw_request_mode
        self._http_session = None  # requests.Session，按需初始化

        # ===== response_format 开关 =====
        raw_disable_response_format = (
            config.get("disable_response_format")
            if "disable_response_format" in config
            else os.getenv("LLM_DISABLE_RESPONSE_FORMAT")
        )
        self.disable_response_format = str(raw_disable_response_format).lower() in {"1", "true", "yes", "on"}

        # ===== base_url：从 cfg.yaml 读取并自动修正 =====
        base_url = config.get("base_url") or os.getenv("OPENAI_BASE_URL")
        if not base_url:
            raise ValueError("❌ 未找到 base_url，请在 cfg.yaml 的 llm 块中配置")
        
        # 自动修正 base_url（如 LongCat 需要补全 /openai/v1）
        base_url = self._normalize_base_url(base_url)

        # ===== model：从 cfg.yaml 读取 =====
        self.model = config.get("model_name") or config.get("model")
        if not self.model:
            raise ValueError("❌ 未找到 model_name，请在 cfg.yaml 的 llm 块中配置")

        # ===== 创建 OpenAI SDK 客户端（按需）=====
        self.client = None
        if self.request_mode in {"sdk", "auto"}:
            if OpenAI is None:
                if self.request_mode == "sdk":
                    raise ImportError("未安装 openai，请先 pip install openai，或设置 llm.request_mode=post")
            else:
                self.client = OpenAI(api_key=self._current_api_key, base_url=base_url)
        self.base_url = base_url
        self.temperature = config.get("temperature", 0.1)
        self.max_retries = config.get("max_retries", 3)
        self.no_retry = bool(
            config.get("no_retry")
            or str(os.getenv("LLM_NO_RETRY", "")).lower() in {"1", "true", "yes", "on"}
        )
        self.top_p = config.get("top_p")
        self.timeout = config.get("timeout", 60)
        
        # ===== 思考模式配置 =====
        self.enable_thinking = config.get("enable_thinking", False)
        self.extra_body = None
        raw_extra_body = config.get("extra_body")
        if raw_extra_body is not None:
            if isinstance(raw_extra_body, dict):
                self.extra_body = raw_extra_body
            elif isinstance(raw_extra_body, str):
                try:
                    self.extra_body = json.loads(raw_extra_body)
                except json.JSONDecodeError:
                    logger.warning("extra_body JSON 解析失败，已忽略。")
            else:
                logger.warning("extra_body 类型不支持，已忽略。")
        if self.extra_body is not None and self.enable_thinking:
            logger.info("extra_body 已提供，将忽略 enable_thinking 设置。")
        
        # ===== 检测 API 提供商特性 =====
        self._provider_name = self._detect_provider(base_url)
        self._supports_response_format = self._provider_name not in _PROVIDERS_NO_RESPONSE_FORMAT
        if self.disable_response_format:
            logger.info("已强制禁用 response_format 参数（disable_response_format=true）")
        
        # ===== max_tokens 配置 =====
        # 语义：只有在 cfg.yaml 中显式给出 max_tokens 时才传给 API。
        # 默认不传 max_tokens，让后端自行使用默认输出上限。
        raw_max_tokens = config.get("max_tokens")
        self.max_tokens = raw_max_tokens if raw_max_tokens is not None else None
        
        # 记录初始化信息
        key_preview = self._current_api_key[:8] + "..."
        thinking_status = "✅" if self.enable_thinking else "❌"
        logger.info(
            f"LLM 客户端初始化: model={self.model}, "
            f"provider={self._provider_name or 'openai'}, "
            f"thinking={thinking_status}, "
            f"key={key_preview}, "
            f"available_keys={self._key_manager.available_count}/{self._key_manager.total_count}"
        )

    def _normalize_base_url(self, base_url: str) -> str:
        """
        规范化 base_url，自动修正已知的第三方 API 路径问题。
        
        已知修正：
        - LongCat: https://api.longcat.chat -> https://api.longcat.chat/openai/v1
        
        Args:
            base_url: 原始 base_url
            
        Returns:
            修正后的 base_url
        """
        original_url = base_url
        base_url = base_url.rstrip("/")
        
        # 检查是否需要自动补全路径
        for domain_pattern, suffix in _PROVIDER_URL_FIXES.items():
            if domain_pattern in base_url.lower():
                # 检查是否已经包含正确的路径
                if not base_url.endswith(suffix):
                    # 处理部分路径的情况
                    if "/openai" in base_url and not base_url.endswith("/v1"):
                        base_url = base_url.rstrip("/") + "/v1"
                    elif "/openai" not in base_url:
                        base_url = base_url + suffix
                    
                    logger.info(f"自动修正 base_url: {original_url} -> {base_url}")
                break
        
        return base_url

    def _detect_provider(self, base_url: str) -> str:
        """
        根据 base_url 检测 API 提供商。
        
        Args:
            base_url: API 地址
            
        Returns:
            提供商标识（小写），如 'longcat', 'gemini'，未知则返回空字符串
        """
        url_lower = base_url.lower()
        for provider in _PROVIDERS_NO_RESPONSE_FORMAT:
            if provider in url_lower:
                return provider
        return ""

    def _resolve_request_backend(self) -> str:
        """
        解析当前实际使用的请求后端。

        request_mode 语义：
        - sdk: 强制使用 OpenAI SDK
        - post: 强制使用 HTTP POST（OpenAI 兼容接口）
        - auto: 优先 SDK，若 SDK 不可用则退化为 POST
        """
        if self.request_mode == "auto":
            return "sdk" if self.client is not None else "post"
        return self.request_mode

    def _call_chat_completions_sdk(self, params: Dict[str, Any]) -> str:
        """通过 OpenAI SDK 调用 chat.completions.create。"""
        if self.client is None:
            raise RuntimeError("OpenAI SDK 客户端未初始化（请检查 request_mode / openai 安装）")
        resp = self.client.chat.completions.create(**params)
        return resp.choices[0].message.content or ""

    def _call_chat_completions_post(self, params: Dict[str, Any]) -> str:
        """
        通过 HTTP POST 调用 OpenAI 兼容的 /chat/completions 接口。

        设计目标：
        - 与 curl / requests 调用等价；
        - 不依赖 OpenAI SDK；
        - 失败时抛出包含 HTTP 状态码的异常，便于上层重试/换 key。
        """
        timeout = float(params.get("timeout", self.timeout))
        request_body = {k: v for k, v in params.items() if k != "timeout"}
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._current_api_key}",
        }
        body_json = json.dumps(request_body, ensure_ascii=False)

        # 优先使用 requests（若未安装则回退 urllib）
        try:
            import requests  # type: ignore

            if self._http_session is None:
                self._http_session = requests.Session()

            response = self._http_session.post(
                url,
                headers=headers,
                data=body_json.encode("utf-8"),
                timeout=timeout,
            )
            status_code = int(response.status_code)
            text = response.text or ""
            if status_code != 200:
                raise Exception(f"HTTP {status_code}: {text[:1000]}")
            result = response.json()

        except ImportError:
            import urllib.request
            import urllib.error

            req = urllib.request.Request(
                url,
                data=body_json.encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    status_code = int(resp.getcode() or 0)
                    text = resp.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as http_error:
                status_code = int(http_error.code or 0)
                text = http_error.read().decode("utf-8", errors="replace")
            if status_code != 200:
                raise Exception(f"HTTP {status_code}: {text[:1000]}")
            result = json.loads(text)

        choices = result.get("choices") or []
        if not choices:
            raise Exception(f"无效响应: {str(result)[:500]}")
        content = choices[0].get("message", {}).get("content", "") or ""
        return content

    def _call_chat_completions(self, params: Dict[str, Any]) -> str:
        """根据 request_mode 分派到 SDK 或 POST 后端。"""
        backend = self._resolve_request_backend()
        if backend == "sdk":
            return self._call_chat_completions_sdk(params)
        if backend == "post":
            return self._call_chat_completions_post(params)
        raise ValueError(f"未知请求后端: {backend}")

    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
    ) -> str:
        """
        单轮对话。
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            json_mode: 是否要求返回 JSON 格式
            
        Returns:
            模型响应文本
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.chat_messages(messages, json_mode=json_mode)

    def chat_messages(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
    ) -> str:
        """
        多轮对话。
        
        Args:
            messages: 消息列表，每条消息包含 role 和 content
            json_mode: 是否要求返回 JSON 格式（部分 API 不支持）
            
        Returns:
            模型响应文本
            
        Raises:
            AccountBlockedError: 认证失败 (401)
            RateLimitError: 触发限流 (429)
            ServiceUnavailableError: 服务不可用 (5xx)
            EndpointNotFoundError: 端点不存在 (404)
        """
        last_error = None
        # 是否尝试使用 response_format（如果 API 不支持会自动禁用，或被配置强制关闭）
        use_response_format = (
            json_mode
            and self._supports_response_format
            and not self.disable_response_format
        )

        # 是否开启详细请求日志（用于排查超时/限流等问题）
        debug_llm = os.getenv("LLM_DEBUG", "").lower() in {"1", "true", "yes", "on"}
        debug_curl = os.getenv("LLM_DEBUG_CURL", "").lower() in {"1", "true", "yes", "on"}

        def truncate_for_log(text: str, max_chars: int = 400) -> str:
            """截断文本用于日志打印，避免过长。"""
            clean_text = (text or "").replace("\n", " ").strip()
            if max_chars <= 0 or len(clean_text) <= max_chars:
                return clean_text
            return clean_text[:max_chars] + f"...(截断，原长 {len(clean_text)} 字)"

        def flush_log_handlers() -> None:
            """刷新日志 handlers，确保每次调用及时落盘。"""
            for handler in logger.handlers:
                try:
                    handler.flush()
                except Exception:
                    continue

        def shell_escape_single_quotes(text: str) -> str:
            """在 shell 单引号字符串中安全转义单引号。"""
            return (text or "").replace("'", "'\"'\"'")
        
        attempts_total = 1 if self.no_retry else self.max_retries
        for attempt in range(attempts_total):
            try:
                # ===== 构建请求参数 =====
                params = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.1 if json_mode else self.temperature,
                    "timeout": self.timeout,
                }
                if self.max_tokens is not None:
                    params["max_tokens"] = self.max_tokens
                if self.top_p is not None:
                    params["top_p"] = self.top_p
                
                # 只有支持 response_format 的 API 才添加此参数
                if use_response_format:
                    params["response_format"] = {"type": "json_object"}
                
                # ===== 发送请求 =====
                extra_body = self.extra_body
                if extra_body is None and self.enable_thinking:
                    extra_body = {"thinking": {"type": "enabled"}}
                if extra_body is not None:
                    params["extra_body"] = extra_body
                    logger.debug("🧠 extra_body 已启用，正在调用 LLM...")
                else:
                    logger.debug("💬 普通模式调用 LLM...")

                if debug_llm:
                    total_chars = sum(len(m.get("content", "")) for m in messages)
                    msg_lines = []
                    for msg_idx, msg in enumerate(messages, start=1):
                        role = msg.get("role", "")
                        content = msg.get("content", "")
                        msg_lines.append(
                            f"  - msg{msg_idx} role={role}, len={len(content)}, "
                            f"preview={truncate_for_log(content)}"
                        )
                    logger.info("=" * 80)
                    logger.info(
                        "[LLM][REQ] attempt=%s/%s provider=%s model=%s base_url=%s "
                        "json_mode=%s response_format=%s thinking=%s extra_body=%s timeout=%ss "
                        "temperature=%s max_tokens=%s messages=%s total_chars=%s\n%s",
                        attempt + 1,
                        attempts_total,
                        self.provider,
                        self.model,
                        self.base_url,
                        json_mode,
                        use_response_format,
                        self.enable_thinking,
                        "set" if extra_body is not None else "none",
                        self.timeout,
                        params.get("temperature"),
                        self.max_tokens,
                        len(messages),
                        total_chars,
                        "\n".join(msg_lines),
                    )
                    flush_log_handlers()

                    if debug_curl:
                        request_url = f"{self.base_url.rstrip('/')}/chat/completions"
                        request_body = dict(params)
                        request_body.pop("timeout", None)  # timeout 用 curl 的 --max-time 表达
                        body_json = json.dumps(request_body, ensure_ascii=False)
                        escaped_body = shell_escape_single_quotes(body_json)
                        curl_lines = [
                            f"curl -sS -X POST '{request_url}' \\",
                            "  -H 'Content-Type: application/json' \\",
                            "  -H 'Authorization: Bearer ${OPENAI_API_KEY}' \\",
                            f"  --max-time {self.timeout} \\",
                            f"  -d '{escaped_body}'",
                        ]
                        logger.info("[LLM][CURL]\n%s", "\n".join(curl_lines))
                        flush_log_handlers()

                request_start = time.time()
                content = self._call_chat_completions(params)
                
                # 成功时记录日志
                if attempt > 0:
                    logger.info(f"LLM 调用成功（第 {attempt + 1} 次尝试）")

                if debug_llm:
                    elapsed = time.time() - request_start
                    logger.info(
                        "[LLM][RESP] attempt=%s/%s elapsed=%.2fs content_len=%s preview=%s",
                        attempt + 1,
                        attempts_total,
                        elapsed,
                        len(content),
                        truncate_for_log(content, max_chars=600),
                    )
                    flush_log_handlers()
                
                return content
                
            except TypeError as e:
                # ===== API 不支持某些参数（如 response_format）=====
                err_str = str(e)
                if debug_llm:
                    logger.warning(
                        "[LLM][ERR] attempt=%s/%s error_type=TypeError error=%s",
                        attempt + 1,
                        self.max_retries,
                        err_str[:800],
                    )
                    flush_log_handlers()
                if "response_format" in err_str or "unexpected keyword argument" in err_str:
                    if use_response_format:
                        if self.no_retry:
                            raise
                        logger.warning(
                            f"API 不支持 response_format 参数，已禁用并重试 "
                            f"(provider={self._provider_name or 'unknown'})"
                        )
                        use_response_format = False
                        self._supports_response_format = False  # 更新标记，避免后续重复尝试
                        continue  # 不计入重试次数
                
                # 其他 TypeError
                last_error = e
                logger.error(f"LLM 调用类型错误: {e}")
                
            except Exception as e:
                last_error = e
                err_msg = str(e)
                err_lower = err_msg.lower()

                if debug_llm:
                    logger.warning(
                        "[LLM][ERR] attempt=%s/%s error_type=%s error=%s",
                        attempt + 1,
                        self.max_retries,
                        type(e).__name__,
                        err_msg[:800],
                    )
                    flush_log_handlers()
                
                # ===== 404 端点不存在：通常是 base_url 配置错误 =====
                if "404" in err_lower or "not found" in err_lower:
                    logger.error(
                        f"❌ API 端点不存在 (404): {err_msg}\n"
                        f"   当前 base_url: {self.base_url}\n"
                        f"   请检查 cfg.yaml 中的 llm.base_url 配置是否正确"
                    )
                    # 404 错误不重试，直接抛出
                    raise EndpointNotFoundError(
                        f"API 端点不存在，请检查 base_url 配置: {self.base_url}"
                    ) from e
                
                # ===== 401 认证失败：不重试 =====
                if "401" in err_lower or "unauthorized" in err_lower:
                    logger.error(f"❌ API 认证失败 (401): {err_msg}")
                    raise AccountBlockedError(str(e))
                
                # ===== 429 限流：尝试切换 Key =====
                if "429" in err_lower or "rate limit" in err_lower:
                    if self.no_retry:
                        raise RateLimitError(str(e))
                    # 标记当前 Key 为限流，尝试切换到下一个
                    if self._switch_to_next_key():
                        # 成功切换到新 Key，立即重试（不算作重试次数）
                        logger.info("已切换 API Key，立即重试...")
                        continue
                    else:
                        # 所有 Key 都已限流，等待后重试
                        wait = 2 ** attempt
                        logger.warning(
                            f"⏳ 所有 Key 均已限流，等待 {wait}s 后重试 "
                            f"({attempt + 1}/{self.max_retries})"
                        )
                        time.sleep(wait)
                        continue
                
                # ===== 5xx 服务不可用：等待 60s 后重试 =====
                if any(code in err_lower for code in ["500", "502", "503", "504"]):
                    if self.no_retry:
                        raise ServiceUnavailableError(str(e))
                    if attempt < self.max_retries - 1:
                        logger.warning(
                            f"⏳ API 服务不可用 (5xx)，等待 60s 后重试 "
                            f"({attempt + 1}/{self.max_retries}): {err_msg[:100]}"
                        )
                        time.sleep(60)
                        continue
                    logger.error(f"❌ API 服务持续不可用: {err_msg}")
                    raise ServiceUnavailableError(str(e))

                # ===== 其他错误：等待 60s 后重试 =====
                if self.no_retry:
                    raise
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"⚠️ LLM 调用失败，等待 60s 后重试 ({attempt + 1}/{self.max_retries}): {err_msg[:200]}"
                    )
                    time.sleep(60)
                else:
                    logger.error(f"❌ LLM 调用失败（已重试 {self.max_retries} 次）: {err_msg[:500]}")
        
        # ===== 所有重试均失败 =====
        if last_error:
            if "429" in str(last_error):
                raise RateLimitError(str(last_error))
            logger.error(f"⚠️ API 调用最终失败: {last_error}")
        
        return ""

    def is_available(self) -> bool:
        """
        检查 LLM 后端是否可用。
        
        发送一个简单请求验证连接和认证。
        
        Returns:
            True 如果后端可用，否则 False
        """
        try:
            params = {
                "model": self.model,
                "messages": [{"role": "user", "content": "hi"}],
                "temperature": self.temperature,
                "timeout": 15,
                "max_tokens": 10,
            }
            self._call_chat_completions(params)
            logger.info(f"LLM 后端验证通过: model={self.model}")
            return True
        except Exception as e:
            err_msg = str(e)[:200]
            logger.warning(f"⚠️ LLM 后端不可用: {err_msg}")
            return False
    
    @property
    def provider(self) -> str:
        """获取 API 提供商标识"""
        return self._provider_name or "openai"

    def _switch_to_next_key(self) -> bool:
        """
        切换到下一个可用的 API Key。

        当遇到 429 限流时调用，标记当前 Key 并切换到下一个。

        Returns:
            True 如果成功切换到新 Key，False 如果所有 Key 都已限流
        """
        # 标记当前 Key 为限流
        has_next = self._key_manager.mark_rate_limited(self._current_api_key)

        if not has_next:
            return False

        try:
            # 获取新的 Key
            new_key = self._key_manager.get_current_key()
            if new_key == self._current_api_key:
                return False

            # 关闭旧客户端
            if self.client is not None:
                try:
                    self.client.close()
                except Exception:
                    pass

            # 更新当前 Key；按需创建新 SDK 客户端
            self._current_api_key = new_key
            if OpenAI is not None and self.request_mode in {"sdk", "auto"}:
                self.client = OpenAI(api_key=new_key, base_url=self.base_url)
            else:
                self.client = None

            key_preview = new_key[:8] + "..."
            logger.info(
                f"已切换到新 API Key: {key_preview}, "
                f"剩余可用: {self._key_manager.available_count}/{self._key_manager.total_count}"
            )
            return True

        except AllKeysExhaustedError:
            return False

    def close(self) -> None:
        """
        关闭 LLM 客户端，释放 HTTP 连接资源。
        
        重要：使用完 LLM 客户端后应调用此方法，
        否则程序可能会在退出时等待连接超时。
        """
        if self.client is not None:
            try:
                self.client.close()
                logger.debug("LLM 客户端已关闭")
            except Exception as e:
                logger.warning(f"关闭 LLM 客户端时出错: {e}")
        
        if self._http_session is not None:
            try:
                self._http_session.close()
                self._http_session = None
            except Exception as e:
                logger.warning(f"关闭 HTTP Session 时出错: {e}")

    def __enter__(self) -> "LLMClient":
        """支持上下文管理器"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出时自动关闭连接"""
        self.close()


# =============================================================================
# 工厂函数（兼容旧代码）
# =============================================================================
class LLMFactory:
    """LLM 工厂，用于创建 LLM 客户端"""
    
    @staticmethod
    def create(llm_config: dict) -> LLMClient:
        """
        创建 LLM 客户端。
        
        Args:
            llm_config: 来自 cfg.yaml 的 llm 配置块
            
        Returns:
            LLMClient 实例
        """
        model = llm_config.get("model_name") or llm_config.get("model", "unknown")
        base_url = llm_config.get("base_url", "")[:50]
        logger.info(f"[LLMFactory] 创建客户端: model={model}, base_url={base_url}...")
        return LLMClient(llm_config)


# 向后兼容的别名
LLMBackend = LLMClient
UnifiedOpenAIBackend = LLMClient
OpenAIBackend = LLMClient


# =============================================================================
# 辅助函数
# =============================================================================
def draft_answer_with_graph(question: str, evidence: list, llm_config: dict) -> str:
    """
    基于图谱三元组生成答案。
    
    Args:
        question: 用户问题
        evidence: 知识图谱三元组列表 [(subject, relation, object), ...]
        llm_config: LLM 配置
        
    Returns:
        生成的答案文本
    """
    evidence_str = "\n".join([f"- {s} {r} {o}" for s, r, o in evidence])
    prompt = f"""请根据以下知识图谱信息回答问题。

【知识证据】：
{evidence_str}

【问题】：{question}

要求：回答准确连贯，证据不足时如实说明。"""
    
    llm = LLMFactory.create(llm_config)
    return llm.chat(prompt, system_prompt="你是灾害问答专家。")


__all__ = [
    # 异常类
    "RateLimitError",
    "AccountBlockedError", 
    "ServiceUnavailableError",
    "EndpointNotFoundError",
    "AllKeysExhaustedError",
    # API Key 管理
    "APIKeyManager",
    "get_key_manager",
    # 客户端
    "LLMClient",
    "LLMFactory",
    # 兼容别名
    "LLMBackend",
    "OpenAIBackend",
    # 辅助函数
    "draft_answer_with_graph",
    # 日志配置
    "configure_logger",
    "set_logger",
]
