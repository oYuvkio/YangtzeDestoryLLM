"""
提示模板仓库：集中管理各阶段的 Prompt，便于统一维护与复用。

覆盖范围：
* P1–P5 的 CQ 驱动流程（与 summary/CQ_Summary.txt 一致）
* 旧版的简单抽取模板（向下兼容）
"""

# ========== P1：能力问题设计 ==========
P1_CQ_PROMPT = """
你是一名流域防洪减灾领域专家和本体工程师，负责为“长江流域水旱灾害防治与应急响应知识图谱”设计能力问题（CQ）。
请按照以下要求输出 JSON：
1) 设计不少于 {n_cq} 个中文能力问题，覆盖主题：典型事件、空间分布、致灾因子、防治措施、应急响应、工程调度、气候背景；
2) 每个问题包含唯一 id（如 CQ-001）、主题 theme、问题 question；
3) 严格输出 JSON，结构：
{{
  "cqs": [{{"id": "CQ-001", "theme": "主题", "question": "问题"}}]
}}

领域说明：
{domain_desc}
"""

# ========== P2：CQ -> 初始模式 ==========
P2_SCHEMA_PROMPT = """
你是一名知识图谱本体工程师，任务是从能力问题（CQ）中归纳实体类、关系、属性。
请对下面的 CQ JSON 进行归纳，输出 classes、relations、attributes：
* class: name (PascalCase)、cn_name、definition、examples
* relation: name (snake_case)、cn_name、domain、range、definition
* attribute: owner、name、cn_name、value_type (string|number|datetime)

CQ 列表：
{cq_json}

请严格输出 JSON：
{{
  "classes": [{{"name": "...", "cn_name": "...", "definition": "...", "examples": ["..."]}}],
  "relations": [{{"name": "...", "cn_name": "...", "domain": "...", "range": "...", "definition": "..."}}],
  "attributes": [{{"owner": "...", "name": "...", "cn_name": "...", "value_type": "string|number|datetime"}}]
}}
"""

# ========== P3：模式重构与层次化 ==========
P3_REFINEMENT_PROMPT = """
你是一名本体工程师，请整理下面的模式草案：
{schema_json}

任务：
1) 输出 class_hierarchy（parent, children）
2) 输出 merged_class_aliases（canonical, aliases）
3) 清洗后的 relations（name, cn_name, domain, range, definition, functional）

返回 JSON：
{{
  "class_hierarchy": [...],
  "merged_class_aliases": [...],
  "relations": [...]
}}
"""

# ========== P4：文献驱动模式补充 ==========
P4_AUGMENT_PROMPT = """
你是一名水旱灾害知识图谱本体工程师，现有模式如下：
{schema_json}

下面的文本可能包含尚未覆盖的重要概念或关系，请给出补充建议：
\"\"\"{doc_text}\"\"\"

输出 JSON：
{{
  "suggestions": [
    {{
      "type": "class|relation|attribute",
      "name": "...",
      "cn_name": "...",
      "definition": "...",
      "parent_or_domain_range_or_owner": "...",
      "value_type": "string|number|datetime|null",
      "evidence": "原文句子"
    }}
  ]
}}
"""

# ========== P5：事件与三元组抽取 ==========
EVENT_SCHEMA_HINT = """
{{
  "event_id": "evt_年份_序号",
  "event_type": "TBox 中的类名，如 FloodEvent 或 DroughtEvent",
  "name": "事件中文名称",
  "time": {{"start_time": "YYYY-MM-DD", "end_time": "YYYY-MM-DD"}},
  "space": {{
    "main_stream": ["主要干流"],
    "tributaries": ["受影响支流或湖泊"],
    "provinces": ["主要受灾省份"]
  }},
  "causes": ["致灾因子列表"],
  "impacts": {{
    "affected_population": "受灾人口（原文表述）",
    "deaths": "死亡人数",
    "direct_economic_loss": "直接经济损失（原文表述）"
  }},
  "responses": [{{"stage": "防御准备/应急响应/恢复重建", "measures": ["措施列表"]}}],
  "source": "数据来源"
}}
"""

P5_EXTRACTION_PROMPT = """
你是一名面向水旱灾害的知识图谱构建助手。
TBox 定义：
{schema_json}

事件 Schema 参考：
{event_schema}

请阅读下面的文本，抽取 0~N 个灾害事件，并输出 events 与 triples。
要求：
* event_type 必须来自 TBox.classes.name
* predicate 必须来自 TBox.relations.name
* 仅输出 JSON:
{{
  "events": [...],
  "triples": [...]
}}

文本：
\"\"\"{paragraph}\"\"\"
"""


# ========== 旧版简单抽取模板（保留向下兼容） ==========
EXTRACT_PROMPT_TEMPLATE = """
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
