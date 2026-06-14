"""净值模块蓝图（标准任务端点，worker 子进程拉取）。"""
from __future__ import annotations

from pathlib import Path

from app.common.task_support import make_task_blueprint

WORKER_SCRIPT = str(Path(__file__).resolve().parents[1] / "fetch" / "worker.py")
bp = make_task_blueprint("fund_nav", "fetch_fund_nav", WORKER_SCRIPT)
