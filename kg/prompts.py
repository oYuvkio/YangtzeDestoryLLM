"""
提示模板仓库：集中管理各阶段的 Prompt，便于统一维护与复用。

覆盖范围：
* P1–P5 的 CQ 驱动流程（与 summary/CQ_Summary.txt 一致）
* 旧版的简单抽取模板（向下兼容）
"""

# ========== P1：能力问题设计 ==========
P1_CQ_PROMPT = """
角色：你是一名本体工程师专家，正在开发一个针对长江流域防灾减灾与应急响应的专项本体。


该本体旨在支持开发一个关于长江流域水旱灾害的LLM增强问答系统，其目标包括：
1) 支撑关于“长江流域洪水与干旱”的结构化问答与知识检索；
2) 刻画典型灾害事件、防治与应急措施，以及对重要城市、流域单元和人群的影响；
3) 为后续的“知识图谱检索增强型大模型（KG-RAG）”提供清晰、可计算的语义约束。


领域本体范围
该本体涵盖长江流域灾害风险管理周期的关键要素，包括但不限于以下方面：
  {domain_desc}

  
你的任务：
在上述目标与范围约束下，生成 {n_cq} 条高层次、核心的能力问题（CQ）。

每个问题必须同时满足以下要求：
1) 清晰代表与长江流域防灾或应急响应相关的重要用户信息需求或查询场景，而不是泛泛而谈；
2) 使用简洁、规范的中文书面语表述，语言准确、无歧义；
   - 不要使用含糊词汇（如“很多”“大量”“最近”“比较多”）；
   - 不要出现“你/我/我们/系统”等对话式表述；
3) 问题的答案应当可以通过对知识图谱进行结构化查询获得,便于后续转化为图数据库查询；
   （例如基于时间、空间、事件、致灾因子、防治措施等维度检索或统计）
4) 问题应具体涉及到图谱中的实体类型，例如：
   - 询问特定实体的属性（如：“三峡水库的汛限水位是多少？”）
   - 询问实体间的关系（如：“哪些支流的洪水汇入导致了1998年干流高水位？”）
   - 避免生成纯粹的定义性问题（如“什么是洪水？”），重点关注事实性、关联性问题。

类别（category）说明：
请为每个能力问题指定一个最合适的类别，用简短中文短语表示。
类别可以从下列候选中选择，也可以在保持风格一致的前提下少量扩展：
- 灾害事件分析（例如：某次洪水/干旱事件的成因、演变、特征）
- 致灾因子诊断（例如：降水、水库调度、人类活动对灾害的贡献）
- 灾害影响评估（例如：人员伤亡、经济损失、农田受灾、基础设施影响）
- 空间分布与脆弱性（例如：高风险地区、重点城市、脆弱人群）
- 时序演变与统计（例如：某时段灾害频率、强度变化趋势）
- 防治与工程措施（例如：堤防、水库群联合调度、分洪蓄滞洪区运用）
- 应急响应与预案（例如：应急响应级别、启动条件、处置流程）
- 综合情景与联合调度（例如：干旱与洪水交替、流域上下游联动）

整体分布要求（由你在生成时自动考虑）：
- 生成的 {n_cq} 条能力问题应尽量覆盖上述不同类别，不要将所有问题都归为同一类别；

参考示例如下（仅为结构示例，内容可自行生成）：
{{
  "cqs": [
    {{
      "id": 1,
      "question": "1990年以来长江流域发生过哪些重大洪水事件，其主要受影响省份和经济损失是什么？",
      "category": "灾害事件分析"
    }},
    {{
      "id": 2,
      "question": "在什么条件下会启动长江流域防汛IV级应急响应，地方政府需要采取哪些行动？",
      "category": "应急响应与预案"
    }}
  ]
}}

输出格式要求：
1) 仅输出一个 JSON 对象，不要输出任何额外的文字说明、注释或总结；
2) 顶层必须包含字段 "cqs"，其值是一个长度为 {n_cq} 的数组；
3) 数组中的每个元素是一个对象，包含以下字段：
   - "id": 能力问题编号，从 1 开始递增；
   - "question": 能力问题的中文内容；
   - "category": 该问题所属的类别（如上所述）。
4) 严格保证输出是合法的 JSON，最外层只能有一个对象，数组外不要有其他多余字符，也不要使用 Markdown 代码块语法。
"""


# ========== P2：CQ -> 初始模式 ==========

P2_SCHEMA_PROMPT = """

你是一名知识图谱本体工程师，擅长从能力问题中提炼实体类（classes）、关系（relations）和属性（attributes）。
你将看到一组关于“长江流域水旱灾害防治与应急响应”的能力问题（CQ）。

输入 CQ 列表示例（结构说明，仅供理解）：
{{
  "cqs": [
    {{
      "id": 1,
      "question": "1998 年长江特大洪水主要影响了哪些省市和重要城市？造成了哪些主要经济损失类型？",
      "category": "灾害事件分析"
    }},
    {{
      "id": 2,
      "question": "在什么条件下会启动长江流域防汛IV级应急响应，地方政府需要采取哪些行动？",
      "category": "应急响应与预案"
    }}
  ]
}}

实际输入的 CQ 列表如下（JSON）：
{cq_json}


你的任务是：

1. 根据 CQ 中隐含的语义需求，归纳出候选实体类（classes）：
   - 请严格采用“以事件为中心（Event-Centric）”的建模思路。
     * 必须构建一个核心类（如 DisasterEvent），并围绕它构建关联类。
     * 确保 schema 能清晰回答：一个事件发生在什么 Time（时间）、什么 Location（地点），由什么 Cause（致灾因子）引起，造成了什么 Impact（灾害影响），并采取了什么 Response（应急响应）。
     * 避免生成孤立的、无法与事件挂钩的静态概念。
   - 每个类用英文 name（如 FloodEvent）、中文名 cn_name（如 洪水事件）和定义 (definition) 描述；
   - examples 中给出 1~3 个典型实例（中文字符串）；
   - parent 字段用于表达继承关系（可选）：
     * 若该类是某个更通用类的子类，则 parent 为父类的 name（如 FloodEvent 的 parent 为 DisasterEvent）；
     * 若该类是顶层类或独立概念，则 parent 为 null 或省略；
     * 建议构建2-3层的适度层级结构，既能表达通用-具体关系，又不过度复杂。

2. 归纳出候选关系（relations）：
   - name 为关系英文名（如 has_cause）；
   - cn_name 为中文名（如 致灾因子）；
   - domain / range 分别为主语类和宾语类（必须使用 classes 中已有类名）；
   - definition 用中文简要说明语义；
   - functional 表示该关系从 domain 到 range 是否「多对一或一对一」：
     - 若通常一个主体只有一个此类关系对象，则 functional = true，例如：
       - DisasterEvent -> has_main_cause -> HazardFactor
     - 若通常是多对多关系，则 functional = false，例如：
       - DisasterEvent -> affects_region -> AdministrativeRegion

3. 归纳出关键属性（attributes）：
   - owner：该属性所属的类名（必须是 classes.name 中的一个）；
   - name：属性英文名（如 start_time, peak_discharge）；
   - cn_name：中文名（如 开始时间, 洪峰流量）；
   - value_type：取值类型，限定为以下枚举之一：
     - "string", "number", "integer", "float", "boolean", "datetime"

4. 命名要求：
   - 类名和关系名使用驼峰或下划线风格，保持全局一致，例如：
     - 类名：FloodEvent, DroughtEvent, AdministrativeRegion
     - 关系名：has_cause, affects_region
   - 不要生成语义高度重复的类或关系（如 FloodEvent 与 FloodDisaster 含义几乎相同，应合并）。

---

输出格式要求（非常重要）：

1. 仅输出一个 JSON 对象，不要输出任何额外说明或注释。
2. 顶层对象必须包含以下三个字段，且都为数组（即使为空也必须给出空数组）：
   - "classes": [...]
   - "relations": [...]
   - "attributes": [...]
3. "classes" 中每个元素必须包含字段：
   - "name": string
   - "cn_name": string
   - "definition": string
   - "examples": string 数组
   - "parent": string 或 null（可选，表示父类名称）
4. "relations" 中每个元素必须包含字段：
   - "name": string
   - "cn_name": string
   - "domain": string
   - "range": string
   - "definition": string
   - "functional": 布尔值 true/false
5. "attributes" 中每个元素必须包含字段：
   - "owner": string
   - "name": string
   - "cn_name": string
   - "value_type": 上述枚举之一
6. 严格保证输出是合法 JSON，最外层只允许出现一个对象，不要使用 Markdown 代码块语法。

参考输出结构示例（内容仅供参考）：
{{
  "classes": [
    {
      "name": "DisasterEvent",
      "cn_name": "灾害事件",
      "definition": "在一定时间和空间范围内发生的与长江流域相关的水旱灾害过程",
      "examples": ["1998年长江特大洪水", "2022年长江流域特大干旱"],
      "parent": null
    },
    {
      "name": "FloodEvent",
      "cn_name": "洪水事件",
      "definition": "特指长江干流或支流发生的明显洪水过程",
      "examples": ["1998年长江特大洪水"],
      "parent": "DisasterEvent"
    }
  ],
  "relations": [
    {{
      "name": "has_cause",
      "cn_name": "致灾因子",
      "domain": "DisasterEvent",
      "range": "HazardFactor",
      "definition": "描述导致该灾害发生的主要气象、水文或人为因素",
      "functional": false
    }}
  ],
  "attributes": [
    {{
      "owner": "DisasterEvent",
      "name": "start_time",
      "cn_name": "开始时间",
      "value_type": "datetime"
    }}
  ]
}}
"""


# ========== P3：模式重构与层次化 ==========
P3_REFINEMENT_PROMPT = """
你是一名本体工程师，请对下面的初始模式草案进行整理和规范化处理。

初始模式（JSON）：
{schema_json}

---

任务说明：

1. 构建类层次结构（class_hierarchy）：
   - 找出明显的父类 / 子类关系，例如：
     - DisasterEvent 是 FloodEvent 和 DroughtEvent 的父类；
     - AdministrativeRegion 是 Province、City 的父类。
   - 每个元素为一个对象，包含：
     - "parent": 父类英文名（必须出现在原有 classes.name 中）
     - "children": 子类英文名数组（每个也必须是 classes.name 中的某个值）

2. 归并类的别名（merged_class_aliases）：
   - 对语义高度相似或明显是同一概念的类进行合并；
   - 每个元素为一个对象，包含：
     - "canonical": 选定的规范类名（英文）
     - "aliases": 需要归并到该规范类名下的其他类名列表（英文）
   - 若暂时没有明显别名，可以给出空数组。

3. 清洗关系定义（relations）：
   - 合并重复或语义相同的关系（例如 has_cause / caused_by 等）；
   - 对每条关系补充或校正以下字段：
     - "name": 关系英文名
     - "cn_name": 关系中文名
     - "domain": 主语类名（使用规范类名）
     - "range": 宾语类名（使用规范类名）
     - "definition": 简要中文定义
     - "functional": 布尔值，表示从 domain 到 range 是否通常为函数式关系

---

输出格式要求：

1. 仅输出一个 JSON 对象，不要输出任何额外文字。
2. 顶层必须包含以下字段：
   - "class_hierarchy": 数组
   - "merged_class_aliases": 数组
   - "relations": 数组
3. "class_hierarchy" 中每个元素含字段：
   - "parent": string
   - "children": string 数组
4. "merged_class_aliases" 中每个元素含字段：
   - "canonical": string
   - "aliases": string 数组
5. "relations" 中每个元素含字段：
   - "name": string
   - "cn_name": string
   - "domain": string
   - "range": string
   - "definition": string
   - "functional": boolean

参考输出结构示例（内容仅供参考）：
{{
  "class_hierarchy": [
    {{
      "parent": "DisasterEvent",
      "children": ["FloodEvent", "DroughtEvent"]
    }}
  ],
  "merged_class_aliases": [
    {{
      "canonical": "DisasterEvent",
      "aliases": ["DisasterProcess"]
    }}
  ],
  "relations": [
    {{
      "name": "has_cause",
      "cn_name": "致灾因子",
      "domain": "DisasterEvent",
      "range": "HazardFactor",
      "definition": "描述导致该灾害发生的主要气象、水文或人为因素",
      "functional": false
    }}
  ]
}}
"""


# ========== P4：文献驱动模式补充 ==========
P4_AUGMENT_PROMPT = """
你是一名水旱灾害知识图谱本体工程师，现有模式如下：
{schema_json}

下面的文本可能包含尚未覆盖的重要概念或关系，请在现有模式基础上给出「补充建议」，而不是完全重写。

待分析文本：
\"\"\"{doc_text}\"\"\"

---

任务说明：

1. 从文本中识别出当前知识图谱Schema中尚未很好覆盖的「候选类、关系或属性」。
2. 对每个补充建议，给出：
   - type: "class" | "relation" | "attribute"
   - name: 英文名（类名/关系名/属性名）
   - cn_name: 中文名
   - definition: 简要中文定义（对于关系，可说明主语宾语及语义）
   - parent_or_domain_range_or_owner:
     - 若 type = "class"：填该类的父类英文名（若不确定，可填 "DisasterEvent" 或 "null"）
     - 若 type = "relation"：填 "DomainClass -> RangeClass" 形式的字符串，例如：
       - "DisasterEvent -> EmergencyMeasure"
     - 若 type = "attribute"：填该属性所属的类名，例如：
       - "DisasterEvent"
   - value_type:
     - 若 type = "class" 或 "relation"，固定填 "null"
     - 若 type = "attribute"，从以下枚举中选择："string", "number", "integer", "float", "boolean", "datetime"
   - evidence:
     - 从原文中复制能支撑该建议的一句话或一个短语（中文）

---

输出格式要求：

1. 仅输出一个 JSON 对象，不要输出额外文字。
2. 顶层必须包含字段 "suggestions"，其值是一个数组（可以为空数组）。
3. "suggestions" 中每个元素必须包含字段：
   - "type"
   - "name"
   - "cn_name"
   - "definition"
   - "parent_or_domain_range_or_owner"
   - "value_type"
   - "evidence"

参考输出结构示例（内容仅供参考）：
{{
  "suggestions": [
    {{
      "type": "class",
      "name": "EmergencyPlan",
      "cn_name": "应急预案",
      "definition": "在灾害发生前预先编制的应对洪水或干旱事件的行动和处置方案",
      "parent_or_domain_range_or_owner": "ManagementDocument",
      "value_type": "null",
      "evidence": "……启动防汛应急预案……"
    }},
    {{
      "type": "relation",
      "name": "triggers_emergency_response",
      "cn_name": "触发应急响应",
      "definition": "描述某个阈值条件或事件触发某级别应急响应的关系",
      "parent_or_domain_range_or_owner": "ThresholdCondition -> EmergencyResponseLevel",
      "value_type": "null",
      "evidence": "……当水位达到警戒水位以上时，启动Ⅳ级应急响应……"
    }},
    {{
      "type": "attribute",
      "name": "emergency_level",
      "cn_name": "应急响应级别",
      "definition": "表示应急响应的等级，如I级、II级、III级、IV级",
      "parent_or_domain_range_or_owner": "EmergencyResponse",
      "value_type": "string",
      "evidence": "……启动防汛II级应急响应……"
    }}
  ]
}}
"""


# ========== P5：事件与三元组抽取 ==========
P5_EXTRACTION_PROMPT = """
你是一名面向水旱灾害的知识图谱构建助手。

知识图谱Schema定义（classes / relations / attributes）：
{schema_json}

事件结构参考：
{event_schema}

---

【重要说明】

输入文本可能包含三个部分：
1. 【前文参考】：提供上下文背景，帮助理解当前段落
2. 【待抽取文本】：**主要抽取目标**，请重点从此部分抽取事件和三元组
3. 【后文参考】：提供后续上下文，帮助补充信息

抽取策略：
- 事件和三元组应**主要来自【待抽取文本】**部分
- 前文/后文仅用于辅助理解，帮助确定实体边界、时间范围、因果关系等
- 如果前文/后文包含与待抽取文本强相关的补充信息（如事件的后续影响），也可以纳入

---

任务说明：

类使用提示：{class_usage_hint}

1. 识别【待抽取文本】中的 0~N 个灾害事件（如某次洪水或干旱过程），结合前后文完善事件信息，并为每个事件构建一个结构化对象。
   - event_type 必须使用知识图谱Schema中已有的某个类名，例如 "FloodEvent", "DroughtEvent"。
   - 若无法确定具体子类，可以使用更上层的类，如 "DisasterEvent"。

2. 针对知识图谱Schema中定义的以下核心关系，请逐一扫描文本，寻找符合条件的实体对：
   (1) has_cause (致灾因子): 寻找 [灾害事件] -> [致灾因子]
   (2) affects_region (影响区域): 寻找 [灾害事件] -> [行政区/流域]
   (3) triggers_response (触发响应): 寻找 [灾害事件/水位] -> [应急响应]
   ... (列出所有关键关系)

   对于每种关系，如果文中存在明确证据，请生成三元组；如果不存在，请跳过该关系。
   不要编造文中未提及的关系。
---

输入文本:
{input_text}

---


输出格式要求：

1. 仅输出一个 JSON 对象，不要输出任何额外文字。
2. 顶层必须包含字段：
   - "events": 数组
   - "triples": 数组

3. "events" 中每个元素建议包含字段（可为空字符串或空数组，但字段必须存在）：
   - "event_id": string，例如 "evt_1998_01"
   - "event_type": string，来自知识图谱Schema中的类名
   - "name": string，事件中文名称
   - "time": {{
       "start_time": "YYYY-MM-DD" 或 "",
       "end_time": "YYYY-MM-DD" 或 ""
     }}
   - "space": {{
       "main_stream": string 数组,
       "tributaries": string 数组,
       "provinces": string 数组
     }}
   - "causes": string 数组
   - "impacts": {{
       "affected_population": string,
       "deaths": string,
       "direct_economic_loss": string
     }}
   - "responses": 数组，每个元素为：
     {{
       "stage": "防御准备" | "应急响应" | "恢复重建" | "其他",
       "measures": string 数组
     }}
   - "source": string，例如文献或数据来源名，若未知可写 ""。

4. "triples" 中每个元素必须包含字段：
   - "subject": string
   - "predicate": string（来自知识图谱Schema中的关系名）
   - "object": string
   - "event_id": string 或 ""（若该三元组与某个事件关联，则填写对应 event_id）
   - "evidence": string（从原文复制的支撑句，若不方便可写空字符串）

参考输出结构示例（内容仅供参考）：
{{
  "events": [
    {{
      "event_id": "evt_1998_01",
      "event_type": "FloodEvent",
      "name": "1998年长江特大洪水",
      "time": {{"start_time": "1998-06-01", "end_time": "1998-09-01"}},
      "space": {{
        "main_stream": ["长江中下游干流"],
        "tributaries": ["洞庭湖", "鄱阳湖"],
        "provinces": ["湖北省", "湖南省", "江西省", "安徽省", "江苏省"]
      }},
      "causes": ["持续性强降雨", "上游来水偏多", "两湖来水与干流洪水叠加"],
      "impacts": {{
        "affected_population": "全国受灾人口 2.23 亿人",
        "deaths": "死亡 4150 人",
        "direct_economic_loss": "直接经济损失约 1660 亿元"
      }},
      "responses": [
        {{
          "stage": "应急响应",
          "measures": ["启动防汛Ⅱ级应急响应", "启动防汛Ⅰ级应急响应", "启用部分分洪蓄滞洪区", "大规模巡堤查险和抢险救援"]
        }}
      ],
      "source": "长江流域洪水公报或相关文献"
    }}
  ],
  "triples": [
    {{
      "subject": "1998年长江特大洪水",
      "predicate": "has_cause",
      "object": "持续性强降雨",
      "event_id": "evt_1998_01",
      "evidence": "1998年，受流域范围内持续性强降雨和上游来水偏多影响，长江中下游干流水位长期高于警戒……"
    }},
    {{
      "subject": "1998年长江特大洪水",
      "predicate": "affects_region",
      "object": "长江中下游干流",
      "event_id": "evt_1998_01",
      "evidence": "长江中下游干流水位长期高于警戒……"
    }}
  ]
}}
"""

EVENT_SCHEMA_HINT = """
{
  "event_id": "evt_年份_序号",
  "event_type": "知识图谱Schema中的类名，如 FloodEvent 或 DroughtEvent",
  "name": "事件中文名称",
  "time": {"start_time": "YYYY-MM-DD", "end_time": "YYYY-MM-DD"},
  "space": {
    "main_stream": ["主要干流"],
    "tributaries": ["受影响支流或湖泊"],
    "provinces": ["主要受灾省份"]
  },
  "causes": ["致灾因子列表"],
  "impacts": {
    "affected_population": "受灾人口（原文表述）",
    "deaths": "死亡人数",
    "direct_economic_loss": "直接经济损失（原文表述）"
  },
  "responses": [{"stage": "防御准备/应急响应/恢复重建", "measures": ["措施列表"]}],
  "source": "数据来源"
}
"""


"""
评估语料过滤（Eval Pool 筛选）提示词：
- System：要求严格、保守，只输出 JSON。
- User：提供评估维度与决策规则，引导模型输出判定结果。
"""
EVAL_SEGMENT_FILTER_SYSTEM = """
你是一名“长江流域水旱灾害知识图谱构建助手”。你的任务不是抽取三元组，而是对输入的中文或中英混合段落进行质量和相关性评估，判断它是否适合作为“长江流域水旱灾害知识图谱”的评估语料（eval pool）的一部分。

请严格、保守一点，宁可少收，不要把明显不相关或乱码的段落收进去。最后必须只输出一个 JSON，不要输出多余文字。
"""

EVAL_SEGMENT_FILTER_USER_TEMPLATE = """
现在给你一段从文献中切分出来的文本片段，请你判断它是否适合放入"长江流域水旱灾害知识图谱"的评估语料库（eval pool）。

【评估维度】

1. 相关性（领域）
   - 如果内容主要讨论以下主题之一，则认为 "与水旱灾害领域相关（is_water_disaster_domain = true）"：
     * 洪水、暴雨洪涝、山洪、城市内涝、干旱、枯水、水资源短缺；
     * 与水旱灾害相关的致灾因子：极端降水、持续少雨、高温热浪、台风、风暴潮、地质灾害诱发堰塞湖等；
     * 防汛抗旱、防洪排涝、水利工程运行（堤防、水库、蓄滞洪区、水闸、泵站等）；
     * 灾害影响：人员伤亡、农田受灾、供水中断、航运受阻、电力供应受影响等；
     * 灾害防御与应急响应：预警、会商、响应级别、转移安置、应急抢险、水库调度、防御工作总结等。
   - 如果内容主要是与上述无关的算法推导、自然语言处理方法说明、纯数学公式、与其他领域（如交通事故、金融、教育等）相关，请认为 is_water_disaster_domain = false。

2. 是否与"长江流域"紧密相关（is_yangtze_related）
   - 如果段落中出现 "长江" 或其主要支流/区域（如：汉江、嘉陵江、洞庭湖、鄱阳湖、三峡水库、长江上游/中游/下游、沿江城市等），则 is_yangtze_related = true；
   - 如果只是讲中国其他流域或全球一般性水旱灾害，且没有明显长江线索，则 is_yangtze_related = false。

3. 文本质量（text_quality）—— 请严格区分！
   - excellent：文本非常规范，句子完整流畅，无任何乱码或排版问题，表述清晰专业；
   - good：文本基本连贯，句子完整，偶有小瑕疵但不影响理解；
   - noisy：有明显的排版问题、少量乱码、断句不自然，但主要内容仍可理解；
   - garbled：大量乱码或字符残片，句子严重破碎，几乎看不出原意；或几乎全是公式、变量名、单词碎片、参考文献条目。

4. 是否包含对 KG 有用的内容（contains_event_or_rule）
   - true：段落中至少包含一类：
     * 描述某次具体灾害事件的发生、发展、影响或应对（哪一年、哪个地区、发生了什么、造成了什么后果、采取了什么措施等）；
     * 描述防汛抗旱/应急响应的制度、流程、职责分工、启动条件、响应级别等（类似应急预案、公报中的规则性文字）；
     * 描述水利工程（堤防、水库、闸站、蓄滞洪区等）在防灾中的功能、运行方式、调度规则；
     * 描述灾害致灾因子、气候异常、降水异常等科学事实或统计特征。
   - false：纯方法论说明（如"本文采用 LDA 模型对新闻进行主题分析…"）、纯技术细节、不含任何具体灾害/防御/规则/影响事实的段落，一般认为不适合作为知识图谱 eval 样本。

5. 可能来源类型（source_guess）
   - law_plan：法律、条例、应急预案、制度办法等规范性文件；
   - gazette_yearbook：公报、年鉴、年报等年度统计或总结；
   - case_paper：灾害案例分析、学术论文、技术报告等；
   - news_popular：新闻报道、官方科普文章、媒体评论等；
   - other：无法判断或混合。

6. 信息完备性（关键维度！）
   知识图谱的核心价值在于结构化的关联信息，请**分类型**严格评估：
   
   【时间信息】
   has_temporal_info（是否包含明确的时间信息）：
   - true：段落中出现明确的年份（如"1998年""2020年7月"）、日期、时间段、时间范围等
   - false：没有任何时间线索，或只有模糊表述（如"近年来""曾经"）
   
   temporal_detail（时间信息详细程度）：0/1/2
   - 0=无时间信息；1=仅有年份或模糊时间；2=有精确日期或时间段（如"2020年7月1日-15日"）
   
   extracted_time（从文中提取的时间信息）：
   - 提取段落中出现的最主要的时间表述，如 "1998年6月-9月"、"2022年8月" 等
   - 如果没有明确时间，填 ""
   
   【空间信息】
   has_spatial_info（是否包含明确的空间信息）：
   - true：段落中出现明确的地点：省份、城市、河流、湖泊、水库、流域分区等
   - false：没有任何地点线索，或只有模糊表述（如"某地""部分地区"）
   
   spatial_detail（空间信息详细程度）：0/1/2
   - 0=无空间信息；1=仅有省级或流域级别；2=有市县级或具体水文站点/水利工程
   
   extracted_location（从文中提取的地点信息）：
   - 提取段落中出现的最主要的地点，用逗号分隔，如 "长江中下游,湖北省,武汉市"
   - 如果没有明确地点，填 ""
   
   【主体信息】（重要！尤其对于法规制度类）
   has_issuer_info（是否包含明确的发布/责任主体）：
   - true：段落中出现明确的机构名称，如"国家防汛抗旱总指挥部""水利部""XX省人民政府""长江水利委员会"等
   - false：没有任何主体信息
   
   issuer_detail（主体信息详细程度）：0/1/2
   - 0=无主体信息；1=仅有泛称（如"有关部门""地方政府"）；2=有明确机构名称
   
   extracted_issuer（从文中提取的发布/责任主体）：
   - 提取段落中出现的主要机构名称，如 "国家防总,水利部,湖北省防汛抗旱指挥部"
   - 如果没有明确主体，填 ""

【分维度打分】
请为以下维度分别给出 0/1/2 的整数评分：
relevance_yangtze：0=完全无关；1=泛水旱灾害相关；2=明确提到长江流域或可直接用于长江场景
kg_potential：0=几乎没有可抽知识；1=有少量事实/措施；2=有清晰的事件、指标、因果或措施，适合抽取
cleanliness：0=严重乱码；1=有少量噪声但可读；2=文本规范、句子完整
temporal_detail：0=无时间信息；1=仅有年份或模糊时间；2=有精确日期或时间段
spatial_detail：0=无空间信息；1=仅有省级或流域级别；2=有市县级或具体站点
issuer_detail：0=无主体信息；1=仅有泛称；2=有明确机构名称

【语义主题标签】
为段落指定一个 topic_label（必须从以下选项中选择）：
- disaster_event（灾害事件叙述：描述某次具体洪水/干旱事件的发生过程）
- impact_assessment（影响与损失：描述灾害造成的人员伤亡、经济损失、受灾面积等）
- measure_response（防治措施/应急响应：描述具体的防汛抗旱行动、抢险救灾、水库调度等）
- institution_regulation（制度/法规/流程：描述应急预案、职责分工、响应启动条件等规则性内容）
- background_analysis（致灾因子/气候背景/统计特征：描述降水异常、气候变化、历史统计等）
- other（其他无法归类）

【总体决策规则（keep_for_eval）】

请根据以上标签，给出最终布尔值 keep_for_eval。

**严格筛选标准**：只有在下面条件**全部满足**时，才给 keep_for_eval = true：
  1) is_water_disaster_domain = true；
  2) text_quality 为 "excellent"、"good" 或 "noisy"（不能是 "garbled"）且 cleanliness >= 1；
  3) contains_event_or_rule = true，且 kg_potential >= 1；
  4) relevance_yangtze >= 1；
  5) **信息完备性**（按类型区分要求）：
     - disaster_event / impact_assessment 类型：temporal_detail >= 1 且 spatial_detail >= 1（必须有时间和地点）
     - institution_regulation 类型：temporal_detail >= 1 或 issuer_detail >= 1（必须有时间或发布主体）
     - measure_response 类型：temporal_detail >= 1 且 (spatial_detail >= 1 或 issuer_detail >= 1)
     - background_analysis 类型：temporal_detail >= 1 或 spatial_detail >= 1（至少有时间或空间背景）
     - other 类型：至少满足 temporal_detail + spatial_detail + issuer_detail >= 2

**偏向保守**：
  - 如果时间、空间、主体信息都不明确（三者 detail 都为 0），即使其他条件满足，也必须 keep_for_eval = false；
  - 如果你犹豫不决，请偏向 keep_for_eval = false（宁可漏掉，不要把明显不合适的段落收进去）。

【输出要求】

1. 请严格按照下面 JSON 模板输出，不要添加任何额外说明文字或注释。
2. 所有字段都必须给出；字符串用双引号，布尔用 true/false，小写。
3. reason 字段用简短中文（不超过 50 字）概括保留/剔除的主要原因。

JSON 模板如下（请替换成你的判断结果）：

{
  "keep_for_eval": true,
  "reason": "……",
  "labels": {
    "is_yangtze_related": true,
    "is_water_disaster_domain": true,
    "text_quality": "good",
    "contains_event_or_rule": true,
    "relevance_yangtze": 2,
    "kg_potential": 2,
    "cleanliness": 2,
    "topic_label": "disaster_event",
    "main_topic": "……",
    "source_guess": "case_paper",
    "has_temporal_info": true,
    "has_spatial_info": true,
    "has_issuer_info": false,
    "temporal_detail": 2,
    "spatial_detail": 2,
    "issuer_detail": 0,
    "extracted_time": "1998年6月-9月",
    "extracted_location": "长江中下游,湖北省,武汉市",
    "extracted_issuer": ""
  }
}

【待评估文本】

<<<SEGMENT_START>>>
{segment_text}
<<<SEGMENT_END>>>
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


# ==============================================================================
# P5 上下文感知抽取辅助工具
# ==============================================================================


class P5PromptBuilder:
    """
    P5 提示词构建器。
    
    提供统一的提示词构建和上下文格式化功能。
    """
    
    # 上下文标记
    MARKER_BEFORE = "【前文参考】"
    MARKER_MAIN = "【待抽取文本】"
    MARKER_AFTER = "【后文参考】"
    
    @classmethod
    def format_input_text(
        cls,
        main_text: str,
        context_before: str = "",
        context_after: str = "",
    ) -> str:
        """
        格式化输入文本（包含上下文标记）。
        
        Args:
            main_text: 主文本（待抽取）
            context_before: 前文上下文
            context_after: 后文上下文
            
        Returns:
            格式化后的文本
        """
        parts = []
        
        if context_before and context_before.strip():
            parts.append(f"{cls.MARKER_BEFORE}\n{context_before.strip()}")
        
        parts.append(f"{cls.MARKER_MAIN}\n{main_text.strip()}")
        
        if context_after and context_after.strip():
            parts.append(f"{cls.MARKER_AFTER}\n{context_after.strip()}")
        
        return "\n\n".join(parts)
    
    @classmethod
    def build_class_usage_hint(
        cls,
        classes: list,
        max_classes: int = 10,
    ) -> str:
        """
        构建类使用提示。
        
        Args:
            classes: 类定义列表，每个元素包含 name 和 cn_name
            max_classes: 最多显示的类数量
            
        Returns:
            类使用提示字符串
        """
        if not classes:
            return "请根据知识图谱Schema中定义的类进行分类。"
        
        # 筛选事件类
        event_classes = [
            c for c in classes 
            if "Event" in c.get("name", "") or "事件" in c.get("cn_name", "")
        ]
        
        if not event_classes:
            event_classes = classes[:max_classes]
        
        hints = []
        for c in event_classes[:max_classes]:
            name = c.get("name", "")
            cn_name = c.get("cn_name", "")
            if name and cn_name:
                hints.append(f"{name}({cn_name})")
            elif name:
                hints.append(name)
        
        return f"可用事件类型: {', '.join(hints)}"
    
    @classmethod
    def build_p5_prompt(
        cls,
        schema_json: str,
        input_text: str,
        context_before: str = "",
        context_after: str = "",
        class_usage_hint: str = "",
        event_schema: str = "",
    ) -> str:
        """
        构建完整的 P5 抽取提示词。
        
        Args:
            schema_json: 知识图谱Schema 定义 JSON
            input_text: 主文本
            context_before: 前文上下文
            context_after: 后文上下文
            class_usage_hint: 类使用提示
            event_schema: 事件结构参考
            
        Returns:
            格式化后的提示词
        """
        # 格式化输入文本
        formatted_input = cls.format_input_text(
            main_text=input_text,
            context_before=context_before,
            context_after=context_after,
        )
        
        # 填充模板
        return P5_EXTRACTION_PROMPT.format(
            schema_json=schema_json,
            event_schema=event_schema or EVENT_SCHEMA_HINT,
            class_usage_hint=class_usage_hint or "请根据知识图谱Schema中定义的类进行分类",
            input_text=formatted_input,
        )


# 简化的辅助函数（便于直接调用）

def format_extraction_input(
    main_text: str,
    context_before: str = "",
    context_after: str = "",
) -> str:
    """
    格式化 P5 抽取输入文本。
    
    将主文本和上下文组装成结构化格式，便于 LLM 理解抽取边界。
    
    Args:
        main_text: 待抽取的主文本
        context_before: 前文上下文（可选）
        context_after: 后文上下文（可选）
        
    Returns:
        格式化后的文本
        
    Example:
        >>> text = format_extraction_input(
        ...     "1998年长江发生特大洪水...",
        ...     context_before="当年降雨量异常偏多..."
        ... )
        >>> print(text)
        【前文参考】
        当年降雨量异常偏多...
        
        【待抽取文本】
        1998年长江发生特大洪水...
    """
    return P5PromptBuilder.format_input_text(
        main_text=main_text,
        context_before=context_before,
        context_after=context_after,
    )


def build_p5_extraction_prompt(
    schema_json: str,
    input_text: str,
    context_before: str = "",
    context_after: str = "",
    classes: list = None,
) -> str:
    """
    构建 P5 抽取提示词。
    
    封装常用的提示词构建流程，简化调用。
    
    Args:
    schema_json: 知识图谱Schema 定义 JSON 字符串
        input_text: 待抽取的主文本
        context_before: 前文上下文
        context_after: 后文上下文
    classes: 知识图谱Schema中的类定义列表（用于生成提示）
        
    Returns:
        完整的 P5 提示词
    """
    class_hint = ""
    if classes:
        class_hint = P5PromptBuilder.build_class_usage_hint(classes)
    
    return P5PromptBuilder.build_p5_prompt(
        schema_json=schema_json,
        input_text=input_text,
        context_before=context_before,
        context_after=context_after,
        class_usage_hint=class_hint,
    )


# ========== P5：事件与三元组抽取（CoT增强版） ==========
P5_COT_EXTRACTION_PROMPT = """
你是一名水旱灾害知识图谱构建专家。

知识图谱Schema定义（classes / relations / attributes）：
{schema_json}

事件结构参考：
{event_schema}

---

【重要说明】

输入文本可能包含三个部分：
1. 【前文参考】：提供上下文背景
2. 【待抽取文本】：**主要抽取目标**
3. 【后文参考】：提供后续上下文

---

【核心约束 - 请务必遵守】

1. **所有抽取的实体必须是原文的子串**，不可改写、推断或编造
2. 关系必须来自知识图谱Schema定义的关系列表，不可自创
3. 如果文本中找不到相关信息，返回空列表而非编造

---

【⚠️ 关键规则 - 必须严格遵守】

**规则1：区分时间和事件**
- 判断标准：是否包含灾害性质词（洪水/旱灾/大水/奇旱/涝/决口等）
- ❌ 错误："乾隆二十九年(1764年)" → DisasterEvent
  【原因：只有年份，无灾害性质词】
- ✅ 正确："乾隆二十九年(1764年)" → TemporalEntity
- ✅ 正确："乾隆五十年(1785年)奇旱" → DroughtEvent
  【原因：包含"奇旱"灾害词】

**规则2：三元组主语规范**
- 纯时间不能独立表达"发生了什么"，必须有事件主体
- ❌ ("1998年", affects_region, "长江流域")
  【问题：1998年发生了什么？缺少事件主体】
- ✅ ("1998年长江洪水", affects_region, "长江流域")
- ✅ ("1998年长江洪水", occurs_at, "1998年")

**规则3：实体必须是原文精确子串**
- ❌ 合并："长江中下游地区" ← 原文是"长江中下游"
- ❌ 推断："三峡大坝" ← 原文只有"三峡"
- ✅ 保持原样：使用原文中完全一致的表述

**规则4：不确定情况的处理**
- 如果实体类型不确定，优先选择上位类（如用 DisasterEvent 而非具体子类）
- 如果关系不在知识图谱Schema中，**不要发明新关系**，跳过该三元组
- **宁可漏抽，不可错抽**

---

【示例1：现代水文干旱】

原文片段：
"以收集的实测水文气象资料为依据,以洞庭湖水系出口控制站岳阳城陵矶水文站水位流量过程线和相关水文气象因子变化情况为参照,兼顾全省抗旱应急调度有关时间节点,将2022年水文干旱过程划分为四个阶段...第一阶段(干旱露头):2022年7月8日—8月底。7月8日全省集中降雨基本结束,天气转入高温少雨阶段,来水偏少,洞庭湖8月4日达到枯水位(24.50 m),为1971年以来最早,洞庭湖汛期反枯,涝旱急转,8月12日全省启动抗旱Ⅳ级应急响应。"

正确输出：
```json
{{
  "entities": [
    {{"name": "2022年水文干旱过程", "type": "DroughtEvent"}},
    {{"name": "城陵矶水文站", "type": "HydrologicalStation"}},
    {{"name": "洞庭湖", "type": "Lake"}},
    {{"name": "2022年7月8日", "type": "TemporalEntity"}},
    {{"name": "抗旱Ⅳ级应急响应", "type": "EmergencyResponse"}}
  ],
  "triples": [
    {{"subject": "城陵矶水文站", "predicate": "monitors_river", "object": "洞庭湖", "evidence": "洞庭湖水系出口控制站岳阳城陵矶水文站"}},
    {{"subject": "2022年水文干旱过程", "predicate": "occurs_at", "object": "2022年7月8日", "evidence": "2022年7月8日—8月底"}},
    {{"subject": "2022年水文干旱过程", "predicate": "triggers_response", "object": "抗旱Ⅳ级应急响应", "evidence": "8月12日全省启动抗旱Ⅳ级应急响应"}}
  ]
}}
```

---

【示例2：历史灾害记录】

原文片段：
"清代无为有水、旱、震、疫、风、雪、雹、虫等自然灾害共158次。其中水灾达60次,占比近38%,旱灾33次,占比近21%...乾隆五十年(1785年)奇旱,"自去冬至是年终岁无雨,江潮闭,山田籽粒无收,圩之滨河者收三十之一";五十一年(1786年)春仍旱,大饥而疫死者弥望。"

正确输出：
```json
{{
  "entities": [
    {{"name": "无为", "type": "GeographicRegion"}},
    {{"name": "乾隆五十年(1785年)奇旱", "type": "DroughtEvent"}},
    {{"name": "水灾", "type": "DisasterEvent"}},
    {{"name": "大饥", "type": "DisasterImpact"}}
  ],
  "triples": [
    {{"subject": "水灾", "predicate": "affects_region", "object": "无为", "evidence": "其中水灾达60次"}},
    {{"subject": "乾隆五十年(1785年)奇旱", "predicate": "affects_region", "object": "无为", "evidence": "乾隆五十年(1785年)奇旱,自去冬至是年终岁无雨"}},
    {{"subject": "乾隆五十年(1785年)奇旱", "predicate": "causes_impact", "object": "大饥", "evidence": "大饥而疫死者弥望"}}
  ]
}}
```

---

请按照以下步骤进行**逐步推理（Chain of Thought）**：

**Step 1: 实体扫描与定位**
仔细阅读【待抽取文本】，识别所有可能属于知识图谱Schema类别的实体（如时间、地点、河流、数值、灾害名等）。
*自我验证*：逐一检查这些实体是否在原文中**原样出现**？如果不是原文子串，请修正为原文表述或丢弃。
*特别注意*：纯时间（如"1998年"）应标为 TemporalEntity，不是 DisasterEvent

**Step 2: 事件识别与分类**
判断文本是否描述了具体灾害事件，确定事件类型。
类使用提示：{class_usage_hint}

**Step 3: 关系判断与知识图谱Schema约束**
对于识别出的实体对，判断它们之间是否存在知识图谱Schema定义的关系。
检查：
- 关系predicate是否在知识图谱Schema的关系列表中？
- 关系的subject和object类型是否符合domain/range约束？
- *去幻觉*：这条关系在原文中有明确的句子支持吗？如果没有，请丢弃。
- *特别注意*：纯时间不能作为三元组主语，应使用 occurs_at 连接事件和时间

**Step 4: 三元组组装与证据标注**【核心步骤】
将验证通过的实体和关系组装为规范化JSON格式。
为每个三元组标注evidence字段（从原文复制支撑该关系的句子片段）。
- 如果找不到明确的原文依据，请**丢弃**该三元组
- 实体名称必须与原文**完全一致**，不可改写或推断

---

输入文本:
{input_text}

---

输出格式要求：

1. **请先输出思考过程**（以"【思考过程】"开头），简述你识别到的关键实体和推理逻辑（50-100字即可）。
2. 然后输出一个JSON对象（以```json开头），包含"events"和"triples"字段。
3. JSON结构必须严格符合以下定义：

```json
{{
  "events": [
    {{
      "event_id": "evt_年份_序号",
      "event_type": "知识图谱Schema中的类名（如FloodEvent）",
      "name": "事件中文名称",
      "time": {{"start_time": "YYYY-MM-DD或空字符串", "end_time": "YYYY-MM-DD或空字符串"}},
      "space": {{
        "main_stream": ["主要干流"],
        "tributaries": ["受影响支流或湖泊"],
        "provinces": ["主要受灾省份"]
      }},
      "causes": ["致灾因子列表"],
      "impacts": {{
        "affected_population": "受灾人口（原文表述）",
        "deaths": "死亡人数（原文表述）",
        "direct_economic_loss": "直接经济损失（原文表述）"
      }},
      "responses": [{{"stage": "应急响应", "measures": ["措施列表"]}}],
      "source": "数据来源"
    }}
  ],
  "triples": [
    {{
      "subject": "实体名（必须是原文子串）",
      "predicate": "关系名（必须来自知识图谱Schema的关系列表）",
      "object": "实体名（必须是原文子串）",
      "event_id": "关联的事件ID或空字符串",
      "evidence": "支撑该三元组的原文句子片段"
    }}
  ]
}}
```

请开始推理：
"""


# ========== P5：图结构增强的链式 CoT 抽取 ==========

# 注：递进式 CoT 步骤由 GraphStructure.get_cot_steps() 动态生成
# 如需使用模板方式，可调用 graph_structure.get_cot_config() 获取配置字典

P5_GRAPH_COT_EXTRACTION_PROMPT = """
你是一名水旱灾害知识图谱构建专家。

【图结构提示】
{graph_prompt}

知识图谱Schema定义（classes / relations / attributes）：
{schema_json}

事件结构参考：
{event_schema}

---

【核心约束 - 请务必遵守】

1. **实体必须是原文子串**，不可改写、推断或编造
2. 关系必须来自知识图谱Schema的关系列表，不可自创
3. 找不到证据就丢弃三元组，宁可漏抽不可错抽
4. {class_usage_hint}

---

【链式推理步骤（图结构驱动）】
{graph_steps}

---

输入文本:
{input_text}

---

输出格式要求：

1. 先输出思考过程（以"【思考过程】"开头，50-100字）
2. 再输出 JSON（以```json开头）
3. JSON 须包含 "events" 与 "triples" 字段

```json
{{
  "events": [
    {{
      "event_id": "evt_年份_序号",
      "event_type": "知识图谱Schema中的类名（如FloodEvent）",
      "name": "事件中文名称",
      "time": {{"start_time": "YYYY-MM-DD或空字符串", "end_time": "YYYY-MM-DD或空字符串"}},
      "space": {{
        "main_stream": ["主要干流"],
        "tributaries": ["受影响支流或湖泊"],
        "provinces": ["主要受灾省份"]
      }},
      "causes": ["致灾因子列表"],
      "impacts": {{
        "affected_population": "受灾人口（原文表述）",
        "deaths": "死亡人数（原文表述）",
        "direct_economic_loss": "直接经济损失（原文表述）"
      }},
      "responses": [{{"stage": "应急响应", "measures": ["措施列表"]}}],
      "source": "数据来源"
    }}
  ],
  "triples": [
    {{
      "subject": "实体名（必须是原文子串）",
      "subject_type": "实体类型（知识图谱Schema类名）",
      "predicate": "关系名（必须来自知识图谱Schema的关系列表）",
      "object": "实体名（必须是原文子串）",
      "object_type": "实体类型（知识图谱Schema类名）",
      "event_id": "关联的事件ID或空字符串",
      "evidence": "支撑该三元组的原文句子片段"
    }}
  ]
}}
```

请开始推理：
"""


# ==============================================================================
# CoT响应解析工具
# ==============================================================================

import json
import re
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


def parse_cot_response(response_text: str) -> Optional[Dict]:
    """
    解析带有CoT思考过程的LLM响应

    处理逻辑：
    1. 尝试提取```json代码块中的内容
    2. 如果没有代码块，尝试找{...}
    3. 解析JSON并返回
    4. 解析失败返回None

    Args:
        response_text: LLM的原始响应文本

    Returns:
        解析后的字典，包含events和triples字段
        解析失败返回None
    """
    if not response_text:
        return None

    # 1. 尝试提取```json代码块
    json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)

    if json_match:
        json_str = json_match.group(1)
    else:
        # 2. 尝试提取```代码块（不带json标记）
        code_match = re.search(r"```\s*(.*?)\s*```", response_text, re.DOTALL)
        if code_match:
            json_str = code_match.group(1)
        else:
            # 3. 尝试找{...}
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start != -1 and end > start:
                json_str = response_text[start:end]
            else:
                return None

    try:
        data = json.loads(json_str.strip())
        return data
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {json_str[:200]}... Error: {e}")
        return None


def extract_cot_thought(response_text: str) -> str:
    """
    提取CoT思考过程

    Args:
        response_text: LLM的原始响应文本

    Returns:
        思考过程字符串，无则返回空字符串
    """
    if not response_text:
        return ""

    # 查找【思考过程】标记后的内容
    match = re.search(r"【思考过程】(.*?)(?=```|$)", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


class P5CotPromptBuilder:
    """
    P5 CoT 提示词构建器。

    提供CoT版本的提示词构建和响应解析功能。
    """

    @classmethod
    def build_p5_cot_prompt(
        cls,
        schema_json: str,
        input_text: str,
        context_before: str = "",
        context_after: str = "",
        class_usage_hint: str = "",
        event_schema: str = "",
    ) -> str:
        """
        构建完整的 P5 CoT 抽取提示词。

        Args:
            schema_json: 知识图谱Schema 定义 JSON
            input_text: 主文本
            context_before: 前文上下文
            context_after: 后文上下文
            class_usage_hint: 类使用提示
            event_schema: 事件结构参考

        Returns:
            格式化后的CoT提示词
        """
        # 格式化输入文本
        formatted_input = P5PromptBuilder.format_input_text(
            main_text=input_text,
            context_before=context_before,
            context_after=context_after,
        )

        # 填充模板
        return P5_COT_EXTRACTION_PROMPT.format(
            schema_json=schema_json,
            event_schema=event_schema or EVENT_SCHEMA_HINT,
            class_usage_hint=class_usage_hint or "请根据知识图谱Schema中定义的类进行分类",
            input_text=formatted_input,
        )

    @classmethod
    def parse_response(cls, response_text: str) -> Optional[Dict]:
        """解析CoT响应"""
        return parse_cot_response(response_text)

    @classmethod
    def extract_thought(cls, response_text: str) -> str:
        """提取思考过程"""
        return extract_cot_thought(response_text)



# ========== 统一抽取 Prompt（Gold 和 Pred 使用相同 Prompt，含 Few-shot + CoT） ==========
UNIFIED_EXTRACTION_PROMPT = """你是一名水旱灾害领域知识图谱构建专家。
【知识图谱Schema定义】
{schema_text}
---
## 【⚠️ 核心原则】
### 原则1：区分"通用知识"与"具体事件"
- ❌ **拒绝通用描述**：不要抽取规律性、定义性描述
- ✅ **仅抽取具体事实**：必须有明确的时间、地点或具体事件实例
### 原则2：实体必须是原文精确子串
- ❌ 改写合并："长江中下游地区" ← 原文是"长江中下游"
- ❌ 推断补充："三峡大坝" ← 原文只有"三峡"
- ✅ 保持原样：使用原文中完全一致的表述
### 原则3：关系方向必须符合知识图谱Schema
- 主语类型必须匹配 domain，宾语类型必须匹配 range
- 如果方向不确定，宁可不抽
### 原则4：宁缺毋滥
- 如果关系不在知识图谱Schema中，**不要发明新关系**
- 如果证据不充分，**不要强行抽取**
- **宁可漏抽，不可错抽**
---
## 【⚠️ 关系方向速查表】
| 关系名 | 正确方向示例 | 错误方向示例 |
|--------|-------------|-------------|
| has_hazard_factor | (洪水事件, has_hazard_factor, 暴雨) | ❌ (暴雨, has_hazard_factor, 洪水事件) |
| affects_region | (洪水事件, affects_region, 武汉市) | ❌ (武汉市, affects_region, 洪水事件) |
| influenced_by_climate | (干旱事件, influenced_by_climate, 厄尔尼诺) | ❌ (厄尔尼诺, influenced_by_climate, 干旱事件) |
| causes_impact | (洪水事件, causes_impact, 经济损失) | ❌ (经济损失, causes_impact, 洪水事件) |
| triggers_response | (洪水事件, triggers_response, 防汛Ⅱ级响应) | ❌ (防汛Ⅱ级响应, triggers_response, 洪水事件) |
| occurs_at | (洪水事件, occurs_at, 1998年7月) | ❌ (1998年7月, occurs_at, 洪水事件) |
| part_of | (汉江, part_of, 长江流域) | ❌ (长江流域, part_of, 汉江) |
---
## 【⚠️ 区分时间实体与事件实体】
**判断标准**：是否包含灾害性质词（洪水/旱灾/大水/奇旱/涝/决口/枯水等）
| 原文表述 | 正确分类 | 错误分类 | 原因 |
|---------|---------|---------|------|
| "1998年" | TemporalEntity | ❌ DisasterEvent | 只有年份，无灾害词 |
| "乾隆二十九年(1764年)" | TemporalEntity | ❌ DisasterEvent | 只有年份，无灾害词 |
| "1998年长江洪水" | DisasterEvent | - | 包含"洪水"灾害词 |
| "乾隆五十年(1785年)奇旱" | DroughtEvent | - | 包含"奇旱"灾害词 |
| "2022年水文干旱过程" | DroughtEvent | - | 包含"干旱"灾害词 |
---
## 【正例演示】
### 📗 正例1：现代水文干旱事件
**原文**：
"以洞庭湖水系出口控制站城陵矶水文站水位流量过程线为参照，将2022年水文干旱过程划分为四个阶段。第一阶段(干旱露头):2022年7月8日—8月底。7月8日全省集中降雨基本结束，洞庭湖8月4日达到枯水位(24.50 m)，为1971年以来最早，8月12日全省启动抗旱Ⅳ级应急响应。"
**【思考过程】**
1. **实体扫描**：识别到"2022年水文干旱过程"（含"干旱"→DroughtEvent）、"城陵矶水文站"（水文站）、"洞庭湖"（湖泊）、"2022年7月8日"（时间）、"抗旱Ⅳ级应急响应"（应急响应）、"24.50 m"（数值）
2. **事件判断**：文本描述具体的2022年干旱事件，有明确时间和地点
3. **关系验证**：
   - 城陵矶水文站监测洞庭湖 → monitors_river ✓
   - 干旱事件发生于2022年7月8日 → occurs_at ✓
   - 干旱事件触发应急响应 → triggers_response ✓
4. **方向检查**：所有关系主语为事件或设施，符合domain约束
**正确输出**：
```json
{{
  "entities": [
    {{"name": "2022年水文干旱过程", "type": "DroughtEvent"}},
    {{"name": "城陵矶水文站", "type": "HydrologicalStation"}},
    {{"name": "洞庭湖", "type": "Lake"}},
    {{"name": "2022年7月8日", "type": "TemporalEntity"}},
    {{"name": "抗旱Ⅳ级应急响应", "type": "EmergencyResponse"}},
    {{"name": "24.50 m", "type": "NumericValue"}}
  ],
  "events": [
    {{
      "name": "2022年水文干旱过程",
      "event_type": "DroughtEvent",
      "time": {{"start_time": "2022-07-08", "end_time": ""}},
      "location": ["洞庭湖", "全省"]
    }}
  ],
  "triples": [
    {{
      "subject": "城陵矶水文站",
      "predicate": "monitors_river",
      "object": "洞庭湖",
      "evidence": "洞庭湖水系出口控制站城陵矶水文站",
      "confidence": "high"
    }},
    {{
      "subject": "2022年水文干旱过程",
      "predicate": "occurs_at",
      "object": "2022年7月8日",
      "evidence": "第一阶段(干旱露头):2022年7月8日—8月底",
      "confidence": "high"
    }},
    {{
      "subject": "2022年水文干旱过程",
      "predicate": "triggers_response",
      "object": "抗旱Ⅳ级应急响应",
      "evidence": "8月12日全省启动抗旱Ⅳ级应急响应",
      "confidence": "high"
    }},
    {{
      "subject": "城陵矶水文站",
      "predicate": "has_value",
      "object": "24.50 m",
      "evidence": "洞庭湖8月4日达到枯水位(24.50 m)",
      "confidence": "high"
    }}
  ]
}}
```
【反例演示】
📕 反例1：通用知识描述（应返回空）
原文：
"洪水是由暴雨、急剧融冰化雪、风暴潮等自然因素引起的江河湖海水量迅速增加或水位迅猛上涨的水流现象。根据成因，洪水可分为暴雨洪水、融雪洪水、冰凌洪水等类型。"

【思考过程】

内容判断：这是洪水的定义和分类说明，属于通用知识
具体事件：无 —— 没有提到任何具体的洪水事件（无时间、无地点、无具体事件名）
决策：不抽取任何三元组
❌ 错误输出（不要这样做）：

<JSON>
{{
  "triples": [
    {{"subject": "洪水", "predicate": "has_hazard_factor", "object": "暴雨"}}
  ]
}}
错误原因：这是通用规律描述，不是具体事件事实

✅ 正确输出：

<JSON>
{{
  "entities": [],
  "events": [],
  "triples": []
}}
📕 反例2：关系方向错误
原文：
"1998年长江特大洪水造成直接经济损失约1660亿元，受灾人口2.23亿人。"

❌ 错误输出（关系方向反了）：

<JSON>
{{
  "triples": [
    {{
      "subject": "直接经济损失约1660亿元",
      "predicate": "causes_impact",
      "object": "1998年长江特大洪水"
    }}
  ]
}}
错误原因：causes_impact 的 domain 是 DisasterEvent，range 是 DisasterImpact。应该是"事件造成影响"，不是"影响造成事件"

✅ 正确输出：

<JSON>
{{
  "triples": [
    {{
      "subject": "1998年长江特大洪水",
      "predicate": "causes_impact",
      "object": "直接经济损失约1660亿元",
      "evidence": "1998年长江特大洪水造成直接经济损失约1660亿元",
      "confidence": "high"
    }}
  ]
}}
📕 反例3：纯时间作为事件主语
原文：
"1998年，长江流域发生了严重的洪涝灾害。"

❌ 错误输出（纯时间不能作为事件主语）：

<JSON>
{{
  "entities": [
    {{"name": "1998年", "type": "DisasterEvent"}}
  ],
  "triples": [
    {{
      "subject": "1998年",
      "predicate": "affects_region",
      "object": "长江流域"
    }}
  ]
}}
错误原因："1998年"只是时间，不是事件。应该用完整的事件名称

✅ 正确输出：

<JSON>
{{
  "entities": [
    {{"name": "1998年", "type": "TemporalEntity"}},
    {{"name": "长江流域", "type": "Basin"}},
    {{"name": "严重的洪涝灾害", "type": "DisasterEvent"}}
  ],
  "triples": [
    {{
      "subject": "严重的洪涝灾害",
      "predicate": "affects_region",
      "object": "长江流域",
      "evidence": "长江流域发生了严重的洪涝灾害",
      "confidence": "high"
    }},
    {{
      "subject": "严重的洪涝灾害",
      "predicate": "occurs_at",
      "object": "1998年",
      "evidence": "1998年，长江流域发生了严重的洪涝灾害",
      "confidence": "high"
    }}
  ]
}}

【抽取步骤（Chain of Thought）】
请严格按以下步骤进行推理：

Step 1: 内容类型判断

这段文本是在描述具体事件/事实，还是在讲通用知识/定义？
如果是通用知识，直接返回空列表
Step 2: 实体扫描与验证

识别所有可能的实体
逐一验证：该实体是否是原文的精确子串？
区分时间实体和事件实体（看是否包含灾害词）
Step 3: 事件识别

是否存在具体的灾害事件？
事件是否有明确的时间或地点？
确定事件类型（使用知识图谱Schema中的类型ID）
Step 4: 关系抽取与方向验证

对于每对实体，判断是否存在知识图谱Schema中定义的关系
关键：检查关系方向是否正确（主语类型匹配 domain，宾语类型匹配 range）
如果方向不确定，宁可不抽
Step 5: 证据标注与置信度

为每个三元组标注原文证据
根据证据明确程度标注置信度（high/medium/low）
【待抽取文本】
{input_text}

【输出要求】
先输出思考过程（以"【思考过程】"开头，50-150字）
再输出 JSON（以 ```json 开头）
<JSON>
{{
  "entities": [
    {{"name": "实体名（必须是原文子串）", "type": "类型ID（英文）"}}
  ],
  "events": [
    {{
      "name": "事件名称",
      "event_type": "事件类型ID（英文）",
      "time": {{"start_time": "YYYY-MM-DD或空", "end_time": "YYYY-MM-DD或空"}},
      "location": ["地点1", "地点2"]
    }}
  ],
  "triples": [
    {{
      "subject": "主语（必须是原文子串）",
      "predicate": "关系ID（必须来自知识图谱Schema）",
      "object": "宾语（必须是原文子串）",
      "evidence": "原文证据句",
      "confidence": "high/medium/low"
    }}
  ]
}}
最终检查清单：

 所有实体名称都是原文的精确子串
 所有关系都来自知识图谱Schema定义
 所有关系方向都符合 domain/range 约束
 纯时间实体标记为 TemporalEntity，不是 DisasterEvent
 如果是通用知识描述，返回空列表
请开始推理：
"""


# ==============================================================================
# Gold/Pred 统一 Prompt（优化版：含 Few-shot 正反例 + CoT）
# ==============================================================================

# 统一 System Prompt（Gold 和 Pred 共用）
UNIFIED_SYSTEM_PROMPT_COT = """你是一名水旱灾害领域知识图谱标注专家，负责生成高质量的评测标准数据（Gold Standard）。

【你的职责】
1. 从文本中抽取实体和关系三元组，作为模型评测的标准答案
2. 确保抽取结果的**准确性**和**一致性**
3. 严格遵循知识图谱Schema约束，不发明新类型或关系

【核心原则】
1. **准确性优先**：所有实体必须是原文的**精确子串**，不可改写
2. **知识图谱Schema约束**：类型和关系必须来自给定的知识图谱Schema
3. **方向正确**：关系方向必须符合 domain → range 约束
4. **证据支撑**：每条三元组必须有原文证据
5. **宁缺毋滥**：不确定时宁可不抽，不可错抽"""


# 统一 User Prompt（Gold 和 Pred 共用，含 Few-shot 正反例）
UNIFIED_USER_PROMPT_COT = """请从以下文本中抽取实体和关系三元组，作为评测标准数据。

{tbox_schema}

---

## 【⚠️ 核心规则 - 必须严格遵守】

### 规则1：区分"通用知识"与"具体事件"
- ❌ **拒绝通用描述**：不要抽取 "洪水通常由暴雨引起" 这样的规律性描述
- ✅ **仅抽取具体事实**：只抽取 "1998年长江洪水由持续暴雨引起" 这样有时间/地点的具体记录
- 如果文本只讨论理论、规律或定义，没有具体事件实例，请返回空列表

### 规则2：区分时间实体与事件实体
判断标准：是否包含灾害性质词（洪水/旱灾/大水/奇旱/涝/决口/枯水等）

| 原文表述                 | 正确分类       | 错误分类        | 原因               |
| ------------------------ | -------------- | --------------- | ------------------ |
| "1998年"                 | TemporalEntity | ❌ DisasterEvent | 只有年份，无灾害词 |
| "乾隆二十九年(1764年)"   | TemporalEntity | ❌ DisasterEvent | 只有年份，无灾害词 |
| "1998年长江洪水"         | DisasterEvent  | -               | 包含"洪水"灾害词   |
| "乾隆五十年(1785年)奇旱" | DroughtEvent   | -               | 包含"奇旱"灾害词   |

### 规则3：三元组主语规范
- 纯时间不能独立表达"发生了什么"，必须有事件主体
- ❌ ("1998年", affects_region, "长江流域") — 1998年发生了什么？缺少事件主体
- ✅ ("1998年长江洪水", affects_region, "长江流域")
- ✅ ("1998年长江洪水", occurs_at, "1998年")

### 规则4：实体必须是原文精确子串
- ❌ 合并改写："长江中下游地区" ← 原文是"长江中下游"
- ❌ 推断补充："三峡大坝" ← 原文只有"三峡"
- ✅ 保持原样：使用原文中完全一致的表述

### 规则5：关系方向必须正确
关系的方向由知识图谱Schema中的 domain（主语类型）和 range（宾语类型）决定：

| 关系名                | 正确方向                                    | 错误方向                                      |
| --------------------- | ------------------------------------------- | --------------------------------------------- |
| has_hazard_factor     | (灾害事件, has_hazard_factor, 致灾因子)     | ❌ (致灾因子, has_hazard_factor, 灾害事件)     |
| affects_region        | (灾害事件, affects_region, 地理区域)        | ❌ (地理区域, affects_region, 灾害事件)        |
| influenced_by_climate | (灾害事件, influenced_by_climate, 气候异常) | ❌ (气候异常, influenced_by_climate, 灾害事件) |
| causes_impact         | (灾害事件, causes_impact, 灾害影响)         | ❌ (灾害影响, causes_impact, 灾害事件)         |
| triggers_response     | (灾害事件, triggers_response, 应急响应)     | ❌ (应急响应, triggers_response, 灾害事件)     |

---

## 【📗 正例演示】

### 正例1：现代水文干旱事件

**原文**：
"以洞庭湖水系出口控制站城陵矶水文站水位流量过程线为参照，将2022年水文干旱过程划分为四个阶段。第一阶段(干旱露头):2022年7月8日—8月底。7月8日全省集中降雨基本结束，洞庭湖8月4日达到枯水位(24.50 m)，为1971年以来最早，8月12日全省启动抗旱Ⅳ级应急响应。"

**【思考过程】**
1. 实体扫描：识别到"2022年水文干旱过程"（含"干旱"→DroughtEvent）、"城陵矶水文站"（水文站）、"洞庭湖"（湖泊）、"2022年7月8日"（时间）、"抗旱Ⅳ级应急响应"（应急响应）、"24.50 m"（数值）
2. 事件判断：文本描述具体的2022年干旱事件，有明确时间和地点，是具体事实而非通用知识
3. 关系验证：城陵矶水文站监测洞庭湖(monitors_river)、干旱事件发生于2022年7月8日(occurs_at)、干旱事件触发应急响应(triggers_response)
4. 方向检查：所有关系主语为事件或设施，符合domain约束

**正确输出**：
```json
{{{{
  "entities": [
    {{{{"name": "2022年水文干旱过程", "type": "DroughtEvent"}}}},
    {{{{"name": "城陵矶水文站", "type": "HydrologicalStation"}}}},
    {{{{"name": "洞庭湖", "type": "Lake"}}}},
    {{{{"name": "2022年7月8日", "type": "TemporalEntity"}}}},
    {{{{"name": "抗旱Ⅳ级应急响应", "type": "EmergencyResponse"}}}},
    {{{{"name": "24.50 m", "type": "NumericValue"}}}}
  ],
  "events": [
    {{{{
      "name": "2022年水文干旱过程",
      "event_type": "DroughtEvent",
      "time": {{{{"start_time": "2022-07-08", "end_time": ""}}}},
      "location": ["洞庭湖", "全省"]
    }}}}
  ],
  "triples": [
    {{{{"subject": "城陵矶水文站", "predicate": "monitors_river", "object": "洞庭湖", "evidence": "洞庭湖水系出口控制站城陵矶水文站", "confidence": "high"}}}},
    {{{{"subject": "2022年水文干旱过程", "predicate": "occurs_at", "object": "2022年7月8日", "evidence": "第一阶段(干旱露头):2022年7月8日—8月底", "confidence": "high"}}}},
    {{{{"subject": "2022年水文干旱过程", "predicate": "triggers_response", "object": "抗旱Ⅳ级应急响应", "evidence": "8月12日全省启动抗旱Ⅳ级应急响应", "confidence": "high"}}}},
    {{{{"subject": "城陵矶水文站", "predicate": "has_value", "object": "24.50 m", "evidence": "洞庭湖8月4日达到枯水位(24.50 m)", "confidence": "high"}}}}
  ]
}}}}
```

## 【📕 反例演示 - 常见错误】

### 反例1：通用知识描述（应返回空）

**原文**：
"洪水是由暴雨、急剧融冰化雪、风暴潮等自然因素引起的江河湖海水量迅速增加或水位迅猛上涨的水流现象。根据成因，洪水可分为暴雨洪水、融雪洪水、冰凌洪水等类型。"

**【思考过程】**
这是洪水的定义和分类说明，属于通用知识，没有提到任何具体的洪水事件（无时间、无地点、无具体事件名）。应返回空列表。

**❌ 错误输出**（不要这样做）：
```json
{{{{
  "triples": [
    {{{{"subject": "洪水", "predicate": "has_hazard_factor", "object": "暴雨"}}}}
  ]
}}}}
```
**错误原因**：这是通用规律描述，不是具体事件事实

**✅ 正确输出**：
```json
{{{{
  "entities": [],
  "events": [],
  "triples": []
}}}}
```

---

### 反例2：关系方向错误

**原文**：
"持续暴雨导致了1998年长江特大洪水。"

**❌ 错误输出**（关系方向反了）：
```json
{{{{
  "triples": [
    {{{{"subject": "持续暴雨", "predicate": "has_hazard_factor", "object": "1998年长江特大洪水"}}}}
  ]
}}}}
```
**错误原因**：has_hazard_factor 的 domain 是 DisasterEvent，range 是 HazardFactor。应该是"事件具有致灾因子"，不是"致灾因子具有事件"

**✅ 正确输出**：
```json
{{{{
  "triples": [
    {{{{"subject": "1998年长江特大洪水", "predicate": "has_hazard_factor", "object": "持续暴雨", "evidence": "持续暴雨导致了1998年长江特大洪水", "confidence": "high"}}}}
  ]
}}}}
```

---

### 反例3：纯时间作为事件主语

**原文**：
"1998年，长江流域发生了严重的洪涝灾害。"

**❌ 错误输出**：
```json
{{{{
  "entities": [{{{{"name": "1998年", "type": "DisasterEvent"}}}}],
  "triples": [{{{{"subject": "1998年", "predicate": "affects_region", "object": "长江流域"}}}}]
}}}}
```
**错误原因**："1998年"只是时间，不是事件

**✅ 正确输出**：
```json
{{{{
  "entities": [
    {{{{"name": "1998年", "type": "TemporalEntity"}}}},
    {{{{"name": "长江流域", "type": "Basin"}}}},
    {{{{"name": "严重的洪涝灾害", "type": "DisasterEvent"}}}}
  ],
  "triples": [
    {{{{"subject": "严重的洪涝灾害", "predicate": "affects_region", "object": "长江流域", "evidence": "长江流域发生了严重的洪涝灾害", "confidence": "high"}}}},
    {{{{"subject": "严重的洪涝灾害", "predicate": "occurs_at", "object": "1998年", "evidence": "1998年，长江流域发生了严重的洪涝灾害", "confidence": "high"}}}}
  ]
}}}}
```

---

## 【抽取步骤（Chain of Thought）】

请严格按以下步骤进行推理：

**Step 1: 内容类型判断**
- 这段文本是在描述具体事件/事实，还是在讲通用知识/定义？
- 如果是通用知识（无具体时间、地点、事件名），直接返回空列表

**Step 2: 实体扫描与验证**
- 识别所有可能的实体
- 逐一验证：该实体是否是原文的**精确子串**？
- 区分时间实体和事件实体（看是否包含灾害词）
- 确定实体类型（必须来自知识图谱Schema）

**Step 3: 事件识别**
- 是否存在具体的灾害事件？
- 事件是否有明确的时间或地点？
- 确定事件类型（使用知识图谱Schema中的类型）

**Step 4: 关系抽取与方向验证**
- 对于每对实体，判断是否存在知识图谱Schema中定义的关系
- **关键**：检查关系方向是否正确（主语类型匹配 domain，宾语类型匹配 range）
- 如果方向不确定，宁可不抽

**Step 5: 证据标注与置信度**
- 为每个三元组标注原文证据（evidence）
- 根据证据明确程度标注置信度：
  - high: 原文直接表述
  - medium: 需要简单推理
  - low: 证据不够充分

---

## 【待标注文本】

```
{text}
```

---

## 【输出要求】

1. **先输出思考过程**（以"【思考过程】"开头，50-150字，简述关键实体和推理逻辑）
2. **再输出 JSON**（以 ```json 开头）

```json
{{{{
  "entities": [
    {{{{"name": "实体名（必须是原文子串）", "type": "知识图谱Schema中的类型"}}}}
  ],
  "events": [
    {{{{
      "name": "事件名称",
      "event_type": "DisasterEvent/DroughtEvent等",
      "time": {{{{"start_time": "YYYY-MM-DD或空", "end_time": "YYYY-MM-DD或空"}}}},
      "location": ["地点"]
    }}}}
  ],
  "triples": [
    {{{{
      "subject": "主语（原文子串）",
      "predicate": "知识图谱Schema中的关系名",
      "object": "宾语（原文子串）",
      "evidence": "原文支撑句",
      "confidence": "high/medium/low"
    }}}}
  ]
}}}}
```

**最终检查清单**（输出前请自检）：
- [ ] 所有实体名称都是原文的精确子串
- [ ] 所有实体类型都来自知识图谱Schema
- [ ] 所有关系都来自知识图谱Schema定义
- [ ] 所有关系方向都符合 domain/range 约束
- [ ] 纯时间实体标记为 TemporalEntity，不是 DisasterEvent
- [ ] 如果是通用知识描述，返回空列表
- [ ] 每个三元组都有 evidence 字段

请开始推理："""


# ========== 混合本体构建：语料挖掘与聚类标注 ==========
HYBRID_VOCAB_MINING_PROMPT = """
请从以下水旱灾害领域文本中提取关键词汇：

文本：
{batch_text}

请提取：
1. 实体词（名词短语）：地名、机构、设施、事件、数值等
2. 关系词（动词短语）：动作、状态变化、因果关系等

输出 JSON 格式：
{{"entities": ["词1", "词2"], "relations": ["词1", "词2"]}}
"""


HYBRID_CLUSTER_LABEL_PROMPT = """
以下是水旱灾害领域的一组相关词汇，请为其生成一个{type_hint}标签。

词汇：{members}

输出 JSON 格式：
{{"label": "英文标签", "label_cn": "中文标签", "description": "描述"}}
"""


HYBRID_RELATION_LABEL_PROMPT = """
以下是水旱灾害领域的一组关系词汇，请为其生成一个关系类型标签，并给出 domain / range。

候选实体类型：
{class_candidates}

关系词汇：{members}

输出 JSON 格式：
{{
  "label": "英文标签",
  "label_cn": "中文标签",
  "description": "描述",
  "domain": ["主语类型"],
  "range": ["宾语类型"]
}}
"""


# 统一的过滤阈值常量
UNIFIED_VERIFICATION_THRESHOLD = 0.85  # 保留用于向后兼容

# Gold/Pred 差异化过滤配置
GOLD_VERIFICATION_THRESHOLD = 0.9    # Gold 标注：严格模式，高阈值
GOLD_STRICT_FILTER = True            # Gold 标注：仅精确匹配

PRED_VERIFICATION_THRESHOLD = 0.75   # Pred 抽取：宽松模式，低阈值
PRED_STRICT_FILTER = False           # Pred 抽取：允许模糊匹配
