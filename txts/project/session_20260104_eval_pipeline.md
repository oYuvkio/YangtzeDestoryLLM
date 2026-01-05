# 会话总结：小模型评测与消融实验准备

## 日期
2026-01-04

## 完成的工作

### 1. 评测数据集划分（已完成）
- **test_final.jsonl**: 546 条（有 gold 标注，含 doc_id）
- **dev_final.jsonl**: 300 条（无标注，展示用）
- 位置: `data/p5_eval_pool/final/`

### 2. 现有脚本确认
| 脚本 | 功能 | 状态 |
|------|------|------|
| `scripts/p5/align_pred_to_gold.py` | 按 doc_id 对齐预测结果 | ✅ 可用 |
| `tools/abox_metrics.py` | 计算 Event/Triple F1 | ✅ 可用 |

### 3. 新增脚本
| 脚本 | 功能 |
|------|------|
| `scripts/p5/run_extraction_on_test.py` | 在测试集上运行 LLM 抽取 |
| `scripts/p5/run_model_comparison.sh` | 多模型一键对比评测 |
| `scripts/p5/compare_models.py` | 汇总多模型指标 |

## 完整评测流程

### 方式一：单模型评测（三步）

```bash
# Step 1: 抽取
python scripts/p5/run_extraction_on_test.py \
    --model "gpt-4o-mini" \
    --output outputs/eval_models/gpt4o_mini/predictions.jsonl

# Step 2: 对齐
python scripts/p5/align_pred_to_gold.py \
    --gold data/p5_eval_pool/final/test_final.jsonl \
    --pred outputs/eval_models/gpt4o_mini/predictions.jsonl \
    --out outputs/eval_models/gpt4o_mini/predictions_aligned.jsonl

# Step 3: 评测
python tools/abox_metrics.py \
    --gold data/p5_eval_pool/final/test_final.jsonl \
    --pred outputs/eval_models/gpt4o_mini/predictions_aligned.jsonl \
    --tbox outputs/cq_pipeline/final/p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json \
    --out outputs/eval_models/gpt4o_mini/metrics.json
```

### 方式二：多模型对比（一键）

```bash
# 默认三个模型对比
bash scripts/p5/run_model_comparison.sh

# 自定义模型
bash scripts/p5/run_model_comparison.sh --models "gpt-4o-mini,glm-4-flash"

# 小批量测试
bash scripts/p5/run_model_comparison.sh --limit 10
```

## 关键文件路径

### 输入
- **测试集**: `data/p5_eval_pool/final/test_final.jsonl` (546 条)
- **TBox**: `outputs/cq_pipeline/final/p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json`
- **配置**: `configs/cfg.yaml`

### 输出目录结构
```
outputs/eval_models/
├── gpt-4o-mini/
│   ├── predictions.jsonl          # 原始预测
│   ├── predictions.meta.json      # 抽取元数据
│   ├── predictions_aligned.jsonl  # 对齐后的预测
│   ├── align_report.json          # 对齐报告
│   └── metrics.json               # 评测指标
├── glm-4-flash/
│   └── ...
└── comparison_report.json         # 汇总对比报告
```

## 评测指标说明

| 指标 | 说明 |
|------|------|
| `event_f1` | 事件抽取 F1（类型 + 名称 + 时间窗匹配） |
| `triple_f1_strict` | 三元组 F1（严格匹配 s,p,o） |
| `triple_f1_relaxed` | 三元组 F1（宽松，允许时间/地名同义） |
| `tbox_consistency` | 谓词存在性 + domain/range 符合率 |

## 注意事项

1. **doc_id 对齐**: 预测结果必须包含 doc_id，评测前用 `align_pred_to_gold.py` 对齐
2. **顺序匹配**: `abox_metrics.py` 按列表索引匹配，对齐后顺序一致
3. **断点续跑**: `run_extraction_on_test.py` 支持 `--skip-existing` 跳过已完成
4. **配额保护**: 检测到 429/quota 错误自动停止

## 消融实验设计（后续）

确定最佳模型后：
| 实验 | 变量 | TBox 文件 |
|------|------|----------|
| Baseline | 完整 TBox | p4_tbox_dedup_s2_allow1_*_t0p80.json |
| -P4 | 不增强 | p3_tbox.json |
| -Dedup | 不去重 | p4_tbox_augmented_s2_allow1_*.json |
| 阈值 0.7 | 去重阈值 | p4_tbox_dedup_*_t0p70.json |
| 阈值 0.75 | 去重阈值 | p4_tbox_dedup_*_t0p75.json |

## 下一步

1. 选择 2-3 个小模型运行对比
2. 确定最佳模型
3. 基于最佳模型跑消融实验
4. 整理实验结果写入论文
