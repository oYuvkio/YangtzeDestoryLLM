#!/bin/bash
# GLM-4-9B 双 TBox (S2/S3) 抽取脚本（仅抽取，不评测）
# 等 Gold 完成后，再用 run_single_model.sh 跑完整评测流程

set -eo pipefail

cd /home/zjx/project/YangtzeDestoryLLM
source /home/zjx/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM
export PYTHONPATH=.

# 禁用代理
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
export NO_PROXY="localhost,127.0.0.1,::1"

# 配置
MODEL="THUDM/GLM-4-9B-0414"
BASE_URL="https://api.siliconflow.cn/v1/"
API_KEY="sk-lkcpmipopqwkzjnckppepdozrxreabkqvoqemsaxyqsoalhe"
TEMPERATURE=0.1
TEXT_SOURCE="data/p5_eval_pool/pool_v3.jsonl"
TEST_FILE="data/p5_eval_pool/final/test_final.jsonl"

# 设置 API Key
export OPENAI_API_KEYS="$API_KEY"
export OPENAI_API_KEY="$API_KEY"

echo "=========================================="
echo "THUDM/GLM-4-9B-0414 双 TBox 抽取（仅抽取，不评测）"
echo "=========================================="
echo ""

# Step 1: TBox S3 抽取
echo "[1/2] TBox S3 抽取..."
OUT_DIR_S3="outputs/eval_models_tbox_s3/THUDM_GLM-4-9B-0414"
mkdir -p "$OUT_DIR_S3"

python scripts/p5/run_extraction_on_test.py \
    --test-file "$TEST_FILE" \
    --tbox outputs/cq_pipeline/final/tbox_s3_optimized.json \
    --model "$MODEL" \
    --output "$OUT_DIR_S3/predictions.jsonl" \
    --temperature $TEMPERATURE \
    --interval 5 \
    --base-url "$BASE_URL" \
    --text-source "$TEXT_SOURCE" \
    --retry-errors

echo ""
echo "[1/2] ✅ TBox S3 抽取完成: $OUT_DIR_S3/predictions.jsonl"

# Step 2: TBox S2 抽取
echo ""
echo "[2/2] TBox S2 抽取..."
OUT_DIR_S2="outputs/eval_models_tbox_s2/THUDM_GLM-4-9B-0414"
mkdir -p "$OUT_DIR_S2"

python scripts/p5/run_extraction_on_test.py \
    --test-file "$TEST_FILE" \
    --tbox outputs/cq_pipeline/final/tbox_s2_optimized.json \
    --model "$MODEL" \
    --output "$OUT_DIR_S2/predictions.jsonl" \
    --temperature $TEMPERATURE \
    --interval 10 \
    --base-url "$BASE_URL" \
    --text-source "$TEXT_SOURCE" \
    --retry-errors

echo ""
echo "[2/2] ✅ TBox S2 抽取完成: $OUT_DIR_S2/predictions.jsonl"

echo ""
echo "=========================================="
echo "✅ 抽取完成!"
echo "=========================================="
echo ""
echo "输出文件:"
echo "  S3: $OUT_DIR_S3/predictions.jsonl"
echo "  S2: $OUT_DIR_S2/predictions.jsonl"
echo ""
echo "⚠️  等 Gold 完成后，运行以下命令进行评测:"
echo ""
echo "  # S3 评测"
echo "  bash scripts/p5/run_single_model.sh \\"
echo "      --model \"$MODEL\" \\"
echo "      --tbox outputs/cq_pipeline/final/tbox_s3_optimized.json \\"
echo "      --test-file data/p5_eval_pool/gold_s3_xxx.jsonl \\"
echo "      --output-base outputs/eval_models_tbox_s3"
echo ""
echo "  # S2 评测"
echo "  bash scripts/p5/run_single_model.sh \\"
echo "      --model \"$MODEL\" \\"
echo "      --tbox outputs/cq_pipeline/final/tbox_s2_optimized.json \\"
echo "      --test-file data/p5_eval_pool/gold_s2_xxx.jsonl \\"
echo "      --output-base outputs/eval_models_tbox_s2"
