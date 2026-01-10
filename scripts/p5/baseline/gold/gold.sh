#!/bin/bash
# Run Gold annotation for S3 then S2 with configurable parameters.

set -eo pipefail

cd /home/zjx/project/YangtzeDestoryLLM
source /home/zjx/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM
export PYTHONPATH=.

# Disable proxies
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
export NO_PROXY="localhost,127.0.0.1,::1"

# Common inputs
INPUT_FILE="${INPUT_FILE:-data/p5_eval_pool/final/test_final.jsonl}"
TEXT_SOURCE="${TEXT_SOURCE:-data/p5_eval_pool/pool_v3.jsonl}"

# Common flags
TEMPERATURE="${TEMPERATURE:-0.1}"
TOP_P="${TOP_P:-0.1}"
USE_COT="${USE_COT:---use-cot}"
USE_VERIFICATION="${USE_VERIFICATION:---use-verification}"
VERIFICATION_THRESHOLD="${VERIFICATION_THRESHOLD:-0.85}"
STRICT_MODE="${STRICT_MODE:---strict-mode}"
RESUME="${RESUME:---resume}"
YES="${YES:---yes}"

# S3 config
MODEL_S3="${MODEL_S3:-claude-sonnet-4-5-thinking}"
API_KEY_S3="${API_KEY_S3:-sk-Z2nX0nxsxEd8d2NGM3YhbKtfrnjm5IdT1fehJ2urKlwhCi1s}"
BASE_URL_S3="${BASE_URL_S3:-https://www.yxaiapp.com/v1}"
OUTPUT_S3="${OUTPUT_S3:-data/p5_eval_pool/gold_s3_tbox_full_0108.jsonl}"
INTERVAL_S3="${INTERVAL_S3:-30}"

# S2 config
MODEL_S2="${MODEL_S2:-claude-sonnet-4-5-thinking}"
API_KEY_S2="${API_KEY_S2:-sk-Z2nX0nxsxEd8d2NGM3YhbKtfrnjm5IdT1fehJ2urKlwhCi1s}"
BASE_URL_S2="${BASE_URL_S2:-https://www.yxaiapp.com/v1}"
OUTPUT_S2="${OUTPUT_S2:-data/p5_eval_pool/gold_s2_tbox_full_0108.jsonl}"
INTERVAL_S2="${INTERVAL_S2:-30}"

echo "=========================================="
echo "Gold annotation: S3 then S2"
echo "=========================================="
echo ""

echo "[1/2] S3 Gold annotation..."
bash scripts/p5/run_gold_annotation.sh \
    --tbox-version s3 \
    --input "$INPUT_FILE" \
    --text-source "$TEXT_SOURCE" \
    --output "$OUTPUT_S3" \
    --model "$MODEL_S3" \
    --api-key "$API_KEY_S3" \
    --base-url "$BASE_URL_S3" \
    --temperature "$TEMPERATURE" \
    --top-p "$TOP_P" \
    $USE_COT \
    $USE_VERIFICATION \
    --verification-threshold "$VERIFICATION_THRESHOLD" \
    $STRICT_MODE \
    $RESUME \
    $YES \
    --interval "$INTERVAL_S3"

echo ""
echo "[1/2] S3 done: $OUTPUT_S3"

echo ""
echo "[2/2] S2 Gold annotation..."
bash scripts/p5/run_gold_annotation.sh \
    --tbox-version s2 \
    --input "$INPUT_FILE" \
    --text-source "$TEXT_SOURCE" \
    --output "$OUTPUT_S2" \
    --model "$MODEL_S2" \
    --api-key "$API_KEY_S2" \
    --base-url "$BASE_URL_S2" \
    --temperature "$TEMPERATURE" \
    --top-p "$TOP_P" \
    $USE_COT \
    $USE_VERIFICATION \
    --verification-threshold "$VERIFICATION_THRESHOLD" \
    $STRICT_MODE \
    $RESUME \
    $YES \
    --interval "$INTERVAL_S2"

echo ""
echo "[2/2] S2 done: $OUTPUT_S2"
echo ""
echo "=========================================="
echo "Gold annotation completed."
echo "=========================================="
