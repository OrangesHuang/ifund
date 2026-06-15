#!/usr/bin/env bash
# iFund 一键启动：venv + 依赖 + 前端 build + 双服务（后端 :8000 / 前端 dev :9000）
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
PIP_MIRROR="https://mirrors.aliyun.com/pypi/simple/"

# 1. 后端 venv + 依赖
if [ ! -d "$BACKEND/venv" ]; then
  echo "[start] 创建 venv (Python 3.12) ..."
  # 需 Python 3.12+（官方 MCP SDK 要求 3.10+）；优先 python3.12，回退到 python3
  PYBIN="$(command -v python3.12 || command -v python3)"
  "$PYBIN" -m venv "$BACKEND/venv"
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
