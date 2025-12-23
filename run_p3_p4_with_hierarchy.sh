#!/bin/bash
# 使用带层级结构的 P2 TBox 运行 P3 去重和 P4 增强流程

# 遇到错误立即退出，并传播管道错误；不启用 -u，避免 conda.sh 访问未绑定 PS1 报错
set -eo pipefail

cd /home/zjx/dev_ops/YangtzeDestoryLLM

# 激活 conda 环境
source /home/zjx/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM

# 设置 PYTHONPATH
export PYTHONPATH=.

# 准备输出目录
mkdir -p outputs/cq_pipeline/final_with_hierarchy \
         outputs/cq_pipeline/process_with_hierarchy \
         outputs/ontoqa \
         logs/ontoqa \
         logs

echo "========================================"
echo "步骤 1/4: 运行 P3 去重"
echo "========================================"

python scripts/manual_p2_to_p3.py \
  --p2-file outputs/cq_pipeline/final/p2_tbox_with_hierarchy.json \
  --output-dir outputs/cq_pipeline/final_with_hierarchy \
  --dedup-threshold 0.7

echo ""
echo "✅ P3 完成！生成文件："
echo "   - outputs/cq_pipeline/final_with_hierarchy/p3_tbox_dedup.json"
echo "   - outputs/cq_pipeline/final_with_hierarchy/dedup_report.json"
echo ""

echo "========================================"
echo "步骤 2/4: 运行 P4 增强（allow_new_classes=False）"
echo "预计耗时: 约 2-3 小时（259 个文档）"
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

python scripts/run_p4_batch.py \
  --base-tbox outputs/cq_pipeline/final_with_hierarchy/p3_tbox_dedup.json \
  --corpus-jsonl data/corpus_for_onto/p4_only.jsonl \
  --process-dir outputs/cq_pipeline/process_with_hierarchy \
  --final-dir outputs/cq_pipeline/final_with_hierarchy \
  --min-support 2 \
  --extra-supports 1,3 \
  --align-names \
  --dedup-new \
  --dedup-threshold 0.7 \
  --conflict-report outputs/ontoqa/p4_conflicts_with_hierarchy_allow0.json \
  --log-file logs/p4_with_hierarchy_allow0.log

echo ""
echo "✅ P4（allow_new_classes=False）完成！"
echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

echo "========================================"
echo "步骤 3/4: 基于同一聚合结果，生成 allow_new_classes=True 版本（merge-only）"
echo "预计耗时: 约 10 秒（仅合并，无需调用 LLM）"
echo "========================================"

python scripts/run_p4_batch.py \
  --base-tbox outputs/cq_pipeline/final_with_hierarchy/p3_tbox_dedup.json \
  --process-dir outputs/cq_pipeline/process_with_hierarchy \
  --final-dir outputs/cq_pipeline/final_with_hierarchy \
  --agg-file outputs/cq_pipeline/process_with_hierarchy/p4_corpus_suggestions_agg.json \
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
echo "✅ P4（allow_new_classes=True，merge-only）完成！生成 s1/s2/s3 的 allow1 版本。"
echo ""

echo "========================================"
echo "步骤 4/4: 计算 OntoQA 指标"
echo "========================================"

# 确保 P2 文件与其他产物在同一目录，便于对比
cp -f outputs/cq_pipeline/final/p2_tbox_with_hierarchy.json \
      outputs/cq_pipeline/final_with_hierarchy/p2_tbox_with_hierarchy.json

python tools/ontoqa_metrics.py \
  --tboxes "outputs/cq_pipeline/final_with_hierarchy/p2_tbox_with_hierarchy.json,outputs/cq_pipeline/final_with_hierarchy/p3_tbox_dedup.json,outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s2_allow0.json,outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s2_allow1.json" \
  --out-csv "outputs/ontoqa/metrics_with_hierarchy.csv" \
  --out-md "outputs/ontoqa/metrics_with_hierarchy.md" \
  --log-file "logs/ontoqa/with_hierarchy.log"

echo ""
echo "✅ OntoQA 指标计算完成！"
echo "   - outputs/ontoqa/metrics_with_hierarchy.csv"
echo "   - outputs/ontoqa/metrics_with_hierarchy.md"
echo ""

echo "========================================"
echo "🎉 全部完成！"
echo "========================================"
echo ""
echo "📊 查看指标对比："
echo "   cat outputs/ontoqa/metrics_with_hierarchy.md"
echo ""
echo "📋 查看详细日志："
echo "   tail -100 logs/p4_with_hierarchy_allow0.log"
echo "   tail -100 logs/p4_with_hierarchy_allow1.log"
echo ""
