#!/bin/bash
# =============================================================================
# 完整流程执行脚本 v2.0
# 基于新的数据划分 (manifest_v3) 和更新的流程设计
# =============================================================================
#
# 数据现状:
#   - P4语料: data/corpus_for_onto/p4_only_v3.jsonl (567条)
#   - P5语料: data/corpus_for_kg/p5_only_v3.jsonl (5698条)
#   - 评测池: data/p5_eval_pool/pool_v3.jsonl (1100条)
#     - dev.jsonl (647条)
#     - test.jsonl (453条)
#   - CQ问题: outputs/cq_pipeline/final/p1_cqs_train.json (已有)
#
# 流程:
#   阶段1: 本体构建 (P1-P4+)
#   阶段2: 知识抽取 (P5-P6+)
#   阶段3: 黄金标注生成
#   阶段4: 评估与消融实验
#
# 用法:
#   ./scripts/run_full_pipeline_v2.sh [选项]
#
# 选项:
#   --from-p2        从P2开始（使用已有CQ）
#   --from-p4        从P4开始（使用已有P3 TBox）
#   --from-p5        从P5开始（使用已有P4 TBox）
#   --only-gold      仅生成黄金标注
#   --only-eval      仅运行评估
#   --only-ablation  仅运行消融实验
#   --dry-run        仅显示命令不执行
#
# =============================================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
PROJECT_ROOT="/home/zjx/project/YangtzeDestoryLLM"
OUTPUT_DIR="$PROJECT_ROOT/outputs/cq_pipeline/final"
ABLATION_DIR="$PROJECT_ROOT/outputs/ablation"
LOG_DIR="$PROJECT_ROOT/logs/pipeline"

# 数据文件
P4_CORPUS="$PROJECT_ROOT/data/corpus_for_onto/p4_only_v3.jsonl"
P5_CORPUS="$PROJECT_ROOT/data/corpus_for_kg/p5_only_v3.jsonl"
EVAL_TEST="$PROJECT_ROOT/data/p5_eval_pool/test.jsonl"
EVAL_DEV="$PROJECT_ROOT/data/p5_eval_pool/dev.jsonl"

# 输出文件
CQ_TRAIN="$OUTPUT_DIR/p1_cqs_train.json"
CQ_TEST="$OUTPUT_DIR/p1_cqs_test.json"
TBOX_P2="$OUTPUT_DIR/p2_tbox_init.json"
TBOX_P3="$OUTPUT_DIR/p3_tbox_normalized.json"
TBOX_P4="$OUTPUT_DIR/p4_tbox_augmented.json"
TBOX_FINAL="$OUTPUT_DIR/tbox_final_dedup.json"
EXPERT_SKELETON="$PROJECT_ROOT/data/expert_skeleton.json"

# 黄金标注
GOLD_FILE="$PROJECT_ROOT/data/p5_eval_pool/gold_independent.jsonl"

# 参数解析
DRY_RUN=false
START_STEP="p1"
ONLY_MODE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --from-p2) START_STEP="p2"; shift ;;
        --from-p4) START_STEP="p4"; shift ;;
        --from-p5) START_STEP="p5"; shift ;;
        --only-gold) ONLY_MODE="gold"; shift ;;
        --only-eval) ONLY_MODE="eval"; shift ;;
        --only-ablation) ONLY_MODE="ablation"; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

# 创建目录
mkdir -p "$OUTPUT_DIR" "$ABLATION_DIR" "$LOG_DIR"

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

run_cmd() {
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY-RUN]${NC} $1"
    else
        log_info "执行: $1"
        eval "$1"
    fi
}

# =============================================================================
# 阶段1: 本体构建 (P1-P4+)
# =============================================================================
run_ontology_building() {
    echo ""
    echo "============================================================"
    echo "  阶段1: 本体构建 (P1-P4+)"
    echo "============================================================"

    # P1: CQ生成（如果不存在）
    if [[ "$START_STEP" == "p1" ]]; then
        if [[ -f "$CQ_TRAIN" ]]; then
            log_warn "CQ文件已存在，跳过P1: $CQ_TRAIN"
        else
            log_info "P1: 生成CQ问题..."
            run_cmd "cd $PROJECT_ROOT && python scripts/run_cq_pipeline.py --only-stage p1 --n-cq 50"
        fi
    fi

    # P2: CQ → 初始TBox
    if [[ "$START_STEP" == "p1" || "$START_STEP" == "p2" ]]; then
        log_info "P2: CQ → 初始TBox..."
        run_cmd "cd $PROJECT_ROOT && python scripts/run_cq_pipeline.py --start-step p2 --only-stage p2"
    fi

    # P3: TBox规范化
    if [[ "$START_STEP" == "p1" || "$START_STEP" == "p2" || "$START_STEP" == "p3" ]]; then
        log_info "P3: TBox规范化..."
        run_cmd "cd $PROJECT_ROOT && python scripts/run_cq_pipeline.py --start-step p3 --only-stage p3"
    fi

    # P4: 文献增强（使用新语料）
    if [[ "$START_STEP" != "p5" ]]; then
        log_info "P4: 文献驱动增强 (使用 p4_only_v3.jsonl)..."
        run_cmd "cd $PROJECT_ROOT && python scripts/run_p4_batch.py \\
            --base-tbox $TBOX_P3 \\
            --corpus-jsonl $P4_CORPUS \\
            --min-support 2 \\
            --allow-new-classes false \\
            --output $OUTPUT_DIR"
    fi

    log_success "本体构建完成！"
    log_info "最终TBox: $TBOX_P4"
}

# =============================================================================
# 阶段2: 知识抽取 (P5-P6+)
# =============================================================================
run_knowledge_extraction() {
    echo ""
    echo "============================================================"
    echo "  阶段2: 知识抽取 (P5-P6+)"
    echo "============================================================"

    # 检查TBox是否存在
    if [[ ! -f "$TBOX_P4" ]]; then
        log_error "P4 TBox不存在: $TBOX_P4"
        log_error "请先运行本体构建阶段，或使用 --from-p4"
        exit 1
    fi

    # P5: CoT抽取 + P6: 幻觉过滤
    log_info "P5+P6: CoT抽取 + 原文回溯校验..."
    run_cmd "cd $PROJECT_ROOT && python scripts/run_p2_to_p6.py \\
        --tbox $TBOX_P4 \\
        --corpus $P5_CORPUS \\
        --output-dir $OUTPUT_DIR/p5_extraction \\
        --use-cot \\
        --use-verification \\
        --max-docs 100"

    log_success "知识抽取完成！"
}

# =============================================================================
# 阶段3: 黄金标注生成
# =============================================================================
run_gold_generation() {
    echo ""
    echo "============================================================"
    echo "  阶段3: 黄金标注生成 (独立Schema)"
    echo "============================================================"

    if [[ -f "$GOLD_FILE" ]]; then
        log_warn "黄金标注已存在: $GOLD_FILE"
        read -p "是否覆盖? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "跳过黄金标注生成"
            return
        fi
    fi

    log_info "使用独立Schema生成黄金标注..."
    run_cmd "cd $PROJECT_ROOT && python scripts/generate_gold_independent.py \\
        --input $EVAL_TEST \\
        --out $GOLD_FILE \\
        --model gpt-4o \\
        --temperature 0.1 \\
        --resume"

    log_success "黄金标注生成完成: $GOLD_FILE"
}

# =============================================================================
# 阶段4: 消融实验
# =============================================================================
run_ablation() {
    echo ""
    echo "============================================================"
    echo "  阶段4: 消融实验"
    echo "============================================================"

    # 检查必要文件
    if [[ ! -f "$GOLD_FILE" ]]; then
        log_error "黄金标注不存在: $GOLD_FILE"
        log_error "请先运行黄金标注生成: --only-gold"
        exit 1
    fi

    # -----------------------------
    # 4.1 TBox消融实验
    # -----------------------------
    log_info "4.1 TBox消融实验..."

    # 准备wo_cq变体的TBox（专家骨架 + P4增强）
    TBOX_WO_CQ="$ABLATION_DIR/tbox/wo_cq_p4_augmented.json"
    if [[ ! -f "$TBOX_WO_CQ" ]]; then
        log_info "生成wo_cq变体TBox（专家骨架 + P4增强）..."
        mkdir -p "$ABLATION_DIR/tbox"
        run_cmd "cd $PROJECT_ROOT && python scripts/run_p4_batch.py \\
            --base-tbox $EXPERT_SKELETON \\
            --corpus-jsonl $P4_CORPUS \\
            --min-support 2 \\
            --allow-new-classes false \\
            --output $ABLATION_DIR/tbox"
    fi

    # 运行TBox评估
    log_info "运行TBox消融评估..."
    run_cmd "cd $PROJECT_ROOT && python scripts/run_ablation_full.py \\
        --tbox-ablation \\
        --test-cqs $CQ_TEST \\
        --output-dir $ABLATION_DIR"

    # -----------------------------
    # 4.2 ABox消融实验
    # -----------------------------
    log_info "4.2 ABox消融实验..."
    run_cmd "cd $PROJECT_ROOT && python scripts/run_ablation_full.py \\
        --abox-ablation \\
        --corpus $EVAL_TEST \\
        --gold $GOLD_FILE \\
        --tbox $TBOX_P4 \\
        --output-dir $ABLATION_DIR"

    log_success "消融实验完成！"
    log_info "报告位置: $ABLATION_DIR/ablation_report.json"
    log_info "Markdown报告: $ABLATION_DIR/ablation_report.md"
}

# =============================================================================
# 阶段5: 完整评估
# =============================================================================
run_evaluation() {
    echo ""
    echo "============================================================"
    echo "  阶段5: 完整评估"
    echo "============================================================"

    log_info "运行完整评估..."
    run_cmd "cd $PROJECT_ROOT && python scripts/run_full_evaluation.py \\
        --tbox $TBOX_P4 \\
        --cqs $CQ_TEST \\
        --gold $GOLD_FILE \\
        --preds $OUTPUT_DIR/p5_extraction/predictions.json \\
        --out $OUTPUT_DIR/evaluation_report.json"

    log_success "评估完成！"
    log_info "报告位置: $OUTPUT_DIR/evaluation_report.json"
}

# =============================================================================
# 主流程
# =============================================================================
main() {
    echo ""
    echo "============================================================"
    echo "  CQ-Enhanced 知识图谱构建完整流程 v2.0"
    echo "============================================================"
    echo ""
    log_info "项目根目录: $PROJECT_ROOT"
    log_info "起始步骤: $START_STEP"
    log_info "仅运行模式: ${ONLY_MODE:-无}"
    log_info "Dry-run: $DRY_RUN"
    echo ""

    # 根据模式执行
    if [[ "$ONLY_MODE" == "gold" ]]; then
        run_gold_generation
    elif [[ "$ONLY_MODE" == "eval" ]]; then
        run_evaluation
    elif [[ "$ONLY_MODE" == "ablation" ]]; then
        run_ablation
    else
        # 完整流程
        if [[ "$START_STEP" != "p5" ]]; then
            run_ontology_building
        fi
        run_knowledge_extraction
        run_gold_generation
        run_ablation
        run_evaluation
    fi

    echo ""
    echo "============================================================"
    log_success "全部流程执行完成！"
    echo "============================================================"
}

# 执行主流程
main
