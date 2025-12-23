#!/bin/bash
# P4 文献驱动 TBox 增强批处理脚本

cd /home/zjx/dev_ops/YangtzeDestoryLLM

# 使用完整 Python 路径（或者用户需要在运行前激活 conda 环境）
PYTHONPATH=. /home/zjx/miniconda3/envs/YangtzeLLM/bin/python scripts/run_p4_batch.py \
    --base-tbox outputs/cq_pipeline/final/p3_tbox_dedup.json \
    --corpus-jsonl data/corpus_for_onto/p4_only.jsonl \
    --min-support 2 \
    --extra-supports 1,3 \
    --align-names \
    --dedup-new \
    --conflict-policy keep_existing \
    --conflict-report outputs/ontoqa/p4_conflicts.json \
    --log-file logs/p4_batch.log \
    --seed 42
