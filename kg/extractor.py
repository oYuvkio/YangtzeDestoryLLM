"""知识抽取模块，负责将原始文本转为结构化三元组。"""
import json
from .llm import chat_with_llm


class KnowledgeExtractor:
    """利用 LLM 对输入文本执行命名实体和关系抽取。"""

    def __init__(self):
        # 目前无额外初始化逻辑，预留扩展空间（如模型缓存、配置加载等）
        pass

    def extract(self, text: str) -> dict:
        """生成抽取提示并解析 LLM 返回的 JSON 结果。"""
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
        # 请求模型返回结构化 JSON，减少后处理复杂度
        response = chat_with_llm(prompt, system_prompt="你是一个精准的信息抽取助手。", json_mode=True)
        try:
            return json.loads(response)
        except Exception:
            # 捕获解析异常，避免上层流程因格式问题中断
            print("抽取结果JSON解析失败")
            return {"entities": [], "relations": []}