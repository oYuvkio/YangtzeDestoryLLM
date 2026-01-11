# 您的方案与论文方法对比分析

## 一、整体对比

| 维度           | 论文方法（煤矿事故）                        | 您的方法（水旱灾害）                   | 评价                       |
| -------------- | ------------------------------------------- | -------------------------------------- | -------------------------- |
| **本体构建**   | LLM挖掘 + K-means聚类 + Dice合并 + 行业规范 | 专家骨架 + LLM聚类 + 支持度/置信度筛选 | ✅ 您的更完善（有专家锚点） |
| **图结构设计** | 按文本结构分3类固定模板                     | 按灾害类型分5类动态检测                | ✅ 您的更灵活               |
| **图结构粒度** | 细粒度（Subject→Intermediate→Object固定）   | 路径模式（多条路径组合）               | ⚠️ 各有优劣                 |
| **数据标注**   | 少样本人工标注 + 微调                       | 强模型自动标注Gold                     | ✅ 您的成本更低             |
| **抽取方式**   | 图结构Prompt + 微调LLM                      | 图结构Prompt + CoT + 后校验            | ✅ 您的更适合零样本         |

---

## 二、论文的亮点（可借鉴）

### 2.1 按文本结构分类图结构

论文将文本按**结构功能**分为3类，每类有固定的图结构：

| 文本类型      | 图结构特点               | 示例                                 |
| ------------- | ------------------------ | ------------------------------------ |
| 事故概述/原因 | 一对多（起始→多个终止）  | XX煤矿 → 时间/地点/事故类型/死亡人数 |
| 事故单位情况  | 链式（起始→中间→终止）   | 煤矿 → 证照 → 有效期                 |
| 事故发生经过  | 时序链（时间→人员→行动） | 时间点 → 人员 → 业务/设备            |

**启发**：您可以考虑对水旱灾害文本做更细的结构分类。

### 2.2 显式的节点角色标注

论文在Prompt中使用显式标签：
```
SUBJECT_1, INTERMEDIATE_1, OBJECT_1, OBJECT_2, ...
```

**启发**：您的CoT步骤可以更显式地要求LLM标注节点角色。

---

## 三、您的方案优势

| 优势             | 说明                                           |
| ---------------- | ---------------------------------------------- |
| **专家骨架锚点** | 论文完全依赖聚类，您有专家预定义保证核心覆盖   |
| **动态类型检测** | 论文按文档结构固定分类，您按内容自动检测更灵活 |
| **双重校验机制** | 论文无后校验，您有原文回溯+Schema校验降低幻觉  |
| **无需微调**     | 论文需要微调LLM，您的方案零样本即可工作        |

---

## 四、建议改进点

### 4.1 图结构可以更细化（可选）

当前您的5种图结构按**灾害类型**分类，可以考虑增加按**文本功能**的子分类：

```python
# 当前：按灾害类型
flood_event, drought_event, dispatch_rule, impact_statistics, general_disaster

# 可选增强：按文本功能细分
flood_event_overview    # 洪水概述（一对多）
flood_event_process     # 洪水过程（时序链）
flood_event_response    # 应急响应（链式）
```

**但这会增加复杂度，建议先用当前方案验证效果，再决定是否细化。**

### 4.2 CoT步骤可以更显式（推荐）

参考论文的显式标签，在CoT步骤中增加节点角色标注：

```python
# 当前的CoT步骤
Step1: 识别实体
Step2: 连接关系
Step3: 证据回溯

# 建议增强
Step1: 识别实体并标注角色
  - 起始节点(S): Time, HazardFactor, ...
  - 中间节点(I): FloodEvent, Facility, ...
  - 终止节点(O): Impact, Value, ...
Step2: 按路径模式连接 (S→关系→I, I→关系→O)
Step3: 证据回溯
```

### 4.3 Prompt模板优化（推荐）

参考论文的target格式，在Prompt中更清晰地展示图结构：

```python
# 当前格式
路径: Time → occurs_during → FloodEvent

# 建议增强格式
路径: [起始:Time] --occurs_during--> [中间:FloodEvent]
      [中间:FloodEvent] --causes_impact--> [终止:Impact]
```

---

## 五、具体代码修改建议

### 5.1 增强CoT步骤生成

```python
# graph_structure.py 中的 get_cot_steps() 方法

def get_cot_steps(self) -> List[str]:
    steps = []
  
    # Step 1: 增强版节点识别
    node_lines = []
    role_labels = {"subject": "S(起始)", "intermediate": "I(中间)", "object": "O(终止)"}
    for role, node in self.nodes.items():
        label = role_labels.get(role, role)
        types = ", ".join(node.entity_types[:4])
        node_lines.append(f"  - **{label}**: {types}")
  
    steps.append(f"""**Step 1: 识别实体并标注角色**

按以下角色分类识别文本中的实体：
{chr(10).join(node_lines)}

【输出格式】
- S1: "1998年8月" (Time)
- I1: "长江特大洪水" (FloodEvent)
- O1: "100万人受灾" (Impact)

【自检】实体是否原样保留？角色是否正确？""")
  
    # Step 2: 路径连接（保持不变）
    # Step 3: 证据回溯（保持不变）
  
    return steps
```

### 5.2 增强Prompt中的图结构展示

```python
# graph_structure.py 中的 format_for_prompt() 方法

def format_for_prompt(self) -> str:
    lines = [
        f"**文本类型**: {self.name}",
        "",
        "**图结构角色**:",
        "```",
        "[S:起始] ──关系──→ [I:中间] ──关系──→ [O:终止]",
        "```",
        ""
    ]
  
    # 节点角色
    role_labels = {"subject": "起始(S)", "intermediate": "中间(I)", "object": "终止(O)"}
    lines.append("**节点类型**:")
    for role, node in self.nodes.items():
        label = role_labels.get(role, role)
        types = ", ".join(node.entity_types[:4])
        lines.append(f"- **{label}**: {types}")
    lines.append("")
  
    # 路径模式
    lines.append("**抽取路径**:")
    for i, p in enumerate(self.paths[:6], 1):
        # 添加角色标注
        pattern_with_role = self._add_role_to_pattern(p.pattern)
        lines.append(f"{i}. {pattern_with_role}")
        lines.append(f"   提示: {p.extraction_hint}")
  
    return "\n".join(lines)

def _add_role_to_pattern(self, pattern: str) -> str:
    """为路径添加角色标注"""
    # Time → occurs_during → FloodEvent
    # 变为 [S:Time] → occurs_during → [I:FloodEvent]
    parts = pattern.split(" → ")
    if len(parts) == 3:
        s, r, o = parts
        s_role = self._get_role(s)
        o_role = self._get_role(o)
        return f"[{s_role}:{s}] → {r} → [{o_role}:{o}]"
    return pattern

def _get_role(self, entity_type: str) -> str:
    """获取实体类型的角色"""
    for role, node in self.nodes.items():
        if entity_type in node.entity_types:
            return {"subject": "S", "intermediate": "I", "object": "O"}.get(role, "?")
    return "?"
```

---

## 六、总结

| 方面          | 当前状态  | 建议                   | 优先级 |
| ------------- | --------- | ---------------------- | ------ |
| 本体构建      | ✅ 完善    | 保持现状               | -      |
| 图结构分类    | ✅ 5种类型 | 先验证效果，再考虑细化 | 低     |
| CoT步骤       | ⚠️ 可增强  | 增加显式角色标注       | **中** |
| Prompt格式    | ⚠️ 可增强  | 增加角色标签展示       | **中** |
| 后校验        | ✅ 完善    | 保持现状               | -      |
| Gold/Pred模式 | ⚠️ 需修改  | Gold严格，Pred宽松     | **高** |

**建议执行顺序**：
1. 先修改Gold/Pred的严格模式配置
2. 增强CoT步骤的角色标注
3. 运行实验验证效果
4. 根据结果决定是否细化图结构