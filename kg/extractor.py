# 文件路径: kg/extractor.py 
# 知识抽取器 - 创新点一 
# 作用：负责将非结构化文本转化为结构化图谱数据 

import json
from .llm import chat_with_llm

from .prompts import EXTRACT_PROMPT_TEMPLATE # 导入提示词模板

# 知识抽取器（非结构化 -> 结构化）
class KnowledgeExtractor:
    def __init__(self):
        pass

    def extract(self, text: str) -> dict:
        # 1. 填充模板：将由于文本填入 Prompt
        prompt = EXTRACT_PROMPT_TEMPLATE.format(text=text)
        # 2. 强力约束：使用 json_mode=True 强制大模型只输出 JSON，方便后续程序解析
        response = chat_with_llm(prompt, system_prompt="你是一个精准的信息抽取助手。", json_mode=True)
        try:
            return json.loads(response)
        # 3. 容错处理：如果模型输出不规范，这里要有 try-except 兜底
        except json.JSONDecodeError:
            print("抽取结果JSON解析失败")
            return {"entities": [], "relations": []}
        except Exception as e:
            print(f"未知错误: {e}")
            return {"entities": [], "relations": []}