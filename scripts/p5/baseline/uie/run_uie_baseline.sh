#!/bin/bash
#===============================================================================
# UIE Baseline 评测脚本
#
# 流程：抽取（NER+RE）→ 对齐 →（可选）关系映射 → 评测（分任务 Entity/Triple/Event）
#
# 使用方式：
#   bash scripts/p5/baseline/uie/run_uie_baseline.sh \
#       --tbox outputs/kg_final/tbox_final.json \
#       --test-file data/p5_eval_pool/final/test_final.jsonl \
#       --gold-file data/p5_eval_pool/gold_hybrid_tbox.jsonl \
#       --text-source data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl \
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
TBOX="outputs/kg_final/tbox_final.json"
TEST_FILE="data/p5_eval_pool/final/test_final.jsonl"
# Gold 文件用于评测（与 TEST_FILE 分离，TEST_FILE 用于获取 doc_id 列表）
GOLD_FILE="data/p5_eval_pool/gold_hybrid_tbox.jsonl"
OUTPUT_BASE="outputs/eval_models_hybrid"
REL_MAPPING=""
# 完整文本来源：使用 light_pool_v2_dedup.jsonl 的 text 字段（未截断）
TEXT_SOURCE="data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl"
TASK="all"  # ner, re, all

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
        --gold-file)
            GOLD_FILE="$2"
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
        --task)
            TASK="$2"
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
            echo "  --test-file        测试集文件路径（用于获取 doc_id 列表）"
            echo "  --gold-file        Gold 标注文件路径（用于评测对比）"
            echo "  --output-base      输出基目录（默认 outputs/eval_models_hybrid）"
            echo "  --relation-mapping 关系映射配置文件路径（可选）"
            echo "  --text-source      完整文本来源文件（推荐 light_pool_v2_dedup.jsonl）"
            echo "  --task             任务类型：ner（仅实体识别）, re（仅关系抽取）, all（全部，默认）"
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

if [ -n "$GOLD_FILE" ] && [ ! -f "$GOLD_FILE" ]; then
    echo "[ERROR] Gold 文件不存在: $GOLD_FILE"
    exit 1
fi

MODEL_DIR="uie_${MODEL_NAME//\//_}"
MODEL_DIR="${MODEL_DIR//:/_}"
OUT_DIR="$OUTPUT_BASE/$MODEL_DIR"
mkdir -p "$OUT_DIR"

echo "============================================================"
echo "UIE Baseline 评测（分任务：NER/RE/EE）"
echo "============================================================"
echo "Model: $MODEL_NAME"
echo "Precision: $PRECISION"
echo "Batch Size: $BATCH_SIZE"
echo "Interval: $INTERVAL"
echo "Limit: ${LIMIT_COUNT:-未设置}"
echo "Task: $TASK"
echo "TBox: $TBOX"
echo "Test: $TEST_FILE"
echo "Gold: ${GOLD_FILE:-与 Test 相同}"
echo "Relation Mapping: ${REL_MAPPING:-未启用}"
echo "Text Source: ${TEXT_SOURCE:-未设置（可能导致无文本）}"
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

TASK_FLAG="--task $TASK"

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
            $TEXT_SOURCE_FLAG \
            $TASK_FLAG
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
        $TEXT_SOURCE_FLAG \
        $TASK_FLAG
fi

echo ""
echo "[Step 2] 对齐..."
# 使用 GOLD_FILE 进行对齐（如果未指定则使用 TEST_FILE）
GOLD_FOR_ALIGN="${GOLD_FILE:-$TEST_FILE}"
python scripts/p5/align_pred_to_gold.py \
    --gold "$GOLD_FOR_ALIGN" \
    --pred "$PRED_FILE" \
    --out "$ALIGNED_FILE" \
    --report "$ALIGN_REPORT"

echo ""
echo "[Step 2.1] 过滤 Gold/Pred 中的 error 行..."
GOLD_FILTERED="$OUT_DIR/gold_filtered.jsonl"
PRED_FILTERED="$OUT_DIR/predictions_filtered.jsonl"
python scripts/p5/filter_gold_errors.py \
    --gold "$GOLD_FOR_ALIGN" \
    --pred "$ALIGNED_FILE" \
    --gold-out "$GOLD_FILTERED" \
    --pred-out "$PRED_FILTERED"

# ============================================================================
# 归一化 Pipeline（顺序重要：关系映射 → 实体归一化 → 方向归一化）
# ============================================================================

# Step 2.2: 关系映射（先做 - 将非标准关系映射到标准关系）
GOLD_FOR_NORM="$GOLD_FILTERED"
PRED_FOR_NORM="$PRED_FILTERED"
if [ -n "$REL_MAPPING" ]; then
    echo ""
    echo "[Step 2.2] 关系映射（中文→英文，同义词→标准词）..."
    MAPPED_GOLD="$OUT_DIR/gold_relation_mapped.jsonl"
    MAPPED_PRED="$OUT_DIR/predictions_relation_mapped.jsonl"
    python scripts/p5/apply_relation_mapping.py \
        --pred "$PRED_FILTERED" \
        --gold "$GOLD_FILTERED" \
        --mapping "$REL_MAPPING" \
        --out-pred "$MAPPED_PRED" \
        --out-gold "$MAPPED_GOLD"
    GOLD_FOR_NORM="$MAPPED_GOLD"
    PRED_FOR_NORM="$MAPPED_PRED"
fi

# Step 2.3: 实体同义词归一化（第二步）
echo ""
echo "[Step 2.3] 实体同义词归一化..."
SYNONYMS_FILE="configs/entity_synonyms.json"
GOLD_ENTITY_NORM="$OUT_DIR/gold_entity_normalized.jsonl"
PRED_ENTITY_NORM="$OUT_DIR/predictions_entity_normalized.jsonl"
if [ -f "$SYNONYMS_FILE" ]; then
    python scripts/p5/normalize_entities.py \
        --gold "$GOLD_FOR_NORM" \
        --pred "$PRED_FOR_NORM" \
        --synonyms "$SYNONYMS_FILE" \
        --gold-out "$GOLD_ENTITY_NORM" \
        --pred-out "$PRED_ENTITY_NORM"
    GOLD_FOR_DIRECTION="$GOLD_ENTITY_NORM"
    PRED_FOR_DIRECTION="$PRED_ENTITY_NORM"
else
    echo "  同义词库不存在，跳过实体归一化"
    GOLD_FOR_DIRECTION="$GOLD_FOR_NORM"
    PRED_FOR_DIRECTION="$PRED_FOR_NORM"
fi

# Step 2.4: 三元组方向归一化（最后做 - 基于已归一化的关系和实体判断方向）
echo ""
echo "[Step 2.4] 三元组方向归一化..."
GOLD_NORMALIZED="$OUT_DIR/gold_normalized.jsonl"
PRED_NORMALIZED="$OUT_DIR/predictions_normalized.jsonl"
python scripts/p5/normalize_triple_direction.py \
    --gold "$GOLD_FOR_DIRECTION" \
    --pred "$PRED_FOR_DIRECTION" \
    --tbox "$TBOX" \
    --gold-out "$GOLD_NORMALIZED" \
    --pred-out "$PRED_NORMALIZED"

# 设置最终用于评测的文件
GOLD_FOR_METRICS="$GOLD_NORMALIZED"
PRED_FOR_METRICS="$PRED_NORMALIZED"

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

# Step 3.2: 诊断报告
echo ""
echo "[Step 3.2] 生成诊断报告..."
DIAGNOSIS_FILE="$OUT_DIR/diagnosis_report.json"
python scripts/p5/diagnose_extraction.py \
    --gold "$GOLD_FOR_METRICS" \
    --pred "$PRED_FOR_METRICS" \
    --tbox "$TBOX" \
    --output "$DIAGNOSIS_FILE"

echo ""
echo "============================================================"
echo "评测完成"
echo "============================================================"

# 显示评估配置摘要
echo ""
echo "【评估配置】"
if [ -n "$REL_MAPPING" ]; then
    echo "  关系映射:         ✅ 已启用"
else
    echo "  关系映射:         ❌ 未启用"
fi
if [ -f "$SYNONYMS_FILE" ]; then
    echo "  实体同义词归一化: ✅ 已启用"
else
    echo "  实体同义词归一化: ❌ 未启用"
fi
echo "  三元组方向归一化: ✅ 已启用"
echo "  TBox类型回退:     ✅ 已启用（同时输出原始类型指标）"
echo ""
echo "【归一化文件】"
if [ -n "$REL_MAPPING" ]; then
    echo "  关系映射配置: $REL_MAPPING"
fi
if [ -f "$SYNONYMS_FILE" ]; then
    echo "  实体同义词库: $SYNONYMS_FILE"
fi
echo "  归一化Gold:   $GOLD_NORMALIZED"
echo "  归一化Pred:   $PRED_NORMALIZED"
echo "  诊断报告:     $DIAGNOSIS_FILE"

echo ""
echo "【输出文件】"
echo "  预测结果:     $PRED_FILE"
echo "  对齐结果:     $ALIGNED_FILE"
echo "  指标(回退):   $METRICS_FILE"
echo "  指标(原始):   $METRICS_RAW_FILE"
