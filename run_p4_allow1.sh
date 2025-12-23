#!/bin/bash
# P4 增强：allow_new_classes=True
# 用法: bash run_p4_allow1.sh
# 说明: 基于 P3 TBox，允许新增类，增强类、属性和关系

# 遇到错误立即退出
set -eo pipefail

cd /home/zjx/dev_ops/YangtzeDestoryLLM

# 激活 conda 环境
source /home/zjx/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM

# 设置 PYTHONPATH
export PYTHONPATH=.

# 准备输出目录
mkdir -p outputs/cq_pipeline/final_with_hierarchy \
         outputs/cq_pipeline/process_with_hierarchy_allow1 \
         outputs/ontoqa \
         logs

echo "========================================"
echo "P4 增强：allow_new_classes=True"
echo "预计耗时: 约 2-3 小时（259 个文档）"
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

python scripts/run_p4_batch.py \
  --base-tbox outputs/cq_pipeline/final_with_hierarchy/p3_tbox_dedup.json \
  --corpus-jsonl data/corpus_for_onto/p4_only.jsonl \
  --process-dir outputs/cq_pipeline/process_with_hierarchy_allow1 \
  --final-dir outputs/cq_pipeline/final_with_hierarchy \
  --min-support 2 \
  --extra-supports 1,3 \
  --allow-new-classes \
  --align-names \
  --dedup-new \
  --dedup-threshold 0.7 \
  --conflict-report outputs/ontoqa/p4_conflicts_with_hierarchy_allow1.json \
  --log-file logs/p4_with_hierarchy_allow1.log

echo ""
echo "✅ P4（allow_new_classes=True）完成！"
echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "生成文件："
echo "   - outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s1_allow1.json"
echo "   - outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s2_allow1.json"
echo "   - outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s3_allow1.json"
echo ""
echo "查看日志："
echo "   tail -f logs/p4_with_hierarchy_allow1.log"
echo ""
