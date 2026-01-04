#!/bin/bash
#===============================================================================
# P5 知识抽取脚本
#
# 使用选定的TBox对语料进行事件与三元组抽取
#
# TBox文件：p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json
#
# 使用方式：
#   bash scripts/run_p5_extraction.sh
#   bash scripts/run_p5_extraction.sh --limit 50   # 限制处理数量
#   bash scripts/run_p5_extraction.sh --rerun      # 重跑失败的
#===============================================================================

set -e

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# 选定的TBox文件
TBOX_FILE="outputs/cq_pipeline/final/p4_tbox_dedup_s2_allow1_20260102_232204_t0p80.json"

# 语料目录（P5抽取用的语料）
CORPUS_DIR="data/corpus_for_extraction"

# 输出目录
OUTPUT_DIR="outputs/cq_pipeline/p5_extraction"

# 默认参数
MAX_FILES=""
RERUN_EMPTY=""
OVERWRITE=""
MODEL="gpt-4o-mini"
PROVIDER="openai"

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --limit)
            MAX_FILES="--max-files $2"
            shift 2
            ;;
        --rerun)
            RERUN_EMPTY="--rerun-empty"
            shift
            ;;
        --overwrite)
            OVERWRITE="--overwrite"
            shift
            ;;
        --model)
            MODEL="$2"
            shift 2
            ;;
        --provider)
            PROVIDER="$2"
            shift 2
            ;;
        --corpus)
            CORPUS_DIR="$2"
            shift 2
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

# 检查TBox文件
if [ ! -f "$TBOX_FILE" ]; then
    echo "[ERROR] TBox文件不存在: $TBOX_FILE"
    exit 1
fi

# 检查语料目录
if [ ! -d "$CORPUS_DIR" ]; then
    echo "[WARN] 语料目录不存在: $CORPUS_DIR"
    echo "[INFO] 请先准备语料目录，或使用 --corpus 指定路径"
    echo ""
    echo "示例语料准备："
    echo "  mkdir -p $CORPUS_DIR"
    echo "  # 将待抽取的txt文件放入该目录"
    echo ""

    # 尝试使用P4语料
    ALT_CORPUS="data/corpus_for_onto"
    if [ -d "$ALT_CORPUS" ]; then
        echo "[INFO] 发现P4语料目录: $ALT_CORPUS"
        echo "[INFO] 可以使用: bash scripts/run_p5_extraction.sh --corpus $ALT_CORPUS"
    fi
    exit 1
fi

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 统计信息
TBOX_CLASSES=$(python3 -c "import json; d=json.load(open('$TBOX_FILE')); print(len(d.get('classes',[])))")
TBOX_RELATIONS=$(python3 -c "import json; d=json.load(open('$TBOX_FILE')); print(len(d.get('relations',[])))")
TBOX_ATTRS=$(python3 -c "import json; d=json.load(open('$TBOX_FILE')); print(len(d.get('attributes',[])))")
CORPUS_COUNT=$(find "$CORPUS_DIR" -name "*.txt" -type f | wc -l)

echo "============================================================"
echo "P5 知识抽取"
echo "============================================================"
echo "TBox文件: $TBOX_FILE"
echo "  - 类: $TBOX_CLASSES"
echo "  - 关系: $TBOX_RELATIONS"
echo "  - 属性: $TBOX_ATTRS"
echo "------------------------------------------------------------"
echo "语料目录: $CORPUS_DIR"
echo "语料数量: $CORPUS_COUNT 个文件"
echo "输出目录: $OUTPUT_DIR"
echo "------------------------------------------------------------"
echo "模型: $PROVIDER / $MODEL"
echo "参数: $MAX_FILES $RERUN_EMPTY $OVERWRITE"
echo "============================================================"
echo ""

# 运行P5抽取
python scripts/p5_from_tbox.py \
    --tbox-file "$TBOX_FILE" \
    --corpus-dir "$CORPUS_DIR" \
    --output-dir "$OUTPUT_DIR" \
    --provider "$PROVIDER" \
    --model "$MODEL" \
    --split-long \
    --favor-existing-classes \
    $MAX_FILES \
    $RERUN_EMPTY \
    $OVERWRITE

echo ""
echo "============================================================"
echo "P5 抽取完成"
echo "============================================================"
echo "输出目录: $OUTPUT_DIR"
echo "进度文件: $OUTPUT_DIR/_p5_progress.json"
echo ""

# 统计结果
if [ -f "$OUTPUT_DIR/_p5_progress.json" ]; then
    echo "抽取统计:"
    python3 -c "
import json
from pathlib import Path

progress = json.load(open('$OUTPUT_DIR/_p5_progress.json'))
print(f'  处理完成: {len(progress.get(\"processed\", []))} 个文件')
print(f'  跳过已存在: {len(progress.get(\"skipped_existing\", []))} 个')
print(f'  失败: {len(progress.get(\"failed\", []))} 个')
print(f'  配额耗尽: {progress.get(\"quota_exhausted\", False)}')

# 统计事件和三元组
out_dir = Path('$OUTPUT_DIR')
total_events = 0
total_triples = 0
for f in out_dir.rglob('*_p5.json'):
    try:
        d = json.loads(f.read_text())
        total_events += len(d.get('events', []))
        total_triples += len(d.get('triples', []))
    except:
        pass
print(f'  总事件数: {total_events}')
print(f'  总三元组数: {total_triples}')
"
fi
