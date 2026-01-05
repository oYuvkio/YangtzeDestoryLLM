# 关于标注

## 现在我缺少黄金标注，虽然在论文中最合适的做法和写法是说人工进行提取，但是我为了省时间准备用最强模型进行标注。 这个标注使用的Prompt是什么样的呢？是和我P5用的Prompt一样的吗（cot+后校验）？ 我在论文中应该怎么写？注意事项有哪些？

## 我想舍弃人工进行抽检的部分，完全由最强的模型负责标注，有哪些部分需要修改？ 注意事项有哪些？

## 这个Prompt中的schema部分需要使用经过cq增强和文献、法案增强以及去重后的schema吗？



# Schema选择问题分析

## 一、核心问题

您的问题是：**黄金标注Prompt中是否应该使用最终的Schema（经过CQ增强+文献增强+去重后的）？**

## 二、结论

**答：不建议使用。黄金标注Prompt应该使用更通用的、预定义的关系类型，而非您系统生成的Schema。**

## 三、原因分析

### 3.1 使用最终Schema的问题

| 问题 | 说明 |
|-----|-----|
| **循环依赖** | 您的Schema是通过CQ+文献生成的，用它来标注评测集，再用评测集评估抽取效果，存在逻辑循环 |
| **评估偏差** | 如果标注Prompt使用的Schema和抽取Prompt完全一致，评测会偏向有利于您的系统 |
| **泛化性差** | 无法验证您的方法在"未见过的关系类型"上的表现 |
| **Schema过拟合** | 您的Schema可能有缺陷（如关系定义不完整），标注数据也会继承这些缺陷 |

### 3.2 正确的做法

**使用独立的、更通用的关系类型列表作为标注Schema**

这样做的好处：
1. **评估更公平**：标注数据与系统Schema独立
2. **发现Schema问题**：如果标注数据中有关系类型是您Schema未覆盖的，说明Schema需要扩展
3. **符合学术规范**：评测集应该独立于被评测系统

---

## 四、修改后的Prompt

```python
# 在 prompts.py 中修改

GOLD_ANNOTATION_PROMPT_V2 = """
你是一名资深的水旱灾害领域知识图谱标注专家。你的任务是为给定文本生成**高质量的黄金标准标注**。

---

【标注原则】

1. **完整性**：尽可能抽取所有有意义的实体和关系
2. **准确性**：所有标注必须有原文依据，实体必须是原文的**精确子串**
3. **规范性**：严格遵循输出格式要求

---

【待标注文本】

{text}

---

【预定义实体类型】

请识别以下类型的实体：
- TIME：时间表达（年份、日期、时间段，如"1998年8月"、"7月至9月"）
- LOCATION：地理位置（省市、河流、湖泊、水库、水文站点，如"长江中下游"、"沙市站"）
- EVENT：灾害事件名称（如"1998年长江特大洪水"）
- VALUE：数值指标（水位、流量、损失数据，如"45.22米"、"2.23亿人"）
- CAUSE：致灾因子（如"持续性强降雨"、"上游来水偏多"）
- MEASURE：应急措施/响应（如"启动防汛II级应急响应"、"启用分洪区"）
- FACILITY：水利工程设施（如"三峡水库"、"荆江分洪区"）
- ORG：机构组织（如"国家防总"、"水利部"）
- IMPACT：灾害影响描述（如"倒塌房屋680万间"）

---

【预定义关系类型】

请识别实体间的以下关系：

| 关系名称 | 中文含义 | 主语类型 | 宾语类型 | 示例 |
|---------|---------|---------|---------|------|
| occurs_at | 发生于（时间） | EVENT | TIME | 1998年长江洪水 - occurs_at - 1998年 |
| located_in | 位于/发生地点 | EVENT/FACILITY | LOCATION | 沙市站 - located_in - 长江干流 |
| has_cause | 由...引起 | EVENT | CAUSE | 洪水 - has_cause - 强降雨 |
| causes_impact | 造成影响 | EVENT | IMPACT/VALUE | 洪水 - causes_impact - 死亡4150人 |
| has_value | 测量值为 | FACILITY/LOCATION | VALUE | 沙市站 - has_value - 水位45.22米 |
| triggers | 触发 | EVENT/VALUE | MEASURE | 超警戒水位 - triggers - 启动应急响应 |
| implements | 实施/采取 | ORG | MEASURE | 国家防总 - implements - 启动I级响应 |
| part_of | 属于/包含于 | LOCATION | LOCATION | 洞庭湖 - part_of - 长江流域 |
| affects | 影响/波及 | EVENT | LOCATION | 洪水 - affects - 湖北省 |

**注意**：如果文中存在上表未列出但明确表达的关系，可以自定义关系名（使用英文下划线格式），但需在annotation_notes中说明。

---

【标注步骤】

**Step 1: 实体识别**
逐句阅读文本，识别所有符合上述类型的实体。
注意：实体必须是原文的**精确子串**，不可改写。

**Step 2: 关系抽取**
对于识别出的实体对，判断它们之间是否存在上述预定义关系。
只标注**原文明确表达**的关系，不要推断。

**Step 3: 自我校验**【必须执行】
对每个三元组检查：
- subject是否在原文中原样出现？
- object是否在原文中原样出现？
- 原文是否明确支持这个关系？

如果任一检查不通过，请**删除**该三元组。

---

【输出格式】

```json
{{
  "entities": [
    {{"name": "实体名（原文子串）", "type": "实体类型"}}
  ],
  "triples": [
    {{
      "subject": "主语（原文子串）",
      "subject_type": "主语类型",
      "predicate": "关系类型",
      "object": "宾语（原文子串）",
      "object_type": "宾语类型",
      "evidence": "原文支撑句",
      "confidence": "high/medium/low"
    }}
  ],
  "events": [
    {{
      "name": "事件名称",
      "type": "FloodEvent/DroughtEvent/Other",
      "time": "时间",
      "location": "地点"
    }}
  ],
  "annotation_notes": "标注备注（如自定义关系说明、不确定之处等）"
}}
```

**置信度说明**：
- high：关系在原文中直接、明确表述
- medium：关系需要简单推理但有明确依据
- low：关系较隐含或不太确定

请直接输出JSON，不要添加其他内容：
"""
```

---

## 五、标注Schema vs 抽取Schema的关系

### 5.1 两个Schema的设计思路

```
【标注Schema】（通用、固定）
├── 关系类型：预定义的9-10种通用关系
├── 实体类型：预定义的9种通用类型
├── 设计目标：覆盖领域内常见的知识结构
└── 特点：稳定、独立、通用

【抽取Schema】（您系统生成的）
├── 关系类型：CQ + 文献增强生成的具体关系
├── 实体类型：动态生成，可能更细粒度
├── 设计目标：适配您的特定应用场景
└── 特点：动态、依赖数据、可能更细或更粗
```

### 5.2 评估时的映射

在评估时，需要将**抽取结果的Schema**映射到**标注Schema**进行对比：

```python
# 关系映射示例
SCHEMA_MAPPING = {
    # 抽取Schema -> 标注Schema
    "has_cause": "has_cause",
    "caused_by": "has_cause",  # 反向关系归一化
    "affects_region": "affects",
    "occurs_at_time": "occurs_at",
    "occurs_at_location": "located_in",
    "triggers_response": "triggers",
    "has_impact": "causes_impact",
    # ... 更多映射
}

def map_predicate(extracted_predicate: str) -> str:
    """将抽取的关系映射到标注Schema"""
    return SCHEMA_MAPPING.get(extracted_predicate, extracted_predicate)
```

### 5.3 评估指标计算

```python
def evaluate_with_mapping(predictions: List[Dict], gold: List[Dict]) -> Dict:
    """
    带映射的评估
    
    1. 先将predictions中的predicate映射到标注Schema
    2. 再计算P/R/F1
    """
    # 映射预测结果
    mapped_predictions = []
    for p in predictions:
        mapped_p = p.copy()
        mapped_p['predicate'] = map_predicate(p['predicate'])
        mapped_predictions.append(mapped_p)
    
    # 计算指标
    # ... (常规的P/R/F1计算)
```

---

## 六、完整的评估流程

```
1. 标注阶段（使用通用Schema）
   └── GPT-4o + 预定义的9种关系类型
   
2. 抽取阶段（使用您的Schema）
   └── DeepSeek + CQ增强+文献增强后的Schema
   
3. 评估阶段（映射后对比）
   ├── 将抽取结果的predicate映射到标注Schema
   ├── 计算 Precision / Recall / F1
   └── 分析未覆盖的关系类型（发现Schema问题）
```

---

## 七、论文中的相关表述

```
4.2.2 自动化标注方法

...

需要说明的是，为确保评测的公平性和独立性，标注过程使用的实体类型和关系类型
是预先定义的通用类别（见表4-2），而非本文方法生成的Schema。这样设计的目的是：
（1）避免评测数据与被评测系统之间的循环依赖；
（2）验证本文方法对预定义Schema之外关系的泛化能力。

在评估时，通过关系映射表（见附录A）将抽取结果的关系类型对齐到标注Schema，
再进行指标计算。
```

---

## 八、总结

| 问题 | 答案 |
|-----|-----|
| 标注Prompt用什么Schema？ | **使用预定义的通用Schema，不用您系统生成的** |
| 为什么？ | 避免循环依赖、保证评估公平、发现Schema问题 |
| 评估时怎么办？ | 通过映射表将抽取Schema对齐到标注Schema |
| 代码改动 | 修改Prompt中的关系类型列表为固定的通用列表 |

### 关键要点

1. **标注Schema = 固定的、预定义的通用关系类型**
2. **抽取Schema = 您系统动态生成的Schema**
3. **评估时 = 映射后对比**
4. **好处 = 公平评估 + 发现Schema覆盖问题**