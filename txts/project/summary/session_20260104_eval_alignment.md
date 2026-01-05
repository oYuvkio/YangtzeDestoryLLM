# 会话总结（2026-01-04）

## 背景与决定
- 本次评测使用小模型在测试集上抽取，再与 gold 标注对比评估。
- 评测 TBox 选择：`outputs/cq_pipeline/final/p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json`
- 测试集：`data/p5_eval_pool/final/test_final.jsonl`（来自 `gold_reviewed.jsonl`）

## 新增脚本
- **对齐脚本**：`scripts/p5/align_pred_to_gold.py`
  - 功能：按 `doc_id` 将预测结果顺序对齐 gold，缺失项自动补空，生成对齐报告。
  - 输入：gold（json/jsonl）、pred（json/jsonl）
  - 输出：对齐后的 pred（jsonl）+ 对齐报告（json）

## 推荐评测流程
1) **P5 抽取（小模型）**  
```bash
python scripts/run_cq_pipeline.py \
  --start-step p5 \
  --p4-file outputs/cq_pipeline/final/p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json \
  --corpus-jsonl data/p5_eval_pool/final/test_final.jsonl \
  --include-context \
  --favor-existing-classes \
  --output-dir outputs/p5_small_model_test \
  --provider openai \
  --model gpt-4o-mini \
  --save-interval 10 \
  --cfg configs/cfg.yaml
```

2) **关系映射（项目Schema → 标准Schema）**  
```bash
python tools/relation_mapping.py \
  --pred outputs/p5_small_model_test/p5_batch_results.jsonl \
  --out outputs/p5_small_model_test/p5_batch_results_mapped.jsonl
```

3) **按 doc_id 对齐**  
```bash
python scripts/p5/align_pred_to_gold.py \
  --gold data/p5_eval_pool/final/test_final.jsonl \
  --pred outputs/p5_small_model_test/p5_batch_results_mapped.jsonl \
  --out outputs/p5_small_model_test/p5_batch_results_aligned.jsonl \
  --report outputs/p5_small_model_test/align_report.json
```

4) **评测指标**  
```bash
python tools/abox_metrics.py \
  --gold data/p5_eval_pool/final/test_final.jsonl \
  --pred outputs/p5_small_model_test/p5_batch_results_aligned.jsonl \
  --tbox outputs/cq_pipeline/final/p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json \
  --out outputs/p5_small_model_test/metrics_small_model.json
```

## 注意事项
- `tools/abox_metrics.py` 默认按列表顺序逐条对齐，因此 **必须先按 `doc_id` 对齐**。
- gold 为独立标注 schema，评测前需先做 **关系映射**。
