目标：从 dev/test 集抽取事件与三元组，计算严格/宽松 F1 与 TBox 一致性。


任务：完善 tools/abox_metrics.py，支持以下指标：
- Event F1：事件类型 + 时间窗命中
- Triple F1 (Strict/Relaxed)：(h,r,t) 匹配；宽松允许时间±1日、地名同义/上位合并
- TBox Consistency：所有三元组谓词的 domain/range 与 TBox 签名一致率

[改动点]
1) tools/abox_metrics.py：
   - 输入：--gold gold.jsonl --pred pred.jsonl --tbox p4_tbox_enhanced.json
   - 参数：--time-tolerance-days 1 --geo-syn "resources/geo_synonyms.json"
   - 输出：JSON 指标 + 详细错误分类（time_mismatch, geo_mismatch, predicate_violation 等）
2) 在 resources/geo_synonyms.json 提供简单地名同义/上位映射（如 “武汉市” ~ “武汉”、“长江中下游” 上位于 “安徽段”等）——先占位，留扩展接口。

[CLI]
python tools/abox_metrics.py \
  --gold data/p5_eval_pool/dev_gold.jsonl \
  --pred outputs/extract/triples_dev.jsonl \
  --tbox outputs/cq_pipeline/final/p4_tbox_enhanced.json \
  --time-tolerance-days 1 \
  --geo-syn resources/geo_synonyms.json \
  --out "outputs/abox/metrics_dev.json" \
  --log-file "logs/abox/metrics_dev.log"

[验收标准]
- 指标 JSON 包含：event_f1, triple_f1_strict, triple_f1_relaxed, tbox_consistency, error_breakdown
- 可运行且在 dev/test 上输出
