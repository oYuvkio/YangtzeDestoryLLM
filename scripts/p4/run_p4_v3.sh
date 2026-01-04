#!/bin/bash
# =============================================================================
# P4 文献增强脚本 v3
# 生成两个版本：allow1（允许新增类）和 allow0（不允许新增类）
# 用于对比分析新增类的质量
# =============================================================================

set -eo pipefail

# 环境设置
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
export NO_PROXY="localhost,127.0.0.1,api.uglycat.cc,api.longcat.chat"

cd /home/zjx/project/YangtzeDestoryLLM

source /home/zjx/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM
export PYTHONPATH=.

# 路径配置
BASE_TBOX="outputs/cq_pipeline/final/p3_tbox_normalized.json"
CORPUS="data/corpus_for_onto/p4_only_v3.jsonl"
PROCESS_DIR="outputs/cq_pipeline/process_v3"
FINAL_DIR="outputs/cq_pipeline/final"

mkdir -p "$PROCESS_DIR" "$FINAL_DIR" logs

echo "========================================"
echo "P4 文献增强 v3"
echo "语料: $CORPUS (567条)"
echo "基线TBox: $BASE_TBOX"
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

# -----------------------------------------------------------------------------
# 版本1: allow_new_classes=True（允许新增类）
# 策略: 召回优先，后续通过P4+去重保证精确率
# -----------------------------------------------------------------------------
echo ""
echo "========================================"
echo "[1/2] 运行 allow_new_classes=True 版本"
echo "  - min_support: 2, 3"
echo "  - 允许从语料中发现新概念"
echo "========================================"

python scripts/run_p4_batch.py \
    --base-tbox "$BASE_TBOX" \
    --corpus-jsonl "$CORPUS" \
    --process-dir "${PROCESS_DIR}_allow1" \
    --final-dir "$FINAL_DIR" \
    --min-support 2 \
    --extra-supports 3 \
    --allow-new-classes \
    --no-auto-allow1 \
    --align-names \
    --dedup-new \
    --dedup-threshold 0.7 \
    --conflict-report outputs/ontoqa/p4_conflicts_v3_allow1.json \
    --log-file logs/p4_v3_allow1.log

echo "[1/2] allow1 版本完成"

# -----------------------------------------------------------------------------
# 版本2: allow_new_classes=False（不允许新增类）
# 策略: 仅增强现有类的属性和关系，不引入新类
# -----------------------------------------------------------------------------
echo ""
echo "========================================"
echo "[2/2] 运行 allow_new_classes=False 版本"
echo "  - min_support: 2, 3"
echo "  - 仅增强现有类"
echo "========================================"

python scripts/run_p4_batch.py \
    --base-tbox "$BASE_TBOX" \
    --corpus-jsonl "$CORPUS" \
    --process-dir "${PROCESS_DIR}_allow0" \
    --final-dir "$FINAL_DIR" \
    --min-support 2 \
    --extra-supports 3 \
    --no-auto-allow1 \
    --align-names \
    --dedup-new \
    --dedup-threshold 0.7 \
    --conflict-report outputs/ontoqa/p4_conflicts_v3_allow0.json \
    --log-file logs/p4_v3_allow0.log

echo "[2/2] allow0 版本完成"

# -----------------------------------------------------------------------------
# 对比分析
# -----------------------------------------------------------------------------
echo ""
echo "========================================"
echo "生成对比报告"
echo "========================================"

python -c "
import json
from pathlib import Path
from glob import glob

# 找到最新的输出文件
allow1_files = sorted(glob('$FINAL_DIR/p4_tbox_augmented_s2_allow1*.json'), reverse=True)
allow0_files = sorted(glob('$FINAL_DIR/p4_tbox_augmented_s2_allow0*.json'), reverse=True)

if not allow1_files or not allow0_files:
    print('警告: 未找到输出文件')
    exit(0)

allow1_path = allow1_files[0]
allow0_path = allow0_files[0]

print(f'对比文件:')
print(f'  allow1: {allow1_path}')
print(f'  allow0: {allow0_path}')
print()

# 加载数据
with open(allow1_path, 'r', encoding='utf-8') as f:
    allow1 = json.load(f)
with open(allow0_path, 'r', encoding='utf-8') as f:
    allow0 = json.load(f)

# 提取类名
classes_allow1 = {c['name'] for c in allow1.get('classes', [])}
classes_allow0 = {c['name'] for c in allow0.get('classes', [])}

# 新增的类
new_classes = classes_allow1 - classes_allow0

print('=' * 60)
print('对比结果')
print('=' * 60)
print(f'allow1 类数量: {len(classes_allow1)}')
print(f'allow0 类数量: {len(classes_allow0)}')
print(f'新增类数量: {len(new_classes)}')
print()

if new_classes:
    print('新增的类:')
    # 找到新增类的详细信息
    new_class_details = [c for c in allow1.get('classes', []) if c['name'] in new_classes]
    for c in sorted(new_class_details, key=lambda x: x.get('name', '')):
        name = c.get('name', '')
        cn_name = c.get('cn_name', '')
        parent = c.get('parent', '')
        print(f'  - {name} ({cn_name}) [parent: {parent}]')

    # 保存新增类报告
    report = {
        'allow1_file': allow1_path,
        'allow0_file': allow0_path,
        'allow1_class_count': len(classes_allow1),
        'allow0_class_count': len(classes_allow0),
        'new_classes': new_class_details
    }
    report_path = Path('outputs/ontoqa/p4_new_classes_report.json')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print()
    print(f'详细报告已保存: {report_path}')
else:
    print('无新增类')

# 对比关系
rels_allow1 = {r['name'] for r in allow1.get('relations', [])}
rels_allow0 = {r['name'] for r in allow0.get('relations', [])}
new_rels = rels_allow1 - rels_allow0

print()
print(f'allow1 关系数量: {len(rels_allow1)}')
print(f'allow0 关系数量: {len(rels_allow0)}')
print(f'新增关系数量: {len(new_rels)}')
if new_rels:
    print('新增的关系:')
    for r in sorted(new_rels):
        print(f'  - {r}')
"

echo ""
echo "========================================"
echo "全部完成！"
echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"
echo ""
echo "生成文件:"
echo "  - $FINAL_DIR/p4_tbox_augmented_s2_allow1_*.json (允许新类)"
echo "  - $FINAL_DIR/p4_tbox_augmented_s3_allow1_*.json (允许新类, support=3)"
echo "  - $FINAL_DIR/p4_tbox_augmented_s2_allow0_*.json (不允许新类)"
echo "  - $FINAL_DIR/p4_tbox_augmented_s3_allow0_*.json (不允许新类, support=3)"
echo "  - outputs/ontoqa/p4_new_classes_report.json (新增类对比报告)"
echo ""
echo "推荐使用:"
echo "  - 若追求覆盖度: 使用 allow1 版本"
echo "  - 若追求精确度: 使用 allow0 版本"
echo ""
