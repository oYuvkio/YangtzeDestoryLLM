#!/bin/bash
# 并行运行 P4 增强的两个版本（allow0 和 allow1）
# 用法: bash run_p4_parallel.sh
# 说明: 在两个独立的后台进程中同时运行，节省时间

set -eo pipefail

cd /home/zjx/dev_ops/YangtzeDestoryLLM

# 确保日志目录存在，避免后台重定向失败
mkdir -p logs

echo "========================================"
echo "🚀 并行启动 P4 增强任务"
echo "========================================"
echo ""
echo "任务 1: allow_new_classes=False"
echo "任务 2: allow_new_classes=True"
echo ""
echo "预计总耗时: 约 2-3 小时（并行执行）"
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 启动 allow0（后台）
echo "▶️  启动任务 1 (allow0)..."
bash run_p4_allow0.sh > logs/p4_parallel_allow0.log 2>&1 &
PID_ALLOW0=$!
echo "   PID: $PID_ALLOW0"
echo "   日志: logs/p4_parallel_allow0.log"

# 启动 allow1（后台）
echo "▶️  启动任务 2 (allow1)..."
bash run_p4_allow1.sh > logs/p4_parallel_allow1.log 2>&1 &
PID_ALLOW1=$!
echo "   PID: $PID_ALLOW1"
echo "   日志: logs/p4_parallel_allow1.log"

echo ""
echo "✅ 两个任务已启动！"
echo ""
echo "========================================"
echo "📊 监控进度"
echo "========================================"
echo ""
echo "实时查看日志："
echo "   tail -f logs/p4_parallel_allow0.log"
echo "   tail -f logs/p4_parallel_allow1.log"
echo ""
echo "或者："
echo "   tail -f logs/p4_with_hierarchy_allow0.log"
echo "   tail -f logs/p4_with_hierarchy_allow1.log"
echo ""
echo "检查进程状态："
echo "   ps aux | grep run_p4_batch.py"
echo ""
echo "等待两个任务完成："
echo "   wait $PID_ALLOW0 $PID_ALLOW1"
echo ""
echo "========================================"

# 可选：等待两个任务完成
# wait $PID_ALLOW0
# wait $PID_ALLOW1
# echo ""
# echo "🎉 两个任务都已完成！"
# echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
