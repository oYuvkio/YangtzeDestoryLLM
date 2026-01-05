# 本体漂移处理建议（更新版）

## 1. 现状与核心矛盾
- **Gold 标注**：更贴近自然语言（如 `has_value`, `located_in`, `affects`）。
- **TBox 定义**：更规范化（如 `has_hazard_factor`, `causes_impact`）。
- **结果**：关系与类型交集偏小，导致 F1 低，出现“漂移”。

核心矛盾：**Gold 的“方言” vs TBox 的“标准语”**。

---

## 2. 推荐方案（当前代码已支持）

### Step 1：漂移分析
先运行分析脚本，生成映射模板。

```bash
python scripts/p5/analyze_schema_drift.py \
    --gold data/p5_eval_pool/final/test_final.jsonl \
    --tbox outputs/cq_pipeline/final/p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json \
    --output-mapping configs/relation_mapping_template.json
```

### Step 2：编辑映射配置
根据模板生成正式映射文件：`configs/relation_mapping.json`。

**配置格式（与 apply_relation_mapping.py 一致）：**
- `relation_mapping`: 直接映射或 `IGNORE`
- `inverse_relations`: 需要交换主客体时使用
- `ignore_relations`: 额外忽略列表

**推荐初版（可按实际情况增删）：**
```json
{
  "relation_mapping": {
    "affects": "affects_region",
    "part_of": "located_in",
    "has_cause": "has_hazard_factor",
    "triggers": "triggers_response",
    "mitigates": "implements_measure",
    "resolves": "implements_measure",
    "has_impact": "causes_impact",
    "has_value": "IGNORE",
    "occurs_at": "IGNORE"
  },
  "inverse_relations": {
    "affected_by": {"standard": "affects_region", "swap_direction": true}
  },
  "ignore_relations": [
    "has_value",
    "occurs_at",
    "has_disaster_types"
  ]
}
```

### Step 3：评测时启用映射
**已集成在评测脚本中**，直接传参即可：

```bash
bash scripts/p5/run_single_model.sh \
    --model "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B" \
    --relation-mapping configs/relation_mapping.json
```

或多模型对比：
```bash
bash scripts/p5/run_model_comparison.sh \
    --models "gpt-4o-mini,glm-4-flash" \
    --relation-mapping configs/relation_mapping.json
```

---

## 3. 双版本评测（回退 vs 原始）
系统会自动输出两份指标：
- **回退逻辑版**：`metrics.json`
- **原始输出版**：`metrics_raw.json`（内部使用 `--use-original-type`）

用途：
- 回退版更符合 TBox 约束
- 原始版更能体现模型“自由输出能力”

---

## 4. 指标要求（已支持）
评测输出包含：
- **Precision / Recall / F1**（事件 + 三元组，严格/宽松）
- **Hallucination Rate（幻觉率）**
- **Entity Redundancy Rate（实体冗余率）**
- **TBox Consistency（本体一致性）**

说明：
- 幻觉率只有在开启校验（`use_verify=True`）时才有值，否则为 `null`。
- 实体冗余率当前基于三元组实体重复率统计（非融合后实体数）。

---

## 5. 注意事项
1. **`has_value` / `occurs_at` 建议忽略**：它们属于属性表达，不是实体关系。
2. **`part_of` 的映射有歧义**：统一映射为 `located_in` 可以跑通，但需在论文中说明。
3. **映射是全局的**：apply_relation_mapping 不支持按实体类型条件映射。
4. **若需评测属性抽取**：需要 P5 Prompt 输出 `attributes` 字段，并扩展评测脚本。
5. **回退逻辑会影响类型评测**：建议同时报告 `metrics.json` 与 `metrics_raw.json`。

---

## 6. 下一步该做什么
1. **生成并完善映射配置**（`configs/relation_mapping.json`）。
2. **启用映射评测**（`--relation-mapping`）。
3. **对比回退版 vs 原始版指标**（`metrics.json` vs `metrics_raw.json`）。
4. 若仍漂移严重：补充映射规则或扩展 TBox（慎重）。

---

## 7. 建议写入论文的表述
- “Gold 标注采用独立 schema，为避免破坏 CQ 驱动构建的 TBox，我们采用关系映射对齐评测。”
- “报告回退逻辑与原始输出两组指标，以区分‘规范一致性’与‘模型自由表达能力’。”
- “引入幻觉率与实体冗余率补充指标，体现校验与融合模块效果。”
