#!/bin/bash
# 跑完 P4 allow0/allow1 后的一键后处理脚本：
# 1) 计算 OntoQA 全量对比表（P2/P3/P4 六版本）
# 2) 选择一个 best TBox 跑 P5 抽取（dev/test）
# 3) 若存在 gold 标注则跑 ABox 指标评测
#
# 用法：
#   bash run_post_p4_and_p5_eval.sh [BEST_TBOX_PATH]
#   例如：
#   bash run_post_p4_and_p5_eval.sh outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s2_allow1.json
#
# 说明：
# - BEST_TBOX 不传时默认用 s2_allow0（你可按 OntoQA 结果改）
# - ABox gold 文件若不存在会自动跳过评测

set -eo pipefail

cd /home/zjx/dev_ops/YangtzeDestoryLLM

# 激活 conda 环境
source /home/zjx/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM

# 设置 PYTHONPATH
export PYTHONPATH=.

OUT_DIR="outputs/cq_pipeline/final_with_hierarchy"
ONTOQA_OUT_DIR="outputs/ontoqa"
ABOX_OUT_DIR="outputs/abox"
LOG_DIR="logs"

mkdir -p "$ONTOQA_OUT_DIR" "$ABOX_OUT_DIR" "$LOG_DIR"

echo "========================================"
echo "Step 1/3: OntoQA 全量对比"
echo "========================================"

TBOXES=(
  "$OUT_DIR/p2_tbox_with_hierarchy.json"
  "$OUT_DIR/p3_tbox_dedup.json"
  "$OUT_DIR/p4_tbox_augmented_s1_allow0.json"
  "$OUT_DIR/p4_tbox_augmented_s2_allow0.json"
  "$OUT_DIR/p4_tbox_augmented_s3_allow0.json"
  "$OUT_DIR/p4_tbox_augmented_s1_allow1.json"
  "$OUT_DIR/p4_tbox_augmented_s2_allow1.json"
  "$OUT_DIR/p4_tbox_augmented_s3_allow1.json"
)

NAMES=(
  "P2"
  "P3"
  "P4-s1-a0"
  "P4-s2-a0"
  "P4-s3-a0"
  "P4-s1-a1"
  "P4-s2-a1"
  "P4-s3-a1"
)

TBOXES_CSV="$(IFS=,; echo "${TBOXES[*]}")"
NAMES_CSV="$(IFS=,; echo "${NAMES[*]}")"

python tools/ontoqa_metrics.py \
  --tboxes "$TBOXES_CSV" \
  --names "$NAMES_CSV" \
  --baseline "$OUT_DIR/p3_tbox_dedup.json" \
  --sc-mode strict \
  --out-csv "$ONTOQA_OUT_DIR/metrics_full_with_hierarchy.csv" \
  --out-md "$ONTOQA_OUT_DIR/metrics_full_with_hierarchy.md" \
  --md-full \
  --out-json "$ONTOQA_OUT_DIR/metrics_full_with_hierarchy.json" \
  --log-file "$LOG_DIR/ontoqa/run_full_with_hierarchy.log"

echo ""
echo "✅ OntoQA 对比完成："
echo "  - $ONTOQA_OUT_DIR/metrics_full_with_hierarchy.csv"
echo "  - $ONTOQA_OUT_DIR/metrics_full_with_hierarchy.md"

echo ""
echo "========================================"
echo "Step 2/3: P5 抽取（dev/test）"
echo "========================================"

BEST_TBOX="${1:-$OUT_DIR/p4_tbox_augmented_s2_allow0.json}"
BEST_STEM="$(basename "$BEST_TBOX" .json)"
P5_OUT_ROOT="outputs/p5_eval/${BEST_STEM}"

echo "使用 BEST_TBOX=$BEST_TBOX"
mkdir -p "$P5_OUT_ROOT/dev" "$P5_OUT_ROOT/test"

python scripts/run_cq_pipeline.py \
  --start-step p5 \
  --only-stage \
  --p4-file "$BEST_TBOX" \
  --corpus-jsonl data/p5_eval_pool/dev.jsonl \
  --include-context \
  --output-dir "$P5_OUT_ROOT/dev"

python scripts/run_cq_pipeline.py \
  --start-step p5 \
  --only-stage \
  --p4-file "$BEST_TBOX" \
  --corpus-jsonl data/p5_eval_pool/test.jsonl \
  --include-context \
  --output-dir "$P5_OUT_ROOT/test"

echo ""
echo "✅ P5 抽取完成："
echo "  - dev: $P5_OUT_ROOT/dev/p5_batch_results.jsonl"
echo "  - test: $P5_OUT_ROOT/test/p5_batch_results.jsonl"

echo ""
echo "========================================"
echo "Step 3/3: ABox 指标评测（若有 gold）"
echo "========================================"

DEV_GOLD="data/p5_eval_pool/dev_gold.jsonl"
TEST_GOLD="data/p5_eval_pool/test_gold.jsonl"

if [ -f "$DEV_GOLD" ]; then
  python tools/abox_metrics.py \
    --gold "$DEV_GOLD" \
    --pred "$P5_OUT_ROOT/dev/p5_batch_results.jsonl" \
    --tbox "$BEST_TBOX" \
    --time-tolerance-days 1 \
    --geo-syn resources/geo_synonyms.json \
    --out "$ABOX_OUT_DIR/metrics_dev_${BEST_STEM}.json" \
    --log-file "$LOG_DIR/abox/metrics_dev_${BEST_STEM}.log"
  echo "✅ dev 指标已保存：$ABOX_OUT_DIR/metrics_dev_${BEST_STEM}.json"
else
  echo "⚠️ 未找到 dev gold：$DEV_GOLD，跳过 dev 评测"
fi

if [ -f "$TEST_GOLD" ]; then
  python tools/abox_metrics.py \
    --gold "$TEST_GOLD" \
    --pred "$P5_OUT_ROOT/test/p5_batch_results.jsonl" \
    --tbox "$BEST_TBOX" \
    --time-tolerance-days 1 \
    --geo-syn resources/geo_synonyms.json \
    --out "$ABOX_OUT_DIR/metrics_test_${BEST_STEM}.json" \
    --log-file "$LOG_DIR/abox/metrics_test_${BEST_STEM}.log"
  echo "✅ test 指标已保存：$ABOX_OUT_DIR/metrics_test_${BEST_STEM}.json"
else
  echo "⚠️ 未找到 test gold：$TEST_GOLD，跳过 test 评测"
fi

echo ""
echo "🎉 全流程完成。接下来你只要根据 OntoQA + ABox 结果写对比/消融即可。"

