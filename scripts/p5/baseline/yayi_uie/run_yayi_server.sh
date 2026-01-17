#!/bin/bash
# YAYI-UIE HTTP 服务启动脚本
#
# 使用方式：
#   bash run_yayi_server.sh [port]
#
# 示例：
#   bash run_yayi_server.sh 8000

set -e

# 默认配置
PORT=${1:-8000}
HOST="0.0.0.0"
MODEL_PATH="/hy-tmp/zjx/models/modelscope/wenge-research/yayi-uie"

# 设置 CUDA 环境
export CUDA_VISIBLE_DEVICES=0,1,2
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

# 激活 conda 环境
source ~/miniconda3/etc/profile.d/conda.sh 2>/dev/null || source ~/anaconda3/etc/profile.d/conda.sh 2>/dev/null || true
conda activate yayi 2>/dev/null || conda activate YangtzeLLM 2>/dev/null || true

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

echo "=========================================="
echo "YAYI-UIE HTTP 服务"
echo "=========================================="
echo "模型路径: $MODEL_PATH"
echo "服务地址: http://$HOST:$PORT"
echo "API 文档: http://$HOST:$PORT/docs"
echo "=========================================="

# 启动服务
cd "$PROJECT_ROOT"
python -m scripts.p5.baseline.yayi_uie.api \
    --host "$HOST" \
    --port "$PORT" \
    --model-path "$MODEL_PATH"
