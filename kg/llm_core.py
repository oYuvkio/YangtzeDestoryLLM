# 文件路径: kg/llm_core.py
"""
统一的 LLM 调用模块，基于 OpenAI 兼容接口。

配置方式：
- API Key: 放在 .env 文件中 (OPENAI_API_KEY)
- 其他配置: 放在 cfg.yaml 的 llm 块中 (base_url, model_name, temperature 等)

支持的第三方 API：
- OpenAI 原生 API
- LongCat API（自动补全 /openai/v1，禁用 response_format）
- 其他 OpenAI 兼容 API（如 Gemini 代理等）
"""
from typing import Any, Dict, List, Optional
import os
import re
import time
import logging
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
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
    
    如果调用方已经配置了根 logger，设置 propagate=True 就可以自动继承。
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


# =============================================================================
# 已知的第三方 API 配置
# =============================================================================
# 不支持 response_format 参数的 API 提供商（小写匹配）
_PROVIDERS_NO_RESPONSE_FORMAT = {
    "longcat",      # LongCat API
    "gemini",       # Gemini 代理
    "deepseek",     # DeepSeek（部分模型）
}

# 需要自动补全路径的 API 提供商
_PROVIDER_URL_FIXES = {
    "longcat.chat": "/openai/v1",  # LongCat: api.longcat.chat -> api.longcat.chat/openai/v1
}


# =============================================================================
# LLM 客户端
# =============================================================================
class LLMClient:
    """
    统一的 LLM 客户端，基于 OpenAI 兼容接口。
    
    特性：
    - 自动识别第三方 API 并适配（如 LongCat、Gemini 代理）
    - 自动修正 base_url（如 LongCat 需要补全 /openai/v1）
    - 自动禁用不支持的参数（如 response_format）
    - 完整的错误处理和日志记录
    
    使用方式：
        llm = LLMClient(config)  # config 来自 cfg.yaml 的 llm 块
        response = llm.chat("你好")
    """

    def __init__(self, config: dict):
        """
        初始化 LLM 客户端。
        
        Args:
            config: LLM 配置字典，包含以下字段：
                - base_url: API 基础地址（必需）
                - model_name: 模型名称（必需）
                - temperature: 温度参数（默认 0.1）
                - max_retries: 最大重试次数（默认 3）
                - timeout: 超时时间秒（默认 60）
                - max_tokens: 最大生成 token 数（默认 8192）
        
        Raises:
            ImportError: 未安装 openai 库
            ValueError: 缺少必要配置
        """
        if OpenAI is None:
            raise ImportError("未安装 openai，请先 pip install openai")

        # ===== API Key：从 .env 读取 =====
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("❌ 未找到 OPENAI_API_KEY，请在 .env 中配置")

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

        # ===== 创建客户端 =====
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.base_url = base_url
        self.temperature = config.get("temperature", 0.1)
        self.max_retries = config.get("max_retries", 3)
        self.timeout = config.get("timeout", 60)
        self.max_tokens = config.get("max_tokens", 8192)  # LongCat 默认需要指定
        
        # ===== 检测 API 提供商特性 =====
        self._provider_name = self._detect_provider(base_url)
        self._supports_response_format = self._provider_name not in _PROVIDERS_NO_RESPONSE_FORMAT
        
        # 记录初始化信息
        logger.info(
            f"LLM 客户端初始化: model={self.model}, "
            f"provider={self._provider_name or 'openai'}, "
            f"supports_response_format={self._supports_response_format}"
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
        # 是否尝试使用 response_format（如果 API 不支持会自动禁用）
        use_response_format = json_mode and self._supports_response_format
        
        for attempt in range(self.max_retries):
            try:
                # ===== 构建请求参数 =====
                params = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.1 if json_mode else self.temperature,
                    "timeout": self.timeout,
                    "max_tokens": self.max_tokens,
                }
                
                # 只有支持 response_format 的 API 才添加此参数
                if use_response_format:
                    params["response_format"] = {"type": "json_object"}
                
                # ===== 发送请求 =====
                resp = self.client.chat.completions.create(**params)
                content = resp.choices[0].message.content or ""
                
                # 成功时记录日志
                if attempt > 0:
                    logger.info(f"LLM 调用成功（第 {attempt + 1} 次尝试）")
                
                return content
                
            except TypeError as e:
                # ===== API 不支持某些参数（如 response_format）=====
                err_str = str(e)
                if "response_format" in err_str or "unexpected keyword argument" in err_str:
                    if use_response_format:
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
                
                # ===== 429 限流：指数退避 =====
                if "429" in err_lower or "rate limit" in err_lower:
                    wait = 2 ** attempt
                    logger.warning(
                        f"⏳ API 限流 (429)，等待 {wait}s 后重试 "
                        f"({attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(wait)
                    continue
                
                # ===== 5xx 服务不可用：短暂等待 =====
                if any(code in err_lower for code in ["500", "502", "503", "504"]):
                    if attempt < self.max_retries - 1:
                        logger.warning(
                            f"⏳ API 服务不可用 (5xx)，等待 1s 后重试 "
                            f"({attempt + 1}/{self.max_retries}): {err_msg[:100]}"
                        )
                        time.sleep(1)
                        continue
                    logger.error(f"❌ API 服务持续不可用: {err_msg}")
                    raise ServiceUnavailableError(str(e))
                
                # ===== 其他错误：记录并重试 =====
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"⚠️ LLM 调用失败，重试中 ({attempt + 1}/{self.max_retries}): {err_msg[:200]}"
                    )
                    time.sleep(1)
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
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=10,
                timeout=15,
            )
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
