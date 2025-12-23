#!/bin/bash
# P4 增强：allow_new_classes=True（仅合并，不重新调用 LLM）
# 用法: bash run_p4_allow1_merge_only.sh
# 说明:
#   1) 先运行 run_p4_allow0.sh 生成聚合文件 p4_corpus_suggestions_agg.json
#   2) 本脚本基于 allow0 的聚合结果，快速生成 allow1 版本，避免重复消耗配额

set -eo pipefail

cd /home/zjx/dev_ops/YangtzeDestoryLLM

# 激活 conda 环境
source /home/zjx/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM

# 设置 PYTHONPATH
export PYTHONPATH=.

# 输出目录
mkdir -p outputs/cq_pipeline/final_with_hierarchy \
         outputs/cq_pipeline/process_with_hierarchy_allow1 \
         outputs/ontoqa \
         logs

echo "========================================"
echo "P4 增强（merge-only）：allow_new_classes=True"
echo "依赖聚合文件：process_with_hierarchy_allow0/p4_corpus_suggestions_agg.json"
echo "预计耗时: 约 5-10 秒"
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

python scripts/run_p4_batch.py \
  --base-tbox outputs/cq_pipeline/final_with_hierarchy/p3_tbox_dedup.json \
  --process-dir outputs/cq_pipeline/process_with_hierarchy_allow1 \
  --final-dir outputs/cq_pipeline/final_with_hierarchy \
  --agg-file outputs/cq_pipeline/process_with_hierarchy_allow0/p4_corpus_suggestions_agg.json \
  --merge-only \
  --min-support 2 \
  --extra-supports 1,3 \
  --allow-new-classes \
  --align-names \
  --dedup-new \
  --dedup-threshold 0.7 \
  --conflict-report outputs/ontoqa/p4_conflicts_with_hierarchy_allow1.json \
  --log-file logs/p4_with_hierarchy_allow1.log

echo ""
echo "✅ P4（merge-only, allow_new_classes=True）完成！"
echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "生成文件："
echo "   - outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s1_allow1.json"
echo "   - outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s2_allow1.json"
echo "   - outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s3_allow1.json"
echo ""
