# 文件路径: kg/extractor.py
import json
from .llm import chat_with_llm

class KnowledgeExtractor:
    def __init__(self):
        pass

    def extract(self, text: str) -> dict:
        prompt = f"""
        你是一个长江流域灾害领域的知识图谱构建专家。
        请从以下文本中抽取实体和关系，构建知识三元组。
        
        文本内容：
        {text}

        请严格遵循以下JSON格式输出：
        {{
            "entities": [
                {{"name": "实体名", "type": "实体类型(如:灾害事件, 地点, 原因, 影响, 措施)"}}
            ],
            "relations": [
                {{"head": "头实体名", "relation": "关系(如:发生于, 导致, 影响, 应对)", "tail": "尾实体名"}}
            ]
        }}
        """
        response = chat_with_llm(prompt, system_prompt="你是一个精准的信息抽取助手。", json_mode=True)
        try:
            return json.loads(response)
        except:
            print("抽取结果JSON解析失败")
            return {"entities": [], "relations": []}