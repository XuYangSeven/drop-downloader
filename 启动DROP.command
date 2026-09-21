#!/bin/bash
# DROP 双击启动脚本 (macOS) — 启动本地下载服务并自动打开网页
cd "$(dirname "$0")"

if lsof -ti :8777 >/dev/null 2>&1; then
  open "http://127.0.0.1:8777/"
  exit 0
fi

echo "=============================="
echo "  DROP · 本地视频下载器"
echo "=============================="
echo "正在启动服务 ..."

# 首次运行自动装依赖
if ! python3 -c "import fastapi, uvicorn, yt_dlp" >/dev/null 2>&1; then
  echo "首次运行, 正在安装依赖 ..."
  python3 -m pip install -r requirements.txt
fi

# 此窗口保持打开, 关闭窗口 = 停止服务
exec python3 server.py
