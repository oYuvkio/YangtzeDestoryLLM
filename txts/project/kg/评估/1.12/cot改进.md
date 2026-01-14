# CoT 与图结构结合指导文档

---

## 📊 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     图结构驱动的递进推理                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  文本输入 ──→ get_graph_structure_for_text() ──→ GraphStructure │
│                                                        │        │
│                         ┌──────────────────────────────┘        │
│                         ▼                                       │
│              ┌─────────────────────┐                            │
│              │  动态注入图结构信息  │                            │
│              └─────────────────────┘                            │
│                         │                                       │
│         ┌───────────────┼───────────────┐                       │
│         ▼               ▼               ▼                       │
│   Step 1 注入      Step 2 注入      Step 3 注入                 │
│   start_types      path_rules      验证规则                     │
│   intermediate     edge_types                                   │
│   end_types                                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔧 代码改动清单

### 改动1：`GraphStructure` 类增加路径规则方法

**文件**：`kg/graph_structure.py`

```python
class GraphStructure:
    def __init__(self, structure_type: str, ...):
        self.structure_type = structure_type
        self.start_types = [...]      # S节点类型
        self.intermediate_types = [...] # I节点类型
        self.end_types = [...]        # O节点类型
        self.edge_types = [...]       # 边类型（关系）
    
    # ===== 新增方法 =====
    
    def get_path_rules(self) -> str:
        """生成路径连接规则（用于Step 2）"""
        rules = []
        # S → I 路径
        for s in self.start_types:
            for i in self.intermediate_types:
                rules.append(f"  - {s} → {i}: 使用关系 [occurs_at, triggered_by, ...]")
        # I → O 路径
        for i in self.intermediate_types:
            for o in self.end_types:
                rules.append(f"  - {i} → {o}: 使用关系 [affects, causes, located_at, ...]")
        return "\n".join(rules)
    
    def get_valid_predicates(self) -> str:
        """返回该图结构允许的谓词列表（用于Step 3验证）"""
        return ", ".join(self.edge_types)
    
    def get_cot_steps(self) -> str:
        """生成递进式CoT步骤"""
        return f"""
【Step 1: 节点识别与角色标注】
按图结构 [{self.structure_type}] 的角色定义识别实体：
  - S(起始节点): {', '.join(self.start_types)}
  - I(中间节点): {', '.join(self.intermediate_types)}
  - O(终止节点): {', '.join(self.end_types)}
约束：实体必须是原文的精确子串
▶ 输出格式：
  S节点: ["实体1", "实体2"]
  I节点: ["实体3"]
  O节点: ["实体4", "实体5"]

---

【Step 2: 路径驱动关系连接】（基于Step 1的节点）
任务：将Step 1识别的节点按以下路径规则连接
路径规则（{self.structure_type}）：
{self.get_path_rules()}
可用谓词：{self.get_valid_predicates()}
▶ 输出候选三元组：
  (S节点实体, 谓词, I节点实体)
  (I节点实体, 谓词, O节点实体)

---

【Step 3: 证据回溯与逻辑验证】（基于Step 2的候选三元组）
对Step 2的每条候选三元组进行双重验证：
  1. 证据验证：找到原文中的支撑句
  2. 逻辑验证：
     - 谓词是否在可用列表 [{self.get_valid_predicates()}] 中？
     - 关系方向是否符合 S→I→O 路径？
▶ 输出格式：
  三元组: (主语, 谓词, 宾语)
  证据句: "..."
  判定: ✓保留 / ✗丢弃(原因)

---

【Step 4: 整合输出】（基于Step 3的验证结果）
将Step 3中判定为"保留"的三元组整合为最终JSON格式。
"""
```

---

### 改动2：不同图结构类型的差异化配置

**文件**：`kg/graph_structure.py`

```python
# 洪水事件图结构
class FloodEventStructure(GraphStructure):
    def __init__(self):
        super().__init__(
            structure_type="flood_event",
            start_types=["Time", "TemporalEntity", "Cause"],
            intermediate_types=["FloodEvent", "DisasterEvent"],
            end_types=["Location", "Impact", "Value", "Response"],
            edge_types=["occurs_at", "located_in", "causes", "affects", 
                       "has_impact", "triggers_response"]
        )
    
    def get_path_rules(self) -> str:
        return """
  - Time → FloodEvent: occurs_at（事件发生时间）
  - Cause → FloodEvent: causes（导致事件）
  - FloodEvent → Location: located_in, affects（影响区域）
  - FloodEvent → Impact: has_impact（造成影响）
  - FloodEvent → Response: triggers_response（触发响应）"""

# 地理实体图结构
class GeographicStructure(GraphStructure):
    def __init__(self):
        super().__init__(
            structure_type="geographic",
            start_types=["Location"],
            intermediate_types=["River", "Lake", "Basin"],
            end_types=["Attribute", "Value", "SubLocation"],
            edge_types=["contains", "part_of", "has_attribute", "flows_through"]
        )
    
    def get_path_rules(self) -> str:
        return """
  - Location → River/Lake: contains（包含水体）
  - River → SubLocation: flows_through（流经区域）
  - River/Lake → Attribute: has_attribute（属性描述）"""
```

---

### 改动3：Prompt模板整合

**文件**：`kg/prompts.py`

```python
P5_GRAPH_COT_EXTRACTION_PROMPT = """
你是一名水旱灾害知识图谱构建专家。

【图结构类型】: {graph_type}
【图结构说明】: {graph_description}

---

知识图谱Schema定义：
{schema_json}

---

【递进推理步骤】
{cot_steps}   ← 这里插入 graph_structure.get_cot_steps() 的结果

---

【核心约束】
1. 实体必须是原文子串，不可改写
2. 每步必须基于前一步的输出
3. 谓词必须来自Schema定义
4. 无证据支撑则丢弃

---

输入文本:
{input_text}

请严格按照上述4个Step递进执行，输出思考过程和最终JSON。
"""
```

---

### 改动4：Pipeline调用逻辑

**文件**：`kg/cq_pipeline.py`

```python
def extract_events_with_verification(self, paragraph: str, ...):
    # 1. 检测图结构类型
    graph_structure, type_id, confidence = get_graph_structure_for_text(paragraph)
    
    # 2. 生成递进式CoT步骤（动态注入图结构信息）
    cot_steps = graph_structure.get_cot_steps()
    
    # 3. 构建Prompt
    prompt = P5_GRAPH_COT_EXTRACTION_PROMPT.format(
        graph_type=graph_structure.structure_type,
        graph_description=graph_structure.get_description(),
        schema_json=json.dumps(schema, ensure_ascii=False),
        cot_steps=cot_steps,  # ← 递进CoT步骤
        input_text=paragraph
    )
    
    # 4. 调用LLM
    response = self.llm_client.chat(prompt)
    
    # 5. 解析响应（需要适配递进输出格式）
    result = self._parse_progressive_cot_response(response)
    
    # 6. 后校验（保持不变）
    verified = self.halluc_filter.verify(result, paragraph)
    
    return verified
```

---

## ⚠️ 注意事项

### 1. 保持图结构与CoT的一致性

| 检查项 | 说明 |
|-------|------|
| Step 1 的类型列表 | 必须来自 `graph_structure.start/intermediate/end_types` |
| Step 2 的路径规则 | 必须来自 `graph_structure.get_path_rules()` |
| Step 3 的谓词验证 | 必须来自 `graph_structure.edge_types` |

**错误示例**：
```
Step 1 识别出 "FloodEvent" 
但 Step 2 用了 geographic 结构的路径规则
```

### 2. 递进依赖的措辞必须明确

```python
# ✓ 正确：明确引用前一步
"【Step 2】基于Step 1识别的节点，按路径规则连接..."
"【Step 3】对Step 2的每条候选三元组..."

# ✗ 错误：无引用关系
"【Step 2】识别关系..."
"【Step 3】验证三元组..."
```

### 3. 输出格式标记统一

```python
# 每步输出用 ▶ 标记，便于后续解析
"▶ 输出格式：..."
"▶ 输出候选三元组：..."
```

### 4. 解析逻辑需适配

```python
def _parse_progressive_cot_response(self, response: str) -> dict:
    """解析递进式CoT响应"""
    result = {
        "step1_nodes": {"S": [], "I": [], "O": []},
        "step2_candidates": [],
        "step3_verified": [],
        "final_triples": []
    }
    
    # 解析每步输出
    # Step 1: 提取 S/I/O 节点列表
    # Step 2: 提取候选三元组
    # Step 3: 提取验证结果
    # Step 4: 提取最终JSON
    
    return result
```

### 5. 图结构切换时的兼容性

```python
# 确保所有图结构类型都实现了相同的方法
class GraphStructure(ABC):
    @abstractmethod
    def get_cot_steps(self) -> str: pass
    
    @abstractmethod
    def get_path_rules(self) -> str: pass
    
    @abstractmethod
    def get_valid_predicates(self) -> str: pass
```

---

## ✅ 自检清单

| 序号 | 检查项 | 状态 |
|-----|-------|------|
| 1 | `get_cot_steps()` 中 Step 1 的类型是否动态来自图结构？ | ☐ |
| 2 | `get_cot_steps()` 中 Step 2 是否调用 `get_path_rules()`？ | ☐ |
| 3 | `get_cot_steps()` 中 Step 3 是否引用 `get_valid_predicates()`？ | ☐ |
| 4 | 每个 Step 是否有 `▶ 输出格式` 标记？ | ☐ |
| 5 | Step 2/3/4 是否明确引用前一步？ | ☐ |
| 6 | 不同图结构类型是否都实现了所需方法？ | ☐ |
| 7 | Pipeline 是否正确传递 `cot_steps` 到 Prompt？ | ☐ |
| 8 | 解析逻辑是否适配新的输出格式？ | ☐ |

---

## 📝 改动总结

| 文件 | 改动内容 |
|-----|---------|
| `kg/graph_structure.py` | 新增 `get_path_rules()`、`get_valid_predicates()`；重写 `get_cot_steps()` |
| `kg/prompts.py` | 更新 Prompt 模板，整合递进 CoT |
| `kg/cq_pipeline.py` | 调用逻辑适配、解析逻辑适配 |


# 注意事项：
你的计划非常扎实，逻辑清晰，已经将“图结构先验”与“递进式 CoT”完美融合。这套架构在论文中会是一个非常亮眼的 **Methodology**。

不过，从**工程落地**和**模型稳定性**的角度来看，我有 **4 个关键的优化建议** 和 **3 个潜在风险预警**，希望能帮助你避坑。

---

### 🚀 关键优化建议

#### 1. 解析策略：不要过度解析中间步骤（Critical）
在你的 `_parse_progressive_cot_response` 设计中，你计划解析 Step 1、Step 2、Step 3 的输出。
*   **风险**：LLM 在输出中间思考过程（CoT）时，格式往往不稳定（比如有时候用 `[`，有时候用 `-`，有时候换行）。如果你编写正则去严格解析 Step 1-3，代码会非常脆弱，容易因为格式微小变化导致整个 Pipeline 崩溃。
*   **建议**：
    *   **只严格解析 Step 4 (最终 JSON)**。
    *   Step 1-3 仅作为 **“思维链（Thought）”** 保留在 `thought` 字段中，供人工检查或论文 Case Study 使用，**不要**尝试用代码去结构化解析它们（除非你打算做非常细粒度的步间干预）。
    *   **修改**：`_parse_progressive_cot_response` 只需提取 ````json ... ```` 块，其余部分全部作为 `thought` 字符串保存。

#### 2. 强化 S-I-O 的“锚点”属性
你沿用了 S-I-O（起-中-止）的图拓扑结构。为了体现“递进推理”，必须在 Prompt 中强调 **I节点（中间节点）的核心地位**。
*   **问题**：如果 S、I、O 平权识别，模型可能还是会“平行”地找实体。
*   **优化**：在 `get_cot_steps` 的 Step 1 中，明确指示：
    > "首先识别 **I(中间节点)**，这是图的核心（锚点）；然后基于 I 节点去寻找 S(起始) 和 O(终止) 节点。"
*   **效果**：这能更好地对齐人类“先找事件，再找时间地点”的认知逻辑。

#### 3. 动态 Prompt 的维护性
将大段的 Prompt 模板（`get_cot_steps`）写在 Python 类的方法里，会导致代码和提示词耦合，调试不便。
*   **建议**：
    *   在 `kg/prompts.py` 中定义一个基础模板 `STEP_BY_STEP_TEMPLATE`。
    *   `GraphStructure` 类只返回**变量字典**（如 `start_types`, `path_rules`）。
    *   在 Pipeline 中用 `TEMPLATE.format(**graph.get_cot_config())` 进行组装。
*   **好处**：改 Prompt 不需要重启服务或重新加载类，且代码更干净。

#### 4. 证据（Evidence）的强制传递
你在 Step 3 做了证据回溯，但在 Step 4 的 JSON 输出中，必须强制模型把 Step 3 找到的证据填进去。
*   **Prompt 补充**：
    > "【Step 4】... JSON中的 `evidence` 字段必须直接复制 Step 3 中找到的证据句。"

---

### ⚠️ 潜在风险预警

#### 2. 图结构分类错误（Error Propagation）
*   **风险**：如果 `get_graph_structure_for_text` 把一段“河流介绍”错误分类为“洪水事件”，后续的 CoT 就会强制模型去找“受灾人数”，导致严重的幻觉。
*   **对策**：
    *   增加一个 **`GeneralStructure` (通用图结构)** 作为兜底。
    *   如果分类置信度（confidence）低于某个阈值（如 0.6），强制降级为通用结构（只找实体，不强求特定路径）。

#### 3. 路径规则过死
*   **风险**：`get_path_rules` 如果写得太死（例如只允许 `Time -> occurs_at -> Event`），可能会漏掉一些灵活的表达（例如“事件发生于...”）。
*   **对策**：
    *   路径规则的描述要加上“例如”或“包括但不限于”，给 LLM 一定的泛化空间。

---

### 📝 优化后的代码片段参考

**1. 解耦后的 GraphStructure (kg/graph_structure.py)**

```python
class GraphStructure:
    # ... (初始化不变)

    def get_cot_config(self) -> dict:
        """只返回配置数据，不返回完整Prompt文本"""
        return {
            "s_types": ", ".join(self.start_types),
            "i_types": ", ".join(self.intermediate_types),
            "o_types": ", ".join(self.end_types),
            "path_rules": self._generate_path_rules_str(), # 内部方法生成字符串
            "valid_predicates": ", ".join(self.edge_types)
        }

    def _generate_path_rules_str(self) -> str:
        # ... 生成规则字符串逻辑 ...
        return rules_str
```

**2. 优化后的 Prompt 模板 (kg/prompts.py)**

```python
PROGRESSIVE_COT_TEMPLATE = """
... (前文省略) ...

【Step 1: 锚点与节点识别】
1. 首先识别核心锚点 **I(中间节点)**: [{i_types}]
2. 基于锚点，寻找 **S(起始节点)**: [{s_types}]
3. 基于锚点，寻找 **O(终止节点)**: [{o_types}]
▶ 输出：列出识别到的实体及其类型。

【Step 2: 路径驱动连接】
基于Step 1的实体，参考以下路径规则建立连接：
{path_rules}
▶ 输出：列出候选三元组 (S->I, I->O)。

【Step 3: 证据与逻辑校验】
对Step 2的候选三元组：
1. 原文证据：必须找到支撑句。
2. 谓词校验：必须在 [{valid_predicates}] 中。
▶ 输出：判定每条三元组是否保留。

【Step 4: JSON生成】
将Step 3保留的三元组转换为JSON，**务必包含evidence字段**。
"""
```

**3. Pipeline 调用 (kg/cq_pipeline.py)**

```python
# 获取配置
cot_config = graph_structure.get_cot_config()

# 组装 Prompt
prompt = P5_GRAPH_COT_EXTRACTION_PROMPT.format(
    graph_type=graph_structure.structure_type,
    schema_json=json.dumps(schema, ensure_ascii=False),
    input_text=paragraph,
    **cot_config  # 动态解包注入 s_types, path_rules 等
)
```

### 总结
你的计划**完全可行**。只要注意**不要过度解析中间步骤**，并处理好**图分类错误的兜底**，这套系统在论文和实际效果上都会非常出色。可以开始动手了！