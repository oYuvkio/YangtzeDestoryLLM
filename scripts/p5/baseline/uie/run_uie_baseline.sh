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

# 默认使用 paddle 环境（需要预先创建并安装 paddlenlp）
# 创建方式: conda create -n paddle python=3.10 && conda activate paddle && pip install paddlenlp paddlepaddle-gpu
#CONDA_ENV="${CONDA_ENV:-paddle}"
#conda activate "$CONDA_ENV"
export PYTHONPATH=.

# 载入 .env（用于 HF_ENDPOINT 等配置）
if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

# 默认参数
MODEL_NAME="paddlenlp/PP-UIE-0.5B"
PRECISION="float16"
BATCH_SIZE=1
INTERVAL=0
LIMIT_COUNT=""
TBOX="outputs/cq_pipeline/final/tbox_s2_optimized.json"
TEST_FILE="data/p5_eval_pool/gold_s2_tbox_full_0105.jsonl"
OUTPUT_BASE="outputs/eval_models_tbox_s2"
REL_MAPPING=""
TEXT_SOURCE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --model-name)
            MODEL_NAME="$2"
            shift 2
            ;;
        --precision)
            PRECISION="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
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
        --text-source)
            if [ -z "$2" ] || [[ "$2" == --* ]]; then
                echo "[ERROR] --text-source 需要指定文件路径"
                exit 1
            fi
            TEXT_SOURCE="$2"
            shift 2
            ;;
        --help)
            echo "使用方式:"
            echo "  --model-name       PP-UIE 模型名称（默认 paddlenlp/PP-UIE-0.5B，可选 1.5B/7B/14B）"
            echo "  --precision        模型精度（默认 float16，可选 bfloat16/float32）"
            echo "  --batch-size       批处理大小（默认 1）"
            echo "  --interval         样本间隔秒数（默认 0）"
            echo "  --limit            最多处理样本数"
            echo "  --tbox             TBox 文件路径（必填）"
            echo "  --test-file        测试集文件路径（必填）"
            echo "  --output-base      输出基目录（默认 outputs/eval_models）"
            echo "  --relation-mapping 关系映射配置文件路径（可选）"
            echo "  --text-source      完整文本来源文件（可选，通过 doc_id 映射获取完整文本）"
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
echo "Precision: $PRECISION"
echo "Batch Size: $BATCH_SIZE"
echo "Interval: $INTERVAL"
echo "Limit: ${LIMIT_COUNT:-未设置}"
echo "TBox: $TBOX"
echo "Test: $TEST_FILE"
echo "Relation Mapping: ${REL_MAPPING:-未启用}"
echo "Text Source: ${TEXT_SOURCE:-未设置（使用输入文件中的文本）}"
echo "Output: $OUT_DIR"
echo "============================================================"
echo ""

LIMIT_FLAG=""
if [ -n "$LIMIT_COUNT" ]; then
    LIMIT_FLAG="--limit $LIMIT_COUNT"
fi

TEXT_SOURCE_FLAG=""
if [ -n "$TEXT_SOURCE" ]; then
    TEXT_SOURCE_FLAG="--text-source $TEXT_SOURCE"
fi

PRED_FILE="$OUT_DIR/predictions.jsonl"
ALIGNED_FILE="$OUT_DIR/predictions_aligned.jsonl"
ALIGN_REPORT="$OUT_DIR/align_report.json"
METRICS_FILE="$OUT_DIR/metrics.json"
METRICS_RAW_FILE="$OUT_DIR/metrics_raw.json"

echo ""
echo "[Step 1] 抽取..."

# 断点续传检测
if [ -f "$PRED_FILE" ]; then
    EXISTING_COUNT=$(wc -l < "$PRED_FILE")
    TOTAL_COUNT=$(wc -l < "$TEST_FILE")
    if [ "$EXISTING_COUNT" -eq "$TOTAL_COUNT" ]; then
        echo "  已完成抽取，跳过 ($EXISTING_COUNT/$TOTAL_COUNT)"
    else
        echo "  发现已有预测 $EXISTING_COUNT/$TOTAL_COUNT 条，启用断点续传..."
        python scripts/p5/baseline/uie/run_uie_baseline.py \
            --model-name "$MODEL_NAME" \
            --precision "$PRECISION" \
            --batch-size "$BATCH_SIZE" \
            --tbox "$TBOX" \
            --test-file "$TEST_FILE" \
            --output "$PRED_FILE" \
            --interval "$INTERVAL" \
            --skip-existing \
            $LIMIT_FLAG \
            $TEXT_SOURCE_FLAG
    fi
else
    python scripts/p5/baseline/uie/run_uie_baseline.py \
        --model-name "$MODEL_NAME" \
        --precision "$PRECISION" \
        --batch-size "$BATCH_SIZE" \
        --tbox "$TBOX" \
        --test-file "$TEST_FILE" \
        --output "$PRED_FILE" \
        --interval "$INTERVAL" \
        $LIMIT_FLAG \
        $TEXT_SOURCE_FLAG
fi

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
