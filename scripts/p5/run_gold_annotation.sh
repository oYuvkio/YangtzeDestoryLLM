#!/bin/bash
# =============================================================================
# 黄金标注生成脚本（支持 TBox 约束 + 自定义 API 配置）
#
# 支持两种模式：
#   1. 独立 Schema 模式（默认）：使用预定义的通用 Schema
#   2. TBox 约束模式：使用项目 TBox 约束生成，确保 Gold 与 Pred Schema 对齐
#
# 使用方式：
#   # 独立 Schema 模式（默认）
#   bash scripts/p5/run_gold_annotation.sh \
#       --api-key "sk-xxx" \
#       --base-url "https://api.openai.com/v1" \
#       --model "gpt-4o"
#
#   # TBox 约束模式（S2 版本）
#   bash scripts/p5/run_gold_annotation.sh \
#       --tbox-version s2 \
#       --model "gpt-4o" \
#       --base-url "https://api.openai.com/v1"
#
#   # TBox 约束模式（S3 版本）
#   bash scripts/p5/run_gold_annotation.sh \
#       --tbox-version s3 \
#       --model "gemini-2.0-flash-thinking" \
#       --base-url "https://xxx"
#
#   # 小规模测试
#   bash scripts/p5/run_gold_annotation.sh \
#       --tbox-version s3 \
#       --model "gpt-4o" \
#       --limit 20
# =============================================================================

set -eo pipefail

# 项目目录
PROJECT_DIR="/home/zjx/project/YangtzeDestoryLLM"
cd "$PROJECT_DIR"

# 激活环境
source /home/zjx/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM
export PYTHONPATH=.

# 禁用代理（避免本地服务连接问题）
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
export NO_PROXY="localhost,127.0.0.1,::1"

# ==============================================================================
# 默认配置
# ==============================================================================
DEFAULT_MODEL="gpt-4o"
DEFAULT_TEMPERATURE="0.1"
DEFAULT_INTERVAL="1.0"
DEFAULT_MAX_RETRIES="3"
DEFAULT_INPUT="data/p5_eval_pool/final/test_final.jsonl"
DEFAULT_BASE_URL="https://api.openai.com/v1"

# 运行时变量
API_KEY=""
BASE_URL="$DEFAULT_BASE_URL"
MODEL="$DEFAULT_MODEL"
TEMPERATURE="$DEFAULT_TEMPERATURE"
INTERVAL="$DEFAULT_INTERVAL"
MAX_RETRIES="$DEFAULT_MAX_RETRIES"
INPUT_FILE="$DEFAULT_INPUT"
OUTPUT_FILE=""
CONFIG_FILE=""
RESUME=""
LIMIT=""
TOP_P=""
TBOX_VERSION=""  # 空表示独立 Schema 模式，s2/s3 表示 TBox 约束模式
NO_CONFIRM=""
TEXT_SOURCE=""  # 完整文本来源文件

# CoT 和幻觉过滤配置（默认开启）
USE_COT="1"
USE_VERIFICATION="1"
VERIFICATION_THRESHOLD="0.7"
STRICT_MODE=""

# ==============================================================================
# 帮助信息
# ==============================================================================
print_usage() {
    echo "使用方式:"
    echo "  bash scripts/p5/run_gold_annotation.sh [选项]"
    echo ""
    echo "模式选择:"
    echo "  --tbox-version VER  使用 TBox 约束模式 (s2/s3)，不指定则使用独立 Schema 模式"
    echo ""
    echo "API 配置:"
    echo "  --api-key KEY       API 密钥 (必需，或通过环境变量/配置文件提供)"
    echo "  --base-url URL      API 基础 URL (默认: $DEFAULT_BASE_URL)"
    echo "  --model NAME        模型名称 (默认: $DEFAULT_MODEL)"
    echo "  --temperature T     温度参数 (默认: $DEFAULT_TEMPERATURE)"
    echo "  --top-p P           Top-P 参数 (可选)"
    echo ""
    echo "CoT 和幻觉过滤配置（TBox 模式专用）:"
    echo "  --use-cot           使用 CoT 思维链 (默认开启)"
    echo "  --no-cot            禁用 CoT"
    echo "  --use-verification  使用幻觉过滤后校验 (默认开启)"
    echo "  --no-verification   禁用后校验"
    echo "  --verification-threshold T  模糊匹配阈值 (默认: 0.7，Gold 推荐)"
    echo "  --strict-mode       严格模式（仅精确匹配，不推荐用于 Gold）"
    echo ""
    echo "运行控制:"
    echo "  --interval SEC      请求间隔秒数 (默认: $DEFAULT_INTERVAL)"
    echo "  --max-retries N     最大重试次数 (默认: $DEFAULT_MAX_RETRIES)"
    echo "  --input FILE        输入文件 (默认: $DEFAULT_INPUT)"
    echo "  --text-source FILE  完整文本来源文件（可选，用于映射 doc_id 获取完整文本）"
    echo "  --output FILE       输出文件 (默认根据模式自动生成)"
    echo "  --resume            断点续跑"
    echo "  --limit N           最多处理 N 条"
    echo "  --config FILE       从配置文件加载"
    echo "  -y, --yes           跳过确认提示"
    echo "  --help              显示此帮助"
    echo ""
    echo "示例:"
    echo "  # TBox 约束模式 + CoT + 幻觉过滤 (推荐用于评测)"
    echo "  bash scripts/p5/run_gold_annotation.sh \\"
    echo "      --tbox-version s2 \\"
    echo "      --model gpt-4o \\"
    echo "      --api-key \"\$OPENAI_API_KEY\" \\"
    echo "      --use-cot \\"
    echo "      --use-verification \\"
    echo "      --verification-threshold 0.7"
    echo ""
    echo "  # 快速模式（无 CoT、无校验）"
    echo "  bash scripts/p5/run_gold_annotation.sh \\"
    echo "      --tbox-version s2 \\"
    echo "      --model gpt-4o \\"
    echo "      --no-cot \\"
    echo "      --no-verification"
}

# ==============================================================================
# 解析命令行参数
# ==============================================================================
while [[ $# -gt 0 ]]; do
    case $1 in
        --tbox-version)
            TBOX_VERSION="$2"
            shift 2
            ;;
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
        --top-p)
            TOP_P="$2"
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
        --text-source)
            TEXT_SOURCE="$2"
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
        # CoT 和幻觉过滤参数
        --use-cot)
            USE_COT="1"
            shift
            ;;
        --no-cot)
            USE_COT=""
            shift
            ;;
        --use-verification)
            USE_VERIFICATION="1"
            shift
            ;;
        --no-verification)
            USE_VERIFICATION=""
            shift
            ;;
        --verification-threshold)
            VERIFICATION_THRESHOLD="$2"
            shift 2
            ;;
        --strict-mode)
            STRICT_MODE="--strict-mode"
            shift
            ;;
        -y|--yes)
            NO_CONFIRM="1"
            shift
            ;;
        --help|-h)
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

# ==============================================================================
# 加载配置文件
# ==============================================================================
if [[ -n "$CONFIG_FILE" && -f "$CONFIG_FILE" ]]; then
    echo "📄 加载配置文件: $CONFIG_FILE"
    source "$CONFIG_FILE"
    API_KEY="${API_KEY:-$GOLD_API_KEY}"
    BASE_URL="${BASE_URL:-$GOLD_BASE_URL}"
    MODEL="${MODEL:-$GOLD_MODEL}"
    TEMPERATURE="${TEMPERATURE:-$GOLD_TEMPERATURE}"
    INTERVAL="${INTERVAL:-$GOLD_INTERVAL}"
fi

# ==============================================================================
# 交互式输入（如果必需参数未提供）
# ==============================================================================
if [[ -z "$API_KEY" ]]; then
    # 尝试从环境变量获取
    API_KEY="${OPENAI_API_KEY:-}"
fi

if [[ -z "$API_KEY" ]]; then
    echo ""
    echo "请输入 API 配置"
    echo "================================================"
    read -p "API Key: " API_KEY
fi

if [[ -z "$API_KEY" ]]; then
    echo "❌ 错误: 必须提供 API Key (--api-key 或 OPENAI_API_KEY 环境变量)"
    exit 1
fi

# ==============================================================================
# 确定运行模式和输出路径
# ==============================================================================
if [[ -n "$TBOX_VERSION" ]]; then
    # TBox 约束模式
    MODE="tbox"
    TBOX_FILE="outputs/cq_pipeline/final/tbox_${TBOX_VERSION}_optimized.json"

    # 检查 TBox 文件是否存在
    if [[ ! -f "$TBOX_FILE" ]]; then
        echo "⚠️  TBox 文件不存在: $TBOX_FILE"
        echo "   正在创建优化版 TBox..."
        python scripts/create_optimized_tbox.py --version "$TBOX_VERSION"

        if [[ ! -f "$TBOX_FILE" ]]; then
            echo "❌ 无法创建 TBox 文件"
            exit 1
        fi
    fi

    # 默认输出文件
    OUTPUT_FILE="${OUTPUT_FILE:-data/p5_eval_pool/gold_${TBOX_VERSION}.jsonl}"
    PYTHON_SCRIPT="scripts/generate_gold_with_tbox.py"
else
    # 独立 Schema 模式
    MODE="independent"
    TBOX_FILE=""
    OUTPUT_FILE="${OUTPUT_FILE:-data/p5_eval_pool/gold_independent.jsonl}"
    PYTHON_SCRIPT="scripts/p5/generate_gold_independent.py"
fi

# ==============================================================================
# 设置 API 环境变量
# ==============================================================================
export OPENAI_API_KEY="$API_KEY"
export OPENAI_API_KEYS=""  # 清空多 Key 配置，使用单 Key

# ==============================================================================
# 创建临时配置文件
# ==============================================================================
TMP_CFG=$(mktemp /tmp/cfg_gold_XXXXXX.yaml)
cat > "$TMP_CFG" << EOF
llm:
  base_url: "$BASE_URL"
  model_name: "$MODEL"
  temperature: $TEMPERATURE
  max_retries: $MAX_RETRIES
  timeout: 180
EOF

# ==============================================================================
# 打印配置
# ==============================================================================
echo ""
echo "========================================"
echo "🏷️  黄金标注生成配置"
echo "========================================"
if [[ "$MODE" == "tbox" ]]; then
    echo "📋 模式:       TBox 约束模式 (${TBOX_VERSION})"
    echo "📋 TBox 文件:  $TBOX_FILE"
    echo "🧠 CoT 思维链: $([[ -n "$USE_COT" ]] && echo '✅ 开启' || echo '❌ 关闭')"
    echo "🔍 幻觉过滤:   $([[ -n "$USE_VERIFICATION" ]] && echo '✅ 开启' || echo '❌ 关闭')"
    [[ -n "$USE_VERIFICATION" ]] && echo "📏 匹配阈值:   $VERIFICATION_THRESHOLD"
    [[ -n "$STRICT_MODE" ]] && echo "⚠️  严格模式:   是"
else
    echo "📋 模式:       独立 Schema 模式"
fi
echo "📍 Base URL:   $BASE_URL"
echo "🤖 模型:       $MODEL"
echo "🌡️  温度:       $TEMPERATURE"
[[ -n "$TOP_P" ]] && echo "🎲 Top-P:      $TOP_P"
echo "⏱️  请求间隔:   ${INTERVAL}s"
echo "🔄 最大重试:   $MAX_RETRIES"
echo "📁 输入文件:   $INPUT_FILE"
[[ -n "$TEXT_SOURCE" ]] && echo "📂 文本来源:   $TEXT_SOURCE"
echo "📁 输出文件:   $OUTPUT_FILE"
echo "📌 断点续跑:   ${RESUME:-否}"
[[ -n "$LIMIT" ]] && echo "📊 限制条数:   $LIMIT"
echo "========================================"
echo ""

# ==============================================================================
# 确认执行
# ==============================================================================
if [[ -z "$NO_CONFIRM" ]]; then
    read -p "确认开始? [Y/n] " confirm
    if [[ "$confirm" =~ ^[Nn] ]]; then
        echo "已取消"
        rm -f "$TMP_CFG"
        exit 0
    fi
fi

# ==============================================================================
# 构建命令
# ==============================================================================
if [[ "$MODE" == "tbox" ]]; then
    # TBox 约束模式
    CMD="python $PYTHON_SCRIPT"
    CMD="$CMD --input \"$INPUT_FILE\""
    CMD="$CMD --tbox \"$TBOX_FILE\""
    CMD="$CMD --output \"$OUTPUT_FILE\""
    CMD="$CMD --model \"$MODEL\""
    CMD="$CMD --base-url \"$BASE_URL\""
    CMD="$CMD --temperature $TEMPERATURE"
    CMD="$CMD --interval $INTERVAL"
    CMD="$CMD --max-retries $MAX_RETRIES"

    # CoT 配置
    [[ -n "$USE_COT" ]] && CMD="$CMD --use-cot" || CMD="$CMD --no-cot"

    # 幻觉过滤配置
    [[ -n "$USE_VERIFICATION" ]] && CMD="$CMD --use-verification" || CMD="$CMD --no-verification"
    [[ -n "$USE_VERIFICATION" ]] && CMD="$CMD --verification-threshold $VERIFICATION_THRESHOLD"
    [[ -n "$STRICT_MODE" ]] && CMD="$CMD $STRICT_MODE"

    [[ -n "$TOP_P" ]] && CMD="$CMD --top-p $TOP_P"
    [[ -n "$RESUME" ]] && CMD="$CMD $RESUME"
    [[ -n "$LIMIT" ]] && CMD="$CMD --limit $LIMIT"
    [[ -n "$TEXT_SOURCE" ]] && CMD="$CMD --text-source \"$TEXT_SOURCE\""
else
    # 独立 Schema 模式
    CMD="python $PYTHON_SCRIPT"
    CMD="$CMD --input \"$INPUT_FILE\""
    CMD="$CMD --out \"$OUTPUT_FILE\""
    CMD="$CMD --cfg \"$TMP_CFG\""
    CMD="$CMD --model \"$MODEL\""
    CMD="$CMD --temperature $TEMPERATURE"
    CMD="$CMD --interval $INTERVAL"
    CMD="$CMD --max-retries $MAX_RETRIES"

    [[ -n "$RESUME" ]] && CMD="$CMD $RESUME"
    [[ -n "$LIMIT" ]] && CMD="$CMD --limit $LIMIT"
fi

# ==============================================================================
# 执行
# ==============================================================================
echo ""
echo "🚀 开始执行..."
echo "命令: $CMD"
echo ""

eval $CMD
EXIT_CODE=$?

# ==============================================================================
# 清理
# ==============================================================================
rm -f "$TMP_CFG"

# ==============================================================================
# 完成后统计
# ==============================================================================
if [[ $EXIT_CODE -eq 0 ]]; then
    echo ""
    echo "========================================"
    echo "✅ 黄金标注生成完成!"
    echo "========================================"
    echo "📁 输出文件: $OUTPUT_FILE"

    if [[ -f "$OUTPUT_FILE" ]]; then
        echo ""
        echo "统计信息:"
        python3 -c "
import json
from collections import Counter

rels = Counter()
n_samples = 0
n_triples = 0
n_events = 0
n_errors = 0

with open('$OUTPUT_FILE') as f:
    for line in f:
        if not line.strip():
            continue
        data = json.loads(line)
        n_samples += 1
        if data.get('parse_error') or data.get('error'):
            n_errors += 1
            continue
        triples = data.get('triples', [])
        n_triples += len(triples)
        n_events += len(data.get('events', []))
        for t in triples:
            rels[t.get('predicate', '')] += 1

print(f'  样本数:     {n_samples}')
print(f'  成功:       {n_samples - n_errors}')
print(f'  失败:       {n_errors}')
print(f'  三元组数:   {n_triples}')
print(f'  事件数:     {n_events}')
print(f'  关系种类:   {len(rels)}')
print()
print('  关系分布 (Top 10):')
for r, c in rels.most_common(10):
    print(f'    {r}: {c}')
"
    fi
else
    echo ""
    echo "❌ 执行失败 (退出码: $EXIT_CODE)"
fi

exit $EXIT_CODE
