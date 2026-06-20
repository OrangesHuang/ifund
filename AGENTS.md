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
- **MCP server** (`mcp_server/server.py`) shares `backend/venv`. Auth via PAT (env `IFUND_API_TOKEN`); server internally exchanges for short-lived JWT.

## Repo Conventions

- Commit messages in **Chinese**, conventional prefix: `feat:`, `fix:`, `docs:`, `refactor:`.
- Single `main` branch; no PR workflow in place.
- `backend/.env` is gitignored — copy from `backend/.env.example` if present.
