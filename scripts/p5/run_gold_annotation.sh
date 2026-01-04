#!/bin/bash
# =============================================================================
# 黄金标注生成脚本（支持自定义API配置）
#
# 使用方式：
#   # 直接运行（会提示输入配置）
#   bash scripts/run_gold_annotation.sh
#
#   # 指定配置运行
#   bash scripts/run_gold_annotation.sh \
#       --api-key "sk-xxx" \
#       --base-url "https://api.openai.com/v1" \
#       --model "gpt-4o" \
#       --interval 1.5
#
#   # 使用配置文件
#   bash scripts/run_gold_annotation.sh --config /path/to/config.env
# =============================================================================

set -eo pipefail

# 默认值
DEFAULT_MODEL="claude-opus-4-5 [官逆1]"
DEFAULT_TEMPERATURE="0.1"
DEFAULT_INTERVAL="30"
DEFAULT_MAX_RETRIES="2"
DEFAULT_INPUT="data/p5_eval_pool/test_failed_retry.jsonl"
DEFAULT_OUTPUT="data/p5_eval_pool/gold_failed_retry_v1.jsonl"

# 解析命令行参数
API_KEY="sk-lkcpmipopqwkzjnckppepdozrxreabkqvoqemsaxyqsoalhe"
BASE_URL="https://api.siliconflow.cn/v1/"
MODEL="zai-org/GLM-4.6"
TEMPERATURE="0.1"
INTERVAL="10"
MAX_RETRIES="2"
INPUT_FILE="data/p5_eval_pool/test_failed_retry.jsonl"
OUTPUT_FILE="data/p5_eval_pool/gold_failed_retry_v1.jsonl"
CONFIG_FILE=""
RESUME=""
LIMIT=""

print_usage() {
    echo "使用方式:"
    echo "  bash scripts/run_gold_annotation.sh [选项]"
    echo ""
    echo "选项:"
    echo "  --api-key KEY       API密钥 (必需)"
    echo "  --base-url URL      API基础URL (必需)"
    echo "  --model NAME        模型名称 (默认: $DEFAULT_MODEL)"
    echo "  --temperature T     温度 (默认: $DEFAULT_TEMPERATURE)"
    echo "  --interval SEC      请求间隔秒数 (默认: $DEFAULT_INTERVAL)"
    echo "  --max-retries N     最大重试次数 (默认: $DEFAULT_MAX_RETRIES)"
    echo "  --input FILE        输入文件 (默认: $DEFAULT_INPUT)"
    echo "  --output FILE       输出文件 (默认: $DEFAULT_OUTPUT)"
    echo "  --config FILE       从配置文件加载 (格式见下方)"
    echo "  --resume            断点续跑"
    echo "  --limit N           最多处理N条"
    echo "  --help              显示此帮助"
    echo ""
    echo "配置文件格式 (config.env):"
    echo "  GOLD_API_KEY=sk-xxx"
    echo "  GOLD_BASE_URL=https://api.openai.com/v1"
    echo "  GOLD_MODEL=gpt-4o"
    echo "  GOLD_TEMPERATURE=0.1"
    echo "  GOLD_INTERVAL=1.0"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --api-key)
            API_KEY="$2"
            shift 2
            ;;
        --base-url)
            BASE_URL="$2"
            shift 2
            ;;
        --model)
            MODEL="$2"
            shift 2
            ;;
        --temperature)
            TEMPERATURE="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --max-retries)
            MAX_RETRIES="$2"
            shift 2
            ;;
        --input)
            INPUT_FILE="$2"
            shift 2
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --resume)
            RESUME="--resume"
            shift
            ;;
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --help)
            print_usage
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            print_usage
            exit 1
            ;;
    esac
done

# 加载配置文件（如果指定）
if [[ -n "$CONFIG_FILE" && -f "$CONFIG_FILE" ]]; then
    echo "📄 加载配置文件: $CONFIG_FILE"
    source "$CONFIG_FILE"
    # 配置文件中的变量会覆盖默认值
    API_KEY="${API_KEY:-$GOLD_API_KEY}"
    BASE_URL="${BASE_URL:-$GOLD_BASE_URL}"
    MODEL="${MODEL:-$GOLD_MODEL}"
    TEMPERATURE="${TEMPERATURE:-$GOLD_TEMPERATURE}"
    INTERVAL="${INTERVAL:-$GOLD_INTERVAL}"
fi

# 交互式输入（如果必需参数未提供）
if [[ -z "$API_KEY" ]]; then
    echo ""
    echo "请输入 API 配置（或使用 --config 指定配置文件）"
    echo "================================================"
    read -p "API Key: " API_KEY
fi

if [[ -z "$BASE_URL" ]]; then
    read -p "Base URL (如 https://api.openai.com/v1): " BASE_URL
fi

if [[ -z "$MODEL" ]]; then
    read -p "Model (默认 $DEFAULT_MODEL): " MODEL
    MODEL="${MODEL:-$DEFAULT_MODEL}"
fi

# 应用默认值
TEMPERATURE="${TEMPERATURE:-$DEFAULT_TEMPERATURE}"
INTERVAL="${INTERVAL:-$DEFAULT_INTERVAL}"
MAX_RETRIES="${MAX_RETRIES:-$DEFAULT_MAX_RETRIES}"
INPUT_FILE="${INPUT_FILE:-$DEFAULT_INPUT}"
OUTPUT_FILE="${OUTPUT_FILE:-$DEFAULT_OUTPUT}"

# 验证必需参数
if [[ -z "$API_KEY" ]]; then
    echo "❌ 错误: 必须提供 API Key"
    exit 1
fi

if [[ -z "$BASE_URL" ]]; then
    echo "❌ 错误: 必须提供 Base URL"
    exit 1
fi

# 进入项目目录
cd /home/zjx/project/YangtzeDestoryLLM

# 激活环境
source /home/zjx/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM
export PYTHONPATH=.

# 设置 API 环境变量（覆盖 .env 中的配置）
export OPENAI_API_KEY="$API_KEY"
export OPENAI_API_KEYS=""  # 清空多Key配置

# 创建临时配置文件
TMP_CFG=$(mktemp /tmp/cfg_gold_XXXXXX.yaml)
cat > "$TMP_CFG" << EOF
llm:
  base_url: "$BASE_URL"
  model_name: "$MODEL"
  temperature: $TEMPERATURE
  max_retries: $MAX_RETRIES
  timeout: 180
EOF

# 打印配置
echo ""
echo "========================================"
echo "🏷️  黄金标注生成配置"
echo "========================================"
echo "📍 Base URL: $BASE_URL"
echo "🤖 Model: $MODEL"
echo "🌡️  Temperature: $TEMPERATURE"
echo "⏱️  Interval: ${INTERVAL}s"
echo "🔄 Max Retries: $MAX_RETRIES"
echo "📁 Input: $INPUT_FILE"
echo "📁 Output: $OUTPUT_FILE"
echo "📌 Resume: ${RESUME:-否}"
[[ -n "$LIMIT" ]] && echo "📊 Limit: $LIMIT"
echo "========================================"
echo ""

# 确认执行
read -p "确认开始? [Y/n] " confirm
if [[ "$confirm" =~ ^[Nn] ]]; then
    echo "已取消"
    rm -f "$TMP_CFG"
    exit 0
fi

# 构建命令
CMD="python scripts/p5/generate_gold_independent.py \
    --input \"$INPUT_FILE\" \
    --out \"$OUTPUT_FILE\" \
    --cfg \"$TMP_CFG\" \
    --model \"$MODEL\" \
    --temperature $TEMPERATURE \
    --interval $INTERVAL \
    --max-retries $MAX_RETRIES"

[[ -n "$RESUME" ]] && CMD="$CMD $RESUME"
[[ -n "$LIMIT" ]] && CMD="$CMD --limit $LIMIT"

# 执行
echo ""
echo "🚀 开始执行..."
echo "命令: $CMD"
echo ""

eval $CMD
EXIT_CODE=$?

# 清理
rm -f "$TMP_CFG"

if [[ $EXIT_CODE -eq 0 ]]; then
    echo ""
    echo "✅ 黄金标注生成完成!"
    echo "📁 输出文件: $OUTPUT_FILE"
else
    echo ""
    echo "❌ 执行失败 (退出码: $EXIT_CODE)"
fi

exit $EXIT_CODE
