#!/usr/bin/env bash
# iFund 一键启动：venv + 依赖 + 前端 build + 双服务（后端 :8000 / 前端 dev :9000）
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
PIP_MIRROR="https://mirrors.aliyun.com/pypi/simple/"

# 1. 后端 venv + 依赖
if [ ! -d "$BACKEND/venv" ]; then
  echo "[start] 创建 venv ..."
  python3 -m venv "$BACKEND/venv"
fi
echo "[start] 安装后端依赖 ..."
"$BACKEND/venv/bin/pip" install -q --upgrade pip
"$BACKEND/venv/bin/pip" install -q -r "$BACKEND/requirements.txt" -i "$PIP_MIRROR"

# 2. 前端依赖 + build（输出到 backend/static）
echo "[start] 构建前端 ..."
cd "$FRONTEND"
npm install
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
