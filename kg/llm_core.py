# 文件路径: kg/llm_core.py
"""
封装多家 LLM 提供商的调用策略，向上暴露统一接口（策略模式）。

新增特性：
1. 支持 OpenAI 兼容接口，便于直接复用 CQ_Summary 中的示例代码；
2. 统一的 ``chat_messages`` 方法，既能处理单条 prompt 也能处理多轮 messages，
   方便在不同 provider 之间切换；
3. response_format/json_mode 兼容，便于强制返回 JSON。
"""
from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod
import os
from dotenv import load_dotenv
# 加载 .env 环境变量
load_dotenv()


# 可选依赖：未安装时延迟报错，保持代码健壮
try:
    from zhipuai import ZhipuAI
except Exception:
    ZhipuAI = None  # type: ignore

try:
    import google.generativeai as genai
except Exception:
    genai = None  # type: ignore

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore


# 1. 定义抽象策略接口
class LLMBackend(ABC):
    """不同 LLM 平台需要实现的统一对话接口。"""

    @abstractmethod
    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """单轮对话接口。"""
        raise NotImplementedError

    def chat_messages(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        多轮消息接口的默认实现：简单拼接为单条 Prompt。
        子类可覆盖以使用原生消息模式。
        """
        merged = []
        for m in messages:
            role = m.get("role", "user")
            merged.append(f"[{role}] {m.get('content', '')}")
        prompt = "\n".join(merged)
        return self.chat(prompt, json_mode=json_mode, response_format=response_format)


# 2. 实现智谱 AI 策略
class ZhipuBackend(LLMBackend):
    """调用智谱 ChatCompletions 接口的实现。"""

    def __init__(self, config: dict):
        if ZhipuAI is None:
            raise ImportError("未安装 zhipuai 库，请先 pip install zhipuai")

        api_key = os.getenv("ZHIPU_API_KEY")
        if not api_key:
            raise ValueError("❌ 未找到 ZHIPU_API_KEY，请检查 .env 文件")
        self.client = ZhipuAI(api_key=api_key)
        self.model = config.get("model_name", "glm-4.5-flash")
        self.default_temp = config.get("temperature", 0.1)

    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        messages = [{"role": "user", "content": prompt}]
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        return self.chat_messages(
            messages,
            json_mode=json_mode,
            response_format=response_format,
        )

    def chat_messages(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        fmt = response_format
        if json_mode:
            fmt = {"type": "json_object"}

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.default_temp if not json_mode else 0.1,
                response_format=fmt,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"⚠️ Zhipu API Error: {e}")
            return ""


# 3. 实现 Google Gemini 策略
class GeminiBackend(LLMBackend):
    """使用 Google Gemini SDK 的聊天实现。"""

    def __init__(self, config: dict):
        if genai is None:
            raise ImportError(
                "未安装 google-generativeai，请先 pip install google-generativeai")

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("❌ 未找到 GEMINI_API_KEY，请检查 .env 文件")
        genai.configure(api_key=api_key)
        model_name = config.get("model_name", "gemini-2.5-flash")
        self.model = genai.GenerativeModel(model_name)
        self.default_temp = config.get("temperature", 0.1)

    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        messages = [{"role": "user", "content": prompt}]
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})
        return self.chat_messages(messages, json_mode=json_mode, response_format=response_format)

    def chat_messages(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        # Gemini 没有原生多条 messages，这里拼接文本
        prompt_lines = []
        for m in messages:
            prompt_lines.append(
                f"{m.get('role', 'user').title()}: {m.get('content', '')}")
        full_prompt = "\n".join(prompt_lines)

        mime_type = "application/json" if json_mode else "text/plain"
        if response_format and response_format.get("type") == "json_object":
            mime_type = "application/json"

        config = genai.types.GenerationConfig(
            response_mime_type=mime_type,
            temperature=0.1 if json_mode else self.default_temp,
        )
        try:
            response = self.model.generate_content(
                full_prompt, generation_config=config)
            return response.text
        except Exception as e:
            print(f"⚠️ Gemini API Error: {e}")
            return ""


# 4. 实现 OpenAI 兼容策略
class OpenAIBackend(LLMBackend):
    """调用 OpenAI 或兼容接口（如自建推理服务）的实现。"""

    def __init__(self, config: dict):
        if OpenAI is None:
            raise ImportError("未安装 openai，请先 pip install openai")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("❌ 未找到 OPENAI_API_KEY，请检查 .env 文件")
        model = os.getenv("OPENAI_MODEL_API")
        if not model:
            raise ValueError("❌ 未找到 OPENAI_MODEL_API，请检查 .env 文件")
        base_url = config.get("base_url") or os.getenv("OPENAI_BASE_URL")
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.default_temp = config.get("temperature", 0.1)

    def chat(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        messages = [{"role": "user", "content": prompt}]
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})
        return self.chat_messages(messages, json_mode=json_mode, response_format=response_format)

    def chat_messages(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        fmt = response_format
        if json_mode:
            fmt = {"type": "json_object"}

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.default_temp if not json_mode else 0.1,
                response_format=fmt,
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"⚠️ OpenAI API Error: {e}")
            return ""


# 5. 工厂模式：统一入口
class LLMFactory:
    """
    根据 provider 字符串创建对应的后端实例。
    支持 zhipu / gemini / openai 三类。
    """

    @staticmethod
    def create(llm_config: dict) -> LLMBackend:
        """
        根据配置字典创建 LLM 实例。
        :param llm_config: 包含 provider, model_name, temperature 的字典
        """
        provider = llm_config.get(
            "provider", os.getenv("LLM_PROVIDER", "zhipu"))

        if provider == "zhipu":
            return ZhipuBackend(llm_config)
        if provider == "gemini":
            return GeminiBackend(llm_config)
        if provider == "openai":
            return OpenAIBackend(llm_config)
        raise ValueError(f"Unknown provider: {provider}")


# 6. 辅助函数：用于 GraphRAG 生成答案
def draft_answer_with_graph(question: str, evidence: list, llm_config: dict) -> str:
    """
    基于图谱三元组生成答案 (接收 llm_config)
    :param evidence: 三元组列表 [(s, r, o), ...]
    """
    evidence_str = "\n".join([f"- {s} {r} {o}" for s, r, o in evidence])

    prompt = f"""
    请根据以下检索到的长江灾害领域知识图谱信息，回答用户的问题。

    【知识证据】：
    {evidence_str}

    【用户问题】：
    {question}

    要求：
    1. 回答要连贯、准确。
    2. 如果证据不足，请实事求是地说明。
    """

    llm = LLMFactory.create(llm_config)
    return llm.chat(prompt, system_prompt="你是一个基于知识图谱的灾害问答专家。")


__all__ = [
    "LLMBackend",
    "ZhipuBackend",
    "GeminiBackend",
    "OpenAIBackend",
    "LLMFactory",
    "draft_answer_with_graph",
]
