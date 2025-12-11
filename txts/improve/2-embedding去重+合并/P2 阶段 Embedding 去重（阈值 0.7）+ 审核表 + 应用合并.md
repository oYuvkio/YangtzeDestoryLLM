目标：落地论文要求：“text-embedding-3-large + 余弦相似度 > 0.7 判定重复并剔除；自动过滤 + 人工微调”。

任务：在 tools/tbox_dedup.py 内实现基于 embedding 的 TBox 去重流程，并提供人工审核与合并工具。

[改动点]
1) 新增 tools/tbox_dedup.py：
   - 子命令 dedup:
     输入：--in-tbox p2_tbox_init.json, --base-tbox p3_tbox_normalized.json（可选）
     参数：--model text-embedding-3-large, --sim-th 0.7
     输出：p3_tbox_dedup.json、以及 review.csv（候选与最相似项的配对）
     逻辑：
       * 对 “类/关系/属性” 分别去重：同类型才比相似度
       * 拼接文本：name || cn_name || def:... || examples:...
       * 若 base-tbox 提供，则以其为已存在集合
       * 记录所有 (candidate, best_match, similarity, action='AUTO_MERGE'|'REVIEW')
       * 相似度≥阈值 → AUTO_MERGE；[0.6,0.7) → REVIEW；<0.6 → KEEP
   - 子命令 apply-review:
     输入：--in-tbox, --review-csv
     输出：合并后的 p3_tbox_dedup.json（落实人工标注列 action=KEEP/MERGE_TO:<name>/REJECT）

2) 在 configs/cfg.yaml 增加：
   tbox_dedup:
     model: "text-embedding-3-large"
     sim_th: 0.7
     review_band: [0.6, 0.7]

[CLI]
python tools/tbox_dedup.py dedup \
  --in-tbox outputs/cq_pipeline/final/p2_tbox_init.json \
  --base-tbox outputs/cq_pipeline/final/p3_tbox_normalized.json \
  --out-tbox outputs/cq_pipeline/final/p3_tbox_dedup.json \
  --review "outputs/cq_pipeline/final/p3_tbox_review.csv" \
  --model text-embedding-3-large \
  --sim-th 0.7 \
  --log-file logs/kg_tbox/dedup_p2.log

# 人工标注后
python tools/tbox_dedup.py apply-review \
  --in-tbox outputs/cq_pipeline/final/p3_tbox_dedup.json \
  --review "outputs/cq_pipeline/final/p3_tbox_review.csv" \
  --out-tbox outputs/cq_pipeline/final/p3_tbox_dedup_final.json \
  --log-file logs/kg_tbox/apply_review.log

[验收标准]
- 生成 review.csv，含列：type,name,cn_name,def,candidate_id,best_match_name,best_match_id,similarity,action,suggestion
- 通过 apply-review 可将 MERGE_TO 生效，生成最终去重 TBox。
- 日志内打印：各类型保留/合并/待审数量。
 
