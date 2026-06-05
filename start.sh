#!/bin/bash
# 友达世界启动脚本 (Mac / Linux)
# 用法: bash start.sh  或  chmod +x start.sh && ./start.sh

cd "$(dirname "$0")"

echo "========================================"
echo "   友达世界 - 多Agent社会模拟"
echo "========================================"
echo

# 清理字节码缓存
if [ -d "__pycache__" ]; then
    rm -rf __pycache__
    echo "已清理 __pycache__"
fi

# 安装依赖
echo "安装依赖..."
pip install -r requirements.txt -q

# 杀掉占用 8000 端口的旧进程
OLD_PID=$(lsof -ti:8000 2>/dev/null)
if [ -n "$OLD_PID" ]; then
    kill -9 $OLD_PID 2>/dev/null
    echo "已终止旧进程 $OLD_PID"
    sleep 1
fi

# 自动打开浏览器（3秒后）
(sleep 3 && open http://localhost:8000) &

echo
echo "启动服务器 http://localhost:8000"
echo "按 Ctrl+C 停止"
echo

python -B server.py
