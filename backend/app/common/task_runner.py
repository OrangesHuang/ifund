"""worker 子进程启动与终止的共享工具（含分布式终止）。"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys

from app import db as database

# 内存中 task_id → 进程句柄（仅本机）
_processes: dict[int, subprocess.Popen] = {}


def get_local_ip() -> str:
    """UDP connect 取本机出口 IP；失败回退 127.0.0.1。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def launch_worker(worker_script, task_type, *, extra_args=None,
                  python_exe=None, env=None, stderr=subprocess.DEVNULL) -> int:
    """insert fetch_tasks → Popen 子进程 → 回填 PID → 返回 task_id。"""
    task = database.insert("fetch_tasks", {
        "task_type": task_type,
        "status": "running",
        "executor_ip": get_local_ip(),
    })
    task_id = task["id"]
    cmd = [python_exe or sys.executable, str(worker_script), str(task_id)] + list(extra_args or [])
    proc = subprocess.Popen(cmd, env=env, stderr=stderr)  # pylint: disable=consider-using-with
    _processes[task_id] = proc
    database.update("fetch_tasks", {"id": task_id}, {"executor_thread": str(proc.pid)})
    return task_id


def terminate_task(task_id: int) -> None:
    """本地进程 terminate，5s 超时则 kill。"""
    proc = _processes.get(task_id)
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    _processes.pop(task_id, None)


def terminate_by_pid(pid: str) -> None:
    """按 PID 发 SIGTERM；用于跨机远程终止。"""
    try:
        os.kill(int(pid), signal.SIGTERM)
    except (ProcessLookupError, ValueError):
        pass
