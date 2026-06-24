"""fetch 组：交易日历 / 行业映射 / 详情 / 持仓 / 净值 拉取。

详情/持仓/净值复用各 worker 的 ``_process_one(code)``（自带「同基准交易日已拉则 skip」缓存），
逐只同步跑（akshare 限流，CONCURRENCY=1）。akshare 相关 import 全部延迟到命令内部，
保证 preset/position/holdings 命令不付 akshare 启动成本。
"""
from __future__ import annotations

from app import db as database

from . import helpers, output


def _run_per_fund(args, process_one) -> None:
    """对 resolve 出的目标基金逐只跑 process_one(code)，打印进度汇总。"""
    from app.common.worker_base import resolve_codes
    targets = resolve_codes(helpers.csv_list(args.codes), helpers.csv_list(args.types))
    n = len(targets)
    ok = skip = fail = 0
    fails: list[str] = []
    for i, code in enumerate(targets, 1):
        try:
            r = process_one(code) or "success"
        except Exception as exc:  # pylint: disable=broad-exception-caught
            r = "fail"
            fails.append(f"{code}:{exc}")
        if r == "success":
            ok += 1
        elif r == "skip":
            skip += 1
        else:
            fail += 1
        if not args.json and (i % 20 == 0 or i == n):
            print(f"\r进度 {i}/{n}  新增{ok} 跳过{skip} 失败{fail}", end="", flush=True)
    if not args.json:
        print()
    out = {"total": n, "success": ok, "skip": skip, "fail": fail, "fails": fails[:20]}
    output.emit(out, args.json, lambda d: d["fails"] and print("失败样例:", "; ".join(d["fails"])))


def cmd_calendar(args) -> None:
    from app.trade_calendar.fetch.fetcher import fetch_trade_dates
    from app.trade_calendar.crud import calendar_crud
    dates = fetch_trade_dates()
    n = calendar_crud.replace_all(dates)
    out = {"count": n, "latest": dates[-1] if dates else None}
    output.emit(out, args.json, lambda d: print(f"✓ 交易日历已更新：{d['count']} 条，最新 {d['latest']}"))


def cmd_industry(args) -> None:
    task = database.insert("fetch_tasks", {"task_type": f"{args.mode}_industry",
                                           "status": "running", "executor_ip": "cli"})
    tid = task["id"]
    if args.mode == "sw":
        from app.stock_industry.fetch import sw_worker
        sw_worker.run(tid, helpers.csv_list(args.codes))
    else:
        from app.stock_industry.fetch import em_worker
        em_worker.run(tid)
    row = database.select_one("fetch_tasks", {"id": f"eq.{tid}"})
    out = {"mode": args.mode, "status": row.get("status"), "target": row.get("target_count"),
           "success": row.get("success_count"), "fail": row.get("fail_count")}
    output.emit(out, args.json, lambda d: print(
        f"✓ 行业映射({d['mode']}) {d['status']}：目标{d['target']} 成功{d['success']} 失败{d['fail']}"))


def cmd_detail(args) -> None:
    from app.fund_detail.fetch.worker import _process_one
    _run_per_fund(args, _process_one)


def cmd_holdings(args) -> None:
    from app.fund_holdings.fetch.worker import _process_one
    _run_per_fund(args, _process_one)


def cmd_nav(args) -> None:
    from app.fund_nav.fetch.worker import _process_one
    _run_per_fund(args, _process_one)
