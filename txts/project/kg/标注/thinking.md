## 关于标注

## 现在我缺少黄金标注，虽然在论文中最合适的做法和写法是说人工进行提取，但是我为了省时间准备用最强模型进行标注。 这个标注使用的Prompt是什么样的呢？是和我P5用的Prompt一样的吗（cot+后校验）？ 我在论文中应该怎么写？注意事项有哪些？

## 我想舍弃人工进行抽检的部分，完全由最强的模型负责标注，有哪些部分需要修改？ 注意事项有哪些？

## 这个Prompt中的schema部分需要使用经过cq增强和文献、法案增强以及去重后的schema吗？


# 黄金标注中Schema使用策略

## 核心结论

**建议：不使用完整的项目Schema，而是使用一个更宽泛的、与项目无关的关系类型列表**

## 一、原因分析

### 1.1 两种选择对比

| 维度 | 使用项目Schema | 使用宽泛关系列表 |
|------|----------------|------------------|
| **标注完整性** | ❌ 可能漏掉Schema未定义的关系 | ✅ 更完整，不受限制 |
| **评估公平性** | ❌ 标注被约束，对抽取系统有利 | ✅ 更客观，真正测试系统能力 |
| **关系匹配** | ✅ 直接匹配 | ⚠️ 需要后处理对齐 |
| **发现问题** | ❌ 无法发现Schema缺陷 | ✅ 可以发现Schema遗漏 |

### 1.2 关键问题

如果标注使用和P5抽取相同的Schema：

```
问题1：标注模型也被Schema约束
       → 可能漏掉重要但Schema未定义的关系
       → 评估结果虚高

问题2：评估变成"自我验证"
       → 你的Schema定义了什么，标注就只有什么
       → 无法发现Schema设计的问题

问题3：不公平对比
       → Baseline（如UIE）不使用你的Schema
       → 但评估数据是按你的Schema标的
```

---

## 二、推荐方案

### 2.1 标注Prompt（修改版）

```python
# ========== 黄金标注Prompt（不依赖项目Schema） ==========
GOLD_ANNOTATION_PROMPT_SCHEMA_FREE = """
你是一名专业的知识图谱标注专家。请从给定文本中穷尽式地抽取所有事实性三元组。

---

【核心约束】

1. subject 和 object 必须是原文的【精确子串】
2. 不可改写、推断或编造任何信息
3. 只标注文中明确陈述的事实

---

【关系类型参考】

请使用以下**通用关系类型**（可根据实际情况扩展）：

**时间关系**
- 发生时间、开始时间、结束时间、持续时间

**空间关系**
- 发生地点、影响区域、位于、流经、覆盖范围

**因果关系**
- 导致、造成、引发、触发、源于

**数值属性**
- 水位为、流量为、损失金额、受灾人口、死亡人数、面积为

**措施行动**
- 采取措施、启动响应、实施、执行、调度

**状态描述**
- 类型为、级别为、状态为、性质为

**组织关系**
- 负责、管辖、隶属于、参与

【注意】：上述只是参考，如果文中存在其他明确的关系，也请标注。
关系名称请使用**简洁的中文动词或动词短语**。

---

【输入文本】

{text}

---

【输出格式】

直接输出JSON：

```json
{{
  "triples": [
    {{
      "subject": "主语【原文子串】",
      "predicate": "关系类型",
      "object": "宾语【原文子串】",
      "evidence": "原文句子"
    }}
  ]
}}
```
"""
```

### 2.2 评估时的关系映射

由于标注使用通用关系，评估时需要将标注关系映射到你的Schema关系：

```python
# ========== 关系映射表 ==========
RELATION_MAPPING = {
    # 标注中的关系 -> 你Schema中的关系
    "发生时间": ["occurs_at", "has_time", "start_time"],
    "开始时间": ["occurs_at", "start_time"],
    "结束时间": ["end_time"],
    "发生地点": ["located_in", "affects_region", "occurs_in"],
    "影响区域": ["affects_region", "located_in"],
    "位于": ["located_in"],
    "导致": ["has_cause", "causes", "leads_to"],
    "造成": ["causes", "has_impact", "results_in"],
    "引发": ["triggers", "causes"],
    "水位为": ["water_level", "has_value"],
    "损失金额": ["economic_loss", "has_loss"],
    "受灾人口": ["affected_population", "has_impact"],
    "死亡人数": ["death_toll", "has_impact"],
    "采取措施": ["has_response", "takes_action"],
    "启动响应": ["triggers_response", "has_response"],
    # ... 更多映射
}

def map_predicate(gold_predicate: str, schema_relations: List[str]) -> str:
    """
    将标注的关系映射到Schema关系
    
    Args:
        gold_predicate: 标注中的关系
        schema_relations: Schema中定义的关系列表
        
    Returns:
        匹配的Schema关系，或原始关系
    """
    # 1. 精确匹配
    if gold_predicate in schema_relations:
        return gold_predicate
    
    # 2. 查映射表
    if gold_predicate in RELATION_MAPPING:
        for candidate in RELATION_MAPPING[gold_predicate]:
            if candidate in schema_relations:
                return candidate
    
    # 3. 模糊匹配（可选）
    # ...
    
    return gold_predicate  # 返回原始关系
```

### 2.3 评估指标调整

```python
def evaluate_extraction(
    predictions: List[Dict],
    gold_annotations: List[Dict],
    schema_relations: List[str],
    match_mode: str = "relaxed"  # "strict" 或 "relaxed"
) -> Dict:
    """
    评估抽取结果
    
    Args:
        predictions: 模型抽取结果
        gold_annotations: 黄金标注
        schema_relations: Schema中的关系列表
        match_mode: 
            - "strict": subject + predicate + object 都要匹配
            - "relaxed": subject + object 匹配即可（推荐）
    """
    
    if match_mode == "relaxed":
        # 宽松匹配：只比较 (subject, object) 对
        # 这是信息抽取领域常用的评估方式
        pred_pairs = {(t["subject"], t["object"]) for t in predictions}
        gold_pairs = {(t["subject"], t["object"]) for t in gold_annotations}
        
    else:  # strict
        # 严格匹配：需要关系映射
        pred_pairs = set()
        for t in predictions:
            pred_pairs.add((t["subject"], t["predicate"], t["object"]))
        
        gold_pairs = set()
        for t in gold_annotations:
            mapped_pred = map_predicate(t["predicate"], schema_relations)
            gold_pairs.add((t["subject"], mapped_pred, t["object"]))
    
    # 计算指标
    tp = len(pred_pairs & gold_pairs)
    precision = tp / len(pred_pairs) if pred_pairs else 0
    recall = tp / len(gold_pairs) if gold_pairs else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "match_mode": match_mode
    }
```

---

## 三、评估策略建议

### 3.1 两种评估方式

| 评估方式 | 说明 | 适用场景 |
|----------|------|----------|
| **实体对匹配** | 只比较(subject, object) | 主要评估方式，更公平 |
| **完整三元组匹配** | 比较(subject, predicate, object) | 辅助评估，需要关系映射 |

### 3.2 推荐的评估报告方式

```
表X：抽取性能评估结果

| 方法 | P(实体对) | R(实体对) | F1(实体对) | P(三元组) | R(三元组) | F1(三元组) | 幻觉率 |
|------|-----------|-----------|------------|-----------|-----------|------------|--------|
| UIE-Base | 72% | 58% | 64% | 65% | 52% | 58% | - |
| Direct-LLM | 70% | 85% | 77% | 62% | 75% | 68% | 18% |
| Ours | 88% | 80% | 84% | 82% | 75% | 78% | 4% |

注：实体对匹配只评估(subject, object)是否正确；三元组匹配同时评估关系类型
```

---

## 四、论文写作调整

### 4.1 评估方法描述

> **4.3 评估方法**
>
> 本文采用**两级评估策略**：
>
> （1）**实体对级别评估**：只考虑三元组的主语和宾语是否正确识别，不考虑关系类型。这是信息抽取领域的常用评估方式，能够更公平地比较不同方法的实体识别能力。
>
> （2）**三元组级别评估**：同时考虑主语、关系和宾语的正确性。由于不同方法可能使用不同的关系命名，本文构建了关系映射表进行标准化对齐。
>
> 评估数据集的构建不依赖特定的本体模式，使用通用的关系类型进行标注，以确保评估的客观性和公平性。

### 4.2 为什么不用项目Schema标注

可以在论文中这样解释（如果评审问到）：

> 为了确保评估的客观性，标注过程不使用本文提出的本体模式（Schema）。原因如下：（1）若使用相同Schema，标注模型也会受到Schema约束，导致评估结果偏向本文方法；（2）通用关系标注能够更全面地覆盖文本中的信息，便于发现Schema设计中可能存在的遗漏。

---

## 五、总结

| 问题 | 回答 |
|------|------|
| 标注时用项目Schema吗？ | **不用**，使用通用关系类型列表 |
| 评估怎么处理关系不一致？ | 构建映射表 或 只评估实体对 |
| 论文怎么写？ | 强调"两级评估"和"客观性" |
| 主要评估指标？ | **实体对F1**（主要）+ 三元组F1（辅助）|

**核心原则**：标注要独立于你的系统设计，这样评估才客观公正。
