# AGENTS.md

This file provides guidance to the AI agent when working with code in this repository.

## Build / Lint / Test

```bash
# Dev (backend :8000 hot-reload + frontend :9000 HMR)
./start.sh

# Backend lint — MUST stay 10.00/10; disable=[] in pyproject.toml, suppress inline only
./backend/venv/bin/pylint app

# Frontend
cd frontend && npx tsc --noEmit   # type check
cd frontend && npm run lint       # eslint
```

Pylint max line length is **120** chars. `pyproject.toml` has relaxed design limits (max-args=10, max-locals=30, max-statements=80, max-branches=20) — don't refactor to satisfy defaults.

## Code Style

- **All backend Python files** must start with `from __future__ import annotations`.
- **Exception**: `mcp_server/server.py` — deliberately omits it because FastMCP reads type annotations as runtime objects; stringified annotations break tool registration.
- No ORM at runtime. `flask-sqlalchemy` is installed but only used for model declarations as documentation. All data access uses raw SQL via the abstraction layer in `backend/app/db/` (`Database` ABC in `base.py`, SQLite impl in `sqlite.py`).
- All `akshare` calls MUST run in a **subprocess worker** (`backend/app/common/worker_base.py`). Calling akshare inside a Flask request thread crashes the server (socket fd conflict).

## Architecture Gotchas

- **Flask 3.1**, not FastAPI (some older docs still say FastAPI — ignore). App factory pattern in `backend/app/main.py`, routes as Blueprints under each module's `api/router.py`.
- **SQLite only** for now. MySQL is planned but unimplemented. The DB abstraction layer (`backend/app/db/base.py`) is the contract — new backends implement the `Database` ABC without touching business code.
- **Frontend dev :9000 proxies `/api` → backend :8000**. Production build outputs to `backend/static`; backend serves the SPA on :8000 directly (no separate frontend server needed in prod).
- **`./service.sh` (launchd+waitress) and `./start.sh` share port :8000** — they cannot run simultaneously. Stop the service before debugging: `./service.sh stop` → `./start.sh` → Ctrl-C → `./service.sh start`.
- **MCP server** (`mcp_server/server.py`) shares `backend/venv`. Slimmed (2026-06) to a **single `ifund(args)` passthrough tool** that execs `backend/ifund_cli.py` — no HTTP/PAT/JWT. It's only a thin bridge for MCP-only agents (e.g. OpenClaw); shell-capable agents should call the CLI directly (see below). Old 33-tool impl in `server.py.33tools.bak`.

## Data CLI (查询/分析 iFund 数据的首选)

需要 iFund 数据（预设/镜像、仓位建议、实盘持仓与穿透、组合表现）或拉取数据时，**优先用
`backend/ifund_cli.py`**，不要打 HTTP API、也不要直接读 `data.db` 原始表。它直连本机
`data.db`、复用后端 crud/算法层（无需后端服务/登录），输出紧凑、可加 `--json` 解析。

```bash
cd /Users/huangcheng/Desktop/ifund/backend
./venv/bin/python3 ifund_cli.py <组> <命令> [--json] [-h]   # 任意命令加 -h 自查参数
```

- `preset  list | show --id N | snapshot --id N | funds --id N [--code C][--keyword K][--ai] | ai-set --code N --data '{...}'`（snapshot=按预设条件重建镜像；funds=查预设镜像内基金+基础信息，--ai 附 AI 定性分析列；ai-set=写入基金 AI 分析，OpenClaw 填充，部分 upsert）
- `fetch   calendar | industry --mode sw|em | detail|holdings|nav [--codes ..] [--types ..]`（联网慢，自带缓存）
- `analyze  run --preset N [--balance 松|中|紧 | --cap 0.10~0.30] [--view weights|industry|stock|perf|all]`（组合分析：必选预设→仓位建议→穿透/赛道/分区间表现）
- `holdings list | show --pid N（实际持仓按赛道簇分组，加 --penetration 附底层穿透）| penetration | perf | rebalance --pid N [--sell-outside] [--no-trim-overflow] [--band B]（调仓建议操作指南）`
- `holdings buy|sell --pid N --fund 代码/名称 --amount A | transfer --from .. --to .. --amount A | txns --pid N | txn-del --pid N --id T`（实盘交易；持仓录入在网页端）

实现拆在 `backend/cli/` 包（薄壳 `ifund_cli.py` 等价于 `python -m cli`）。命令树即文档：`-h`
按需查，无预载成本。**这是替代旧 MCP 多工具的省 Token 方案**——优先 CLI。

## Repo Conventions

- Commit messages in **Chinese**, conventional prefix: `feat:`, `fix:`, `docs:`, `refactor:`.
- Single `main` branch; no PR workflow in place.
- `backend/.env` is gitignored — copy from `backend/.env.example` if present.
