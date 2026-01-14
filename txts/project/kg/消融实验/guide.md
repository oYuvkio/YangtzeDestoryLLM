基于你的 v4 Pipeline，我来帮你设计一套完整的消融实验方案，检验各个模块的贡献。

## 消融实验设计

### 一、核心模块分解

你的 Pipeline 有以下可消融的核心模块：

| 模块 | 对应代码/参数 | 核心价值假设 |
|------|--------------|-------------|
| **图结构检测** | `get_graph_structure_for_text()` | 领域特定的图结构能提升抽取准确性 |
| **CoT 推理** | `--no-cot` | 链式思维能减少幻觉、提升关系方向正确性 |
| **原文回溯校验** | `--no-verify` | 过滤幻觉三元组 |
| **模糊匹配** | `--strict-filter` vs `--fuzzy-threshold` | 宽松匹配能召回更多正确三元组 |
| **Schema 约束** | `--strict-schema` vs `--no-strict-schema` | Schema 约束能保证关系合法性 |
| **Hybrid TBox** | 不同 `--tbox` 文件 | 混合本体优于纯专家骨架 |

---

### 二、推荐消融实验方案

#### 实验 1：ABox 抽取消融（固定 TBox，变 Pred 配置）

这是**最重要**的消融，检验抽取链路各模块的价值：

| 变体 ID | 配置 | 检验目标 | 命令关键参数 |
|---------|------|----------|-------------|
| **full** | 图结构 + CoT + 后校验 + 模糊匹配 | 基准（完整系统） | 默认配置 |
| **wo_cot** | 去掉 CoT | CoT 的价值 | `--no-cot` |
| **wo_verify** | 去掉原文回溯校验 | 后校验的价值 | `--no-verify` |
| **wo_graph** | 去掉图结构（用通用结构） | 图结构检测的价值 | 需新增参数 `--no-graph` |
| **strict_match** | 严格匹配（禁用模糊） | 模糊匹配的价值 | `--strict-filter` |
| **strict_schema** | 严格 Schema 约束 | Schema 宽松策略的价值 | `--strict-schema` |

**预期结论**：
- `wo_cot`: Precision 下降（更多幻觉），关系方向错误增加
- `wo_verify`: Precision 显著下降，幻觉率上升
- `wo_graph`: 特定类型文本（如洪水事件）的 F1 下降
- `strict_match`: Recall 下降（漏掉正确但有微小差异的实体）
- `strict_schema`: Recall 下降（过滤掉部分合理但类型不完全匹配的三元组）

---

#### 实验 2：TBox 消融（变 TBox，固定 Pred 配置）

检验 Hybrid 本体构建的价值：

| 变体 ID | TBox 来源 | 检验目标 |
|---------|----------|----------|
| **expert_only** | `data/expert_skeleton.json` | 纯专家骨架的效果 |
| **hybrid_full** | `outputs/kg_final/tbox_final.json` | 完整 Hybrid TBox |
| **hybrid_wo_filter** | 不做支持度/置信度筛选 | 质量筛选的价值 |

**预期结论**：
- `expert_only`: 覆盖率不足，部分实体/关系无法抽取
- `hybrid_wo_filter`: 噪声类/关系增多，Precision 下降

---

#### 实验 3：CoT 步骤消融（细粒度）

如果 CoT 效果显著，可进一步分解：

| 变体 ID | 配置 | 检验目标 |
|---------|------|----------|
| **cot_full** | 4 步完整 CoT | 基准 |
| **cot_wo_step3** | 去掉 Step3（证据回溯） | 证据验证步骤的价值 |
| **cot_wo_anchor** | 去掉 Step1 的锚点策略 | 锚点识别策略的价值 |

---

### 三、实验执行命令

```bash
# 基准 (full)
python scripts/p5/run_extraction_on_test.py \
  --test-file data/p5_eval_pool/pool.jsonl \
  --text-source data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl \
  --tbox outputs/kg_final/tbox_final.json \
  --model "gpt-4o-mini" \
  --fuzzy-threshold 0.75 \
  --no-strict-schema \
  --output outputs/ablation/pred_full.jsonl

# wo_cot
python scripts/p5/run_extraction_on_test.py \
  ... \
  --no-cot \
  --output outputs/ablation/pred_wo_cot.jsonl

# wo_verify
python scripts/p5/run_extraction_on_test.py \
  ... \
  --no-verify \
  --output outputs/ablation/pred_wo_verify.jsonl

# strict_match
python scripts/p5/run_extraction_on_test.py \
  ... \
  --strict-filter \
  --output outputs/ablation/pred_strict_match.jsonl

# strict_schema
python scripts/p5/run_extraction_on_test.py \
  ... \
  --strict-schema \
  --output outputs/ablation/pred_strict_schema.jsonl

# expert_only (TBox 消融)
python scripts/p5/run_extraction_on_test.py \
  ... \
  --tbox data/expert_skeleton.json \
  --output outputs/ablation/pred_expert_only.jsonl
```

---

### 四、评测指标

对每个变体计算：

| 指标类别 | 具体指标 | 说明 |
|----------|----------|------|
| **三元组质量** | Strict Triple F1 | 主语+谓词+宾语完全匹配 |
| | Relaxed Triple F1 | 允许实体模糊匹配 |
| **事件质量** | Event F1 | 事件识别准确率 |
| **实体质量** | Entity F1 | 实体识别准确率 |
| **幻觉统计** | Hallucination Rate | 被过滤的三元组比例 |
| **Schema 一致性** | Predicate Accuracy | 谓词合法率 |
| | Domain/Range Accuracy | 类型约束符合率 |
| **关系方向** | Direction Accuracy | 关系方向正确率 |

---

### 五、结果呈现建议

#### 表格 1：ABox 消融实验结果

| 变体 | Triple P | Triple R | Triple F1 | Event F1 | Halluc. Rate |
|------|----------|----------|-----------|----------|--------------|
| full | - | - | - | - | - |
| wo_cot | ↓ | - | ↓ | ↓ | ↑ |
| wo_verify | ↓↓ | ↑ | ↓ | - | ↑↑ |
| wo_graph | - | - | ↓ | ↓ | - |
| strict_match | ↑ | ↓↓ | ↓ | - | ↓ |
| strict_schema | ↑ | ↓ | - | - | - |

#### 表格 2：TBox 消融实验结果

| TBox 变体 | Triple F1 | 覆盖类数 | 覆盖关系数 |
|-----------|-----------|----------|------------|
| expert_only | - | 少 | 少 |
| hybrid_full | 最高 | 多 | 多 |

---

### 六、需要新增的代码支持

当前代码已支持大部分消融，但 **wo_graph** 需要新增参数：

```python
# 在 run_extraction_on_test.py 中添加
parser.add_argument("--no-graph", action="store_true",
                    help="禁用图结构检测，强制使用通用结构")

# 在 extract_events_with_verification 中修改
if args.no_graph or not use_cot:
    graph_structure = get_graph_structure("general_disaster")
else:
    graph_structure, type_id, confidence = get_graph_structure_for_text(paragraph)
```

---

### 七、优先级建议

**必做**（核心贡献验证）：
1. `full` vs `wo_cot` — 验证 CoT 的价值
2. `full` vs `wo_verify` — 验证后校验的价值
3. `hybrid_full` vs `expert_only` — 验证 Hybrid TBox 的价值

**推荐做**（完整性）：
4. `full` vs `strict_match` — 验证模糊匹配策略
5. `full` vs `wo_graph` — 验证图结构检测的价值

**可选**（细粒度分析）：
6. CoT 步骤消融
7. 不同 fuzzy_threshold 的敏感性分析

这样的消融实验设计能够清晰地展示你系统中每个模块的贡献，是论文评审非常看重的部分。