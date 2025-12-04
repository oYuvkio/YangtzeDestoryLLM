#!/bin/bash
# ==============================================================================
# 长江水旱灾害知识图谱构建 - 全流程运行脚本
# ==============================================================================
#
# 用法:
#   ./scripts/run_full_pipeline.sh [选项]
#
# 选项:
#   --start-step STEP   从指定步骤开始 (1/2/p1/p2/p3/p4/p5)，默认 1
#   --only-step STEP    仅运行指定步骤
#   --skip-clean        跳过清洗步骤（步骤1）
#   --skip-filter       跳过过滤步骤（步骤2）
#   --dry-run           试运行，仅显示将执行的命令
#   --help              显示帮助信息
#
# 示例:
#   # 完整流程
#   ./scripts/run_full_pipeline.sh
#
#   # 从过滤步骤开始
#   ./scripts/run_full_pipeline.sh --start-step 2
#
#   # 仅运行 P5 批量抽取
#   ./scripts/run_full_pipeline.sh --only-step p5
#
# ==============================================================================

set -e  # 遇到错误立即退出

# ==============================================================================
# 配置变量（可根据项目调整）
# ==============================================================================

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Conda 环境名
CONDA_ENV="YangtzeLLM"

# 数据目录
RAW_CORPUS_DIR="data/raw_corpus"                              # 原始语料目录（PDF/TXT）
HANDLED_CORPUS_DIR="data/corpus_for_kg/handled_all_kg_corpus" # 清洗后语料
LIGHT_POOL_FILE="data/corpus_for_kg/p5_corpus_filtered/light_pool.jsonl"  # 过滤后语料
DOMAIN_DESC_FILE="data/domain_desc.txt"                       # 领域描述文件
P4_CORPUS_DIR="data/enhancing_onto_corpus_docs"               # P4 增强语料

# 输出目录
OUTPUT_DIR="outputs/cq_pipeline/final"

# LLM 配置（可被 cfg.yaml 覆盖）
LLM_PROVIDER="zhipu"
LLM_MODEL="glm-4.5-flash"

# ==============================================================================
# 辅助函数
# ==============================================================================

print_banner() {
    echo ""
    echo "=============================================================="
    echo "  长江水旱灾害知识图谱构建系统 - 全流程运行"
    echo "=============================================================="
    echo "  项目目录: $PROJECT_ROOT"
    echo "  Conda 环境: $CONDA_ENV"
    echo "  输出目录: $OUTPUT_DIR"
    echo "=============================================================="
    echo ""
}

print_step() {
    local step_num=$1
    local step_name=$2
    echo ""
    echo "--------------------------------------------------------------"
    echo "  步骤 $step_num: $step_name"
    echo "--------------------------------------------------------------"
}

check_file_exists() {
    local file=$1
    local desc=$2
    if [[ ! -f "$file" ]]; then
        echo "⚠️  缺少文件: $file ($desc)"
        return 1
    fi
    return 0
}

check_dir_exists() {
    local dir=$1
    local desc=$2
    if [[ ! -d "$dir" ]]; then
        echo "⚠️  缺少目录: $dir ($desc)"
        return 1
    fi
    return 0
}

run_cmd() {
    local cmd=$1
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[DRY-RUN] $cmd"
    else
        echo ">>> $cmd"
        eval "$cmd"
    fi
}

# ==============================================================================
# 激活 Conda 环境
# ==============================================================================

activate_conda() {
    echo "激活 Conda 环境: $CONDA_ENV"
    
    # 尝试多种方式激活 conda
    if [[ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]]; then
        source "$HOME/anaconda3/etc/profile.d/conda.sh"
    elif [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
        source "$HOME/miniconda3/etc/profile.d/conda.sh"
    elif [[ -f "/opt/conda/etc/profile.d/conda.sh" ]]; then
        source "/opt/conda/etc/profile.d/conda.sh"
    else
        # 假设 conda 已在 PATH 中
        eval "$(conda shell.bash hook 2>/dev/null || true)"
    fi
    
    conda activate "$CONDA_ENV" 2>/dev/null || {
        echo "⚠️  无法激活 Conda 环境 $CONDA_ENV，尝试使用系统 Python"
    }
    
    echo "Python 路径: $(which python)"
    echo "Python 版本: $(python --version)"
}

# ==============================================================================
# 步骤1: 语料清洗
# ==============================================================================

step1_clean() {
    print_step 1 "语料清洗 (corpus_cleaner.py)"
    
    if ! check_dir_exists "$RAW_CORPUS_DIR" "原始语料目录"; then
        echo "请将 PDF/TXT 文件放入 $RAW_CORPUS_DIR 目录"
        return 1
    fi
    
    mkdir -p "$HANDLED_CORPUS_DIR"
    
    run_cmd "python tools/corpus_cleaner.py \\
        --input '$RAW_CORPUS_DIR' \\
        --output-dir '$HANDLED_CORPUS_DIR' \\
        --min-chars 500 \\
        --max-chars 3000 \\
        --remove-references \\
        --workers 4 \\
        --cfg configs/cfg.yaml"
    
    echo "✅ 清洗完成，输出目录: $HANDLED_CORPUS_DIR"
}

# ==============================================================================
# 步骤2: 语料过滤
# ==============================================================================

step2_filter() {
    print_step 2 "语料过滤 (filter_corpus_light.py)"
    
    if ! check_dir_exists "$HANDLED_CORPUS_DIR" "清洗后语料目录"; then
        echo "请先运行步骤1（清洗）"
        return 1
    fi
    
    local output_dir
    output_dir=$(dirname "$LIGHT_POOL_FILE")
    mkdir -p "$output_dir"
    
    run_cmd "python tools/filter_corpus_light.py \\
        --input '$HANDLED_CORPUS_DIR' \\
        --output '$LIGHT_POOL_FILE' \\
        --min-chars 200 \\
        --max-chars 4000 \\
        --use-llm \\
        --cfg configs/cfg.yaml"
    
    echo "✅ 过滤完成，输出文件: $LIGHT_POOL_FILE"
}

# ==============================================================================
# 步骤3: P1 - 生成 CQ
# ==============================================================================

step_p1() {
    print_step "P1" "生成能力问题 (CQ)"
    
    if ! check_file_exists "$DOMAIN_DESC_FILE" "领域描述文件"; then
        echo "使用默认领域描述..."
        DOMAIN_ARG=""
    else
        DOMAIN_ARG="--domain-file '$DOMAIN_DESC_FILE'"
    fi
    
    mkdir -p "$OUTPUT_DIR"
    
    run_cmd "python scripts/run_cq_pipeline.py \\
        --start-step p1 \\
        --only-stage \\
        --n-cq 15 \\
        --output-dir '$OUTPUT_DIR' \\
        --provider $LLM_PROVIDER \\
        --model $LLM_MODEL \\
        $DOMAIN_ARG \\
        --cfg configs/cfg.yaml"
    
    echo "✅ P1 完成，输出文件: $OUTPUT_DIR/p1_cqs.json"
}

# ==============================================================================
# 步骤4: P2 - CQ -> 初始 TBox
# ==============================================================================

step_p2() {
    print_step "P2" "CQ -> 初始 TBox"
    
    if ! check_file_exists "$OUTPUT_DIR/p1_cqs.json" "P1 CQ 文件"; then
        echo "请先运行 P1"
        return 1
    fi
    
    run_cmd "python scripts/run_cq_pipeline.py \\
        --start-step p2 \\
        --only-stage \\
        --cqs-file '$OUTPUT_DIR/p1_cqs.json' \\
        --output-dir '$OUTPUT_DIR' \\
        --provider $LLM_PROVIDER \\
        --model $LLM_MODEL \\
        --cfg configs/cfg.yaml"
    
    echo "✅ P2 完成，输出文件: $OUTPUT_DIR/p2_tbox_init.json"
}

# ==============================================================================
# 步骤5: P3 - TBox 规范化
# ==============================================================================

step_p3() {
    print_step "P3" "TBox 规范化"
    
    if ! check_file_exists "$OUTPUT_DIR/p2_tbox_init.json" "P2 TBox 文件"; then
        echo "请先运行 P2"
        return 1
    fi
    
    run_cmd "python scripts/run_cq_pipeline.py \\
        --start-step p3 \\
        --only-stage \\
        --p2-file '$OUTPUT_DIR/p2_tbox_init.json' \\
        --output-dir '$OUTPUT_DIR' \\
        --provider $LLM_PROVIDER \\
        --model $LLM_MODEL \\
        --cfg configs/cfg.yaml"
    
    echo "✅ P3 完成，输出文件: $OUTPUT_DIR/p3_tbox_normalized.json"
}

# ==============================================================================
# 步骤6: P4 - 文献驱动增强
# ==============================================================================

step_p4() {
    print_step "P4" "文献驱动增强 (run_p4_batch.py)"
    
    if ! check_file_exists "$OUTPUT_DIR/p3_tbox_normalized.json" "P3 TBox 文件"; then
        echo "请先运行 P3"
        return 1
    fi
    
    if ! check_dir_exists "$P4_CORPUS_DIR" "P4 增强语料目录"; then
        echo "⚠️  P4 增强语料目录不存在，跳过 P4"
        echo "如需运行 P4，请将语料放入 $P4_CORPUS_DIR"
        # 复制 P3 输出作为 P4 输出
        cp "$OUTPUT_DIR/p3_tbox_normalized.json" "$OUTPUT_DIR/p4_tbox_augmented_s2_allow0.json"
        return 0
    fi
    
    run_cmd "python scripts/run_p4_batch.py \\
        --base-tbox '$OUTPUT_DIR/p3_tbox_normalized.json' \\
        --corpus-dir '$P4_CORPUS_DIR' \\
        --final-dir '$OUTPUT_DIR' \\
        --min-support 2 \\
        --cfg configs/cfg.yaml"
    
    echo "✅ P4 完成，输出文件: $OUTPUT_DIR/p4_tbox_augmented_*.json"
}

# ==============================================================================
# 步骤7: P5 - 批量事件/三元组抽取
# ==============================================================================

step_p5() {
    print_step "P5" "批量事件/三元组抽取"
    
    # 查找最优 TBox（优先 P4 > P3）
    local tbox_file=""
    if [[ -f "$OUTPUT_DIR/p4_tbox_augmented_s2_allow0.json" ]]; then
        tbox_file="$OUTPUT_DIR/p4_tbox_augmented_s2_allow0.json"
    elif [[ -f "$OUTPUT_DIR/p3_tbox_normalized.json" ]]; then
        tbox_file="$OUTPUT_DIR/p3_tbox_normalized.json"
    else
        echo "未找到 TBox 文件，请先运行 P3 或 P4"
        return 1
    fi
    
    if ! check_file_exists "$LIGHT_POOL_FILE" "过滤后语料文件"; then
        echo "请先运行步骤2（过滤）"
        return 1
    fi
    
    run_cmd "python scripts/run_cq_pipeline.py \\
        --start-step p5 \\
        --p4-file '$tbox_file' \\
        --corpus-jsonl '$LIGHT_POOL_FILE' \\
        --include-context \\
        --favor-existing-classes \\
        --output-dir '$OUTPUT_DIR' \\
        --provider $LLM_PROVIDER \\
        --model $LLM_MODEL \\
        --save-interval 10 \\
        --cfg configs/cfg.yaml"
    
    echo "✅ P5 完成，输出文件:"
    echo "   - $OUTPUT_DIR/p5_batch_results.jsonl"
    echo "   - $OUTPUT_DIR/p5_all_events.json"
    echo "   - $OUTPUT_DIR/p5_all_triples.json"
}

# ==============================================================================
# 完整流程运行
# ==============================================================================

run_full_pipeline() {
    local start_step=${1:-1}
    
    print_banner
    
    # 根据起始步骤确定执行顺序
    case $start_step in
        1|clean)
            step1_clean
            step2_filter
            step_p1
            step_p2
            step_p3
            step_p4
            step_p5
            ;;
        2|filter)
            step2_filter
            step_p1
            step_p2
            step_p3
            step_p4
            step_p5
            ;;
        p1)
            step_p1
            step_p2
            step_p3
            step_p4
            step_p5
            ;;
        p2)
            step_p2
            step_p3
            step_p4
            step_p5
            ;;
        p3)
            step_p3
            step_p4
            step_p5
            ;;
        p4)
            step_p4
            step_p5
            ;;
        p5)
            step_p5
            ;;
        *)
            echo "未知步骤: $start_step"
            echo "可选值: 1, 2, p1, p2, p3, p4, p5"
            exit 1
            ;;
    esac
    
    echo ""
    echo "=============================================================="
    echo "  ✅ 流程执行完成！"
    echo "=============================================================="
    echo "  输出目录: $OUTPUT_DIR"
    echo ""
}

run_single_step() {
    local step=$1
    
    print_banner
    
    case $step in
        1|clean)   step1_clean ;;
        2|filter)  step2_filter ;;
        p1)        step_p1 ;;
        p2)        step_p2 ;;
        p3)        step_p3 ;;
        p4)        step_p4 ;;
        p5)        step_p5 ;;
        *)
            echo "未知步骤: $step"
            exit 1
            ;;
    esac
}

# ==============================================================================
# 参数解析
# ==============================================================================

show_help() {
    cat << EOF
用法: $0 [选项]

选项:
  --start-step STEP   从指定步骤开始 (1/2/p1/p2/p3/p4/p5)
  --only-step STEP    仅运行指定步骤
  --skip-clean        跳过清洗步骤
  --skip-filter       跳过过滤步骤
  --dry-run           试运行，仅显示命令
  --help              显示帮助信息

步骤说明:
  1 / clean   - 语料清洗 (corpus_cleaner.py)
  2 / filter  - 语料过滤 (filter_corpus_light.py)
  p1          - 生成 CQ
  p2          - CQ -> 初始 TBox
  p3          - TBox 规范化
  p4          - 文献驱动增强
  p5          - 批量事件/三元组抽取

示例:
  $0                          # 完整流程
  $0 --start-step p1          # 从 P1 开始
  $0 --only-step p5           # 仅运行 P5
  $0 --dry-run                # 试运行
EOF
}

# 默认值
START_STEP="1"
ONLY_STEP=""
DRY_RUN="false"

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --start-step)
            START_STEP="$2"
            shift 2
            ;;
        --only-step)
            ONLY_STEP="$2"
            shift 2
            ;;
        --skip-clean)
            START_STEP="2"
            shift
            ;;
        --skip-filter)
            START_STEP="p1"
            shift
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
done

# ==============================================================================
# 主程序
# ==============================================================================

activate_conda

if [[ -n "$ONLY_STEP" ]]; then
    run_single_step "$ONLY_STEP"
else
    run_full_pipeline "$START_STEP"
fi
