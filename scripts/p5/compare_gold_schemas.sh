#!/bin/bash
#===============================================================================
# Gold Schema 对比评测脚本
#
# 比较不同 Schema 生成的 Gold 标注之间的差异/一致性
# 以其中一个 Gold 作为参考（Reference），计算另一个 Gold 的指标
#
# 使用方式：
#   # 比较 s2 和 s3 Schema 生成的 Gold（以 s2 为参考）
#   bash scripts/p5/compare_gold_schemas.sh \
#       --gold-ref data/p5_eval_pool/gold_s2.jsonl \
#       --gold-cmp data/p5_eval_pool/gold_s3.jsonl \
#       --tbox-ref outputs/cq_pipeline/final/tbox_s2_optimized.json \
#       --tbox-cmp outputs/cq_pipeline/final/tbox_s3_optimized.json \
#       --output-dir outputs/gold_comparison/s2_vs_s3
#
#   # 生成新的 Gold 并比较
#   bash scripts/p5/compare_gold_schemas.sh \
#       --generate \
#       --tbox-ref outputs/cq_pipeline/final/tbox_s2_optimized.json \
#       --tbox-cmp outputs/cq_pipeline/final/tbox_s3_optimized.json \
#       --input data/p5_eval_pool/final/test_final.jsonl \
#       --model "gpt-4o" \
#       --output-dir outputs/gold_comparison/s2_vs_s3
#===============================================================================

set -eo pipefail

cd /home/zjx/project/YangtzeDestoryLLM
source /home/zjx/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM
export PYTHONPATH=.

# 禁用代理
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
export NO_PROXY="localhost,127.0.0.1,::1"

# 默认参数
GOLD_REF=""           # 参考 Gold 文件
GOLD_CMP=""           # 待比较 Gold 文件
TBOX_REF=""           # 参考 TBox
TBOX_CMP=""           # 待比较 TBox
OUTPUT_DIR=""         # 输出目录
GENERATE=false        # 是否生成新的 Gold
INPUT_FILE=""         # 输入文件（生成模式）
MODEL="gpt-4o"        # 模型（生成模式）
BASE_URL=""           # API base URL
API_KEY=""            # API Key
TEMPERATURE=0.1
INTERVAL=2.0
LIMIT=""
REL_MAPPING=""        # 关系映射配置

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --gold-ref)
            GOLD_REF="$2"
            shift 2
            ;;
        --gold-cmp)
            GOLD_CMP="$2"
            shift 2
            ;;
        --tbox-ref)
            TBOX_REF="$2"
            shift 2
            ;;
        --tbox-cmp)
            TBOX_CMP="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --generate)
            GENERATE=true
            shift
            ;;
        --input)
            INPUT_FILE="$2"
            shift 2
            ;;
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
            LIMIT="$2"
            shift 2
            ;;
        --relation-mapping)
            REL_MAPPING="$2"
            shift 2
            ;;
        --help)
            echo "Gold Schema 对比评测脚本"
            echo ""
            echo "使用方式："
            echo "  --gold-ref FILE      参考 Gold 文件"
            echo "  --gold-cmp FILE      待比较 Gold 文件"
            echo "  --tbox-ref FILE      参考 TBox 文件"
            echo "  --tbox-cmp FILE      待比较 TBox 文件（用于 TBox 一致性计算）"
            echo "  --output-dir DIR     输出目录"
            echo "  --generate           生成新的 Gold（需要 --input）"
            echo "  --input FILE         输入文件（生成模式）"
            echo "  --model NAME         模型名称（生成模式，默认 gpt-4o）"
            echo "  --base-url URL       API base URL"
            echo "  --api-key KEY        API Key"
            echo "  --temperature T      温度参数（默认 0.1）"
            echo "  --interval SEC       请求间隔（默认 2.0）"
            echo "  --limit N            限制样本数"
            echo "  --relation-mapping   关系映射配置文件"
            echo ""
            echo "示例："
            echo "  # 比较已有的两个 Gold 文件"
            echo "  bash scripts/p5/compare_gold_schemas.sh \\"
            echo "      --gold-ref data/p5_eval_pool/gold_s2.jsonl \\"
            echo "      --gold-cmp data/p5_eval_pool/gold_s3.jsonl \\"
            echo "      --tbox-ref outputs/cq_pipeline/final/tbox_s2_optimized.json \\"
            echo "      --output-dir outputs/gold_comparison/s2_vs_s3"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

# 检查必须参数
if [ -z "$TBOX_REF" ]; then
    echo "[ERROR] 必须指定 --tbox-ref 参数"
    exit 1
fi

if [ -z "$OUTPUT_DIR" ]; then
    echo "[ERROR] 必须指定 --output-dir 参数"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

# API Key 处理
if [ -n "$API_KEY" ]; then
    export OPENAI_API_KEYS="$API_KEY"
    export OPENAI_API_KEY="${API_KEY%%,*}"
fi

echo "============================================================"
echo "Gold Schema 对比评测"
echo "============================================================"
echo "参考 TBox: $TBOX_REF"
echo "比较 TBox: ${TBOX_CMP:-同参考}"
echo "输出目录: $OUTPUT_DIR"
echo "生成模式: $GENERATE"
echo "============================================================"
echo ""

# 如果需要生成 Gold
if [ "$GENERATE" = true ]; then
    if [ -z "$INPUT_FILE" ]; then
        echo "[ERROR] 生成模式需要指定 --input 参数"
        exit 1
    fi

    if [ ! -f "$INPUT_FILE" ]; then
        echo "[ERROR] 输入文件不存在: $INPUT_FILE"
        exit 1
    fi

    # 构建生成参数
    GEN_FLAGS=""
    [ -n "$BASE_URL" ] && GEN_FLAGS="$GEN_FLAGS --base-url $BASE_URL"
    [ -n "$LIMIT" ] && GEN_FLAGS="$GEN_FLAGS --limit $LIMIT"

    # 生成参考 Gold（使用 TBOX_REF）
    GOLD_REF="$OUTPUT_DIR/gold_ref.jsonl"
    echo "[Step 1.1] 生成参考 Gold (TBox: $TBOX_REF)..."
    if [ ! -f "$GOLD_REF" ]; then
        python scripts/generate_gold_with_tbox.py \
            --input "$INPUT_FILE" \
            --tbox "$TBOX_REF" \
            --output "$GOLD_REF" \
            --model "$MODEL" \
            --temperature "$TEMPERATURE" \
            --interval "$INTERVAL" \
            --use-cot \
            --use-verification \
            $GEN_FLAGS
    else
        echo "  已存在，跳过生成"
    fi

    # 如果指定了比较 TBox，生成比较 Gold
    if [ -n "$TBOX_CMP" ]; then
        GOLD_CMP="$OUTPUT_DIR/gold_cmp.jsonl"
        echo ""
        echo "[Step 1.2] 生成比较 Gold (TBox: $TBOX_CMP)..."
        if [ ! -f "$GOLD_CMP" ]; then
            python scripts/generate_gold_with_tbox.py \
                --input "$INPUT_FILE" \
                --tbox "$TBOX_CMP" \
                --output "$GOLD_CMP" \
                --model "$MODEL" \
                --temperature "$TEMPERATURE" \
                --interval "$INTERVAL" \
                --use-cot \
                --use-verification \
                $GEN_FLAGS
        else
            echo "  已存在，跳过生成"
        fi
    fi
fi

# 检查 Gold 文件
if [ -z "$GOLD_REF" ] || [ ! -f "$GOLD_REF" ]; then
    echo "[ERROR] 参考 Gold 文件不存在: $GOLD_REF"
    exit 1
fi

if [ -z "$GOLD_CMP" ] || [ ! -f "$GOLD_CMP" ]; then
    echo "[ERROR] 比较 Gold 文件不存在: $GOLD_CMP"
    exit 1
fi

echo ""
echo "参考 Gold: $GOLD_REF"
echo "比较 Gold: $GOLD_CMP"
echo ""

# Step 2: 按 doc_id 对齐
echo "[Step 2] 按 doc_id 对齐..."
ALIGNED_CMP="$OUTPUT_DIR/gold_cmp_aligned.jsonl"
ALIGN_REPORT="$OUTPUT_DIR/align_report.json"
python scripts/p5/align_pred_to_gold.py \
    --gold "$GOLD_REF" \
    --pred "$GOLD_CMP" \
    --out "$ALIGNED_CMP" \
    --report "$ALIGN_REPORT"

# Step 2.1: 过滤 error 行
echo ""
echo "[Step 2.1] 过滤 error 行..."
GOLD_REF_FILTERED="$OUTPUT_DIR/gold_ref_filtered.jsonl"
GOLD_CMP_FILTERED="$OUTPUT_DIR/gold_cmp_filtered.jsonl"
python scripts/p5/filter_gold_errors.py \
    --gold "$GOLD_REF" \
    --pred "$ALIGNED_CMP" \
    --gold-out "$GOLD_REF_FILTERED" \
    --pred-out "$GOLD_CMP_FILTERED"

# Step 2.2: 关系映射（如果指定）
GOLD_REF_FOR_NORM="$GOLD_REF_FILTERED"
GOLD_CMP_FOR_NORM="$GOLD_CMP_FILTERED"
if [ -n "$REL_MAPPING" ] && [ -f "$REL_MAPPING" ]; then
    echo ""
    echo "[Step 2.2] 关系映射..."
    GOLD_REF_MAPPED="$OUTPUT_DIR/gold_ref_relation_mapped.jsonl"
    GOLD_CMP_MAPPED="$OUTPUT_DIR/gold_cmp_relation_mapped.jsonl"
    python scripts/p5/apply_relation_mapping.py \
        --pred "$GOLD_CMP_FILTERED" \
        --gold "$GOLD_REF_FILTERED" \
        --mapping "$REL_MAPPING" \
        --out-pred "$GOLD_CMP_MAPPED" \
        --out-gold "$GOLD_REF_MAPPED"
    GOLD_REF_FOR_NORM="$GOLD_REF_MAPPED"
    GOLD_CMP_FOR_NORM="$GOLD_CMP_MAPPED"
fi

# Step 2.3: 实体同义词归一化
echo ""
echo "[Step 2.3] 实体同义词归一化..."
SYNONYMS_FILE="configs/entity_synonyms.json"
GOLD_REF_ENTITY_NORM="$OUTPUT_DIR/gold_ref_entity_normalized.jsonl"
GOLD_CMP_ENTITY_NORM="$OUTPUT_DIR/gold_cmp_entity_normalized.jsonl"
if [ -f "$SYNONYMS_FILE" ]; then
    python scripts/p5/normalize_entities.py \
        --gold "$GOLD_REF_FOR_NORM" \
        --pred "$GOLD_CMP_FOR_NORM" \
        --synonyms "$SYNONYMS_FILE" \
        --gold-out "$GOLD_REF_ENTITY_NORM" \
        --pred-out "$GOLD_CMP_ENTITY_NORM"
    GOLD_REF_FOR_DIRECTION="$GOLD_REF_ENTITY_NORM"
    GOLD_CMP_FOR_DIRECTION="$GOLD_CMP_ENTITY_NORM"
else
    echo "  同义词库不存在，跳过"
    GOLD_REF_FOR_DIRECTION="$GOLD_REF_FOR_NORM"
    GOLD_CMP_FOR_DIRECTION="$GOLD_CMP_FOR_NORM"
fi

# Step 2.4: 三元组方向归一化
echo ""
echo "[Step 2.4] 三元组方向归一化..."
GOLD_REF_NORMALIZED="$OUTPUT_DIR/gold_ref_normalized.jsonl"
GOLD_CMP_NORMALIZED="$OUTPUT_DIR/gold_cmp_normalized.jsonl"
python scripts/p5/normalize_triple_direction.py \
    --gold "$GOLD_REF_FOR_DIRECTION" \
    --pred "$GOLD_CMP_FOR_DIRECTION" \
    --tbox "$TBOX_REF" \
    --gold-out "$GOLD_REF_NORMALIZED" \
    --pred-out "$GOLD_CMP_NORMALIZED"

# Step 3: 计算指标（以 REF 为 Gold，CMP 为 Pred）
echo ""
echo "[Step 3] 计算指标（REF 为参考，CMP 为比较对象）..."
METRICS_FILE="$OUTPUT_DIR/metrics_cmp_vs_ref.json"
python tools/abox_metrics.py \
    --gold "$GOLD_REF_NORMALIZED" \
    --pred "$GOLD_CMP_NORMALIZED" \
    --tbox "$TBOX_REF" \
    --out "$METRICS_FILE"

# Step 3.1: 反向计算（以 CMP 为 Gold，REF 为 Pred）
echo ""
echo "[Step 3.1] 反向计算指标（CMP 为参考，REF 为比较对象）..."
METRICS_FILE_REV="$OUTPUT_DIR/metrics_ref_vs_cmp.json"
TBOX_FOR_REV="${TBOX_CMP:-$TBOX_REF}"
python tools/abox_metrics.py \
    --gold "$GOLD_CMP_NORMALIZED" \
    --pred "$GOLD_REF_NORMALIZED" \
    --tbox "$TBOX_FOR_REV" \
    --out "$METRICS_FILE_REV"

# Step 4: 生成对比报告（包含完整指标）
echo ""
echo "[Step 4] 生成对比报告..."
COMPARISON_REPORT="$OUTPUT_DIR/comparison_report.json"
python3 << EOF
import json
from pathlib import Path

# 加载指标
with open("$METRICS_FILE") as f:
    metrics_cmp_vs_ref = json.load(f)

with open("$METRICS_FILE_REV") as f:
    metrics_ref_vs_cmp = json.load(f)

# 统计基本信息
ref_triple_count = metrics_cmp_vs_ref.get("num_gold_triples", 0)
cmp_triple_count = metrics_cmp_vs_ref.get("num_pred_triples", 0)
ref_event_count = metrics_cmp_vs_ref.get("num_gold_events", 0)
cmp_event_count = metrics_cmp_vs_ref.get("num_pred_events", 0)
ref_entity_count = metrics_cmp_vs_ref.get("num_gold_entities", 0)
cmp_entity_count = metrics_cmp_vs_ref.get("num_pred_entities", 0)

# 计算双向一致性
cmp_precision = metrics_cmp_vs_ref.get("triple_metrics_strict", {}).get("precision", 0)
cmp_recall = metrics_cmp_vs_ref.get("triple_metrics_strict", {}).get("recall", 0)
ref_precision = metrics_ref_vs_cmp.get("triple_metrics_strict", {}).get("precision", 0)
ref_recall = metrics_ref_vs_cmp.get("triple_metrics_strict", {}).get("recall", 0)

# 计算 Jaccard 相似度（交集/并集）
intersection_approx = (cmp_precision * cmp_triple_count + ref_precision * ref_triple_count) / 2
union_approx = ref_triple_count + cmp_triple_count - intersection_approx
jaccard = intersection_approx / union_approx if union_approx > 0 else 0

# 构建完整报告
report = {
    "summary": {
        "ref_triple_count": ref_triple_count,
        "cmp_triple_count": cmp_triple_count,
        "ref_event_count": ref_event_count,
        "cmp_event_count": cmp_event_count,
        "ref_entity_count": ref_entity_count,
        "cmp_entity_count": cmp_entity_count,
        "jaccard_similarity": round(jaccard, 4),
        "agreement_rate": round((cmp_precision + ref_precision) / 2, 4),
    },
    "cmp_vs_ref": {
        "description": "以 REF 为 Gold，评估 CMP",
        # 核心 F1 指标
        "event_f1": metrics_cmp_vs_ref.get("event_f1", 0),
        "triple_f1_strict": metrics_cmp_vs_ref.get("triple_f1_strict", 0),
        "triple_f1_relaxed": metrics_cmp_vs_ref.get("triple_f1_relaxed", 0),
        "entity_f1": metrics_cmp_vs_ref.get("entity_f1", 0),
        "relation_f1": metrics_cmp_vs_ref.get("relation_f1", 0),
        "partial_match_f1": metrics_cmp_vs_ref.get("partial_match_f1", 0),
        # 详细指标
        "event_metrics": metrics_cmp_vs_ref.get("event_metrics", {}),
        "triple_metrics_strict": metrics_cmp_vs_ref.get("triple_metrics_strict", {}),
        "triple_metrics_relaxed": metrics_cmp_vs_ref.get("triple_metrics_relaxed", {}),
        "entity_metrics": metrics_cmp_vs_ref.get("entity_metrics", {}),
        "relation_metrics": metrics_cmp_vs_ref.get("relation_metrics", {}),
        # 质量指标
        "tbox_consistency": metrics_cmp_vs_ref.get("tbox_consistency", 0),
        "direction_error_rate": metrics_cmp_vs_ref.get("direction_error_rate", 0),
        "ece": metrics_cmp_vs_ref.get("ece", 0),
        # 证据质量
        "evidence_quality": metrics_cmp_vs_ref.get("evidence_quality", {}),
        # 事件完整性
        "event_completeness": metrics_cmp_vs_ref.get("event_completeness", {}),
        # 覆盖率
        "schema_coverage": metrics_cmp_vs_ref.get("schema_coverage", {}),
        # 错误分析
        "error_breakdown": metrics_cmp_vs_ref.get("error_breakdown", {}),
    },
    "ref_vs_cmp": {
        "description": "以 CMP 为 Gold，评估 REF",
        # 核心 F1 指标
        "event_f1": metrics_ref_vs_cmp.get("event_f1", 0),
        "triple_f1_strict": metrics_ref_vs_cmp.get("triple_f1_strict", 0),
        "triple_f1_relaxed": metrics_ref_vs_cmp.get("triple_f1_relaxed", 0),
        "entity_f1": metrics_ref_vs_cmp.get("entity_f1", 0),
        "relation_f1": metrics_ref_vs_cmp.get("relation_f1", 0),
        "partial_match_f1": metrics_ref_vs_cmp.get("partial_match_f1", 0),
        # 详细指标
        "event_metrics": metrics_ref_vs_cmp.get("event_metrics", {}),
        "triple_metrics_strict": metrics_ref_vs_cmp.get("triple_metrics_strict", {}),
        "triple_metrics_relaxed": metrics_ref_vs_cmp.get("triple_metrics_relaxed", {}),
        "entity_metrics": metrics_ref_vs_cmp.get("entity_metrics", {}),
        "relation_metrics": metrics_ref_vs_cmp.get("relation_metrics", {}),
        # 质量指标
        "tbox_consistency": metrics_ref_vs_cmp.get("tbox_consistency", 0),
        "direction_error_rate": metrics_ref_vs_cmp.get("direction_error_rate", 0),
        "ece": metrics_ref_vs_cmp.get("ece", 0),
        # 证据质量
        "evidence_quality": metrics_ref_vs_cmp.get("evidence_quality", {}),
        # 事件完整性
        "event_completeness": metrics_ref_vs_cmp.get("event_completeness", {}),
        # 覆盖率
        "schema_coverage": metrics_ref_vs_cmp.get("schema_coverage", {}),
        # 错误分析
        "error_breakdown": metrics_ref_vs_cmp.get("error_breakdown", {}),
    },
    # 分类别指标（双向）
    "per_class_metrics": {
        "cmp_vs_ref": metrics_cmp_vs_ref.get("per_class_metrics", {}),
        "ref_vs_cmp": metrics_ref_vs_cmp.get("per_class_metrics", {}),
    },
    "per_relation_metrics": {
        "cmp_vs_ref": metrics_cmp_vs_ref.get("per_relation_metrics", {}),
        "ref_vs_cmp": metrics_ref_vs_cmp.get("per_relation_metrics", {}),
    },
    "interpretation": {
        "high_precision_low_recall": "CMP 更保守，抽取的三元组更少但更准确",
        "low_precision_high_recall": "CMP 更激进，抽取的三元组更多但有更多噪声",
        "high_jaccard": "两个 Schema 生成的 Gold 高度一致",
        "low_jaccard": "两个 Schema 生成的 Gold 差异较大，可能是 Schema 定义不同导致",
    },
}

with open("$COMPARISON_REPORT", "w") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
EOF

echo ""
echo "============================================================"
echo "对比评测完成"
echo "============================================================"

# 显示摘要
if [ -f "$COMPARISON_REPORT" ]; then
    echo ""
    echo "对比摘要："
    python3 -c "
import json
with open('$COMPARISON_REPORT') as f:
    r = json.load(f)

s = r['summary']
print('=' * 60)
print('📊 基本统计')
print('=' * 60)
print(f'  REF 三元组数:     {s[\"ref_triple_count\"]}')
print(f'  CMP 三元组数:     {s[\"cmp_triple_count\"]}')
print(f'  REF 事件数:       {s[\"ref_event_count\"]}')
print(f'  CMP 事件数:       {s[\"cmp_event_count\"]}')
print(f'  REF 实体数:       {s[\"ref_entity_count\"]}')
print(f'  CMP 实体数:       {s[\"cmp_entity_count\"]}')
print()
print(f'  Jaccard 相似度:   {s[\"jaccard_similarity\"]:.4f}')
print(f'  平均一致率:       {s[\"agreement_rate\"]:.4f}')
print()

# CMP vs REF 详细指标
c = r['cmp_vs_ref']
print('=' * 60)
print('📈 [CMP vs REF] (以 REF 为标准)')
print('=' * 60)
print()
print('  【核心 F1 指标】')
print(f'    Event F1:           {c[\"event_f1\"]:.4f}')
print(f'    Triple F1 (Strict): {c[\"triple_f1_strict\"]:.4f}')
print(f'    Triple F1 (Relaxed):{c[\"triple_f1_relaxed\"]:.4f}')
print(f'    Entity F1:          {c[\"entity_f1\"]:.4f}')
print(f'    Relation F1:        {c[\"relation_f1\"]:.4f}')
print(f'    Partial Match F1:   {c[\"partial_match_f1\"]:.4f}')
print()

print('  【三元组详细指标 (Strict)】')
ts = c.get('triple_metrics_strict', {})
print(f'    Precision:          {ts.get(\"precision\", 0):.4f}')
print(f'    Recall:             {ts.get(\"recall\", 0):.4f}')
print(f'    F1:                 {ts.get(\"f1\", 0):.4f}')
print()

print('  【三元组详细指标 (Relaxed)】')
tr = c.get('triple_metrics_relaxed', {})
print(f'    Precision:          {tr.get(\"precision\", 0):.4f}')
print(f'    Recall:             {tr.get(\"recall\", 0):.4f}')
print(f'    F1:                 {tr.get(\"f1\", 0):.4f}')
print()

print('  【质量指标】')
print(f'    TBox 一致性:        {c[\"tbox_consistency\"]:.4f}')
print(f'    方向错误率:         {c[\"direction_error_rate\"]:.4f}')
print(f'    ECE (校准误差):     {c[\"ece\"]:.4f}')
print()

# 证据质量
eq = c.get('evidence_quality', {})
if eq:
    print('  【证据质量】')
    print(f'    证据覆盖率:         {eq.get(\"evidence_coverage\", 0):.4f}')
    print(f'    证据准确率:         {eq.get(\"evidence_accuracy\", 0):.4f}')
    print(f'    平均证据长度:       {eq.get(\"avg_evidence_length\", 0):.1f}')
    print()

# 事件完整性
ec = c.get('event_completeness', {})
if ec:
    print('  【事件完整性】')
    print(f'    有名称率:           {ec.get(\"has_name_rate\", 0):.4f}')
    print(f'    有类型率:           {ec.get(\"has_type_rate\", 0):.4f}')
    print(f'    有时间率:           {ec.get(\"has_time_rate\", 0):.4f}')
    print(f'    有地点率:           {ec.get(\"has_location_rate\", 0):.4f}')
    print(f'    完整性分数:         {ec.get(\"completeness_score\", 0):.4f}')
    print()

# Schema 覆盖率
sc = c.get('schema_coverage', {})
if sc:
    print('  【Schema 覆盖率】')
    print(f'    关系覆盖率:         {sc.get(\"relation_coverage\", 0):.4f} ({sc.get(\"used_relations\", 0)}/{sc.get(\"defined_relations\", 0)})')
    print(f'    类覆盖率:           {sc.get(\"class_coverage\", 0):.4f} ({sc.get(\"used_classes\", 0)}/{sc.get(\"defined_classes\", 0)})')
    print()

# REF vs CMP 详细指标
v = r['ref_vs_cmp']
print('=' * 60)
print('📉 [REF vs CMP] (以 CMP 为标准)')
print('=' * 60)
print()
print('  【核心 F1 指标】')
print(f'    Event F1:           {v[\"event_f1\"]:.4f}')
print(f'    Triple F1 (Strict): {v[\"triple_f1_strict\"]:.4f}')
print(f'    Triple F1 (Relaxed):{v[\"triple_f1_relaxed\"]:.4f}')
print(f'    Entity F1:          {v[\"entity_f1\"]:.4f}')
print(f'    Relation F1:        {v[\"relation_f1\"]:.4f}')
print(f'    Partial Match F1:   {v[\"partial_match_f1\"]:.4f}')
print()

print('  【三元组详细指标 (Strict)】')
vs = v.get('triple_metrics_strict', {})
print(f'    Precision:          {vs.get(\"precision\", 0):.4f}')
print(f'    Recall:             {vs.get(\"recall\", 0):.4f}')
print(f'    F1:                 {vs.get(\"f1\", 0):.4f}')
print()

print('  【质量指标】')
print(f'    TBox 一致性:        {v[\"tbox_consistency\"]:.4f}')
print(f'    方向错误率:         {v[\"direction_error_rate\"]:.4f}')
print(f'    ECE (校准误差):     {v[\"ece\"]:.4f}')
print()

# 错误分析摘要
print('=' * 60)
print('🔍 错误分析摘要')
print('=' * 60)
eb_cmp = c.get('error_breakdown', {})
eb_ref = v.get('error_breakdown', {})

if eb_cmp.get('triples'):
    t_err = eb_cmp['triples']
    print()
    print('  [CMP vs REF 三元组错误]')
    print(f'    严格匹配:           {t_err.get(\"strict_matched\", 0)}')
    print(f'    宽松匹配:           {t_err.get(\"relaxed_matched\", 0)}')
    print(f'    谓词不匹配:         {t_err.get(\"predicate_mismatch\", 0)}')
    print(f'    地理不匹配:         {t_err.get(\"geo_mismatch\", 0)}')
    print(f'    时间不匹配:         {t_err.get(\"time_mismatch\", 0)}')
    print(f'    未匹配 Pred:        {t_err.get(\"unmatched_pred\", 0)}')
    print(f'    未匹配 Gold:        {t_err.get(\"unmatched_gold\", 0)}')

if eb_cmp.get('tbox'):
    tbox_err = eb_cmp['tbox']
    print()
    print('  [CMP TBox 一致性错误]')
    print(f'    总三元组:           {tbox_err.get(\"total\", 0)}')
    print(f'    谓词未知:           {tbox_err.get(\"predicate_unknown\", 0)}')
    print(f'    Domain/Range 违规: {tbox_err.get(\"domain_range_violations\", 0)}')
"
fi

echo ""
echo "输出文件："
echo "  对比报告: $COMPARISON_REPORT"
echo "  CMP vs REF 指标: $METRICS_FILE"
echo "  REF vs CMP 指标: $METRICS_FILE_REV"
echo "  对齐报告: $ALIGN_REPORT"
