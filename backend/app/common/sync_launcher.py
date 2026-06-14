"""启动 worker 子进程的共享逻辑（含 PyInstaller 打包路径处理）。"""
from __future__ import annotations

import os
import sys

from app.common import task_runner


def start_sync_task(task_type: str, worker_script: str, *, codes=None, fund_types=None) -> int:
    """组装 CLI 参数并起 worker，返回 task_id。"""
    extra: list[str] = []
    if codes:
        extra += ["--codes", ",".join(codes)]
    if fund_types:
        extra += ["--fund-types", ",".join(fund_types)]
    python_exe = None
    env = None
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        env = {**os.environ, "PYTHONPATH": meipass, "IFUND_BACKEND_DIR": meipass}
        python_exe = "python3"
    return task_runner.launch_worker(
        worker_script, task_type, extra_args=extra, python_exe=python_exe, env=env,
    )
