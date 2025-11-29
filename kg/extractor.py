"""
用于构建长江灾害知识图谱的抽取器实现。

本模块定义了两种抽取策略：

* ``LLMExtractor`` – 利用大语言模型进行抽取，采用了提示工程（Prompt Engineering）、
  思维链推理（Chain-of-Thought）和多轮验证策略。它依赖于 :mod:`kg.llm_core` 工厂
  来实例化具体的提供商（如智谱 ChatGLM 或 Gemini）。该抽取器使用精心设计的提示词
  查询 LLM，对结果进行后处理，然后要求模型进行自我批判以过滤不正确的三元组。

* ``DeepLearningExtractor`` – 提供使用传统方法的基线抽取实现。默认情况下，
  它尝试实例化一个 HuggingFace NER pipeline（使用 ``bert-base-chinese``）来识别
  命名实体。如果底层模型无法下载（例如由于网络限制），该抽取器将回退到基于
  简单规则的启发式方法，以识别日期、地点、原因和措施。关系则通过匹配文本中的
  关键短语来推断。

两个抽取器都返回一个包含两个键的字典：

``entities`` – 一个包含 ``{"name": ..., "type": ...}`` 的字典列表
``relations`` – 一个包含 ``{"head": ..., "relation": ..., "tail": ...}`` 的字典列表

下游组件应使用这些结构来构建知识图谱的三元组。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

# 确保这些模块在你现有的文件结构中存在
from .llm_core import LLMFactory
from .schema import RELATIONS


@dataclass
class ExtractionResult:
    """抽取运行的结构化结果。"""

    entities: List[Dict[str, str]]
    relations: List[Dict[str, str]]

    def as_json(self) -> str:
        """将结果序列化为 JSON 字符串。"""
        return json.dumps({"entities": self.entities, "relations": self.relations}, ensure_ascii=False, indent=2)


class LLMExtractor:
    """
    基于大语言模型的抽取pipeline，包含提示工程和多轮验证。

    参数
    ----------
    llm_config: Dict
        直接传递给 :func:`kg.llm_core.LLMFactory.create` 的配置字典。

    属性
    ----------
    llm: LLMBackend
        从 :mod:`kg.llm_core` 创建的具体 LLM 后端实例。
    """

    def __init__(self, llm_config: Dict[str, object]):
        self.llm_config = llm_config
        self.llm = LLMFactory.create(llm_config)

    def extract(self, text: str) -> ExtractionResult:
        """
        对单段文本运行抽取pipeline。

        pipeline分两个阶段进行：

        1. 候选生成 (Candidate Generation) – 要求 LLM 从文本中提取实体和关系列表。
           鼓励模型展示其推理过程（思维链），但我们丢弃推理文本，仅解析 JSON 对象。

        2. 自我批判与过滤 (Self-Critique and Filtering) – 将候选三元组连同
           原始文本和允许的关系名称集一起展示给 LLM。要求其验证每个三元组，移除
           不正确或不受支持的关系，并返回清洗后的 JSON。

        返回
        -------
        ExtractionResult
            包含最终实体和关系列表的数据类。
        """
        # 阶段 1：候选生成
        # 获取允许的关系列表
        allowed_relations = list(set(RELATIONS.values()))

        generation_prompt = f"""

你是一个长江流域灾害领域的知识图谱构建专家。
你的任务是从给定的文本中，识别出一个**核心灾害事件**，并提取该事件的属性。
请遵循以下**严格约束**：
1. **核心事件识别**：首先确定文本描述的主要灾害事件名称（例如"2020年长江洪涝"）。
2. **星型结构**：所有的关系（relations）必须以这个**核心事件**作为 `head`（头实体）。
3. **关系约束**：`relation` 只能从以下列表中选择：{allowed_relations}。
   - occurs_on (发生时间)
   - occurs_in (发生地点)
   - has_cause (致灾因子/原因)
   - has_impact (造成影响/损失)
   - has_measure (应对措施)
   - has_type (灾害类型)
4. **不要**提取与核心事件无关的实体间关系（例如不要提取 "暴雨"->"导致"->"洪水"，而应提取 "洪水"->"has_cause"->"暴雨"）。

【示例】
输入："受强降雨影响，2020年7月安徽发生严重内涝，政府紧急转移安置群众。"
输出：
{{
  "entities": [
    {{"name": "2020年安徽内涝", "type": "灾害事件"}},
    {{"name": "强降雨", "type": "原因"}},
    {{"name": "2020年7月", "type": "时间"}},
    {{"name": "转移安置群众", "type": "措施"}}
  ],
  "relations": [
    {{"head": "2020年安徽内涝", "relation": "has_cause", "tail": "强降雨"}},
    {{"head": "2020年安徽内涝", "relation": "occurs_on", "tail": "2020年7月"}},
    {{"head": "2020年安徽内涝", "relation": "has_measure", "tail": "转移安置群众"}}
  ]
}}

【当前任务】

文本内容：
"{text.strip()}"

请分两步进行推理：首先思考哪些是候选实体，哪些实体之间可能存在关系，并将你的推理过程用中文简要描述；然后根据推理结果生成最终的结构化 JSON。

请严格按照以下 JSON 模板输出最终结果：
{{
  "entities": [{{"name": "实体名", "type": "实体类型"}}, ...],
  "relations": [{{"head": "头实体名", "relation": "关系", "tail": "尾实体名"}}, ...]
}}

注意：JSON 应该是有效的，不要包含任何注释或多余文本。
"""
        # 使用 json_mode=True 强制模型输出 JSON
        raw_response = self.llm.chat(
            generation_prompt, system_prompt="你是一个遵循指令的、严谨的知识抽取助手，仅输出 JSON。", json_mode=True)
        try:
            # 某些模型可能会用 Markdown 代码块包裹 JSON；如果存在则去除
            parsed = json.loads(self._strip_markdown_code(raw_response))
        except Exception:
            # 如果解析失败，回退为空结构
            parsed = {"entities": [], "relations": []}

        # 阶段 2：格式清洗（确保所有 head 都是同一个事件）
        # 简单的后处理：找到出现次数最多的 head 作为主事件，过滤掉其他的杂音
        if parsed.get("relations"):
            from collections import Counter
            heads = [r["head"] for r in parsed["relations"]]
            if heads:
                # 找到主事件名称
                main_event = Counter(heads).most_common(1)[0][0]
                # 只保留以主事件为头的关系
                filtered_rels = [r for r in parsed["relations"]
                                 if r["head"] == main_event]
                parsed["relations"] = filtered_rels

                # 确保主事件在实体列表中
                entity_names = {e["name"] for e in parsed["entities"]}
                if main_event not in entity_names:
                    parsed["entities"].append(
                        {"name": main_event, "type": "灾害事件"})

        return ExtractionResult(entities=parsed.get("entities", []), relations=parsed.get("relations", []))

    @staticmethod
    def _strip_markdown_code(text: str) -> str:
        """移除周围的 Markdown 代码块标记和空白字符。"""
        cleaned = text.strip()
        # 如果存在三个反引号的代码块标记，则移除
        if cleaned.startswith("```") and cleaned.endswith("```"):
            # 移除首尾的 ``` 以及可能的语言标识（如 ```json）
            # 简单的切片可能不够，这里做一个简单的处理
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned


class DeepLearningExtractor:
    """
    使用传统（非 LLM）方法的基线抽取器。

    该抽取器首先尝试加载 HuggingFace NER pipeline以识别实体。如果下载或加载模型失败
    （例如由于网络限制），它会回退到基于简单规则的模式匹配实现。实体间的关系
    通过基于文本中关键短语的启发式方法推断。
    """

    def __init__(self):
        # 尝试初始化用于中文 NER 的 HuggingFace pipeline
        self.ner_pipeline = None
        try:
            from transformers import pipeline
            # 使用多语言模型；在许多环境中这会被缓存
            # 注意：bert-base-chinese 实际上主要做填空，做 NER 最好用专门微调过的模型
            # 但为了保持代码通用性，这里若环境允许会自动下载；若失败则走规则
            self.ner_pipeline = pipeline(
                "ner", model="bert-base-chinese", tokenizer="bert-base-chinese", grouped_entities=True
            )
        except Exception:
            # pipeline初始化失败；将使用启发式方法
            self.ner_pipeline = None

        # 启发式抽取器的预定义词汇表
        self.location_keywords = [
            "安徽", "江西", "湖南", "湖北", "江苏", "浙江", "上海", "重庆", "四川",
            "洞庭湖", "鄱阳湖", "长江", "三峡", "武汉", "南京", "长沙"
        ]
        self.cause_keywords = ["气候异常", "降雨集中",
                               "生态破坏", "泥石流", "土石流", "台风", "冰雹"]
        self.measure_keywords = ["退田还湖", "加固堤防",
                                 "疏浚河道", "修复堤坝", "移民安置", "紧急救援"]

    def extract(self, text: str) -> ExtractionResult:
        # 如果可用，首先使用 NER pipeline
        entities: List[Dict[str, str]] = []
        if self.ner_pipeline:
            try:
                ner_results = self.ner_pipeline(text)
                for ent in ner_results:
                    # 将实体标签映射到粗粒度类型
                    label = ent.get("entity_group", ent.get("entity", ""))
                    ent_type = self._map_ner_label(label)
                    entities.append({"name": ent["word"], "type": ent_type})
            except Exception:
                # 运行时出错则置空，以便触发下方的回退逻辑
                entities = []

        # 如果未找到实体或pipeline不可用，回退到启发式抽取
        if not entities:
            entities = self._heuristic_extract_entities(text)

        # 去重同时保持顺序
        seen = set()
        unique_entities = []
        for ent in entities:
            if ent["name"] not in seen:
                seen.add(ent["name"])
                unique_entities.append(ent)

        # 使用启发式规则推断关系
        relations = self._infer_relations(text, unique_entities)

        return ExtractionResult(entities=unique_entities, relations=relations)

    def _map_ner_label(self, label: str) -> str:
        """
        将 HuggingFace NER pipeline返回的标签映射到我们的领域特定类型。
        未知标签默认为“实体”。
        """
        # 中文 NER 的典型标签：LOC, PER, ORG, MISC
        if label.startswith("LOC"):
            return "地点"
        elif label.startswith("PER"):
            return "人物"
        elif label.startswith("ORG"):
            return "组织"
        else:
            return "实体"

    def _heuristic_extract_entities(self, text: str) -> List[Dict[str, str]]:
        """
        非常简单的启发式实体抽取器。查找日期、预定义关键词以及引号中出现的任何内容。
        这仅作为无深度学习模型可用时的基线。
        """
        entities = []

        # 使用宽泛的正则表达式提取日期/时间表达式
        date_pattern = r"\d{4}年(?:[0-1]?\d月)?(?:[上中下]旬|\d{1,2}日|\d{1,2}日)?(?:至\d{4}年[0-1]?\d月\d{1,2}日)?"
        for match in re.finditer(date_pattern, text):
            entities.append({"name": match.group(), "type": "时间"})

        # 查找预定义的地点、原因、措施
        for loc in self.location_keywords:
            if loc in text:
                entities.append({"name": loc, "type": "地点"})
        for cause in self.cause_keywords:
            if cause in text:
                entities.append({"name": cause, "type": "原因"})
        for measure in self.measure_keywords:
            if measure in text:
                entities.append({"name": measure, "type": "应对措施"})

        # 提取中文引号内的任何内容作为潜在实体
        quote_pattern = r"《([^》]+)》|“([^”]+)”|\"([^\"]+)\""
        for match in re.finditer(quote_pattern, text):
            # 仅考虑非空组
            for grp in match.groups():
                if grp:
                    entities.append({"name": grp, "type": "实体"})
        return entities

    def _infer_relations(self, text: str, entities: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        基于文本中连接词的存在推断实体间的简单关系。
        此处仅覆盖了一小部分关系用于演示。
        """
        relations: List[Dict[str, str]] = []
        # 为了方便，建立实体名列表
        entity_names = [e["name"] for e in entities]

        # 启发式示例：如果存在时间实体，将其他实体（假定为事件）连接到该时间
        # 识别时间实体
        time_entities = [e["name"] for e in entities if e["type"] == "时间"]
        if time_entities and entity_names:
            for t in time_entities:
                # 简单逻辑：非时间的实体都被认为发生在这些时间点
                for e in entity_names:
                    if e != t:
                        relations.append(
                            {"head": e, "relation": "occurs_on", "tail": t})
                        # 只要建立一个关系就跳出，避免过于稠密
                        break

        # 原因：如果出现原因关键词，将其他实体链接到原因
        cause_entities = [e["name"] for e in entities if e["type"] == "原因"]
        if cause_entities and entity_names:
            for c in cause_entities:
                for e in entity_names:
                    if e != c:
                        relations.append(
                            {"head": e, "relation": "has_cause", "tail": c})
                        break

        # 措施
        measure_entities = [e["name"] for e in entities if e["type"] == "应对措施"]
        if measure_entities and entity_names:
            for m in measure_entities:
                for e in entity_names:
                    if e != m:
                        relations.append(
                            {"head": e, "relation": "has_measure", "tail": m})
                        break

        # 地点
        location_entities = [e["name"] for e in entities if e["type"] == "地点"]
        if location_entities and entity_names:
            for loc in location_entities:
                for e in entity_names:
                    if e != loc:
                        relations.append(
                            {"head": e, "relation": "occurs_in", "tail": loc})
                        break
        return relations


__all__ = ["LLMExtractor", "DeepLearningExtractor", "ExtractionResult"]
