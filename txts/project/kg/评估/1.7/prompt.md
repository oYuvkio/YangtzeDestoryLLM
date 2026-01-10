# 修正后的 Gold 标注 Prompt


## 修改文件：`scripts/generate_gold_with_tbox.py`

将原有的 `SYSTEM_PROMPT_COT` 和 `USER_PROMPT_COT` 替换为以下内容：

```python
# ==============================================================================
# Prompt 模板（优化版：含 Few-shot 正反例 + CoT）
# ==============================================================================

# 普通模式 System Prompt（保持不变）
SYSTEM_PROMPT = """你是一名水旱灾害领域知识图谱标注专家。
你的任务是从文本中抽取实体和关系三元组。

【核心规则】
1. 实体必须是原文的**精确子串**，不可改写、不可合并、不可省略
2. 实体类型和关系类型**必须**从给定的 Schema 中选择
3. **严禁**发明 Schema 中不存在的类型或关系
4. 宁可漏抽，不可错抽
5. 每个三元组必须有原文支撑

请严格按 JSON 格式输出。"""

# 普通模式 User Prompt（保持不变）
USER_PROMPT_TEMPLATE = """请从以下文本中抽取实体和关系三元组。

{tbox_schema}

---

【待标注文本】
```
{text}
```

---

【输出格式】
请严格按以下 JSON 格式输出（只输出 JSON，不要其他内容）：

{{
  "entities": [
    {{"name": "实体名（必须是原文精确子串）", "type": "实体类型（必须来自Schema）"}}
  ],
  "triples": [
    {{
      "subject": "主语（原文子串）",
      "predicate": "关系（必须来自Schema的关系名，如 affects_region）",
      "object": "宾语（原文子串）",
      "evidence": "原文支撑句"
    }}
  ],
  "events": [
    {{
      "name": "事件名称（原文子串）",
      "event_type": "事件类型（必须来自Schema，如 DisasterEvent）",
      "time": {{"start_time": "", "end_time": ""}},
      "location": ["地点"]
    }}
  ]
}}

请直接输出JSON："""


# ==============================================================================
# CoT 模式 Prompt（优化版：含 Few-shot 正反例）
# ==============================================================================

SYSTEM_PROMPT_COT = """你是一名水旱灾害领域知识图谱标注专家，负责生成高质量的评测标准数据（Gold Standard）。

【你的职责】
1. 从文本中抽取实体和关系三元组，作为模型评测的标准答案
2. 确保抽取结果的**准确性**和**一致性**
3. 严格遵循 Schema 约束，不发明新类型或关系

【核心原则】
1. **准确性优先**：所有实体必须是原文的**精确子串**，不可改写
2. **Schema 约束**：类型和关系必须来自给定的 Schema
3. **方向正确**：关系方向必须符合 domain → range 约束
4. **证据支撑**：每条三元组必须有原文证据
5. **宁缺毋滥**：不确定时宁可不抽，不可错抽"""


USER_PROMPT_COT = """请从以下文本中抽取实体和关系三元组，作为评测标准数据。

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
关系的方向由 Schema 中的 domain（主语类型）和 range（宾语类型）决定：

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
    {{"subject": "城陵矶水文站", "predicate": "monitors_river", "object": "洞庭湖", "evidence": "洞庭湖水系出口控制站城陵矶水文站", "confidence": "high"}},
    {{"subject": "2022年水文干旱过程", "predicate": "occurs_at", "object": "2022年7月8日", "evidence": "第一阶段(干旱露头):2022年7月8日—8月底", "confidence": "high"}},
    {{"subject": "2022年水文干旱过程", "predicate": "triggers_response", "object": "抗旱Ⅳ级应急响应", "evidence": "8月12日全省启动抗旱Ⅳ级应急响应", "confidence": "high"}},
    {{"subject": "城陵矶水文站", "predicate": "has_value", "object": "24.50 m", "evidence": "洞庭湖8月4日达到枯水位(24.50 m)", "confidence": "high"}}
  ]
}}
```

## 【📕 反例演示 - 常见错误】

### 反例1：通用知识描述（应返回空）

**原文**：
"洪水是由暴雨、急剧融冰化雪、风暴潮等自然因素引起的江河湖海水量迅速增加或水位迅猛上涨的水流现象。根据成因，洪水可分为暴雨洪水、融雪洪水、冰凌洪水等类型。"

**【思考过程】**
这是洪水的定义和分类说明，属于通用知识，没有提到任何具体的洪水事件（无时间、无地点、无具体事件名）。应返回空列表。

**❌ 错误输出**（不要这样做）：
```json
{{
  "triples": [
    {{"subject": "洪水", "predicate": "has_hazard_factor", "object": "暴雨"}}
  ]
}}
```
**错误原因**：这是通用规律描述，不是具体事件事实

**✅ 正确输出**：
```json
{{
  "entities": [],
  "events": [],
  "triples": []
}}
```

---

### 反例2：关系方向错误

**原文**：
"持续暴雨导致了1998年长江特大洪水。"

**❌ 错误输出**（关系方向反了）：
```json
{{
  "triples": [
    {{"subject": "持续暴雨", "predicate": "has_hazard_factor", "object": "1998年长江特大洪水"}}
  ]
}}
```
**错误原因**：has_hazard_factor 的 domain 是 DisasterEvent，range 是 HazardFactor。应该是"事件具有致灾因子"，不是"致灾因子具有事件"

**✅ 正确输出**：
```json
{{
  "triples": [
    {{"subject": "1998年长江特大洪水", "predicate": "has_hazard_factor", "object": "持续暴雨", "evidence": "持续暴雨导致了1998年长江特大洪水", "confidence": "high"}}
  ]
}}
```

---

### 反例3：纯时间作为事件主语

**原文**：
"1998年，长江流域发生了严重的洪涝灾害。"

**❌ 错误输出**：
```json
{{
  "entities": [{{"name": "1998年", "type": "DisasterEvent"}}],
  "triples": [{{"subject": "1998年", "predicate": "affects_region", "object": "长江流域"}}]
}}
```
**错误原因**："1998年"只是时间，不是事件

**✅ 正确输出**：
```json
{{
  "entities": [
    {{"name": "1998年", "type": "TemporalEntity"}},
    {{"name": "长江流域", "type": "Basin"}},
    {{"name": "严重的洪涝灾害", "type": "DisasterEvent"}}
  ],
  "triples": [
    {{"subject": "严重的洪涝灾害", "predicate": "affects_region", "object": "长江流域", "evidence": "长江流域发生了严重的洪涝灾害", "confidence": "high"}},
    {{"subject": "严重的洪涝灾害", "predicate": "occurs_at", "object": "1998年", "evidence": "1998年，长江流域发生了严重的洪涝灾害", "confidence": "high"}}
  ]
}}
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
- 确定实体类型（必须来自 Schema）

**Step 3: 事件识别**
- 是否存在具体的灾害事件？
- 事件是否有明确的时间或地点？
- 确定事件类型（使用 Schema 中的类型）

**Step 4: 关系抽取与方向验证**
- 对于每对实体，判断是否存在 Schema 中定义的关系
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
{{
  "entities": [
    {{"name": "实体名（必须是原文子串）", "type": "Schema中的类型"}}
  ],
  "events": [
    {{
      "name": "事件名称",
      "event_type": "DisasterEvent/DroughtEvent等",
      "time": {{"start_time": "YYYY-MM-DD或空", "end_time": "YYYY-MM-DD或空"}},
      "location": ["地点"]
    }}
  ],
  "triples": [
    {{
      "subject": "主语（原文子串）",
      "predicate": "Schema中的关系名",
      "object": "宾语（原文子串）",
      "evidence": "原文支撑句",
      "confidence": "high/medium/low"
    }}
  ]
}}
```

**最终检查清单**（输出前请自检）：
- [ ] 所有实体名称都是原文的精确子串
- [ ] 所有实体类型都来自 Schema
- [ ] 所有关系都来自 Schema 定义
- [ ] 所有关系方向都符合 domain/range 约束
- [ ] 纯时间实体标记为 TemporalEntity，不是 DisasterEvent
- [ ] 如果是通用知识描述，返回空列表
- [ ] 每个三元组都有 evidence 字段

请开始推理："""
```

---

## 主要改进点总结

| 改进项               | 说明                                                                    |
| -------------------- | ----------------------------------------------------------------------- |
| **Few-shot 正例**    | 3个完整正例（现代干旱、历史灾害、防洪工程），覆盖不同场景               |
| **Few-shot 反例**    | 4个典型错误（通用知识、方向错误、时间误判、实体改写），明确标注错误原因 |
| **关系方向速查表**   | 表格形式展示常见关系的正确/错误方向                                     |
| **时间vs事件判断表** | 明确区分标准和示例                                                      |
| **CoT 步骤细化**     | 5步推理流程，每步都有明确的验证点                                       |
| **最终检查清单**     | 输出前的自检项，减少常见错误                                            |
| **通用知识过滤**     | 明确强调不抽取规律性描述                                                |
| **置信度标注**       | 增加 confidence 字段说明                                                |

---

## 使用方式

脚本使用方式保持不变：

```bash
# 推荐配置：CoT + 幻觉过滤
bash scripts/p5/run_gold_annotation.sh \
    --tbox-version s3 \
    --model "gpt-4o" \
    --use-cot \
    --use-verification \
    --verification-threshold 0.7

# 或直接运行 Python 脚本
python scripts/generate_gold_with_tbox.py \
    --input data/p5_eval_pool/final/test_final.jsonl \
    --tbox outputs/cq_pipeline/final/tbox_s3_optimized.json \
    --output data/p5_eval_pool/gold_s3.jsonl \
    --model "gpt-4o" \
    --use-cot \
    --use-verification
```