# Pred 构建全流程详解（论文写作版）

> 本文档基于 v4 主线代码，详细描述 Pred（预测结果）构建的完整流程，包括数据处理、Prompt 设计、CoT 推理、输出格式和后校验机制，可直接用于论文写作。

---

## 一、流程总览

### 1.1 Pipeline 架构

```
输入文本 (source_text)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: 文本类型检测 (Text Type Detection)                 │
│  ├─ 关键词评分 → 确定图结构类型                              │
│  └─ 置信度 < 0.3 时降级为 general_disaster                   │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 2: 图结构驱动的 CoT 抽取 (Graph-CoT Extraction)       │
│  ├─ 构建图结构 Prompt (节点类型 + 路径模式)                  │
│  ├─ 生成 4 步 CoT 推理步骤                                   │
│  └─ LLM 调用 → 解析 JSON 结果                                │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 3: 后校验 (Post-Verification)                         │
│  ├─ 原文回溯校验 (Hallucination Filter)                      │
│  │   ├─ 严格模式: 精确子串匹配                               │
│  │   └─ 宽松模式: 模糊匹配 (fuzzy_threshold=0.75)            │
│  └─ Schema 一致性校验                                        │
│      ├─ predicate ∈ TBox.relations                           │
│      └─ domain/range 类型约束                                │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 4: 输出标准化 (Output Normalization)                  │
│  ├─ 实体轻量归一化                                           │
│  └─ 统一输出格式 (build_extraction_record)                   │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
输出: predictions.jsonl
```

---

## 二、数据处理

### 2.1 输入数据格式

**测试集文件** (`pool.jsonl`):
```json
{"id": "doc_001", "text": "1998年长江发生特大洪水...", ...}
{"id": "doc_002", "text": "2022年夏季长江流域遭遇特大干旱...", ...}
```

**完整文本来源** (`--text-source`):
- 测试集中的 `text` 字段可能被截断
- 通过 `--text-source` 指定完整文本映射文件
- 使用 `doc_id` 进行关联查找

### 2.2 文本解析逻辑

```python
# kg/utils/text_source.py
def resolve_source_text(sample, doc_id, text_lookup, require_text_source):
    """
    优先级：
    1. text_lookup[doc_id]  # 完整文本来源
    2. sample["text"]       # 测试集原始文本
    3. sample["source_text"] # 兼容旧格式
    """
```

---

## 三、图结构检测与 CoT 步骤生成

### 3.1 文本类型检测算法

**算法 1: 文本类型检测 (TextTypeDetection)**

```
输入: text (待分类文本)
输出: (type_id, confidence, graph_structure)

1. 初始化 scores = {}
2. FOR each graph_type in GRAPH_STRUCTURES:
   2.1 strong_hits = count(strong_keywords ∩ text)
   2.2 weak_hits = count(weak_keywords ∩ text)
   2.3 score = strong_hits × 2 + weak_hits
   2.4 max_score = |strong_keywords| × 2 + |weak_keywords|
   2.5 scores[graph_type] = score / max_score
3. best_type = argmax(scores)
4. IF scores[best_type] < threshold (0.3):
   RETURN ("general_disaster", 0.0, GENERAL_STRUCTURE)
5. RETURN (best_type, scores[best_type], GRAPH_STRUCTURES[best_type])
```

### 3.2 预定义图结构类型

| 类型 ID | 名称 | 强关键词 | 弱关键词 |
|---------|------|----------|----------|
| `flood_event` | 洪水事件 | 洪水、洪峰、超警戒、泄洪、溃堤 | 水位、流量、暴雨、汛期 |
| `drought_event` | 干旱事件 | 干旱、旱情、旱灾、抗旱 | 高温、少雨、蓄水、调水 |
| `dispatch_rule` | 调度规则 | 当、若、则应、不得超过 | 调度、运用、下泄、库水位 |
| `impact_statistics` | 灾情统计 | 截至、累计、共计、统计 | 受灾人口、经济损失、万亩 |
| `general_disaster` | 通用灾害 | (无) | 灾害、灾情、防灾、减灾 |

### 3.3 图结构定义

每种图结构包含三类节点角色：

```python
@dataclass
class GraphStructure:
    nodes: Dict[str, NodeType]  # subject(S), intermediate(I), object(O)
    paths: List[PathPattern]     # 抽取路径模式
```

**示例：洪水事件图结构**

```
节点定义:
  S (起始): [Time, HazardFactor, WaterBody]
  I (中间): [FloodEvent, HydrologicalStation, Facility]
  O (终止): [Value, Impact, EmergencyResponse, AdministrativeRegion]

路径模式:
  Time → occurs_during → FloodEvent
  HazardFactor → has_cause → FloodEvent
  FloodEvent → causes_impact → Impact
  FloodEvent → triggers_response → EmergencyResponse
```

### 3.4 CoT 步骤生成

**算法 2: CoT 步骤生成 (GenerateCoTSteps)**

```python
def get_cot_steps(graph_structure) -> List[str]:
    steps = []
    
    # Step 1: 锚点与节点识别
    steps.append(f"""
    【Step 1: 锚点与节点识别】
    1. 首先识别核心锚点 I(中间节点): [{i_types}]
       这是图的核心，通常是灾害事件、设施或机构
    2. 基于锚点，寻找 S(起始节点): [{s_types}]
       通常是时间、原因或触发条件
    3. 基于锚点，寻找 O(终止节点): [{o_types}]
       通常是影响、数值或响应措施
    【约束】实体必须是原文的精确子串
    """)
    
    # Step 2: 路径驱动关系连接
    steps.append(f"""
    【Step 2: 路径驱动关系连接】
    任务：将 Step 1 识别的节点按路径规则连接
    路径规则：{path_rules}
    可用谓词：{valid_predicates}
    """)
    
    # Step 3: 证据回溯与逻辑验证
    steps.append("""
    【Step 3: 证据回溯与逻辑验证】
    对每条候选三元组进行双重验证：
    1. 证据验证：找到原文中的支撑句
    2. 逻辑验证：谓词是否在可用列表中？方向是否符合 S→I→O？
    """)
    
    # Step 4: JSON 输出
    steps.append("""
    【Step 4: 整合输出】
    将验证通过的三元组整合为 JSON 格式
    务必包含 evidence 字段
    """)
    
    return steps
```

---

## 四、Prompt 设计

### 4.1 完整 Prompt 模板


**P5_GRAPH_COT_EXTRACTION_PROMPT 结构**:

```
┌─────────────────────────────────────────────────────────────┐
│ 【图结构提示】                                               │
│   - 文本类型: {graph_type}                                   │
│   - 图结构角色示意: [S:起始] → [I:中间] → [O:终止]           │
│   - 节点类型定义                                             │
│   - 核心抽取路径                                             │
├─────────────────────────────────────────────────────────────┤
│ 【知识图谱 Schema 定义】                                     │
│   - classes: 实体类型列表                                    │
│   - relations: 关系类型列表 (含 domain/range)                │
│   - attributes: 属性定义                                     │
├─────────────────────────────────────────────────────────────┤
│ 【事件结构参考】                                             │
│   - event_id, event_type, name, time, space, causes, ...    │
├─────────────────────────────────────────────────────────────┤
│ 【核心约束】                                                 │
│   1. 实体必须是原文子串                                      │
│   2. 关系必须来自 Schema                                     │
│   3. 找不到证据就丢弃                                        │
├─────────────────────────────────────────────────────────────┤
│ 【链式推理步骤】                                             │
│   Step 1: 锚点与节点识别                                     │
│   Step 2: 路径驱动关系连接                                   │
│   Step 3: 证据回溯与逻辑验证                                 │
│   Step 4: 整合输出                                           │
├─────────────────────────────────────────────────────────────┤
│ 【输入文本】                                                 │
│   {input_text}                                               │
├─────────────────────────────────────────────────────────────┤
│ 【输出格式要求】                                             │
│   1. 先输出思考过程 (【思考过程】)                           │
│   2. 再输出 JSON (```json)                                   │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 System Prompt

```python
UNIFIED_SYSTEM_PROMPT_COT = """
你是一名水旱灾害领域知识图谱标注专家，负责生成高质量的评测标准数据。

【核心原则】
1. 准确性优先：所有实体必须是原文的精确子串
2. Schema 约束：类型和关系必须来自给定的 Schema
3. 方向正确：关系方向必须符合 domain → range 约束
4. 证据支撑：每条三元组必须有原文证据
5. 宁缺毋滥：不确定时宁可不抽
"""
```

### 4.3 关键约束规则

**规则 1: 区分时间实体与事件实体**

| 原文表述 | 正确分类 | 判断依据 |
|---------|---------|---------|
| "1998年" | TemporalEntity | 无灾害词 |
| "1998年长江洪水" | DisasterEvent | 含"洪水" |
| "乾隆五十年奇旱" | DroughtEvent | 含"奇旱" |

**规则 2: 关系方向约束**

```
正确: (灾害事件, has_hazard_factor, 致灾因子)
错误: (致灾因子, has_hazard_factor, 灾害事件)

正确: (灾害事件, affects_region, 地理区域)
错误: (地理区域, affects_region, 灾害事件)
```

---

## 五、LLM 调用与响应解析

### 5.1 调用流程

```python
def extract_events_with_verification(self, paragraph, schema, ...):
    # 1. 文本类型检测
    graph_structure, type_id, confidence = get_graph_structure_for_text(paragraph)
    if confidence < 0.3:
        graph_structure = get_graph_structure("general_disaster")
    
    # 2. 构建 Prompt
    graph_prompt = graph_structure.format_for_prompt()
    graph_steps = "\n\n".join(graph_structure.get_cot_steps())
    user_prompt = P5_GRAPH_COT_EXTRACTION_PROMPT.format(...)
    
    # 3. LLM 调用
    messages = [
        {"role": "system", "content": UNIFIED_SYSTEM_PROMPT_COT},
        {"role": "user", "content": user_prompt}
    ]
    raw_response = self.llm.chat_messages(messages, json_mode=False)
    
    # 4. 解析响应
    thought = extract_cot_thought(raw_response)
    result = parse_cot_response(raw_response)
```

### 5.2 响应解析算法

**算法 3: CoT 响应解析 (ParseCoTResponse)**

```python
def parse_cot_response(response_text: str) -> Optional[Dict]:
    """
    解析策略（优先级递减）:
    1. 提取 ```json ... ``` 代码块
    2. 提取 ``` ... ``` 代码块
    3. 查找 {...} JSON 对象
    """
    # 尝试提取 json 代码块
    json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # 尝试找 {...}
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start != -1 and end > start:
            json_str = response_text[start:end]
        else:
            return None
    
    return json.loads(json_str.strip())

def extract_cot_thought(response_text: str) -> str:
    """提取【思考过程】标记后的内容"""
    match = re.search(r"【思考过程】(.*?)(?=```|$)", response_text, re.DOTALL)
    return match.group(1).strip() if match else ""
```

---

## 六、后校验机制

### 6.1 原文回溯校验 (Hallucination Filter)

**算法 4: 原文回溯校验 (HallucinationFilter)**

```
输入: 
  - triples: 待校验三元组列表
  - original_text: 原始文本
  - strict_mode: 是否严格模式
  - fuzzy_threshold: 模糊匹配阈值 (默认 0.75)

输出:
  - valid_triples: 通过校验的三元组
  - filtered_triples: 被过滤的三元组 (含原因)
  - hallucination_rate: 幻觉率

算法:
FOR each triple in triples:
    subject = triple.subject
    object = triple.object
    
    # 校验 subject
    s_valid = check_entity(subject, original_text, strict_mode, fuzzy_threshold)
    
    # 校验 object
    o_valid = check_entity(object, original_text, strict_mode, fuzzy_threshold)
    
    IF s_valid AND o_valid:
        valid_triples.append(triple)
    ELSE:
        filtered_triples.append((triple, reason))

hallucination_rate = len(filtered_triples) / len(triples)
```

**实体校验函数**:

```python
def check_entity(entity, text, strict_mode, fuzzy_threshold):
    """
    匹配优先级:
    1. 精确匹配 (去空格后)
    2. 原文精确匹配 (保留空格)
    3. 模糊匹配 (非严格模式下)
    """
    clean_entity = re.sub(r'\s+', '', entity)
    clean_text = re.sub(r'\s+', '', text)
    
    # 精确匹配
    if clean_entity in clean_text:
        return True, "精确匹配"
    
    if entity in text:
        return True, "原文匹配"
    
    # 严格模式到此为止
    if strict_mode:
        return False, "原文中不存在"
    
    # 模糊匹配 (滑动窗口)
    similarity = fuzzy_search(clean_entity, clean_text)
    if similarity >= fuzzy_threshold:
        return True, f"模糊匹配({similarity:.2f})"
    
    return False, f"模糊匹配失败(最高{similarity:.2f})"
```

**模糊匹配算法**:

```python
def fuzzy_search(entity: str, text: str) -> float:
    """
    滑动窗口模糊搜索
    使用 SequenceMatcher 计算相似度
    """
    max_similarity = 0.0
    entity_len = len(entity)
    
    # 尝试不同窗口大小
    for window_size in [entity_len, entity_len+1, entity_len-1]:
        for i in range(len(text) - window_size + 1):
            window = text[i:i+window_size]
            similarity = SequenceMatcher(None, entity, window).ratio()
            max_similarity = max(max_similarity, similarity)
    
    return max_similarity
```

### 6.2 Schema 一致性校验

**算法 5: Schema 一致性校验 (SchemaConsistencyFilter)**

```
输入:
  - triples: 原文校验后的三元组
  - schema: TBox Schema
  - strict_mode: 是否严格模式

输出:
  - valid_triples: 通过校验的三元组
  - rejected_triples: 被拒绝的三元组

算法:
relation_map = {r.name: r for r in schema.relations}

FOR each triple in triples:
    predicate = triple.predicate
    
    # 检查 predicate 是否在 TBox 中
    IF predicate NOT IN relation_map:
        rejected.append((triple, "predicate_not_in_tbox"))
        CONTINUE
    
    rel = relation_map[predicate]
    
    # 检查 domain/range 约束
    IF triple.subject_type AND triple.subject_type NOT IN rel.domain:
        IF strict_mode:
            rejected.append((triple, "subject_type_not_in_domain"))
        ELSE:
            triple._schema_warning = "subject_type_not_in_domain"
            valid.append(triple)
        CONTINUE
    
    # 类似检查 object_type 与 range
    ...
    
    valid.append(triple)
```

---

## 七、输出格式

### 7.1 单条记录结构

```json
{
  "doc_id": "doc_001",
  "use_cot": true,
  "use_verify": true,
  "entities": [
    {"name": "1998年长江特大洪水", "type": "FloodEvent"},
    {"name": "持续性强降雨", "type": "HazardFactor"}
  ],
  "events": [
    {
      "event_id": "evt_1998_01",
      "event_type": "FloodEvent",
      "name": "1998年长江特大洪水",
      "time": {"start_time": "1998-06-01", "end_time": "1998-09-01"},
      "space": {
        "main_stream": ["长江中下游干流"],
        "tributaries": ["洞庭湖", "鄱阳湖"],
        "provinces": ["湖北省", "湖南省"]
      },
      "causes": ["持续性强降雨"],
      "impacts": {
        "affected_population": "2.23亿人",
        "deaths": "4150人",
        "direct_economic_loss": "1660亿元"
      }
    }
  ],
  "triples": [
    {
      "subject": "1998年长江特大洪水",
      "subject_type": "FloodEvent",
      "predicate": "has_cause",
      "object": "持续性强降雨",
      "object_type": "HazardFactor",
      "event_id": "evt_1998_01",
      "evidence": "受流域范围内持续性强降雨影响"
    }
  ],
  "filtered_triples": [
    {
      "triple": {"subject": "...", "predicate": "...", "object": "..."},
      "reason": "主语'xxx': 原文中不存在"
    }
  ],
  "schema_filtered_triples": [],
  "hallucination": {
    "enabled": true,
    "original_count": 10,
    "valid_count": 8,
    "filtered_count": 2,
    "schema_filtered_count": 0,
    "rate": 0.2
  }
}
```

### 7.2 输出构建函数

```python
def build_extraction_record(
    doc_id: str,
    source_text: str,
    extraction_result: Dict,
    use_cot: bool = True,
    use_verify: bool = True,
    include_source_text: bool = False,  # v4 默认不输出
    error: str = ""
) -> Dict:
    """
    统一输出格式构建
    - 从 events/triples 中自动收集 entities
    - 计算幻觉统计信息
    - 标准化所有字段
    """
```

---

## 八、完整流程伪代码

```
算法 6: Pred 构建完整流程 (PredictionPipeline)

输入:
  - test_file: 测试集文件路径
  - text_source: 完整文本来源文件
  - tbox: TBox Schema 文件
  - model: LLM 模型名称
  - fuzzy_threshold: 模糊匹配阈值 (默认 0.75)
  - strict_schema: 是否严格 Schema 校验 (默认 False)

输出:
  - predictions.jsonl: 预测结果文件

流程:
1. 加载 TBox Schema
2. 加载完整文本映射 text_lookup
3. 初始化 CQLLMPipeline

FOR each sample in test_file:
    4.1 解析 doc_id
    4.2 获取完整文本 source_text = text_lookup[doc_id]
    
    4.3 调用 extract_events_with_verification:
        a) 文本类型检测 → graph_structure
        b) 构建图结构 Prompt + CoT 步骤
        c) LLM 调用 → raw_response
        d) 解析 CoT 响应 → events, triples
        e) 原文回溯校验 → valid_triples, filtered_triples
        f) Schema 一致性校验 → final_triples
        g) 实体标准化
    
    4.4 构建输出记录 build_extraction_record
    4.5 写入 predictions.jsonl
```

---

## 九、关键参数配置

### 9.1 Pred 默认配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--fuzzy-threshold` | 0.75 | 模糊匹配阈值（宽松） |
| `--no-strict-schema` | True | 不严格执行 Schema 约束 |
| `--use-cot` | True | 使用 CoT Prompt |
| `--use-verify` | True | 启用原文回溯校验 |
| `--temperature` | 0.1 | LLM 温度参数 |
| `--top-p` | 0.1 | LLM Top-P 参数 |

### 9.2 Gold vs Pred 配置差异

| 配置项 | Gold | Pred |
|--------|------|------|
| `strict_filter` | True | False |
| `fuzzy_threshold` | 0.85~0.9 | 0.75 |
| `strict_schema` | True | False |

---

## 十、论文写作建议

### 10.1 方法描述模板

> 我们提出了一种**图结构驱动的链式思维（Graph-CoT）知识抽取方法**。该方法首先通过关键词评分对输入文本进行类型检测，确定其所属的图结构类型（如洪水事件、干旱事件等）。然后，基于预定义的图结构模式（包含起始节点S、中间节点I、终止节点O及其连接路径），生成四步递进式的推理步骤：(1) 锚点与节点识别；(2) 路径驱动关系连接；(3) 证据回溯与逻辑验证；(4) 结构化输出。最后，通过原文回溯校验和Schema一致性校验过滤幻觉三元组。

### 10.2 公式表示

**文本类型检测**:

$$
\text{score}(t) = \frac{2 \cdot |K_s \cap T| + |K_w \cap T|}{2 \cdot |K_s| + |K_w|}
$$

其中 $K_s$ 为强关键词集合，$K_w$ 为弱关键词集合，$T$ 为输入文本。

**幻觉率计算**:

$$
\text{HallucinationRate} = \frac{|\text{FilteredTriples}|}{|\text{TotalTriples}|}
$$

**模糊匹配相似度**:

$$
\text{Similarity}(e, w) = \frac{2 \cdot |LCS(e, w)|}{|e| + |w|}
$$

其中 $e$ 为实体，$w$ 为文本窗口，$LCS$ 为最长公共子序列。


---

## 十一、算法伪代码汇总（论文格式）

### Algorithm 1: Graph-CoT Knowledge Extraction

```
Algorithm 1: Graph-CoT Knowledge Extraction
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Input: text T, TBox schema S, fuzzy_threshold θ
Output: events E, triples R

1:  // Phase 1: Text Type Detection
2:  g ← DetectGraphStructure(T)
3:  if confidence(g) < 0.3 then
4:      g ← GENERAL_DISASTER_STRUCTURE
5:  end if

6:  // Phase 2: Prompt Construction
7:  P_graph ← FormatGraphPrompt(g)
8:  P_cot ← GenerateCoTSteps(g)
9:  P ← BuildPrompt(P_graph, P_cot, S, T)

10: // Phase 3: LLM Extraction
11: response ← LLM.generate(P)
12: thought ← ExtractThought(response)
13: (E_raw, R_raw) ← ParseJSON(response)

14: // Phase 4: Post-Verification
15: (R_valid, R_filtered) ← HallucinationFilter(R_raw, T, θ)
16: (R_final, R_schema) ← SchemaFilter(R_valid, S)

17: // Phase 5: Normalization
18: R_norm ← NormalizeEntities(R_final)

19: return (E_raw, R_norm, R_filtered, R_schema)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Algorithm 2: Hallucination Filter

```
Algorithm 2: Hallucination Filter with Fuzzy Matching
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Input: triples R, source_text T, threshold θ, strict_mode
Output: valid_triples R_v, filtered_triples R_f

1:  R_v ← ∅, R_f ← ∅
2:  T_norm ← RemoveWhitespace(T)

3:  for each r = (s, p, o) ∈ R do
4:      s_valid ← VerifyEntity(s, T, T_norm, θ, strict_mode)
5:      o_valid ← VerifyEntity(o, T, T_norm, θ, strict_mode)
6:      
7:      if s_valid ∧ o_valid then
8:          R_v ← R_v ∪ {r}
9:      else
10:         reason ← BuildFilterReason(s_valid, o_valid)
11:         R_f ← R_f ∪ {(r, reason)}
12:     end if
13: end for

14: return (R_v, R_f)

Function VerifyEntity(e, T, T_norm, θ, strict):
15:     e_norm ← RemoveWhitespace(e)
16:     if e_norm ⊆ T_norm then return True  // Exact match
17:     if e ⊆ T then return True            // Original match
18:     if strict then return False
19:     sim ← FuzzySearch(e_norm, T_norm)
20:     return sim ≥ θ

Function FuzzySearch(e, T):
21:     max_sim ← 0
22:     for w_size ∈ {|e|-1, |e|, |e|+1} do
23:         for i ← 0 to |T| - w_size do
24:             w ← T[i : i+w_size]
25:             sim ← SequenceMatcher(e, w)
26:             max_sim ← max(max_sim, sim)
27:         end for
28:     end for
29:     return max_sim
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Algorithm 3: CoT Step Generation

```
Algorithm 3: Graph-Driven CoT Step Generation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Input: GraphStructure g with nodes N = {S, I, O} and paths P
Output: CoT steps list

1:  steps ← []

2:  // Step 1: Anchor & Node Identification
3:  step1 ← "【Step 1: 锚点与节点识别】\n"
4:  step1 += "1. 首先识别核心锚点 I(中间节点): " + g.I.types
5:  step1 += "2. 基于锚点，寻找 S(起始节点): " + g.S.types
6:  step1 += "3. 基于锚点，寻找 O(终止节点): " + g.O.types
7:  step1 += "【约束】实体必须是原文的精确子串"
8:  steps.append(step1)

9:  // Step 2: Path-Driven Relation Linking
10: step2 ← "【Step 2: 路径驱动关系连接】\n"
11: step2 += "路径规则：\n"
12: for each path ∈ g.paths do
13:     step2 += "  - " + path.name + ": " + path.pattern
14: end for
15: step2 += "可用谓词：" + ExtractPredicates(g.paths)
16: steps.append(step2)

17: // Step 3: Evidence Verification
18: step3 ← "【Step 3: 证据回溯与逻辑验证】\n"
19: step3 += "1. 证据验证：找到原文中的支撑句\n"
20: step3 += "2. 逻辑验证：谓词是否在可用列表中？方向是否符合 S→I→O？"
21: steps.append(step3)

22: // Step 4: JSON Output
23: step4 ← "【Step 4: 整合输出】\n"
24: step4 += "将验证通过的三元组整合为 JSON 格式，务必包含 evidence 字段"
25: steps.append(step4)

26: return steps
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 十二、实际命令示例

### 12.1 完整 Pred 构建命令

```bash
conda activate YangtzeLLM

python scripts/p5/run_extraction_on_test.py \
  --test-file data/p5_eval_pool/pool.jsonl \
  --text-source data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl \
  --tbox outputs/kg_final/tbox_final.json \
  --model "gpt-4o-mini" \
  --base-url "https://api.uglycat.cc/v1/" \
  --temperature 0.1 \
  --top-p 0.1 \
  --output outputs/eval_models_hybrid/predictions_gpt4o_mini_0112.jsonl \
  --fuzzy-threshold 0.75 \
  --no-strict-schema \
  --skip-existing \
  --interval 15 \
  2>&1 | tee outputs/eval_models_hybrid/predictions_gpt4o_mini_0112.log
```

### 12.2 参数说明

| 参数 | 值 | 说明 |
|------|-----|------|
| `--test-file` | `pool.jsonl` | 测试集（含 doc_id） |
| `--text-source` | `light_pool_v2_dedup.jsonl` | 完整文本来源 |
| `--tbox` | `tbox_final.json` | Hybrid TBox |
| `--model` | `gpt-4o-mini` | LLM 模型 |
| `--fuzzy-threshold` | 0.75 | 宽松模糊匹配 |
| `--no-strict-schema` | - | 不严格执行 Schema |
| `--skip-existing` | - | 断点续跑 |
| `--interval` | 15 | 请求间隔（秒） |

---

## 十三、总结

本文档详细描述了 Pred 构建的完整流程：

1. **数据处理**：通过 `text_source` 确保使用完整文本
2. **图结构检测**：基于关键词评分确定文本类型
3. **CoT 推理**：4 步递进式推理（锚点识别→路径连接→证据验证→输出）
4. **后校验**：原文回溯（模糊匹配）+ Schema 一致性
5. **输出标准化**：统一格式，便于评测

核心创新点：
- **图结构驱动的 CoT**：将领域知识编码为图结构，指导 LLM 按路径抽取
- **双重后校验**：原文回溯过滤幻觉 + Schema 约束保证一致性
- **Gold/Pred 同链路**：确保评测公平性
