#!/bin/bash
# =============================================================================
# 黄金标注二次审查启动脚本
#
# 使用方式：
#   bash scripts/run_review_gold.sh
# =============================================================================

set -eo pipefail

cd /home/zjx/project/YangtzeDestoryLLM

source /home/zjx/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM
export PYTHONPATH=.

# =============================================================================
# 配置区域（根据需要修改）
# =============================================================================
API_KEY="sk-lkcpmipopqwkzjnckppepdozrxreabkqvoqemsaxyqsoalhe"
BASE_URL="https://api.siliconflow.cn/v1/"
MODEL="zai-org/GLM-4.6"  # 审查任务用小模型即可
MIN_SCORE=3                        # 低于此分数的样本被拒绝
INTERVAL=5                       # 请求间隔（秒）

# 输入文件（合并两个标注结果）
INPUT_FILES=(
    "data/p5_eval_pool/gold_independent_v1.jsonl"
    "data/p5_eval_pool/gold_failed_retry_v1.jsonl"
)

# 输出文件
OUT_ACCEPTED="data/p5_eval_pool/gold_reviewed.jsonl"
OUT_REJECTED="data/p5_eval_pool/gold_rejected.jsonl"
REPORT="data/p5_eval_pool/review_report.json"

# =============================================================================
# 执行
# =============================================================================
echo "========================================"
echo "🔍 黄金标注二次审查"
echo "========================================"
echo "📍 Base URL: $BASE_URL"
echo "🤖 Model: $MODEL"
echo "📊 最低分数: $MIN_SCORE"
echo "⏱️  请求间隔: ${INTERVAL}s"
echo "📁 输入文件:"
for f in "${INPUT_FILES[@]}"; do
    if [[ -f "$f" ]]; then
        count=$(wc -l < "$f")
        echo "    - $f ($count 行)"
    else
        echo "    - $f (不存在)"
    fi
done
echo "📁 输出:"
echo "    - 通过: $OUT_ACCEPTED"
echo "    - 拒绝: $OUT_REJECTED"
echo "========================================"
echo ""

read -p "确认开始审查? [Y/n] " confirm
if [[ "$confirm" =~ ^[Nn] ]]; then
    echo "已取消"
    exit 0
fi

# 设置环境变量
export OPENAI_API_KEY="$API_KEY"

# 构建输入参数
INPUT_ARGS=""
for f in "${INPUT_FILES[@]}"; do
    if [[ -f "$f" ]]; then
        INPUT_ARGS="$INPUT_ARGS $f"
    fi
done

# 运行审查
python scripts/review_gold_annotations.py \
    --input $INPUT_ARGS \
    --out-accepted "$OUT_ACCEPTED" \
    --out-rejected "$OUT_REJECTED" \
    --report "$REPORT" \
    --base-url "$BASE_URL" \
    --model "$MODEL" \
    --min-score $MIN_SCORE \
    --interval $INTERVAL \
    --resume

echo ""
echo "✅ 审查完成!"
echo "📊 报告: $REPORT"
