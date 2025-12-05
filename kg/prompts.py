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
4) 覆盖风险管理周期的不同阶段，避免仅限于一般性灾害管理问题, 避免过于具体的事件细节（如某次具体洪水的精确数据）

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
   - 每个类用英文 name（如 FloodEvent）、中文名 cn_name（如 洪水事件）和定义 (definition) 描述；
   - examples 中给出 1~3 个典型实例（中文字符串）。

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
    {{
      "name": "DisasterEvent",
      "cn_name": "灾害事件",
      "definition": "在一定时间和空间范围内发生的与长江流域相关的水旱灾害过程",
      "examples": ["1998年长江特大洪水", "2022年长江流域特大干旱"]
    }},
    {{
      "name": "FloodEvent",
      "cn_name": "洪水事件",
      "definition": "特指长江干流或支流发生的明显洪水过程",
      "examples": ["1998年长江特大洪水"]
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

1. 从文本中识别出当前 TBox 中尚未很好覆盖的「候选类、关系或属性」。
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

TBox 定义（classes / relations / attributes）：
{schema_json}

事件 Schema 参考：
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
   - event_type 必须使用 TBox.classes.name 中已有的某个类名，例如 "FloodEvent", "DroughtEvent"。
   - 若无法确定具体子类，可以使用更上层的类，如 "DisasterEvent"。

2. 在 TBox 约束下抽取三元组（triples）：
   - subject 和 object 通常来自【待抽取文本】，是事件名、地名、致灾因子等实体（用中文字符串表示，与原文风格一致）；
   - predicate 必须来自 TBox.relations.name 中已有的某个关系名（如 "has_cause", "affects_region"）；
   - 可利用前后文补充缺失信息（如年份、地点等）
   - 可以根据需要附带 event_id（若该三元组与某个事件强相关）和 evidence（原文中的支撑句）。
  
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
   - "event_type": string，来自 TBox.classes.name
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
   - "predicate": string（来自 TBox.relations.name）
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
  "event_type": "TBox 中的类名，如 FloodEvent 或 DroughtEvent",
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
现在给你一段从文献中切分出来的文本片段，请你判断它是否适合放入“长江流域水旱灾害知识图谱”的评估语料库（eval pool）。

【评估维度】

1. 相关性（领域）
   - 如果内容主要讨论以下主题之一，则认为 “与水旱灾害领域相关（is_water_disaster_domain = true）”：
     * 洪水、暴雨洪涝、山洪、城市内涝、干旱、枯水、水资源短缺；
     * 与水旱灾害相关的致灾因子：极端降水、持续少雨、高温热浪、台风、风暴潮、地质灾害诱发堰塞湖等；
     * 防汛抗旱、防洪排涝、水利工程运行（堤防、水库、蓄滞洪区、水闸、泵站等）；
     * 灾害影响：人员伤亡、农田受灾、供水中断、航运受阻、电力供应受影响等；
     * 灾害防御与应急响应：预警、会商、响应级别、转移安置、应急抢险、水库调度、防御工作总结等。
   - 如果内容主要是与上述无关的算法推导、自然语言处理方法说明、纯数学公式、与其他领域（如交通事故、金融、教育等）相关，请认为 is_water_disaster_domain = false。

2. 是否与“长江流域”紧密相关（is_yangtze_related）
   - 如果段落中出现 “长江” 或其主要支流/区域（如：汉江、嘉陵江、洞庭湖、鄱阳湖、三峡水库、长江上游/中游/下游、沿江城市等），则 is_yangtze_related = true；
   - 如果只是讲中国其他流域或全球一般性水旱灾害，且没有明显长江线索，则 is_yangtze_related = false。

3. 文本质量（text_quality）
   - good：文本基本连贯，句子完整，几乎没有乱码、奇怪的分词或严重排版错误，能看懂主要意思；
   - noisy：少量乱码或排版问题，但不影响理解（比如个别英文大小写混乱、个别符号插入、少量断行）；
   - garbled：大量乱码或字符残片，句子严重破碎，几乎看不出原意；或者几乎全是公式、变量名、单词碎片、参考文献条目，缺乏自然语言句子。这种情况不要收进 eval_pool。

4. 是否包含对 KG 有用的内容（contains_event_or_rule）
   - true：段落中至少包含一类：
     * 描述某次具体灾害事件的发生、发展、影响或应对（哪一年、哪个地区、发生了什么、造成了什么后果、采取了什么措施等）；
     * 描述防汛抗旱/应急响应的制度、流程、职责分工、启动条件、响应级别等（类似应急预案、公报中的规则性文字）；
     * 描述水利工程（堤防、水库、闸站、蓄滞洪区等）在防灾中的功能、运行方式、调度规则；
     * 描述灾害致灾因子、气候异常、降水异常等科学事实或统计特征。
   - false：纯方法论说明（如“本文采用 LDA 模型对新闻进行主题分析…”）、纯技术细节、不含任何具体灾害/防御/规则/影响事实的段落，一般认为不适合作为知识图谱 eval 样本。

5. 可能来源类型（source_guess）
   - law_plan：法律、条例、应急预案、制度办法等规范性文件；
   - gazette_yearbook：公报、年鉴、年报等年度统计或总结；
   - case_paper：灾害案例分析、学术论文、技术报告等；
   - news_popular：新闻报道、官方科普文章、媒体评论等；
   - other：无法判断或混合。

【分维度打分】
请为以下三个维度分别给出 0/1/2 的整数评分：
relevance_yangtze：0=完全无关；1=泛水旱灾害相关；2=明确提到长江流域或可直接用于长江场景
kg_potential：0=几乎没有可抽知识；1=有少量事实/措施；2=有清晰的事件、指标、因果或措施，适合抽取
cleanliness：0=严重乱码；1=有少量噪声但可读；2=文本规范、句子完整

【语义主题标签】
为段落指定一个 topic_label（中文短语即可，可选集合示例）：
- disaster_event（灾害事件叙述）
- impact_assessment（影响与损失）
- measure_response（防治措施/应急响应）
- institution_regulation（制度/法规/流程）
- background_analysis（致灾因子/气候背景/统计特征）
- other（其他无法归类）

【总体决策规则（keep_for_eval）】

请根据以上标签，给出最终布尔值 keep_for_eval：

- 只有在下面条件同时满足时，才给 keep_for_eval = true：
  1) is_water_disaster_domain = true；
  2) text_quality = "good" 或 "noisy"（不能是 "garbled"）且 cleanliness >= 1；
  3) contains_event_or_rule = true，且 kg_potential >= 1；
  4) relevance_yangtze >= 1；

- 在满足上述 3 个条件的前提下：
  - 如果 is_yangtze_related = true，通常应该保留；
  - 如果 is_yangtze_related = false，但内容是通用的水旱灾害制度/规则/方法且对知识图谱有明显价值，也可以保留；
  - 如果你犹豫不决，请偏向 keep_for_eval = false（宁可漏掉，不要把明显不合适的段落收进去）。

【输出要求】

1. 请严格按照下面 JSON 模板输出，不要添加任何额外说明文字或注释。
2. 所有字段都必须给出；字符串用双引号，布尔用 true/false，小写。
3. reason 字段用简短中文（不超过 40 字）概括保留/剔除的主要原因。

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
    "source_guess": "case_paper"
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
            return "请根据 TBox 中定义的类进行分类。"
        
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
            schema_json: TBox 定义 JSON
            input_text: 主文本
            context_before: 前文上下文
            context_after: 后文上下文
            class_usage_hint: 类使用提示
            event_schema: 事件 Schema 参考
            
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
            class_usage_hint=class_usage_hint or "请根据 TBox 中定义的类进行分类",
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
        schema_json: TBox 定义 JSON 字符串
        input_text: 待抽取的主文本
        context_before: 前文上下文
        context_after: 后文上下文
        classes: TBox 中的类定义列表（用于生成提示）
        
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
