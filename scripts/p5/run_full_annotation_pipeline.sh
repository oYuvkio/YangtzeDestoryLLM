#!/bin/bash
# =============================================================================
# 完整的标注-审查-划分流程
#
# 流程：
# 1. 合并 dev + test → combined_pool.jsonl
# 2. 对合并后的语料进行 LLM 标注
# 3. 对标注结果进行二次审查过滤
# 4. 按比例重新划分 dev/test
#
# 使用方式：
#   # 查看当前状态
#   bash scripts/p5/run_full_annotation_pipeline.sh --status
#
#   # 步骤1: 合并语料（排除已标注的test）
#   bash scripts/p5/run_full_annotation_pipeline.sh --step merge
#
#   # 步骤2: 对 dev 进行标注（test 已有标注）
#   bash scripts/p5/run_full_annotation_pipeline.sh --step annotate
#
#   # 步骤3: 合并所有标注 + 二次审查
#   bash scripts/p5/run_full_annotation_pipeline.sh --step review
#
#   # 步骤4: 按比例划分
#   bash scripts/p5/run_full_annotation_pipeline.sh --step split
# =============================================================================

set -eo pipefail

cd /home/zjx/project/YangtzeDestoryLLM
source /home/zjx/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM
export PYTHONPATH=.

# 文件路径
DEV_FILE="data/p5_eval_pool/dev.jsonl"
TEST_FILE="data/p5_eval_pool/test.jsonl"
EXISTING_TEST_GOLD="data/p5_eval_pool/gold_independent_v1.jsonl"
EXISTING_RETRY_GOLD="data/p5_eval_pool/gold_failed_retry_v1.jsonl"

# 新文件路径
DEV_POOL="data/p5_eval_pool/dev_for_annotation.jsonl"
DEV_GOLD="data/p5_eval_pool/gold_dev_v1.jsonl"
COMBINED_GOLD="data/p5_eval_pool/gold_combined_all.jsonl"
REVIEWED_GOLD="data/p5_eval_pool/gold_reviewed.jsonl"
REJECTED_GOLD="data/p5_eval_pool/gold_rejected.jsonl"
FINAL_DIR="data/p5_eval_pool/final"

# 默认参数
DEV_RATIO=0.6
STEP=""

print_status() {
    echo "============================================================"
    echo "当前状态"
    echo "============================================================"
    echo ""
    echo "原始语料:"
    echo "  dev.jsonl:  $(wc -l < $DEV_FILE 2>/dev/null || echo '不存在') 条"
    echo "  test.jsonl: $(wc -l < $TEST_FILE 2>/dev/null || echo '不存在') 条"
    echo ""
    echo "已有标注:"
    echo "  gold_independent_v1.jsonl (test):   $(wc -l < $EXISTING_TEST_GOLD 2>/dev/null || echo '不存在') 条"
    echo "  gold_failed_retry_v1.jsonl (重试):  $(wc -l < $EXISTING_RETRY_GOLD 2>/dev/null || echo '不存在') 条"
    echo ""
    echo "待处理:"
    if [ -f "$DEV_POOL" ]; then
        echo "  dev_for_annotation.jsonl: $(wc -l < $DEV_POOL) 条"
    else
        echo "  dev_for_annotation.jsonl: 未生成"
    fi
    echo ""
    echo "标注结果:"
    if [ -f "$DEV_GOLD" ]; then
        echo "  gold_dev_v1.jsonl: $(wc -l < $DEV_GOLD) 条"
    else
        echo "  gold_dev_v1.jsonl: 未生成"
    fi
    echo ""
    echo "合并+审查:"
    if [ -f "$COMBINED_GOLD" ]; then
        echo "  gold_combined_all.jsonl: $(wc -l < $COMBINED_GOLD) 条"
    else
        echo "  gold_combined_all.jsonl: 未生成"
    fi
    if [ -f "$REVIEWED_GOLD" ]; then
        echo "  gold_reviewed.jsonl: $(wc -l < $REVIEWED_GOLD) 条"
    else
        echo "  gold_reviewed.jsonl: 未生成"
    fi
    if [ -f "$REJECTED_GOLD" ]; then
        echo "  gold_rejected.jsonl: $(wc -l < $REJECTED_GOLD) 条"
    else
        echo "  gold_rejected.jsonl: 未生成"
    fi
    echo ""
    echo "最终划分:"
    if [ -d "$FINAL_DIR" ]; then
        echo "  dev_final.jsonl:  $(wc -l < $FINAL_DIR/dev_final.jsonl 2>/dev/null || echo '不存在') 条"
        echo "  test_final.jsonl: $(wc -l < $FINAL_DIR/test_final.jsonl 2>/dev/null || echo '不存在') 条"
    else
        echo "  final/ 目录: 未生成"
    fi
    echo "============================================================"
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --step)
            STEP="$2"
            shift 2
            ;;
        --status)
            print_status
            exit 0
            ;;
        --dev-ratio)
            DEV_RATIO="$2"
            shift 2
            ;;
        --help)
            echo "使用方式:"
            echo "  --status       查看当前状态"
            echo "  --step merge   步骤1: 准备dev语料（排除已标注的test）"
            echo "  --step annotate 步骤2: 对dev进行标注"
            echo "  --step review  步骤3: 合并所有标注 + 二次审查"
            echo "  --step split   步骤4: 按比例划分"
            echo "  --dev-ratio N  dev比例（默认0.6）"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

case $STEP in
    merge)
        echo "============================================================"
        echo "步骤1: 准备 dev 语料（用于标注）"
        echo "============================================================"
        echo ""
        echo "已有 test 标注，只需对 dev 进行标注"
        echo ""

        # 直接复制 dev 作为待标注语料
        cp "$DEV_FILE" "$DEV_POOL"
        echo "已生成: $DEV_POOL ($(wc -l < $DEV_POOL) 条)"
        echo ""
        echo "下一步: bash scripts/p5/run_full_annotation_pipeline.sh --step annotate"
        ;;

    annotate)
        echo "============================================================"
        echo "步骤2: 对 dev 进行 LLM 标注"
        echo "============================================================"
        echo ""
        if [ ! -f "$DEV_POOL" ]; then
            echo "[ERROR] 请先运行 --step merge"
            exit 1
        fi
        echo "待标注: $DEV_POOL ($(wc -l < $DEV_POOL) 条)"
        echo ""
        echo "请手动运行标注脚本（可自定义 API 配置）:"
        echo ""
        echo "  bash scripts/p5/run_gold_annotation.sh \\"
        echo "      --input $DEV_POOL \\"
        echo "      --output $DEV_GOLD \\"
        echo "      --api-key \"YOUR_API_KEY\" \\"
        echo "      --base-url \"YOUR_BASE_URL\" \\"
        echo "      --model \"YOUR_MODEL\""
        echo ""
        echo "或编辑 scripts/p5/run_gold_annotation.sh 修改默认配置后直接运行"
        echo ""
        echo "标注完成后，运行: bash scripts/p5/run_full_annotation_pipeline.sh --step review"
        ;;

    review)
        echo "============================================================"
        echo "步骤3: 合并所有标注 + 二次审查"
        echo "============================================================"
        echo ""

        # 检查必要文件
        if [ ! -f "$DEV_GOLD" ]; then
            echo "[WARN] dev 标注文件不存在: $DEV_GOLD"
            echo "如果只想审查 test 标注，继续执行..."
        fi

        # 合并所有标注文件
        echo "合并标注文件..."
        cat /dev/null > "$COMBINED_GOLD"  # 清空

        for f in "$EXISTING_TEST_GOLD" "$EXISTING_RETRY_GOLD" "$DEV_GOLD"; do
            if [ -f "$f" ]; then
                echo "  添加: $f ($(wc -l < $f) 条)"
                cat "$f" >> "$COMBINED_GOLD"
            fi
        done

        # 去重（基于 doc_id）
        echo ""
        echo "去重处理..."
        python3 -c "
import json
from pathlib import Path

seen = {}
with open('$COMBINED_GOLD', 'r') as f:
    for line in f:
        if line.strip():
            try:
                doc = json.loads(line)
                doc_id = doc.get('doc_id', '')
                # 优先保留非 parse_error 的
                if doc_id not in seen or not doc.get('parse_error', False):
                    seen[doc_id] = doc
            except:
                pass

with open('$COMBINED_GOLD', 'w') as f:
    for doc in seen.values():
        f.write(json.dumps(doc, ensure_ascii=False) + '\n')

print(f'去重后: {len(seen)} 条')
"

        echo ""
        echo "合并完成: $COMBINED_GOLD ($(wc -l < $COMBINED_GOLD) 条)"
        echo ""
        echo "开始二次审查..."
        echo ""

        # 清空已有审查结果
        rm -f "$REVIEWED_GOLD" "$REJECTED_GOLD"

        # 运行审查脚本
        python scripts/review_gold_annotations.py \
            --input "$COMBINED_GOLD" \
            --out-accepted "$REVIEWED_GOLD" \
            --out-rejected "$REJECTED_GOLD" \
            --model "gpt-4o-mini" \
            --min-score 3 \
            --interval 1.0

        echo ""
        echo "审查完成:"
        echo "  通过: $REVIEWED_GOLD ($(wc -l < $REVIEWED_GOLD 2>/dev/null || echo 0) 条)"
        echo "  拒绝: $REJECTED_GOLD ($(wc -l < $REJECTED_GOLD 2>/dev/null || echo 0) 条)"
        echo ""
        echo "下一步: bash scripts/p5/run_full_annotation_pipeline.sh --step split"
        ;;

    split)
        echo "============================================================"
        echo "步骤4: 按比例划分 dev/test"
        echo "============================================================"
        echo ""

        if [ ! -f "$REVIEWED_GOLD" ]; then
            echo "[ERROR] 请先运行 --step review"
            exit 1
        fi

        echo "输入: $REVIEWED_GOLD ($(wc -l < $REVIEWED_GOLD) 条)"
        echo "dev 比例: $DEV_RATIO"
        echo ""

        python scripts/p5/prepare_combined_pool.py \
            --split \
            --input "$REVIEWED_GOLD" \
            --output-dir "$FINAL_DIR" \
            --dev-ratio $DEV_RATIO

        echo ""
        echo "============================================================"
        echo "全流程完成！"
        echo "============================================================"
        echo ""
        echo "最终数据集:"
        echo "  dev:  $FINAL_DIR/dev_final.jsonl ($(wc -l < $FINAL_DIR/dev_final.jsonl) 条)"
        echo "  test: $FINAL_DIR/test_final.jsonl ($(wc -l < $FINAL_DIR/test_final.jsonl) 条)"
        ;;

    *)
        echo "请指定步骤: --step merge|annotate|review|split"
        echo "或查看状态: --status"
        echo ""
        print_status
        ;;
esac
