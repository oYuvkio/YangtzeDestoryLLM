#!/bin/bash
#===============================================================================
# 单模型评测脚本 - 支持多 tmux 窗口并行运行
#
# 对单个模型执行完整流程：抽取 → 对齐 → 评测
# 可在不同 tmux 窗口中使用不同参数同时运行多个模型
#
# 使用方式：
#   # GPT-4o-mini
#   bash scripts/p5/run_single_model.sh \
#       --model "gpt-4o-mini" \
#       --temperature 0.1 \
#       --interval 1.0
#
#   # GLM-4-Flash (需要指定 base-url)
#   bash scripts/p5/run_single_model.sh \
#       --model "glm-4-flash" \
#       --base-url "https://open.bigmodel.cn/api/paas/v4" \
#       --temperature 0.1 \
#       --interval 0.5
#
#   # Qwen-Turbo
#   bash scripts/p5/run_single_model.sh \
#       --model "qwen-turbo" \
#       --base-url "https://dashscope.aliyuncs.com/compatible-mode/v1" \
#       --temperature 0.1 \
#       --interval 0.5
#
#   # 消融实验（禁用后校验）
#   bash scripts/p5/run_single_model.sh --model "gpt-4o-mini" --no-verify
#
#   # 消融实验（禁用 CoT）
#   bash scripts/p5/run_single_model.sh --model "gpt-4o-mini" --no-cot
#===============================================================================

set -eo pipefail

cd /home/zjx/project/YangtzeDestoryLLM
source /home/zjx/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM
export PYTHONPATH=.

# 禁用代理（避免走 http_proxy/https_proxy）
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
export NO_PROXY="localhost,127.0.0.1,::1"

# 默认参数
MODEL=""
API_KEY=""
BASE_URL="https://api.siliconflow.cn/v1/"
TEMPERATURE=0.1
INTERVAL=3
LIMIT_COUNT=""
NO_COT=false
NO_VERIFY=false
RETRY_ERRORS=false
TBOX="outputs/cq_pipeline/final/tbox_s2_optimized.json"
TEST_FILE="data/p5_eval_pool/final/test_final.jsonl"
TEXT_SOURCE=""  # 完整文本来源文件
OUTPUT_BASE="outputs/eval_models"
REL_MAPPING=""

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --model)
            MODEL="$2"
            shift 2
            ;;
        --base-url)
            BASE_URL="$2"
            shift 2
            ;;
        --api-key)
            API_KEY="$2"
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
        --limit)
            LIMIT_COUNT="$2"
            shift 2
            ;;
        --no-cot)
            NO_COT=true
            shift
            ;;
        --no-verify)
            NO_VERIFY=true
            shift
            ;;
        --retry-errors)
            RETRY_ERRORS=true
            shift
            ;;
        --relation-mapping)
            REL_MAPPING="$2"
            shift 2
            ;;
        --tbox)
            TBOX="$2"
            shift 2
            ;;
        --test-file)
            TEST_FILE="$2"
            shift 2
            ;;
        --text-source)
            TEXT_SOURCE="$2"
            shift 2
            ;;
        --output-base)
            OUTPUT_BASE="$2"
            shift 2
            ;;
        --help)
            echo "使用方式:"
            echo "  --model       模型名称（必须）"
            echo "  --base-url    API base URL（可选）"
            echo "  --api-key     API Key（可选，支持逗号分隔多 Key）"
            echo "  --temperature 温度参数（默认 0.1）"
            echo "  --interval    请求间隔秒数（默认 1.0）"
            echo "  --limit       最多处理的样本数"
            echo "  --no-cot      禁用 CoT（用于消融实验）"
            echo "  --no-verify   禁用后校验（用于消融实验）"
            echo "  --retry-errors 重新跑 error 记录（跳过正常记录）"
            echo "  --relation-mapping 关系映射配置文件路径（启用映射评测）"
            echo "  --tbox        TBox 文件路径"
            echo "  --test-file   测试集文件路径"
            echo "  --text-source 完整文本来源文件（可选，用于映射 doc_id 获取完整文本）"
            echo "  --output-base 输出基目录"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

# 检查必须参数
if [ -z "$MODEL" ]; then
    echo "[ERROR] 必须指定 --model 参数"
    echo "使用 --help 查看帮助"
    exit 1
fi

# 检查文件
if [ ! -f "$TEST_FILE" ]; then
    echo "[ERROR] 测试集不存在: $TEST_FILE"
    exit 1
fi

if [ ! -f "$TBOX" ]; then
    echo "[ERROR] TBox 不存在: $TBOX"
    exit 1
fi

# 构建输出目录
MODEL_DIR="${MODEL//\//_}"  # 替换 / 为 _
MODEL_DIR="${MODEL_DIR//:/_}"  # 替换 : 为 _
OUT_DIR="$OUTPUT_BASE/$MODEL_DIR"

mkdir -p "$OUT_DIR"

MASKED_KEY="未设置"
if [ -n "$API_KEY" ]; then
    if [ ${#API_KEY} -ge 8 ]; then
        MASKED_KEY="${API_KEY:0:4}...${API_KEY: -4}"
    else
        MASKED_KEY="len=${#API_KEY}"
    fi
fi

echo "============================================================"
echo "单模型评测"
echo "============================================================"
echo "模型: $MODEL"
echo "Base URL: ${BASE_URL:-默认}"
echo "API Key: $MASKED_KEY"
echo "Temperature: $TEMPERATURE"
echo "Interval: $INTERVAL"
echo "Limit: ${LIMIT_COUNT:-未设置}"
echo "NO_COT: $NO_COT"
echo "NO_VERIFY: $NO_VERIFY"
echo "RETRY_ERRORS: $RETRY_ERRORS"
echo "RELATION_MAPPING: ${REL_MAPPING:-未启用}"
echo "TEXT_SOURCE: ${TEXT_SOURCE:-未设置}"
echo "输出目录: $OUT_DIR"
echo "============================================================"
echo ""

# 构建 Python 脚本参数
FLAGS=""
[ "$NO_COT" = true ] && FLAGS="$FLAGS --no-cot"
[ "$NO_VERIFY" = true ] && FLAGS="$FLAGS --no-verify"
[ "$RETRY_ERRORS" = true ] && FLAGS="$FLAGS --retry-errors"
[ -n "$BASE_URL" ] && FLAGS="$FLAGS --base-url $BASE_URL"
[ -n "$TEXT_SOURCE" ] && FLAGS="$FLAGS --text-source $TEXT_SOURCE"

# 统一构造 limit 参数
LIMIT_FLAG=""
if [ -n "$LIMIT_COUNT" ]; then
    LIMIT_FLAG="--limit $LIMIT_COUNT"
fi

# API Key 优先使用命令行传入（支持多 Key）
if [ -n "$API_KEY" ]; then
    export OPENAI_API_KEYS="$API_KEY"
    export OPENAI_API_KEY="${API_KEY%%,*}"
fi

PRED_FILE="$OUT_DIR/predictions.jsonl"
ALIGNED_FILE="$OUT_DIR/predictions_aligned.jsonl"
ALIGN_REPORT="$OUT_DIR/align_report.json"
METRICS_FILE="$OUT_DIR/metrics.json"
METRICS_RAW_FILE="$OUT_DIR/metrics_raw.json"

# Step 1: 抽取
echo ""
echo "[Step 1] 运行抽取..."

if [ -f "$PRED_FILE" ]; then
    if [ "$RETRY_ERRORS" = true ]; then
        echo "  发现已有预测，重跑 error 记录..."
        python scripts/p5/run_extraction_on_test.py \
            --test-file "$TEST_FILE" \
            --tbox "$TBOX" \
            --model "$MODEL" \
            --output "$PRED_FILE" \
            --temperature "$TEMPERATURE" \
            --interval "$INTERVAL" \
            $FLAGS \
            $LIMIT_FLAG
    else
        EXISTING_COUNT=$(wc -l < "$PRED_FILE")
        TOTAL_COUNT=$(wc -l < "$TEST_FILE")
        if [ "$EXISTING_COUNT" -eq "$TOTAL_COUNT" ]; then
            echo "  已完成抽取，跳过 ($EXISTING_COUNT/$TOTAL_COUNT)"
        else
            echo "  断点续跑 ($EXISTING_COUNT/$TOTAL_COUNT)..."
            python scripts/p5/run_extraction_on_test.py \
                --test-file "$TEST_FILE" \
                --tbox "$TBOX" \
                --model "$MODEL" \
                --output "$PRED_FILE" \
                --temperature "$TEMPERATURE" \
                --interval "$INTERVAL" \
                --skip-existing \
                $FLAGS \
                $LIMIT_FLAG
        fi
    fi
else
    python scripts/p5/run_extraction_on_test.py \
        --test-file "$TEST_FILE" \
        --tbox "$TBOX" \
        --model "$MODEL" \
        --output "$PRED_FILE" \
        --temperature "$TEMPERATURE" \
        --interval "$INTERVAL" \
        $FLAGS \
        $LIMIT_FLAG
fi

# Step 2: 对齐
echo ""
echo "[Step 2] 按 doc_id 对齐..."
python scripts/p5/align_pred_to_gold.py \
    --gold "$TEST_FILE" \
    --pred "$PRED_FILE" \
    --out "$ALIGNED_FILE" \
    --report "$ALIGN_REPORT"

# Step 2.5: 关系映射（可选）
GOLD_FOR_METRICS="$TEST_FILE"
PRED_FOR_METRICS="$ALIGNED_FILE"
if [ -n "$REL_MAPPING" ]; then
    echo ""
    echo "[Step 2.5] 关系映射..."
    MAPPED_PRED="$OUT_DIR/predictions_mapped.jsonl"
    MAPPED_GOLD="$OUT_DIR/gold_mapped.jsonl"
    python scripts/p5/apply_relation_mapping.py \
        --pred "$ALIGNED_FILE" \
        --gold "$TEST_FILE" \
        --mapping "$REL_MAPPING" \
        --out-pred "$MAPPED_PRED" \
        --out-gold "$MAPPED_GOLD"
    GOLD_FOR_METRICS="$MAPPED_GOLD"
    PRED_FOR_METRICS="$MAPPED_PRED"
fi

# Step 3: 评测
echo ""
echo "[Step 3] 计算指标..."
python tools/abox_metrics.py \
    --gold "$GOLD_FOR_METRICS" \
    --pred "$PRED_FOR_METRICS" \
    --tbox "$TBOX" \
    --out "$METRICS_FILE"

# Step 3.1: 原始类型评测（忽略回退逻辑）
python tools/abox_metrics.py \
    --gold "$GOLD_FOR_METRICS" \
    --pred "$PRED_FOR_METRICS" \
    --tbox "$TBOX" \
    --use-original-type \
    --out "$METRICS_RAW_FILE"

echo ""
echo "============================================================"
echo "评测完成"
echo "============================================================"

# 显示指标摘要
if [ -f "$METRICS_FILE" ]; then
    echo ""
    echo "指标摘要（回退逻辑）:"
    python3 -c "
import json
with open('$METRICS_FILE') as f:
    m = json.load(f)

# 事件指标
em = m.get('event_metrics', {})
print(f'  [Event]')
print(f'    Precision:      {em.get(\"precision\", 0):.4f}')
print(f'    Recall:         {em.get(\"recall\", 0):.4f}')
print(f'    F1:             {em.get(\"f1\", 0):.4f}')

# 三元组指标（严格）
ts = m.get('triple_metrics_strict', {})
print(f'  [Triple-Strict]')
print(f'    Precision:      {ts.get(\"precision\", 0):.4f}')
print(f'    Recall:         {ts.get(\"recall\", 0):.4f}')
print(f'    F1:             {ts.get(\"f1\", 0):.4f}')

# 三元组指标（宽松）
tr = m.get('triple_metrics_relaxed', {})
print(f'  [Triple-Relaxed]')
print(f'    Precision:      {tr.get(\"precision\", 0):.4f}')
print(f'    Recall:         {tr.get(\"recall\", 0):.4f}')
print(f'    F1:             {tr.get(\"f1\", 0):.4f}')

# 核心质量指标
print(f'  [Quality]')
print(f'    TBox Consistency:   {m.get(\"tbox_consistency\", 0):.4f}')
print(f'    Hallucination Rate: {m.get(\"hallucination_rate\", 0):.4f}')
print(f'    Entity Redundancy:  {m.get(\"entity_redundancy_rate\", 0):.4f}')
"
fi

if [ -f "$METRICS_RAW_FILE" ]; then
    echo ""
    echo "指标摘要（原始类型）:"
    python3 -c "
import json
with open('$METRICS_RAW_FILE') as f:
    m = json.load(f)

# 事件指标
em = m.get('event_metrics', {})
print(f'  [Event]')
print(f'    Precision:      {em.get(\"precision\", 0):.4f}')
print(f'    Recall:         {em.get(\"recall\", 0):.4f}')
print(f'    F1:             {em.get(\"f1\", 0):.4f}')

# 三元组指标（严格）
ts = m.get('triple_metrics_strict', {})
print(f'  [Triple-Strict]')
print(f'    Precision:      {ts.get(\"precision\", 0):.4f}')
print(f'    Recall:         {ts.get(\"recall\", 0):.4f}')
print(f'    F1:             {ts.get(\"f1\", 0):.4f}')

# 三元组指标（宽松）
tr = m.get('triple_metrics_relaxed', {})
print(f'  [Triple-Relaxed]')
print(f'    Precision:      {tr.get(\"precision\", 0):.4f}')
print(f'    Recall:         {tr.get(\"recall\", 0):.4f}')
print(f'    F1:             {tr.get(\"f1\", 0):.4f}')

# 核心质量指标
print(f'  [Quality]')
print(f'    TBox Consistency:   {m.get(\"tbox_consistency\", 0):.4f}')
print(f'    Hallucination Rate: {m.get(\"hallucination_rate\", 0):.4f}')
print(f'    Entity Redundancy:  {m.get(\"entity_redundancy_rate\", 0):.4f}')
"
fi

echo ""
echo "输出文件:"
echo "  预测结果: $PRED_FILE"
echo "  对齐结果: $ALIGNED_FILE"
echo "  指标文件(回退): $METRICS_FILE"
echo "  指标文件(原始): $METRICS_RAW_FILE"
