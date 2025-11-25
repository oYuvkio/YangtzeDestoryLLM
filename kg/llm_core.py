# 文件路径: kg/llm_core.py
# LLM基座（策略模式，统一封装智谱/Gemini/OpenAI）
import os
from abc import ABC, abstractmethod
from zhipuai import ZhipuAI
import google.generativeai as genai
from dotenv import load_dotenv

# 加载 .env 环境变量
load_dotenv()

# 1. 定义抽象策略接口
# 作用：屏蔽底层模型差异，想换 GPT-4 只需要加一个类，不用改业务代码。
class LLMBackend(ABC):
    @abstractmethod
    def chat(self, prompt: str, system_prompt: str = None, json_mode: bool = False) -> str:
        pass

# 2. 实现智谱 AI 策略
class ZhipuBackend(LLMBackend):
    def __init__(self):
        api_key = os.getenv("ZHIPU_API_KEY")
        if not api_key:
            raise ValueError("❌ 未找到 ZHIPU_API_KEY，请检查 .env 文件")
        self.client = ZhipuAI(api_key=api_key)

    # 实现智谱的调用逻辑
    def chat(self, prompt: str, system_prompt: str = None, json_mode: bool = False) -> str:
        messages = [{"role": "user", "content": prompt}]
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})
        
        try:
            response = self.client.chat.completions.create(
                model="glm-4.5-flash", # 或 glm-4
                messages=messages,
                temperature=0.1 if json_mode else 0.7,
                response_format={"type": "json_object"} if json_mode else None
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"⚠️ Zhipu API Error: {e}")
            return ""

# 3. 实现 Google Gemini 策略
class GeminiBackend(LLMBackend):
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("❌ 未找到 GEMINI_API_KEY，请检查 .env 文件")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    def chat(self, prompt: str, system_prompt: str = None, json_mode: bool = False) -> str:
        full_prompt = f"System: {system_prompt}\nUser: {prompt}" if system_prompt else prompt
        config = genai.types.GenerationConfig(
            response_mime_type="application/json" if json_mode else "text/plain",
            temperature=0.1 if json_mode else 0.7
        )
        try:
            response = self.model.generate_content(full_prompt, generation_config=config)
            return response.text
        except Exception as e:
            print(f"⚠️ Gemini API Error: {e}")
            return ""

# 4. 工厂模式：统一入口
class LLMFactory:
    # 工厂模式：根据配置字符串 ("zhipu" 或 "gemini") 自动返回对应的模型实例
    @staticmethod
    def create(provider: str = "zhipu") -> LLMBackend:
        if provider == "zhipu":
            return ZhipuBackend()
        elif provider == "gemini":
            return GeminiBackend()
        else:
            raise ValueError(f"Unknown provider: {provider}")

# 5. 辅助函数：用于 GraphRAG 生成答案
def draft_answer_with_graph(question: str, evidence: list, provider: str = "zhipu") -> str:
    """
    基于图谱三元组生成答案
    :param evidence: 三元组列表 [(s, r, o), ...]
    """
    # 格式化证据
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
    
    # 使用工厂创建 LLM 并调用
    llm = LLMFactory.create(provider)
    return llm.chat(prompt, system_prompt="你是一个基于知识图谱的灾害问答专家。")