#!/bin/bash
# 重新运行 P1-P3 生成带继承关系的 TBox

cd /home/zjx/dev_ops/YangtzeDestoryLLM

# 激活环境
source ~/miniconda3/etc/profile.d/conda.sh
conda activate YangtzeLLM

# 设置 PYTHONPATH
export PYTHONPATH=.

# 运行 P1-P3 流程
python scripts/run_cq_pipeline.py \
  --start-step p1 \
  --end-step p3 \
  --output-dir outputs/cq_pipeline/with_hierarchy \
  --log-file logs/rebuild_hierarchy.log \
  --n-cqs 30

echo "✅ P1-P3 完成！"
echo "📁 输出目录: outputs/cq_pipeline/with_hierarchy/"
echo "📋 日志文件: logs/rebuild_hierarchy.log"
