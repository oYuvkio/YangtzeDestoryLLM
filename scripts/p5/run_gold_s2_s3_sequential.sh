#!/bin/bash
# Gold 标注生成脚本：先 S2，再 S3（顺序执行）

set -eo pipefail

cd /home/zjx/project/YangtzeDestoryLLM

echo "=========================================="
echo "Gold 标注顺序生成：S2 -> S3"
echo "=========================================="
echo ""

# Step 1: S2
echo "[1/2] 开始生成 S2 Gold..."
bash scripts/p5/run_gold_annotation.sh \
    --tbox-version s2 \
    --input data/p5_eval_pool/final/test_final.jsonl \
    --text-source data/p5_eval_pool/pool_v3.jsonl \
    --output data/p5_eval_pool/gold_s2_tbox_full_0105.jsonl \
    --model "claude-opus-4-5-thinking" \
    --api-key "sk-ttGQ7LnlVIvsZVZA1U7HLBrjuBfUUvWvMEScv4k1SU3HgebG" \
    --base-url "https://www.yxaiapp.com/v1" \
    --temperature 0.1 \
    --top-p 0.1 \
    --use-cot \
    --use-verification \
    --verification-threshold 0.85 \
    --strict-mode \
    --resume \
    --interval 30 \

echo ""
echo "[1/2] ✅ S2 Gold 生成完成"
echo ""

# Step 2: S3
echo "[2/2] 开始生成 S3 Gold..."
bash scripts/p5/run_gold_annotation.sh \
    --tbox-version s3 \
    --input data/p5_eval_pool/final/test_final.jsonl \
    --text-source data/p5_eval_pool/pool_v3.jsonl \
    --output data/p5_eval_pool/gold_s3_tbox_full_0105_v2.jsonl \
    --model "claude-opus-4-5-thinking" \
    --api-key "sk-ttGQ7LnlVIvsZVZA1U7HLBrjuBfUUvWvMEScv4k1SU3HgebG" \
    --base-url "https://www.yxaiapp.com/v1" \
    --temperature 0.1 \
    --top-p 0.1 \
    --use-cot \
    --use-verification \
    --verification-threshold 0.85 \
    --strict-mode \
    --resume \
    --interval 30 \

echo ""
echo "[2/2] ✅ S3 Gold 生成完成"
echo ""
echo "=========================================="
echo "✅ 全部完成!"
echo "=========================================="
echo "输出文件:"
echo "  S2: data/p5_eval_pool/gold_s2_tbox_full_0105.jsonl"
echo "  S3: data/p5_eval_pool/gold_s3_tbox_full_0105_v2.jsonl"
