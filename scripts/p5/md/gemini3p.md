### 1. 关于“回退逻辑”的解答

**现象**：
日志中出现了 `[P5] 发现不在 TBox 中的 event_type: 1 个，已回退为 DisasterEvent`。

**原因**：
这是你在 `CQLLMPipeline._sanitize_p5_result` 方法中写的一段**兜底逻辑（Fallback Logic）**。
*   **代码位置**：`kg/cq_pipeline.py`
*   **逻辑**：当 LLM 抽取的 `event_type`（例如 "Flood"）不在你的 TBox 定义的类列表（例如 `FloodEvent`）中时，为了不直接丢弃这个事件，代码会自动把它归类为最通用的父类（通常是列表中的第一个类，或者硬编码的 `DisasterEvent`）。

**对实验的影响**：
1.  **正面影响（Recall 保护）**：防止因为 LLM 输出的小瑕疵（比如少写了 "Event" 后缀）导致整个事件被丢弃，从而保护了召回率（Recall）。
2.  **负面影响（Precision 下降）**：如果 LLM 真的瞎编了一个类型，回退到 `DisasterEvent` 虽然保住了事件，但在细粒度分类上是错的。
    *   在 `abox_metrics.py` 计算 `event_f1` 时，如果 Gold 是 `FloodEvent`，而 Pred 回退成了 `DisasterEvent`，会被判为 **Type Mismatch**（类型不匹配），导致 F1 下降。
    *   **证据**：你的 `metrics.json` 显示 `type_mismatch: 3`，说明有 3 个事件虽然找对了，但类型没对上。

**建议**：
保留这个逻辑，但在 Prompt 中加强约束（`class_usage_hint`），让 LLM 尽量输出准确的类名，减少回退的发生。

---

### 2. 关于“评测指标”的补充建议

目前的 `metrics.json` 确实只有 F1，这在学术论文中略显单薄。标准的知识抽取（IE）或知识图谱构建（KGC）论文通常会报告以下指标：

#### 核心指标 (Core Metrics)
1.  **Precision (精确率)**：$P = \frac{TP}{TP + FP}$
    *   含义：抽出来的东西里，有多少是对的？（衡量抗幻觉能力）
2.  **Recall (召回率)**：$R = \frac{TP}{TP + FN}$
    *   含义：该抽的东西里，抽出了多少？（衡量覆盖能力）
3.  **F1-Score**：$F1 = \frac{2 \cdot P \cdot R}{P + R}$
    *   含义：P 和 R 的调和平均。

#### 进阶指标 (Advanced Metrics) - 建议补充！
4.  **Hallucination Rate (幻觉率)**：
    *   定义：$\frac{\text{Pred中无法在原文找到依据的三元组数}}{\text{Pred总三元组数}}$
    *   **重要性**：这是你论文的核心卖点（P5+ 校验）。必须单独列出，证明你的方法比 Baseline 低。
5.  **Entity Redundancy Rate (实体冗余率)**：
    *   定义：$\frac{\text{融合前实体数} - \text{融合后实体数}}{\text{融合前实体数}}$
    *   **重要性**：证明 P6（知识融合）的有效性。
6.  **TBox Consistency (Schema 一致性)**：
    *   定义：$\frac{\text{符合 TBox 约束的三元组数}}{\text{Pred 总三元组数}}$
    *   **重要性**：证明你的方法生成的图谱是规范的，不是乱生成的。

#### 修改建议
你需要修改 `tools/abox_metrics.py`，在输出 JSON 中增加 P 和 R 的计算。

**修改代码片段示例：**

```python
def calculate_f1(matched, pred_total, gold_total):
    p = matched / pred_total if pred_total > 0 else 0.0
    r = matched / gold_total if gold_total > 0 else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return p, r, f1

# 在 main 函数最后：
event_p, event_r, event_f1 = calculate_f1(event_matched, event_pred_total, event_gold_total)
triple_p, triple_r, triple_f1 = calculate_f1(triple_matched, triple_pred_total, triple_gold_total)

output = {
    "event_metrics": {"precision": event_p, "recall": event_r, "f1": event_f1},
    "triple_metrics": {"precision": triple_p, "recall": triple_r, "f1": triple_f1},
    # ... 其他保持不变
}
```

---

### 3. 针对你当前运行结果的紧急诊断

你的 `metrics.json` 显示：
*   `triple_f1_strict`: **0.0**
*   `triple_f1_relaxed`: **0.0**
*   `predicate_mismatch`: **33** (所有预测的三元组关系都错了)
*   `unmatched_gold`: **8298** (漏抽了绝大部分)

**严重问题**：
你的小模型（DeepSeek-R1-Distill）生成的预测结果中，关系（Predicate）完全没有命中 Gold 的标准。
*   **原因**：Gold 数据里用的是 `has_value`, `located_in` 等关系，而你的 TBox 里可能定义的是中文名（如 `位于`）或者其他英文名。
*   **解决**：**必须立刻运行 `analyze_schema_drift.py`**，生成映射表，并在评测前应用映射。否则你的 F1 永远是 0。

**行动清单**：
1.  跑 `python scripts/p5/analyze_schema_drift.py ...`
2.  看输出，写 `configs/relation_mapping.json`。
3.  修改 `run_model_comparison.sh`，加入 `apply_relation_mapping.py` 步骤。
4.  重跑评测。
   


这是一个**非常有实验价值**的想法，但在具体实现上，**“写两份到同一个列表”**（即在同一个 `events` 列表中同时包含原始事件和回退事件）是**不推荐**的，因为这会导致严重的**重复计算（Double Counting）**问题。

### ❌ 为什么不能在同一个列表中写两份？

假设 Gold 标准中只有一个事件：`FloodEvent`。
如果你的预测结果里写了两份：
1.  `{"event_type": "Flood", ...}` (原始)
2.  `{"event_type": "FloodEvent", ...}` (回退后)

**评测脚本会这样判分：**
*   第 2 个匹配成功 -> **TP + 1**
*   第 1 个匹配失败（或被视为多余） -> **FP + 1** (误报)

**结果**：你的 Precision 会被腰斩，F1 值会大幅下降。这无法反映真实性能。

---

### ✅ 最佳实践方案：单文件存储，双模式评测

最科学的做法是：**在抽取结果中保留两个字段，但在评测时通过参数选择用哪个字段去计算。**

这样你只需要跑一次抽取（省钱省时），然后跑两次评测脚本（瞬间完成），就能得到两组 F1 值进行对比。

#### 1. 修改抽取逻辑 (`kg/cq_pipeline.py`)

确保 `_sanitize_p5_result` 方法始终保存两个字段：
*   `event_type`: 存放**回退后**的类型（符合 TBox，用于默认评测）。
*   `original_event_type`: 存放**LLM 原始输出**（用于分析或原始评测）。

```python
# kg/cq_pipeline.py

    def _sanitize_p5_result(self, res: Any, schema: TBoxSchema) -> Dict[str, Any]:
        # ...
        for event_item in events:
            # ...
            raw_type = ev.get("event_type", "")
            
            # 1. 始终保存原始类型
            ev["original_event_type"] = raw_type 

            # 2. 处理回退逻辑 (存入 event_type)
            if allowed_event_types and raw_type not in allowed_event_types:
                ev["event_type"] = fallback_event_type or raw_type
                ev["_is_fallback"] = True
            else:
                ev["event_type"] = raw_type # 如果没问题，两个字段一样
                ev["_is_fallback"] = False
            
            cleaned_events.append(ev)
        # ...
```

#### 2. 修改评测脚本 (`tools/abox_metrics.py`)

增加一个开关 `--use-original-type`，控制评测时取哪个字段。

```python
# tools/abox_metrics.py

def main():
    parser = argparse.ArgumentParser(...)
    # [新增参数]
    parser.add_argument("--use-original-type", action="store_true", 
                        help="使用 LLM 原始输出的类型进行评测（忽略回退逻辑）")
    args = parser.parse_args()

    # ... 在加载预测结果的循环中 ...
    
    for pred_item in pred_data:
        # ...
        pred_events = []
        for ev in pred_item.get("events", []):
            # [核心修改] 根据参数选择使用哪个字段
            if args.use_original_type:
                e_type = ev.get("original_event_type", ev.get("event_type"))
            else:
                e_type = ev.get("event_type")
            
            # 构造用于评测的对象
            pred_events.append({
                "event_type": e_type,
                "time": ev.get("time"),
                "space": ev.get("space"),
                # ... 其他字段
            })
```

#### 3. 运行对比实验

现在你可以通过两条命令得到对比结果：

**实验 A：使用回退逻辑（默认，Standard）**
```bash
python tools/abox_metrics.py \
    --gold data/test_final.jsonl \
    --pred outputs/predictions_aligned.jsonl \
    --tbox outputs/tbox_final.json \
    --out outputs/metrics_fallback.json
```

**实验 B：使用原始输出（Raw）**
```bash
python tools/abox_metrics.py \
    --gold data/test_final.jsonl \
    --pred outputs/predictions_aligned.jsonl \
    --tbox outputs/tbox_final.json \
    --use-original-type \
    --out outputs/metrics_raw.json
```

### 📈 预期结果与分析

你可能会看到以下两种情况之一，这直接决定了你的论文论点：

*   **情况 1：回退版 F1 更高**
    *   **结论**：证明了你的“Schema 约束与回退机制”是有效的，修正了 LLM 的非规范输出（如将 `Flood` 修正为 `FloodEvent`）。
*   **情况 2：原始版 F1 更高**
    *   **结论**：说明 TBox 定义可能不够全，或者 Gold 标注中包含了一些 TBox 外的类型，而 LLM 实际上预测对了，但被回退逻辑“误杀”了。这提示你需要优化 TBox 或 Gold。

### 总结

**不要在抽取阶段生成两份数据，而是在评测阶段通过参数切换视角。** 这样既科学，又方便管理。