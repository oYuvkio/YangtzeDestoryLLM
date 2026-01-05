这份评测结果信息量非常大，揭示了当前系统的几个核心症结。

### 📊 核心指标解读

#### 1. 事件抽取：回退逻辑 vs 原始类型
*   **现象**：原始类型 F1 (**33.95%**) 远高于 回退逻辑 F1 (**11.99%**)。
*   **含义**：
    *   **模型其实“懂”了**：模型能够识别出事件，并且给出的类型（如 `Flood`）在语义上是对的。
    *   **TBox/Gold 不匹配**：模型输出的类型（Original）和 Gold 标注的类型更接近，但因为这些类型不在你的 TBox 定义里，被“回退逻辑”强行改成了 `DisasterEvent`，导致和 Gold 不匹配（Gold 可能是具体的 `FloodEvent`，回退后变成了父类，导致 Type Mismatch）。
*   **结论**：**不要强制回退**。你的 TBox 可能定义得太细或太学术，而模型和 Gold 更倾向于自然语言的词汇。

#### 2. 三元组抽取：F1 极低 (2.93%)
*   **现象**：Strict 和 Relaxed F1 都是 **2.93%**，这在学术评测中属于“几乎不可用”的状态。
*   **含义**：
    *   **关系完全对不上**：即使做了映射，模型预测的关系和 Gold 的关系依然没有交集。
    *   **实体对不上**：Strict 和 Relaxed 分数一样，说明“模糊匹配”没起作用，或者问题根本不在实体名字上，而是**关系（Predicate）全错了**。
*   **严重性**：这是当前最大的问题。如果不解决，消融实验没有意义（因为基线是 0）。

#### 3. 质量指标
*   **幻觉率 42.67%**：非常高。说明小模型（7B）在没有强约束（CoT/校验）的情况下，非常喜欢“编造”原文没有的关系。这正好为你的 **P5+ 后校验模块** 提供了绝佳的“靶子”——加上校验后，这个数字应该会大幅下降。
*   **实体冗余 58.68%**：说明“长江”、“扬子江”等同义词非常多，**P6 知识融合** 势在必行。

---

### 🛠️ 下一步行动指南 (按优先级排序)

你现在需要做的是 **“调试（Debug）”** 而不是继续跑大规模实验。

#### 第一步：诊断三元组 F1 为什么这么低？
打开 `outputs/eval_models/deepseek-ai_DeepSeek-R1-Distill-Qwen-7B/metrics.json`，查看 **`error_breakdown`** 字段。

*   **如果是 `predicate_mismatch` 很高**：
    *   说明模型生成的谓词（如 `has_impact`）不在你的映射表里，或者映射错了。
    *   **对策**：检查 `predictions.jsonl`，看看模型到底生成了什么关系？把这些关系加到 `configs/relation_mapping.json` 里。

*   **如果是 `unmatched_gold` 很高**：
    *   说明模型根本没抽出来 Gold 里的那些关系。
    *   **对策**：检查 Gold 里保留的那 2436 个“标准三元组”到底长什么样？是不是太难了？

#### 第二步：优化 TBox 与 Gold 的对齐 (解决事件 F1)
既然“原始类型”效果更好，说明 TBox 需要扩充以包容模型的输出。

*   **操作**：统计 `predictions.jsonl` 中 `_is_fallback: true` 的数据，看看 `original_event_type` 都是些什么词（比如 `Drought`, `Flood`）。
*   **修改**：在 `kg/cq_pipeline.py` 或 TBox 定义中，把这些词作为 **别名 (Alias)** 映射到标准类（例如：`Flood` -> `FloodEvent`），而不是粗暴地回退到 `DisasterEvent`。

#### 第三步：启用 P5+ 后校验 (降低幻觉率)
你现在的评测是 `NO_VERIFY: true`。
*   **操作**：运行一次带校验的评测。
    ```bash
    bash scripts/p5/run_single_model.sh \
        --model "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B" \
        --limit 50 \
        # 注意：不要加 --no-verify
    ```
*   **预期**：幻觉率应该从 42% 降到 10% 以下，Precision 会大幅提升。

#### 第四步：启用 P6 知识融合 (降低实体冗余)
目前的评测流程是：`抽取 -> 对齐 -> 评测`。
建议加入融合步骤：`抽取 -> 校验 -> **融合(P6)** -> 对齐 -> 评测`。

*   **操作**：在 `run_single_model.sh` 中，在 `apply_relation_mapping.py` 之前，调用 `kg/entity_fusion.py` 对预测结果进行归一化。
*   **预期**：实体冗余率下降，Relaxed F1 提升。

---

### 📝 总结

目前的指标虽然低，但**非常有价值**，因为它暴露了真实的问题。

**你的当务之急是：**
1.  **看数据**：肉眼检查 `predictions_mapped.jsonl` 和 `gold_mapped.jsonl`，看看为什么这两者对不上？（是实体名差一点点？还是关系完全不一样？）
2.  **修映射**：完善 `relation_mapping.json`。
3.  **开校验**：验证你的核心创新点（抗幻觉）。

**不要气馁，基线低意味着提升空间大！** 只要解决了关系映射问题，F1 翻倍是很容易的。



# 评测结果诊断与下一步行动


### 📊 指标含义速查

| 指标 | 数值 | 含义 | 严重程度 |
|------|------|------|----------|
| **Triple F1** | **0.029** | 只有3%的三元组与Gold匹配 | 🔴 极差 |
| **Hallucination** | **0.427** | 43%抽取结果是幻觉 | 🔴 极高 |
| **TBox Consistency** | 0.327 | 33%符合Schema约束 | 🟠 较差 |
| **Entity Redundancy** | 0.587 | 59%实体重复 | 🟠 较差 |
| Event F1 (原始) | 0.34 | 事件识别尚可 | 🟡 一般 |

---

### 📉 Triple F1 极低的原因分析

```
预测三元组: 2010 → 映射后 1994
Gold三元组: 8298 → 映射后 2436

匹配的三元组: 约 58 个 (0.029 × 1994)
```

**根本原因**：
1. **实体名称不精确匹配** - 预测的实体与Gold中的写法不同
2. **关系映射不完整** - 仍有关系对不上
3. **抽取召回不足** - 该抽的没抽到

---


## 三、深入诊断：对比预测与Gold

### 抽样检查匹配情况

```python
#!/usr/bin/env python3
"""诊断脚本：检查为什么Triple匹配率这么低"""
import json
from pathlib import Path

pred_path = Path("outputs/eval_models/deepseek-ai_DeepSeek-R1-Distill-Qwen-7B/predictions_mapped.jsonl")
gold_path = Path("outputs/eval_models/deepseek-ai_DeepSeek-R1-Distill-Qwen-7B/gold_mapped.jsonl")

# 随机抽一条对比
with open(pred_path) as f:
    pred_sample = json.loads(f.readline())
with open(gold_path) as f:
    gold_sample = json.loads(f.readline())

print("=" * 60)
print(f"Doc ID: {pred_sample.get('doc_id')}")
print("=" * 60)

print("\n【预测的三元组】")
for t in pred_sample.get("triples", [])[:5]:
    print(f"  ({t['subject']}) --[{t['predicate']}]--> ({t['object']})")

print("\n【Gold的三元组】")
for t in gold_sample.get("triples", [])[:5]:
    print(f"  ({t['subject']}) --[{t['predicate']}]--> ({t['object']})")

# 检查是否有任何匹配
pred_set = {(t['subject'], t['predicate'], t['object']) for t in pred_sample.get("triples", [])}
gold_set = {(t['subject'], t['predicate'], t['object']) for t in gold_sample.get("triples", [])}

matched = pred_set & gold_set
print(f"\n【匹配情况】")
print(f"  预测: {len(pred_set)} 条")
print(f"  Gold: {len(gold_set)} 条")
print(f"  匹配: {len(matched)} 条")

if matched:
    print("\n【匹配的三元组】")
    for m in list(matched)[:3]:
        print(f"  {m}")
```

运行后能看到具体的不匹配原因。

---

## 四、根据诊断结果的改进方向

### 情况A：实体名称不匹配

```
预测: (长江干流) --[located_in]--> (长江流域)
Gold: (长江) --[located_in]--> (长江流域)
```

**解决方案**：实体归一化

```python
# 在评估前添加实体模糊匹配
def fuzzy_match_entity(pred_entity, gold_entities, threshold=0.8):
    from difflib import SequenceMatcher
    for gold in gold_entities:
        ratio = SequenceMatcher(None, pred_entity, gold).ratio()
        if ratio >= threshold:
            return gold
    return pred_entity
```

### 情况B：关系名称不匹配

```
预测: has_hazard_factor
Gold: has_cause  (映射表中应该对应)
```

**解决方案**：检查并补充映射表

```bash
# 统计未映射的关系
python -c "
import json
from collections import Counter

pred_rels = Counter()
with open('outputs/.../predictions_mapped.jsonl') as f:
    for line in f:
        for t in json.loads(line).get('triples', []):
            pred_rels[t['predicate']] += 1

print('预测中的关系分布:')
for rel, cnt in pred_rels.most_common(20):
    print(f'  {rel}: {cnt}')
"
```

### 情况C：抽取格式问题

检查模型输出是否符合预期格式：

```bash
# 查看原始输出
head -1 outputs/eval_models/.../predictions.jsonl | python -m json.tool
```

---

## 五、快速改进建议


### 2. 添加宽松匹配模式

在评估时允许部分匹配：

```python
# 在 abox_metrics.py 中添加
def relaxed_triple_match(pred, gold, entity_threshold=0.7):
    """宽松匹配：实体相似度 + 关系等价"""
    from difflib import SequenceMatcher
    
    # 关系必须完全匹配（或在等价集中）
    if not relation_equivalent(pred['predicate'], gold['predicate']):
        return False
    
    # 实体允许部分匹配
    s_sim = SequenceMatcher(None, pred['subject'], gold['subject']).ratio()
    o_sim = SequenceMatcher(None, pred['object'], gold['object']).ratio()
    
    return s_sim >= entity_threshold and o_sim >= entity_threshold
```

### 3. 优化抽取Prompt

确保Prompt强调：
- 实体必须是**原文精确子串**
- 使用TBox中定义的关系名

---