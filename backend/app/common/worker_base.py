"""worker 子进程共享主循环：确定基金集合 + 线程池并发 + 进度/协作式终止。

各模块 worker 只需提供 ``process_one(code) -> "success"|"skip"|"fail"``。
"""
from __future__ import annotations

import argparse
import math
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

from app import db as database

CONCURRENCY = 8


def safe_float(value):
    """把值转 float；NaN/None/非数返回 None。"""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(num) else num


def parse_args(argv) -> tuple[int, list[str], list[str]]:
    """解析 ``worker.py <task_id> [--codes a,b] [--fund-types x,y]``。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id", type=int)
    parser.add_argument("--codes", default="")
    parser.add_argument("--fund-types", default="", dest="fund_types")
    ns = parser.parse_args(argv)
    codes = [c for c in ns.codes.split(",") if c]
    fund_types = [t for t in ns.fund_types.split(",") if t]
    return ns.task_id, codes, fund_types


def resolve_codes(codes: list[str], fund_types: list[str]) -> list[str]:
    """--codes 优先；否则按 --fund-types 查 funds；否则全量。"""
    if codes:
        return list(codes)
    params = None
    if fund_types:
        params = {"type": f"in.({','.join(fund_types)})"}
    return [r["code"] for r in database.select("funds", params)]


def _is_terminated(task_id: int) -> bool:
    task = database.select_one("fetch_tasks", {"id": f"eq.{task_id}"})
    return task is None or task.get("status") == "terminated"


def _safe_process(process_one, code: str) -> str:
    try:
        return process_one(code) or "success"
    except Exception:  # pylint: disable=broad-exception-caught
        return "fail"


def run_worker(task_id: int, codes: list[str], fund_types: list[str], process_one) -> None:
    """并发处理每只基金，持续更新进度，支持协作式终止。"""
    load_dotenv()
    targets = resolve_codes(codes, fund_types)
    database.update("fetch_tasks", {"id": task_id}, {"target_count": len(targets)})
    success = fail = current = 0
    terminated = False
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {executor.submit(_safe_process, process_one, code): code for code in targets}
        for future in as_completed(futures):
            current += 1
            if future.result() == "fail":
                fail += 1
            else:
                success += 1
            database.update("fetch_tasks", {"id": task_id}, {
                "current_count": current, "success_count": success, "fail_count": fail,
            })
            if _is_terminated(task_id):
                terminated = True
                for pending in futures:
                    pending.cancel()
                break
    database.update("fetch_tasks", {"id": task_id},
                    {"status": "terminated" if terminated else "finished"})


def main(process_one) -> None:
    """worker 入口：解析 argv 并跑主循环。"""
    task_id, codes, fund_types = parse_args(sys.argv[1:])
    run_worker(task_id, codes, fund_types, process_one)
