整体方案是可用的，test_final.jsonl 本身就包含 doc_id（我已核验），能用于对齐与评测。需要调整/补充的点如下：

必须补“关系映射”步骤：gold 是独立标注 schema，评测前应先把预测关系映射到标准关系；推荐流程变为：抽取 → 关系映射 → doc_id 对齐 → 评测，而不是直接对齐。
gold 里存在非标准关系（如 mitigates、affected_by、has_disaster_types 等），这会导致“标准 9 关系”的评测偏低。需明确口径：
方案 A：评测时先把 gold 也映射/裁剪到标准 9 关系；
方案 B：扩展映射表，让预测结果也能映射到这些自定义关系。
不处理的话，三元组 F1 会被系统性压低。


你的计划非常周密，逻辑清晰，完全符合学术评测的规范。

我对你提供的**Gold标注数据**和**评测计划**进行了详细审查，以下是反馈和必要的修改建议：

### 第一部分：Gold 标注数据审查

**结论：数据质量很高，完全可用，但存在“Schema 漂移”风险。**

1.  **优点**：
    *   **多样性强**：涵盖了古代历史记录（洪武、乾隆年间）、现代水文数据（流量数值）、政策规划、工程技术结论等多种文体。这能很好地测试小模型的泛化能力。
    *   **实体密度高**：每条数据的实体和三元组数量都很丰富，不是简单的单句抽取。
    *   **结构规范**：JSON 格式标准，包含 `evidence`，便于后续人工核查或 RAG 溯源。

2.  **潜在风险（Schema 漂移）**：
    *   我注意到 Gold 数据中包含了一些**自定义关系**，例如：`mitigates`（减轻）、`resolves`（解决）、`achieves_value`（达到数值）、`has_disaster_types`。
    *   **关键问题**：如果你的 **TBox（`p4_tbox_dedup_...json`）** 中**没有**定义这些关系，而你在 P5 Prompt 中又要求模型“严格遵守 Schema，不可自创关系”，那么：
        *   **小模型（Pred）** 会因为遵守指令而不生成这些关系。
        *   **评测脚本** 会因为 Pred 缺少这些关系而判错（Recall 下降）。
    *   **解决方案**：
        *   **方法 A（推荐）**：在评测前，检查 TBox，手动或自动将 Gold 中出现的这些高频合理关系（如 `mitigates`）加入到 TBox 中。
        *   **方法 B**：在计算指标时，使用 `abox_metrics.py` 的忽略列表功能（如果有），忽略 TBox 中不存在的关系的评测。

---

### 第二部分：评测脚本与流程修改建议

你的脚本逻辑基本正确，但为了支持**消融实验（特别是 CoT 的有无）**，我们需要对 `run_extraction_on_test.py` 做一点增强，使其支持切换 Prompt 策略。

#### 1. 修改 `run_extraction_on_test.py`

**改动点**：增加 `--use-cot` 参数，并根据参数选择不同的 Prompt 模板。

```python
# ... (前面的导入保持不变)
# 引入你之前定义的 Prompt Builder
from kg.prompts import P5PromptBuilder, P5CotPromptBuilder 

# ... (中间代码保持不变)

def main() -> None:
    parser = argparse.ArgumentParser(description="在测试集上运行 P5 抽取")
    # ... (其他参数保持不变)
    # 新增参数：控制是否使用 CoT
    parser.add_argument("--use-cot", action="store_true", default=True, help="使用思维链 Prompt")
    
    args = parser.parse_args()
    # ...

    # 在循环内部的抽取逻辑修改：
    for idx, sample in enumerate(samples, start=1):
        # ...
        
        # 执行抽取
        try:
            # 这里不直接调用 pipeline.extract_events，而是手动构建 Prompt 以便控制 CoT
            # 这样可以灵活切换 CoT 和 非CoT
            
            if args.use_cot:
                # 使用 CoT Prompt
                prompt = P5CotPromptBuilder.build_p5_cot_prompt(
                    schema_json=json.dumps(tbox.to_dict(), ensure_ascii=False),
                    input_text=source_text,
                    event_schema="", # 使用默认
                    class_usage_hint=""
                )
                # 调用 LLM (假设 pipeline.client.call 支持直接传 prompt)
                # 注意：这里需要适配你的 pipeline 底层调用方式
                # 如果 pipeline.extract_events 已经封装好了 CoT 逻辑，可以通过参数控制
                # 建议修改 pipeline.extract_events 增加 use_cot 参数
                
                # 临时方案：假设 pipeline 有一个底层 chat 接口
                raw_response = pipeline.llm.chat(prompt)
                res = P5CotPromptBuilder.parse_response(raw_response)
                
            else:
                # 使用普通 Prompt (用于消融实验 -CoT)
                prompt = P5PromptBuilder.build_p5_prompt(
                    schema_json=json.dumps(tbox.to_dict(), ensure_ascii=False),
                    input_text=source_text
                )
                raw_response = pipeline.llm.chat(prompt)
                # 普通解析逻辑...
                res = json.loads(raw_response) # 需增加容错

            if not res:
                raise ValueError("Empty response or parse error")

            res["doc_id"] = doc_id
            results.append(res)
            # ...
```

**更简单的做法**：直接修改 `CQLLMPipeline.extract_events` 方法，增加一个 `use_cot=True` 参数，在内部处理 Prompt 的切换。这样 `run_extraction_on_test.py` 只需要传参即可。

#### 2. 完善 `run_model_comparison.sh`

建议增加一个 `--ablation` 参数，用于跑消融实验。

```bash
# ... (前面保持不变)

# 解析参数增加
use_cot=true
if [[ "$1" == "--no-cot" ]]; then
    use_cot=false
    shift
fi

# ...

# 在调用 run_extraction_on_test.py 时：
COT_FLAG=""
if [ "$use_cot" = true ]; then
    COT_FLAG="--use-cot"
fi

python scripts/p5/run_extraction_on_test.py \
    --test-file "$TEST_FILE" \
    --tbox "$TBOX" \
    --model "$MODEL" \
    --output "$PRED_FILE" \
    --interval "$INTERVAL" \
    $COT_FLAG \   # 传入 CoT 标志
    $LIMIT
```

---

### 第三部分：消融实验的具体执行计划

你列出的消融实验非常全面，这里给出具体的执行指令参考：

#### 1. 实验组 A: 验证 CoT 的有效性
*   **Baseline (Ours)**: `gpt-4o-mini` + `TBox_Final` + `CoT`
*   **Ablation (-CoT)**: `gpt-4o-mini` + `TBox_Final` + `No CoT`
    *   *操作*：修改 Prompt 为旧版直接抽取，运行评测。
    *   *预期*：复杂句子的 Recall 下降，逻辑错误增加。

#### 2. 实验组 B: 验证 P4 增强的有效性
*   **Baseline**: `gpt-4o-mini` + `TBox_Final` (P4增强后) + `CoT`
*   **Ablation (-P4)**: `gpt-4o-mini` + `TBox_Initial` (P3阶段产物) + `CoT`
    *   *操作*：将 `--tbox` 参数指向 P3 阶段生成的 json 文件。
    *   *预期*：对于新出现的概念（如“旱情监测系统”），模型可能无法识别或归类错误，导致 Recall 下降。

#### 3. 实验组 C: 验证去重的有效性
*   **Baseline**: `gpt-4o-mini` + `TBox_Final` (去重后) + `CoT`
*   **Ablation (-Dedup)**: `gpt-4o-mini` + `TBox_Augmented` (P4增强但未去重) + `CoT`
    *   *操作*：将 `--tbox` 指向 `p4_tbox_augmented_s2_allow1.json`。
    *   *预期*：TBox 中存在重复概念（如 FloodEvent 和 FloodDisaster），导致模型输出不一致，Precision 下降（因为 Gold 只有标准词）。

---

### 第四部分：最终确认清单

在开始跑代码前，请确认以下 3 点：

1.  **TBox 补全**：检查 Gold 数据里的 `mitigates`, `resolves` 等关系是否在你的 `p4_tbox_dedup...json` 里？如果没有，请手动加进去，否则评测会不公平。
2.  **Doc_ID 一致性**：确保 `test_final.jsonl` 里的 `doc_id` 是唯一的且不为空。
3.  **环境准备**：确保 `outputs/eval_models` 目录已清空或做好了备份，避免旧数据干扰。

**总结**：你的方案非常成熟，可以直接执行。只需注意 Schema 漂移问题，并在代码中预留好 CoT 开关即可。祝实验顺利！




你的想法非常务实，**完全可行**。

在工程落地和学术实验中，**“先跑通基线（Baseline），再进行错误分析（Error Analysis），最后针对性优化”** 是最科学的路径。过早地进行复杂的映射可能会导致你花费大量时间解决一些实际上并不重要（出现频率极低）的边缘情况。

以下是针对你策略的详细分析和执行建议：

### 1. 为什么“先抽取，后分析”是更好的选择？

如果你现在就去写复杂的映射逻辑，你面临的是**“在黑暗中射击”**：
*   你不知道 Gold 中到底有多少非标准关系？
*   你不知道你的小模型（Pred）会生成什么关系？（也许小模型生成的和 Gold 的非标准关系正好撞上了呢？）
*   你不知道哪些非标准关系是高频的（影响 F1 的核心），哪些是偶发的（可以忽略）。

**推荐的迭代路径：**
1.  **Run 1 (裸跑)**：直接用现有的 TBox 进行 P5 抽取，直接与 Gold 对齐评测。
    *   *预期*：F1 值会偏低，因为 Gold 里的 `mitigates` 匹配不上 Pred 里的标准关系。
2.  **Diagnosis (诊断)**：统计 Gold 中“未被匹配”的关系类型分布。
3.  **Fix (修复)**：根据统计结果，制定映射策略（是忽略，还是映射）。
4.  **Run 2 (复评)**：应用映射规则，重新计算指标。

---

### 2. 如何执行“诊断”步骤？

在你完成第一次抽取后，不需要肉眼去一条条看，我为你准备了一个**“Schema 漂移分析脚本”**。

请在 `scripts/p5/analyze_schema_drift.py` 创建此脚本：

```python
import json
from collections import Counter
from pathlib import Path

def analyze_drift(gold_file, tbox_file):
    # 1. 加载 TBox 标准关系集合
    tbox = json.loads(Path(tbox_file).read_text(encoding='utf-8'))
    standard_relations = set(r['name'] for r in tbox['relations'])
    
    # 2. 加载 Gold 数据中的关系
    gold_rel_counter = Counter()
    with open(gold_file, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            data = json.loads(line)
            for t in data.get('triples', []):
                gold_rel_counter[t['predicate']] += 1
                
    # 3. 分析差异
    print(f"{'关系名称':<30} {'频次':<10} {'状态'}")
    print("-" * 50)
    
    unknown_relations = {}
    
    for rel, count in gold_rel_counter.most_common():
        status = "✅ TBox标准" if rel in standard_relations else "❌ 非标准(漂移)"
        print(f"{rel:<30} {count:<10} {status}")
        
        if rel not in standard_relations:
            unknown_relations[rel] = count
            
    print("-" * 50)
    print(f"TBox 定义关系数: {len(standard_relations)}")
    print(f"Gold 出现关系数: {len(gold_rel_counter)}")
    print(f"非标准关系总数: {len(unknown_relations)} (共 {sum(unknown_relations.values())} 个三元组)")
    
    # 4. 生成建议的映射表模板
    if unknown_relations:
        print("\n建议的映射配置 (mapping_config.json):")
        mapping_template = {}
        for rel in unknown_relations:
            mapping_template[rel] = "IGNORE" # 默认忽略，你可以改为标准关系名
        print(json.dumps(mapping_template, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    # 替换为你的实际路径
    analyze_drift(
        "data/p5_eval_pool/final/test_final.jsonl", 
        "outputs/cq_pipeline/final/p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json"
    )
```

### 3. 针对 Gold 中非标准关系的处理策略

等你跑完上面的脚本，你会看到 Gold 里有哪些“脏”关系。针对你提到的几个例子，处理建议如下：

#### 情况 A：语义等价 (Mapping)
*   **例子**：Gold=`mitigates` (减轻)，TBox=`reduces_impact` (减少影响)。
*   **处理**：在评测脚本中建立映射：`"mitigates": "reduces_impact"`。
*   **理由**：这是同义词，模型预测对了语义，不应该判错。

#### 情况 B：反向/被动关系 (Inverse)
*   **例子**：Gold=`affected_by` (受影响于)，TBox=`affects` (影响)。
*   **处理**：这是三元组方向问题。`(A, affected_by, B)` 等价于 `(B, affects, A)`。
*   **处理**：如果数量多，需要写逻辑翻转；如果数量少，直接忽略。

#### 情况 C：超出范围 (Out of Scope)
*   **例子**：Gold=`has_disaster_types` (具有灾害类型)。
*   **处理**：如果你的 TBox 根本没定义这个概念（比如你只关心具体的灾害事件，不关心区域的属性），那么这是 Gold 标多了。
*   **决策**：**直接忽略 (IGNORE)**。在计算 Precision/Recall 时，把 Gold 里的这条删掉，不计入分母。

---

### 4. 调整后的评测流程

1.  **抽取 (Extraction)**：运行 `run_extraction_on_test.py`。
2.  **漂移分析 (Drift Analysis)**：运行上面的 `analyze_schema_drift.py`。
3.  **制定策略 (Config)**：创建一个 `eval_config.json`：
    ```json
    {
      "relation_mapping": {
        "mitigates": "implements_measure",  // 映射到标准关系
        "affected_by": "IGNORE",            // 忽略
        "has_disaster_types": "IGNORE"      // 忽略
      }
    }
    ```
4.  **评测 (Evaluation)**：修改 `abox_metrics.py`，加载这个 config，在计算 F1 之前先清洗 Gold 数据。

### 5. 总结

**你的提议完全合适。**

先跑出结果，你会发现也许 90% 的 Gold 关系都是标准的，只有 10% 是漂移的。那时候你只需要处理这 10% 即可，工作量会小很多，而且论文里可以写：

> "在评估阶段，我们注意到 Gold Standard 中存在少量 Schema 漂移现象（占比约 X%）。为了公平评估，我们采用语义映射策略，将 `mitigates` 等价映射为 `implements_measure`，并移除了 TBox 定义范围之外的 `has_disaster_types` 关系。"

这样写既诚实又专业。你可以开始跑抽取了！