#!/bin/bash
#===============================================================================
# UIE Baseline 评测脚本
#
# 流程：抽取 → 对齐 →（可选）关系映射 → 评测（回退/原始类型）
#
# 使用方式：
#   bash scripts/p5/baseline/run_uie_baseline.sh \
#       --tbox outputs/cq_pipeline/final/p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json \
#       --test-file data/p5_eval_pool/final/test_final.jsonl \
#       --relation-mapping configs/relation_mapping.json
#===============================================================================

set -eo pipefail

cd /home/zjx/project/YangtzeDestoryLLM
source /home/zjx/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM
export PYTHONPATH=.

# 载入 .env（用于 HF_ENDPOINT 等配置）
if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

# 默认参数
MODEL_NAME="xusenlin/uie-base"
DEVICE="cpu"
INTERVAL=0
LIMIT_COUNT=""
TBOX=""
TEST_FILE=""
OUTPUT_BASE="outputs/eval_models"
REL_MAPPING=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --model-name)
            MODEL_NAME="$2"
            shift 2
            ;;
        --device)
            DEVICE="$2"
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
        --tbox)
            TBOX="$2"
            shift 2
            ;;
        --test-file)
            TEST_FILE="$2"
            shift 2
            ;;
        --output-base)
            OUTPUT_BASE="$2"
            shift 2
            ;;
        --relation-mapping)
            REL_MAPPING="$2"
            shift 2
            ;;
        --help)
            echo "使用方式:"
            echo "  --model-name       UIE 模型名称或本地路径（默认 xusenlin/uie-base）"
            echo "  --device           推理设备（默认 cpu）"
            echo "  --interval         样本间隔秒数（默认 0）"
            echo "  --limit            最多处理样本数"
            echo "  --tbox             TBox 文件路径（必填）"
            echo "  --test-file        测试集文件路径（必填）"
            echo "  --output-base      输出基目录（默认 outputs/eval_models）"
            echo "  --relation-mapping 关系映射配置文件路径（可选）"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

if [ -z "$TBOX" ] || [ -z "$TEST_FILE" ]; then
    echo "[ERROR] 必须指定 --tbox 与 --test-file"
    exit 1
fi

if [ ! -f "$TBOX" ]; then
    echo "[ERROR] TBox 不存在: $TBOX"
    exit 1
fi

if [ ! -f "$TEST_FILE" ]; then
    echo "[ERROR] 测试集不存在: $TEST_FILE"
    exit 1
fi

MODEL_DIR="uie_${MODEL_NAME//\//_}"
MODEL_DIR="${MODEL_DIR//:/_}"
OUT_DIR="$OUTPUT_BASE/$MODEL_DIR"
mkdir -p "$OUT_DIR"

echo "============================================================"
echo "UIE Baseline 评测"
echo "============================================================"
echo "Model: $MODEL_NAME"
echo "Device: $DEVICE"
echo "Interval: $INTERVAL"
echo "Limit: ${LIMIT_COUNT:-未设置}"
echo "TBox: $TBOX"
echo "Test: $TEST_FILE"
echo "Relation Mapping: ${REL_MAPPING:-未启用}"
echo "Output: $OUT_DIR"
echo "============================================================"
echo ""

LIMIT_FLAG=""
if [ -n "$LIMIT_COUNT" ]; then
    LIMIT_FLAG="--limit $LIMIT_COUNT"
fi

PRED_FILE="$OUT_DIR/predictions.jsonl"
ALIGNED_FILE="$OUT_DIR/predictions_aligned.jsonl"
ALIGN_REPORT="$OUT_DIR/align_report.json"
METRICS_FILE="$OUT_DIR/metrics.json"
METRICS_RAW_FILE="$OUT_DIR/metrics_raw.json"

echo ""
echo "[Step 1] 抽取..."
python scripts/p5/baseline/run_uie_baseline.py \
    --model-name "$MODEL_NAME" \
    --device "$DEVICE" \
    --tbox "$TBOX" \
    --test-file "$TEST_FILE" \
    --output "$PRED_FILE" \
    --interval "$INTERVAL" \
    $LIMIT_FLAG

echo ""
echo "[Step 2] 对齐..."
python scripts/p5/align_pred_to_gold.py \
    --gold "$TEST_FILE" \
    --pred "$PRED_FILE" \
    --out "$ALIGNED_FILE" \
    --report "$ALIGN_REPORT"

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

echo ""
echo "[Step 3] 评测（回退）..."
python tools/abox_metrics.py \
    --gold "$GOLD_FOR_METRICS" \
    --pred "$PRED_FOR_METRICS" \
    --tbox "$TBOX" \
    --out "$METRICS_FILE"

echo ""
echo "[Step 3.1] 评测（原始类型）..."
python tools/abox_metrics.py \
    --gold "$GOLD_FOR_METRICS" \
    --pred "$PRED_FOR_METRICS" \
    --tbox "$TBOX" \
    --use-original-type \
    --out "$METRICS_RAW_FILE"

echo ""
echo "============================================================"
echo "完成"
echo "============================================================"
echo "预测结果: $PRED_FILE"
echo "对齐结果: $ALIGNED_FILE"
echo "指标(回退): $METRICS_FILE"
echo "指标(原始): $METRICS_RAW_FILE"
