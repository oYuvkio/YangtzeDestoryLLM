#!/bin/bash
# =============================================================================
# 消融实验运行脚本
# 
# 实验配置：
#   - full:      完整模型（CoT + Graph + Verify）
#   - wo_cot:    禁用思维链
#   - wo_graph:  禁用图结构检测（强制使用通用结构）
#   - wo_verify: 禁用后校验
#
# 使用方式：
#   bash scripts/p5/ablation/run_ablation_experiments.sh [experiment]
#   
#   experiment 可选值: full, wo_cot, wo_graph, wo_verify, all, ablation
#   默认运行 all（全部实验）
#
# 示例：
#   bash scripts/p5/ablation/run_ablation_experiments.sh full      # 只运行完整模型
#   bash scripts/p5/ablation/run_ablation_experiments.sh wo_cot    # 只运行 wo_cot
#   bash scripts/p5/ablation/run_ablation_experiments.sh all       # 运行全部（含 full）
#   bash scripts/p5/ablation/run_ablation_experiments.sh ablation  # 只运行消融实验（跳过 full）
# =============================================================================

set -e  # 遇到错误立即退出

# =============================================================================
# 激活 Conda 环境
# =============================================================================
CONDA_ENV="YangtzeLLM"

# 初始化 conda（支持在脚本中使用 conda activate）
eval "$(conda shell.bash hook)"
conda activate "${CONDA_ENV}"
echo "已激活 Conda 环境: ${CONDA_ENV}"

# =============================================================================
# 配置区域（根据需要修改）
# =============================================================================
#改
MODEL="Qwen/Qwen3-8B"
API_KEY="sk-mxlgfbnmfjvmzdfehaqpvccneranldifltwljaxmilwqxoyf"
BASE_URL="https://api.siliconflow.cn/v1/"
OUTPUT_BASE="outputs/eval_models_hybrid/qwen/"

#不改
TEST_FILE="outputs/eval_models/gold/merge_filted_3.jsonl"
TEXT_SOURCE="data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl"
TBOX="outputs/kg_final/tbox_final.json"
TEMPERATURE=0.1
TOP_P=0.1
FUZZY_THRESHOLD=0.75
INTERVAL=5


# =============================================================================
# 创建输出目录
# =============================================================================
mkdir -p "${OUTPUT_BASE}"/{full,wo_cot,wo_graph,wo_verify}

# =============================================================================
# 公共参数
# =============================================================================
COMMON_ARGS=(
    --test-file "${TEST_FILE}"
    --text-source "${TEXT_SOURCE}"
    --tbox "${TBOX}"
    --model "${MODEL}"
    --base-url "${BASE_URL}"
    --api-key "${API_KEY}"
    --temperature "${TEMPERATURE}"
    --top-p "${TOP_P}"
    --fuzzy-threshold "${FUZZY_THRESHOLD}"
    --no-strict-schema
    --skip-existing
    --interval "${INTERVAL}"
)

# =============================================================================
# 实验函数
# =============================================================================

run_full() {
    echo "============================================================"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始运行: full（完整模型）"
    echo "============================================================"
    python scripts/p5/run_extraction_on_test.py \
        "${COMMON_ARGS[@]}" \
        --output "${OUTPUT_BASE}/full/predictions.jsonl" \
        2>&1 | tee "${OUTPUT_BASE}/full/predictions.log"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] full 完成"
}

run_wo_cot() {
    echo "============================================================"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始运行: wo_cot（禁用思维链）"
    echo "============================================================"
    python scripts/p5/run_extraction_on_test.py \
        "${COMMON_ARGS[@]}" \
        --output "${OUTPUT_BASE}/wo_cot/predictions.jsonl" \
        --no-cot \
        2>&1 | tee "${OUTPUT_BASE}/wo_cot/predictions.log"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] wo_cot 完成"
}

run_wo_graph() {
    echo "============================================================"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始运行: wo_graph（禁用图结构检测）"
    echo "============================================================"
    python scripts/p5/run_extraction_on_test.py \
        "${COMMON_ARGS[@]}" \
        --output "${OUTPUT_BASE}/wo_graph/predictions.jsonl" \
        --no-graph \
        2>&1 | tee "${OUTPUT_BASE}/wo_graph/predictions.log"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] wo_graph 完成"
}

run_wo_verify() {
    echo "============================================================"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始运行: wo_verify（禁用后校验）"
    echo "============================================================"
    python scripts/p5/run_extraction_on_test.py \
        "${COMMON_ARGS[@]}" \
        --output "${OUTPUT_BASE}/wo_verify/predictions.jsonl" \
        --no-verify \
        2>&1 | tee "${OUTPUT_BASE}/wo_verify/predictions.log"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] wo_verify 完成"
}

run_all() {
    echo "============================================================"
    echo "开始运行全部消融实验"
    echo "============================================================"
    run_full
    run_wo_cot
    run_wo_graph
    run_wo_verify
    echo "============================================================"
    echo "全部消融实验完成！"
    echo "============================================================"
}

run_ablation_only() {
    echo "============================================================"
    echo "开始运行消融实验（跳过 full）"
    echo "============================================================"
    run_wo_cot
    run_wo_graph
    run_wo_verify
    echo "============================================================"
    echo "消融实验完成！"
    echo "============================================================"
}

# =============================================================================
# 主逻辑
# =============================================================================
EXPERIMENT="${1:-all}"

case "${EXPERIMENT}" in
    full)
        run_full
        ;;
    wo_cot)
        run_wo_cot
        ;;
    wo_graph)
        run_wo_graph
        ;;
    wo_verify)
        run_wo_verify
        ;;
    all)
        run_all
        ;;
    ablation)
        run_ablation_only
        ;;
    *)
        echo "未知实验: ${EXPERIMENT}"
        echo "可选值: full, wo_cot, wo_graph, wo_verify, all, ablation"
        exit 1
        ;;
esac
