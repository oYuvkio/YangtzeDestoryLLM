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
NO_STRICT_SCHEMA=false
RETRY_ERRORS=false
TBOX="outputs/cq_pipeline/final/tbox_s2_optimized.json"
TEST_FILE="data/p5_eval_pool/final/test_final.jsonl"
TEXT_SOURCE=""  # 完整文本来源文件
OUTPUT_BASE="outputs/eval_models"
REL_MAPPING=""
USER_PRED_FILE=""  # 用户指定的预测文件（跳过抽取步骤）
EVAL_ONLY=false  # 仅评估模式

# 归一化控制参数（默认关闭，实现原始对比模式）
ENABLE_ENTITY_NORMALIZE=false    # 实体同义词归一化
ENABLE_DIRECTION_NORMALIZE=false # 三元组方向归一化
ENABLE_TYPE_FALLBACK=false       # TBox 类型回退

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
        --no-strict-schema)
            NO_STRICT_SCHEMA=true
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
        --pred-file)
            USER_PRED_FILE="$2"
            shift 2
            ;;
        --eval-only)
            EVAL_ONLY=true
            shift
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
        --enable-entity-normalize)
            ENABLE_ENTITY_NORMALIZE=true
            shift
            ;;
        --enable-direction-normalize)
            ENABLE_DIRECTION_NORMALIZE=true
            shift
            ;;
        --enable-type-fallback)
            ENABLE_TYPE_FALLBACK=true
            shift
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
            echo "  --no-strict-schema  关闭严格 Schema 约束"
            echo "  --retry-errors 重新跑 error 记录（跳过正常记录）"
            echo "  --relation-mapping 关系映射配置文件路径（启用映射评测）"
            echo "  --pred-file   指定已有的预测文件（跳过抽取步骤，直接评估）"
            echo "  --eval-only   仅评估模式（需配合 --pred-file 使用）"
            echo "  --tbox        TBox 文件路径"
            echo "  --test-file   测试集文件路径"
            echo "  --text-source 完整文本来源文件（可选，用于映射 doc_id 获取完整文本）"
            echo "  --output-base 输出基目录"
            echo ""
            echo "归一化控制参数（默认关闭）:"
            echo "  --enable-entity-normalize    启用实体同义词归一化（默认关闭）"
            echo "  --enable-direction-normalize 启用三元组方向归一化（默认关闭）"
            echo "  --enable-type-fallback       启用 TBox 类型回退（默认关闭）"
            echo ""
            echo "说明: 默认情况下不做任何归一化，直接对比原始 pred 和 gold 数据。"
            echo "      如需启用归一化，请显式指定对应参数。"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

# 检查必须参数
# 如果指定了 --pred-file，则不需要 --model
if [ -z "$USER_PRED_FILE" ] && [ -z "$MODEL" ]; then
    echo "[ERROR] 必须指定 --model 参数或 --pred-file 参数"
    echo "使用 --help 查看帮助"
    exit 1
fi

# 检查 --pred-file 是否存在
if [ -n "$USER_PRED_FILE" ] && [ ! -f "$USER_PRED_FILE" ]; then
    echo "[ERROR] 预测文件不存在: $USER_PRED_FILE"
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
# 优先使用 --output-base，否则使用 pred 文件所在目录
if [ -n "$USER_PRED_FILE" ]; then
    # 从 pred 文件推断模型名（如果没有指定 --model）
    if [ -z "$MODEL" ]; then
        MODEL=$(basename "$(dirname "$USER_PRED_FILE")")
    fi
    # 如果用户指定了 --output-base，使用它；否则使用 pred 文件所在目录
    if [ "$OUTPUT_BASE" != "outputs/eval_models" ]; then
        OUT_DIR="$OUTPUT_BASE"
    else
        OUT_DIR=$(dirname "$USER_PRED_FILE")
    fi
else
    MODEL_DIR="${MODEL//\//_}"  # 替换 / 为 _
    MODEL_DIR="${MODEL_DIR//:/_}"  # 替换 : 为 _
    OUT_DIR="$OUTPUT_BASE/$MODEL_DIR"
fi

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
echo "PRED_FILE: ${USER_PRED_FILE:-未指定（将使用默认输出路径）}"
echo "TEST_FILE: $TEST_FILE"
echo "输出目录: $OUT_DIR"
echo "============================================================"
echo ""

# 构建 Python 脚本参数
FLAGS=""
[ "$NO_COT" = true ] && FLAGS="$FLAGS --no-cot"
[ "$NO_VERIFY" = true ] && FLAGS="$FLAGS --no-verify"
[ "$NO_STRICT_SCHEMA" = true ] && FLAGS="$FLAGS --no-strict-schema"
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

# 设置预测文件路径
# 如果用户指定了 --pred-file，使用用户指定的文件；否则使用默认输出路径
if [ -n "$USER_PRED_FILE" ]; then
    PRED_FILE="$USER_PRED_FILE"
else
    PRED_FILE="$OUT_DIR/predictions.jsonl"
fi
ALIGNED_FILE="$OUT_DIR/predictions_aligned.jsonl"
ALIGN_REPORT="$OUT_DIR/align_report.json"
METRICS_FILE="$OUT_DIR/metrics.json"
METRICS_RAW_FILE="$OUT_DIR/metrics_raw.json"

# Step 1: 抽取（如果用户指定了 --pred-file，则跳过）
echo ""
if [ -n "$USER_PRED_FILE" ]; then
    echo "[Step 1] 跳过抽取（使用已有预测文件: $PRED_FILE）"
elif [ -f "$PRED_FILE" ]; then
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

# Step 2.1: 过滤 Gold 和 Pred 中的 error 行
echo ""
echo "[Step 2.1] 过滤 Gold/Pred 中的 error 行..."
GOLD_FILTERED="$OUT_DIR/gold_filtered.jsonl"
PRED_FILTERED="$OUT_DIR/predictions_filtered.jsonl"
python scripts/p5/filter_gold_errors.py \
    --gold "$TEST_FILE" \
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

# Step 2.3: 实体同义词归一化（第二步）- 仅当启用时执行
SYNONYMS_FILE="configs/entity_synonyms.json"
GOLD_ENTITY_NORM="$OUT_DIR/gold_entity_normalized.jsonl"
PRED_ENTITY_NORM="$OUT_DIR/predictions_entity_normalized.jsonl"
if [ "$ENABLE_ENTITY_NORMALIZE" = true ]; then
    echo ""
    echo "[Step 2.3] 实体同义词归一化..."
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
        echo "  [警告] 同义词库不存在: $SYNONYMS_FILE，跳过实体归一化"
        GOLD_FOR_DIRECTION="$GOLD_FOR_NORM"
        PRED_FOR_DIRECTION="$PRED_FOR_NORM"
    fi
else
    echo ""
    echo "[Step 2.3] 跳过实体同义词归一化（未启用 --enable-entity-normalize）"
    GOLD_FOR_DIRECTION="$GOLD_FOR_NORM"
    PRED_FOR_DIRECTION="$PRED_FOR_NORM"
fi

# Step 2.4: 三元组方向归一化（最后做）- 仅当启用时执行
GOLD_NORMALIZED="$OUT_DIR/gold_normalized.jsonl"
PRED_NORMALIZED="$OUT_DIR/predictions_normalized.jsonl"
if [ "$ENABLE_DIRECTION_NORMALIZE" = true ]; then
    echo ""
    echo "[Step 2.4] 三元组方向归一化..."
    python scripts/p5/normalize_triple_direction.py \
        --gold "$GOLD_FOR_DIRECTION" \
        --pred "$PRED_FOR_DIRECTION" \
        --tbox "$TBOX" \
        --gold-out "$GOLD_NORMALIZED" \
        --pred-out "$PRED_NORMALIZED"
    GOLD_FOR_METRICS="$GOLD_NORMALIZED"
    PRED_FOR_METRICS="$PRED_NORMALIZED"
else
    echo ""
    echo "[Step 2.4] 跳过三元组方向归一化（未启用 --enable-direction-normalize）"
    GOLD_FOR_METRICS="$GOLD_FOR_DIRECTION"
    PRED_FOR_METRICS="$PRED_FOR_DIRECTION"
fi

# Step 3: 评测（原始对比模式 - 使用过滤后的文件，不做归一化）
echo ""
echo "[Step 3] 计算指标..."

# 构建 abox_metrics.py 的类型回退参数
TYPE_FALLBACK_FLAG=""
if [ "$ENABLE_TYPE_FALLBACK" = true ]; then
    TYPE_FALLBACK_FLAG=""  # 启用类型回退（abox_metrics.py 默认行为）
else
    TYPE_FALLBACK_FLAG="--use-original-type"  # 使用原始类型（不回退）
fi

# 主指标文件（使用归一化后的文件，如果启用了归一化）
python tools/abox_metrics.py \
    --gold "$GOLD_FOR_METRICS" \
    --pred "$PRED_FOR_METRICS" \
    --tbox "$TBOX" \
    $TYPE_FALLBACK_FLAG \
    --out "$METRICS_FILE"

# 如果启用了类型回退，同时输出原始类型指标
if [ "$ENABLE_TYPE_FALLBACK" = true ]; then
    python tools/abox_metrics.py \
        --gold "$GOLD_FOR_METRICS" \
        --pred "$PRED_FOR_METRICS" \
        --tbox "$TBOX" \
        --use-original-type \
        --out "$METRICS_RAW_FILE"
fi

# Step 4.2: 诊断报告
echo ""
echo "[Step 4.2] 生成诊断报告..."
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
if [ "$ENABLE_ENTITY_NORMALIZE" = true ]; then
    echo "  实体同义词归一化: ✅ 已启用"
else
    echo "  实体同义词归一化: ❌ 未启用"
fi
if [ "$ENABLE_DIRECTION_NORMALIZE" = true ]; then
    echo "  三元组方向归一化: ✅ 已启用"
else
    echo "  三元组方向归一化: ❌ 未启用"
fi
if [ "$ENABLE_TYPE_FALLBACK" = true ]; then
    echo "  TBox类型回退:     ✅ 已启用"
else
    echo "  TBox类型回退:     ❌ 未启用（使用原始类型）"
fi
echo ""
echo "【评测文件】"
echo "  Gold 文件:    $GOLD_FOR_METRICS"
echo "  Pred 文件:    $PRED_FOR_METRICS"
if [ -n "$REL_MAPPING" ]; then
    echo "  关系映射配置: $REL_MAPPING"
fi
if [ "$ENABLE_ENTITY_NORMALIZE" = true ] && [ -f "$SYNONYMS_FILE" ]; then
    echo "  实体同义词库: $SYNONYMS_FILE"
fi

# 显示指标摘要
if [ -f "$METRICS_FILE" ]; then
    echo ""
    echo "指标摘要:"
    python3 -c "
import json
with open('$METRICS_FILE') as f:
    data = json.load(f)

# 检查是否为新格式（包含 raw 和 tbox_filtered）
if 'raw' in data and 'tbox_filtered' in data:
    for version in ['raw', 'tbox_filtered']:
        m = data[version]
        print(f'')
        print(f'  === {version.upper()} ===')

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

        # 实体指标（仅名称匹配）
        ent = m.get('entity_metrics', {})
        print(f'  [Entity (name only)]')
        print(f'    Precision:      {ent.get(\"precision\", 0):.4f}')
        print(f'    Recall:         {ent.get(\"recall\", 0):.4f}')
        print(f'    F1:             {ent.get(\"f1\", 0):.4f}')

        # 实体指标（名称+类型匹配）
        ent_type = m.get('entity_metrics_with_type', {})
        if ent_type:
            print(f'  [Entity (name+type)]')
            print(f'    Precision:      {ent_type.get(\"precision\", 0):.4f}')
            print(f'    Recall:         {ent_type.get(\"recall\", 0):.4f}')
            print(f'    F1:             {ent_type.get(\"f1\", 0):.4f}')

        # 关系指标
        rel = m.get('relation_metrics', {})
        print(f'  [Relation]')
        print(f'    Precision:      {rel.get(\"precision\", 0):.4f}')
        print(f'    Recall:         {rel.get(\"recall\", 0):.4f}')
        print(f'    F1:             {rel.get(\"f1\", 0):.4f}')

        # 核心质量指标
        print(f'  [Quality]')
        print(f'    TBox Consistency:   {m.get(\"tbox_consistency\", 0):.4f}')
        hr = m.get('hallucination_rate')
        print(f'    Hallucination Rate: {hr:.4f}' if hr is not None else '    Hallucination Rate: N/A')
        print(f'    Entity Redundancy:  {m.get(\"entity_redundancy_rate\", 0):.4f}')
else:
    # 兼容旧格式
    m = data
    em = m.get('event_metrics', {})
    print(f'  [Event]')
    print(f'    Precision:      {em.get(\"precision\", 0):.4f}')
    print(f'    Recall:         {em.get(\"recall\", 0):.4f}')
    print(f'    F1:             {em.get(\"f1\", 0):.4f}')

    ts = m.get('triple_metrics_strict', {})
    print(f'  [Triple-Strict]')
    print(f'    Precision:      {ts.get(\"precision\", 0):.4f}')
    print(f'    Recall:         {ts.get(\"recall\", 0):.4f}')
    print(f'    F1:             {ts.get(\"f1\", 0):.4f}')

    tr = m.get('triple_metrics_relaxed', {})
    print(f'  [Triple-Relaxed]')
    print(f'    Precision:      {tr.get(\"precision\", 0):.4f}')
    print(f'    Recall:         {tr.get(\"recall\", 0):.4f}')
    print(f'    F1:             {tr.get(\"f1\", 0):.4f}')

    # 实体指标（仅名称匹配）
    ent = m.get('entity_metrics', {})
    print(f'  [Entity (name only)]')
    print(f'    Precision:      {ent.get(\"precision\", 0):.4f}')
    print(f'    Recall:         {ent.get(\"recall\", 0):.4f}')
    print(f'    F1:             {ent.get(\"f1\", 0):.4f}')

    # 实体指标（名称+类型匹配）
    ent_type = m.get('entity_metrics_with_type', {})
    if ent_type:
        print(f'  [Entity (name+type)]')
        print(f'    Precision:      {ent_type.get(\"precision\", 0):.4f}')
        print(f'    Recall:         {ent_type.get(\"recall\", 0):.4f}')
        print(f'    F1:             {ent_type.get(\"f1\", 0):.4f}')

    # 关系指标
    rel = m.get('relation_metrics', {})
    print(f'  [Relation]')
    print(f'    Precision:      {rel.get(\"precision\", 0):.4f}')
    print(f'    Recall:         {rel.get(\"recall\", 0):.4f}')
    print(f'    F1:             {rel.get(\"f1\", 0):.4f}')

    print(f'  [Quality]')
    print(f'    TBox Consistency:   {m.get(\"tbox_consistency\", 0):.4f}')
    print(f'    Hallucination Rate: {m.get(\"hallucination_rate\", 0):.4f}')
    print(f'    Entity Redundancy:  {m.get(\"entity_redundancy_rate\", 0):.4f}')
"
fi

echo ""
echo "【输出文件】"
echo "  预测结果:     $PRED_FILE"
echo "  对齐结果:     $ALIGNED_FILE"
echo "  主指标文件:   $METRICS_FILE"
if [ "$ENABLE_TYPE_FALLBACK" = true ]; then
    echo "  原始类型指标: $METRICS_RAW_FILE"
fi
echo "  诊断报告:     $DIAGNOSIS_FILE"
