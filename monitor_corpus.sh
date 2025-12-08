#!/bin/bash
# 监控 corpus_cleaner 进程的网络连接状态

echo "=== corpus_cleaner 进程监控工具 ==="
echo ""

# 查找进程
PID=$(pgrep -f "corpus_cleaner.py" | head -1)

if [ -z "$PID" ]; then
    echo "❌ 未找到 corpus_cleaner 进程"
    echo ""
    echo "使用方法："
    echo "  1. 在另一个终端运行: python3 tools/corpus_cleaner.py --input ..."
    echo "  2. 然后运行此脚本: ./monitor_corpus.sh"
    exit 1
fi

echo "✅ 找到进程: PID = $PID"
echo ""

# 显示进程基本信息
echo "【进程信息】"
ps -p $PID -o pid,state,etime,cmd --no-headers
echo ""

# 显示网络连接
echo "【网络连接】"
if command -v lsof >/dev/null 2>&1; then
    CONNECTIONS=$(sudo lsof -i -p $PID 2>/dev/null | grep -v "COMMAND")
    if [ -n "$CONNECTIONS" ]; then
        echo "$CONNECTIONS"
        
        # 统计连接状态
        ESTABLISHED=$(echo "$CONNECTIONS" | grep -c "ESTABLISHED" || true)
        TIME_WAIT=$(echo "$CONNECTIONS" | grep -c "TIME_WAIT" || true)
        CLOSE_WAIT=$(echo "$CONNECTIONS" | grep -c "CLOSE_WAIT" || true)
        
        echo ""
        echo "连接统计:"
        echo "  - ESTABLISHED (活跃): $ESTABLISHED"
        echo "  - TIME_WAIT (等待关闭): $TIME_WAIT"
        echo "  - CLOSE_WAIT (待关闭): $CLOSE_WAIT"
    else
        echo "  无网络连接"
    fi
else
    echo "  ⚠️  lsof 未安装，无法查看网络连接"
    echo "  安装命令: sudo apt-get install lsof"
fi

echo ""

# 显示文件描述符数量
echo "【文件描述符】"
if [ -d "/proc/$PID/fd" ]; then
    FD_COUNT=$(ls -1 /proc/$PID/fd 2>/dev/null | wc -l)
    echo "  打开的文件描述符数量: $FD_COUNT"
else
    echo "  无法访问 /proc/$PID/fd"
fi

echo ""
echo "提示："
echo "  - 如果 ESTABLISHED 连接在程序完成后仍不消失，说明连接未关闭"
echo "  - 正常情况下，程序结束后所有连接应该立即关闭"
echo ""
echo "实时监控（每2秒刷新）："
echo "  watch -n 2 './monitor_corpus.sh'"
