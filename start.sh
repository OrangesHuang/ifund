#!/usr/bin/env bash
# iFund 一键启动：venv + 依赖 + 前端 build + 双服务（后端 :8000 / 前端 dev :9000）
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
PIP_MIRROR="https://mirrors.aliyun.com/pypi/simple/"

# 0. 杀掉旧进程 + 清理 Python 缓存（确保每次启动都用最新代码）
echo "[start] 释放端口 :8000 :9000 ..."
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
lsof -ti :9000 | xargs kill -9 2>/dev/null || true
find "$BACKEND" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
sleep 1

# 1. 后端 venv + 依赖
if ! "$BACKEND/venv/bin/pip" --version >/dev/null 2>&1; then
  echo "[start] (重新)创建 venv ..."
  rm -rf "$BACKEND/venv"
  python3 -m venv "$BACKEND/venv"
fi
echo "[start] 安装后端依赖 ..."
echo "[start] 升级 pip ..."
"$BACKEND/venv/bin/pip" install --upgrade pip --default-timeout=1000
echo "[start] 安装 requirements.txt ..."
"$BACKEND/venv/bin/pip" install -r "$BACKEND/requirements.txt" -i "$PIP_MIRROR" --default-timeout=1000

# 2. 前端依赖 + build（输出到 backend/static）
echo "[start] 安装前端依赖 ..."
cd "$FRONTEND"
npm install --verbose
echo "[start] 构建前端 ..."
npm run build

# 3. 启动双服务
cleanup() { kill "$BACK_PID" "$FRONT_PID" 2>/dev/null || true; }
trap cleanup EXIT

echo "[start] 启动后端 :8000 ..."
cd "$BACKEND"
FLASK_APP=app.main FLASK_DEBUG=1 "$BACKEND/venv/bin/flask" run --port 8000 --exclude-patterns "*.db" &
BACK_PID=$!

echo "[start] 启动前端 dev :9000 ..."
cd "$FRONTEND"
npm run dev &
FRONT_PID=$!

wait
