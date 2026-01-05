# P5 小模型评测与消融实验 - 开发总结

**日期**: 2026-01-04
**阶段**: P5 - 知识图谱评测流程优化

---

## 一、本次完成的工作

### 1. Schema 漂移分析脚本

**文件**: `scripts/p5/analyze_schema_drift.py`

**功能**: 分析 Gold 标注中的关系是否在 TBox 中定义，统计非标准关系频次，生成映射建议。

**使用方式**:
```bash
python scripts/p5/analyze_schema_drift.py \
    --gold data/p5_eval_pool/final/test_final.jsonl \
    --tbox outputs/cq_pipeline/final/p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json \
    --output-mapping configs/relation_mapping_template.json
```

---

### 2. 关系映射脚本

**文件**: `scripts/p5/apply_relation_mapping.py`

**功能**: 对 Gold 和 Pred 中的三元组应用关系映射/忽略规则，处理 Schema 漂移问题。

**映射配置格式** (`configs/relation_mapping.json`):
```json
{
  "relation_mapping": {
    "mitigates": "implements_measure",
    "affected_by": "IGNORE"
  },
  "inverse_relations": {
    "contained_by": {"standard": "contains", "swap_direction": true}
  },
  "ignore_relations": ["has_disaster_types"]
}
```

---

### 3. 后校验开关（消融实验 A1）

**修改文件**: `scripts/p5/run_extraction_on_test.py`

**新增功能**:
- `--no-verify`: 禁用原文回溯校验（默认开启校验）
- 抽取后自动调用 `filter_hallucinations()` 过滤幻觉三元组
- 结果中包含 `_meta_hallucination` 字段，记录过滤详情

**参数设计修正**（根据 Code Review 建议）:

| 原设计 | 问题 | 修正后 |
|--------|------|--------|
| `--use-verify` + `--no-verify` | `action="store_true" default=True` 陷阱 | 只保留 `--no-verify` |
| `--use-cot` + `--no-cot` | 同上 | 只保留 `--no-cot` |
| `--favor-existing-classes` | 无法关闭 | 增加 `--no-favor-existing-classes` |

**修正后的参数逻辑**:
```python
# 默认都开启，通过 --no-* 关闭
use_cot = not args.no_cot
use_verify = not args.no_verify
```

---

### 4. 单模型评测脚本（支持 tmux 并行）

**文件**: `scripts/p5/run_single_model.sh`

**支持参数**:
- `--model`: 模型名称（必须）
- `--base-url`: API base URL
- `--temperature`: 温度参数（默认 0.1）
- `--interval`: 请求间隔（默认 1.0）
- `--limit`: 样本数限制
- `--no-cot`: 禁用 CoT
- `--no-verify`: 禁用后校验

---

## 二、消融实验设计

### 实验组 A1: 后校验有效性
| 配置 | 命令 |
|------|------|
| Baseline | `bash scripts/p5/run_single_model.sh --model "gpt-4o-mini"` |
| -Verify | `bash scripts/p5/run_single_model.sh --model "gpt-4o-mini" --no-verify` |

**预期**: 移除后校验后，Precision 下降（幻觉未被过滤）

### 实验组 A2: CoT 有效性
| 配置 | 命令 |
|------|------|
| Baseline | `bash scripts/p5/run_single_model.sh --model "gpt-4o-mini"` |
| -CoT | `bash scripts/p5/run_single_model.sh --model "gpt-4o-mini" --no-cot` |

**注意**: `--no-cot` 目前只记录状态，实际 CoT 切换需要修改 `CQLLMPipeline`

---

## 三、多 tmux 窗口并行运行示例

**窗口 1 - GPT-4o-mini**:
```bash
bash scripts/p5/run_single_model.sh \
    --model "gpt-4o-mini" \
    --temperature 0.1 \
    --interval 1.0
```

**窗口 2 - GLM-4-Flash**:
```bash
bash scripts/p5/run_single_model.sh \
    --model "glm-4-flash" \
    --base-url "https://open.bigmodel.cn/api/paas/v4" \
    --temperature 0.1 \
    --interval 0.5
```

**窗口 3 - Qwen-Turbo**:
```bash
bash scripts/p5/run_single_model.sh \
    --model "qwen-turbo" \
    --base-url "https://dashscope.aliyuncs.com/compatible-mode/v1" \
    --temperature 0.1 \
    --interval 0.5
```

**所有模型跑完后汇总**:
```bash
python scripts/p5/compare_models.py \
    --input-dir outputs/eval_models \
    --models "gpt-4o-mini glm-4-flash qwen-turbo" \
    --output outputs/eval_models/comparison_report.json
```

---

## 四、输出数据结构

### 预测结果 (`predictions.jsonl`)
```json
{
  "doc_id": "doc_001",
  "events": [...],
  "triples": [...],
  "use_cot": true,
  "use_verify": true,
  "_meta_hallucination": {
    "is_filtered": true,
    "original_count": 5,
    "valid_count": 3,
    "filtered_count": 2,
    "rate": 0.4,
    "filtered_triples": [
      {"subject": "武汉站", "predicate": "水位达到", "object": "30米", "reason": "subject not found"}
    ]
  }
}
```

---

## 五、文件清单

| 文件 | 功能 | 状态 |
|------|------|------|
| `scripts/p5/run_extraction_on_test.py` | 测试集抽取 | ✅ 已优化 |
| `scripts/p5/run_single_model.sh` | 单模型评测 | ✅ 新增 |
| `scripts/p5/run_model_comparison.sh` | 多模型对比 | ✅ 已优化 |
| `scripts/p5/analyze_schema_drift.py` | Schema 漂移分析 | ✅ 新增 |
| `scripts/p5/apply_relation_mapping.py` | 关系映射 | ✅ 新增 |
| `scripts/p5/compare_models.py` | 多模型汇总 | ✅ 已有 |
| `tools/abox_metrics.py` | 指标计算 | ✅ 已有 |

---

## 六、已知问题与待办

1. **`--no-cot` 实际不生效**: 目前只记录状态，需要修改 `CQLLMPipeline.extract_events` 支持 `use_cot` 参数切换 prompt
2. **评测流程未集成关系映射**: `run_model_comparison.sh` 中未调用 `apply_relation_mapping.py`
3. **`analyze_schema_drift.py` 未做关系名归一化**: 大小写/空白/标点边界情况可能统计不准

---

## 七、推荐执行路径

```bash
# Phase 1: 漂移分析
python scripts/p5/analyze_schema_drift.py \
    --gold data/p5_eval_pool/final/test_final.jsonl \
    --tbox outputs/cq_pipeline/final/p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json

# Phase 2: 小批量测试
bash scripts/p5/run_single_model.sh --model "gpt-4o-mini" --limit 10

# Phase 3: 验证 --no-verify 开关
bash scripts/p5/run_single_model.sh --model "gpt-4o-mini" --no-verify --limit 10
# 观察日志是否显示 [Raw] 而非幻觉率

# Phase 4: 正式评测
bash scripts/p5/run_single_model.sh --model "gpt-4o-mini"
```
