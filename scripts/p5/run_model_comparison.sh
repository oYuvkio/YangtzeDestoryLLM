#!/bin/bash
#===============================================================================
# 多模型对比评测一键脚本
#
# 对指定的多个模型运行：抽取 → 对齐 → 评测 → 汇总
# 模型依次执行，如需并行请使用 run_single_model.sh 在多个 tmux 窗口运行
#
# 使用方式：
#   # 运行完整对比（默认三个模型）
#   bash scripts/p5/run_model_comparison.sh
#
#   # 自定义模型列表
#   bash scripts/p5/run_model_comparison.sh --models "gpt-4o-mini,glm-4-flash,qwen-turbo"
#
#   # 小批量测试
#   bash scripts/p5/run_model_comparison.sh --limit 10
#
#   # 消融实验
#   bash scripts/p5/run_model_comparison.sh --no-cot
#   bash scripts/p5/run_model_comparison.sh --no-verify
#
# 并行运行提示：
#   若需在多个 tmux 窗口并行运行不同模型，请使用 run_single_model.sh：
#   窗口1: bash scripts/p5/run_single_model.sh --model "gpt-4o-mini" --interval 1.0
#   窗口2: bash scripts/p5/run_single_model.sh --model "glm-4-flash" --base-url "..." --interval 0.5
#   窗口3: bash scripts/p5/run_single_model.sh --model "qwen-turbo" --base-url "..." --interval 0.5
#   完成后汇总: python scripts/p5/compare_models.py --input-dir outputs/eval_models --models "..."
#===============================================================================

set -eo pipefail

cd /home/zjx/project/YangtzeDestoryLLM
source /home/zjx/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM
export PYTHONPATH=.

# 默认参数
MODELS="gpt-4o-mini,glm-4-flash,qwen-turbo"
LIMIT=""
TBOX="outputs/cq_pipeline/final/p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json"
TEST_FILE="data/p5_eval_pool/final/test_final.jsonl"
OUTPUT_BASE="outputs/eval_models"
INTERVAL=1.0
NO_COT=false
NO_VERIFY=false
RETRY_ERRORS=false
REL_MAPPING=""

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --models)
            MODELS="$2"
            shift 2
            ;;
        --limit)
            LIMIT="--limit $2"
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
        --interval)
            INTERVAL="$2"
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
        --help)
            echo "使用方式:"
            echo "  --models    模型列表（逗号分隔，默认 gpt-4o-mini,glm-4-flash,qwen-turbo）"
            echo "  --limit     最多处理的样本数"
            echo "  --tbox      TBox 文件路径"
            echo "  --test-file 测试集文件路径"
            echo "  --interval  请求间隔秒数（默认 1.0）"
            echo "  --no-cot    禁用 CoT（用于消融实验）"
            echo "  --no-verify 禁用后校验（用于消融实验）"
            echo "  --retry-errors 重新跑 error 记录（跳过正常记录）"
            echo "  --relation-mapping 关系映射配置文件路径（启用映射评测）"
            echo ""
            echo "并行运行请使用 run_single_model.sh 在多个 tmux 窗口中执行"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

# 解析模型列表
IFS=',' read -ra MODEL_ARRAY <<< "$MODELS"

echo "============================================================"
echo "多模型对比评测"
echo "============================================================"
echo "模型列表: ${MODEL_ARRAY[*]}"
echo "测试集: $TEST_FILE"
echo "TBox: $TBOX"
echo "输出目录: $OUTPUT_BASE"
echo "NO_COT: $NO_COT"
echo "NO_VERIFY: $NO_VERIFY"
echo "RETRY_ERRORS: $RETRY_ERRORS"
echo "RELATION_MAPPING: ${REL_MAPPING:-未启用}"
echo "============================================================"
echo ""

# 检查文件
if [ ! -f "$TEST_FILE" ]; then
    echo "[ERROR] 测试集不存在: $TEST_FILE"
    exit 1
fi

if [ ! -f "$TBOX" ]; then
    echo "[ERROR] TBox 不存在: $TBOX"
    exit 1
fi

# 创建输出目录
mkdir -p "$OUTPUT_BASE"

# 遍历模型
for MODEL in "${MODEL_ARRAY[@]}"; do
    MODEL_DIR="${MODEL//\//_}"  # 替换 / 为 _
    MODEL_DIR="${MODEL_DIR//:/_}"  # 替换 : 为 _
    OUT_DIR="$OUTPUT_BASE/$MODEL_DIR"

    echo ""
    echo "============================================================"
    echo "模型: $MODEL"
    echo "============================================================"

    mkdir -p "$OUT_DIR"

    # Step 1: 抽取
    echo ""
    echo "[Step 1] 运行抽取..."
    PRED_FILE="$OUT_DIR/predictions.jsonl"

    # 构建 CoT / Verify / Retry 参数
    COT_FLAG=""
    VERIFY_FLAG=""
    RETRY_FLAG=""
    if [ "$NO_COT" = true ]; then
        COT_FLAG="--no-cot"
    fi
    if [ "$NO_VERIFY" = true ]; then
        VERIFY_FLAG="--no-verify"
    fi
    if [ "$RETRY_ERRORS" = true ]; then
        RETRY_FLAG="--retry-errors"
    fi

    if [ -f "$PRED_FILE" ]; then
        if [ "$RETRY_ERRORS" = true ]; then
            echo "  发现已有预测，重跑 error 记录..."
            python scripts/p5/run_extraction_on_test.py \
                --test-file "$TEST_FILE" \
                --tbox "$TBOX" \
                --model "$MODEL" \
                --output "$PRED_FILE" \
                --interval "$INTERVAL" \
                $COT_FLAG \
                $VERIFY_FLAG \
                $RETRY_FLAG \
                $LIMIT
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
                    --interval "$INTERVAL" \
                    --skip-existing \
                    $COT_FLAG \
                    $VERIFY_FLAG \
                    $LIMIT
            fi
        fi
    else
        python scripts/p5/run_extraction_on_test.py \
            --test-file "$TEST_FILE" \
            --tbox "$TBOX" \
            --model "$MODEL" \
            --output "$PRED_FILE" \
            --interval "$INTERVAL" \
            $COT_FLAG \
            $VERIFY_FLAG \
            $RETRY_FLAG \
            $LIMIT
    fi

    # Step 2: 对齐
    echo ""
    echo "[Step 2] 按 doc_id 对齐..."
    ALIGNED_FILE="$OUT_DIR/predictions_aligned.jsonl"
    ALIGN_REPORT="$OUT_DIR/align_report.json"

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
    METRICS_FILE="$OUT_DIR/metrics.json"
    METRICS_RAW_FILE="$OUT_DIR/metrics_raw.json"

    python tools/abox_metrics.py \
        --gold "$GOLD_FOR_METRICS" \
        --pred "$PRED_FOR_METRICS" \
        --tbox "$TBOX" \
        --out "$METRICS_FILE"

    # 原始类型评测（忽略回退逻辑）
    python tools/abox_metrics.py \
        --gold "$GOLD_FOR_METRICS" \
        --pred "$PRED_FOR_METRICS" \
        --tbox "$TBOX" \
        --use-original-type \
        --out "$METRICS_RAW_FILE"

    echo ""
    echo "[$MODEL] 评测完成: $METRICS_FILE"

    # 显示指标摘要
    if [ -f "$METRICS_FILE" ]; then
        echo "  指标摘要:"
        python3 -c "
import json
with open('$METRICS_FILE') as f:
    m = json.load(f)
print(f'    Event F1:        {m.get(\"event_f1\", 0):.4f}')
print(f'    Triple F1 (S):   {m.get(\"triple_f1_strict\", 0):.4f}')
print(f'    Triple F1 (R):   {m.get(\"triple_f1_relaxed\", 0):.4f}')
print(f'    TBox Consistency:{m.get(\"tbox_consistency\", 0):.4f}')
"
    fi
done

# 汇总对比
echo ""
echo "============================================================"
echo "生成汇总报告..."
echo "============================================================"

python scripts/p5/compare_models.py \
    --input-dir "$OUTPUT_BASE" \
    --models "${MODEL_ARRAY[*]}" \
    --output "$OUTPUT_BASE/comparison_report.json"

echo ""
echo "============================================================"
echo "评测完成！"
echo "============================================================"
echo ""
echo "输出目录: $OUTPUT_BASE"
echo "汇总报告: $OUTPUT_BASE/comparison_report.json"
echo ""
echo "各模型结果:"
for MODEL in "${MODEL_ARRAY[@]}"; do
    MODEL_DIR="${MODEL//\//_}"
    MODEL_DIR="${MODEL_DIR//:/_}"
    echo "  - $OUTPUT_BASE/$MODEL_DIR/metrics.json"
    echo "  - $OUTPUT_BASE/$MODEL_DIR/metrics_raw.json"
done
