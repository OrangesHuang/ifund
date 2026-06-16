#!/usr/bin/env python3
"""回填 fund_nav.acc_nav（累计净值，复权口径）。

历史采集用错了接口（「单位净值走势」不返回累计净值列），导致 acc_nav 全库为空，
净值走势图被迫画单位净值、在分红除息日出现断崖。本脚本对每只基金单独拉
「累计净值走势」接口，按 (fund_code, trade_date) 回填 acc_nav。

特性：
- 幂等：已全部回填的基金自动跳过，可随时中断重跑。
- 容错：单只基金接口失败/无数据 → 记录并继续，不中断全量。
- 进度：每只打印一行，便于后台日志跟踪。

用法：
    ./venv/bin/python3 backfill_acc_nav.py                # 全量
    ./venv/bin/python3 backfill_acc_nav.py --limit 5      # 先测前 5 只
    ./venv/bin/python3 backfill_acc_nav.py --codes 000201,000212
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
import time
from pathlib import Path

import akshare as ak  # pylint: disable=import-error

DB_PATH = str(Path(__file__).resolve().parent / "data.db")


def safe_float(value):
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(num) else num


def acc_nav_map(code: str) -> dict[str, float]:
    """累计净值走势 → {trade_date: 累计净值}。"""
    frame = ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势")
    out: dict[str, float] = {}
    for _, row in frame.iterrows():
        day = str(row["净值日期"])
        val = safe_float(row.get("累计净值"))
        if val is not None:
            out[day] = val
    return out


def target_codes(conn: sqlite3.Connection, codes: list[str], limit: int) -> list[str]:
    if codes:
        return codes
    sql = "SELECT DISTINCT fund_code FROM fund_nav ORDER BY fund_code"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [r[0] for r in conn.execute(sql).fetchall()]


def needs_backfill(conn: sqlite3.Connection, code: str) -> bool:
    """该基金是否还有 acc_nav 为空的行（全非空则跳过）。"""
    row = conn.execute(
        "SELECT COUNT(*) FROM fund_nav WHERE fund_code=? AND acc_nav IS NULL",
        (code,),
    ).fetchone()
    return row[0] > 0


def backfill_one(conn: sqlite3.Connection, code: str) -> tuple[str, int]:
    """回填单只基金，返回 (状态, 更新行数)。"""
    if not needs_backfill(conn, code):
        return "skip", 0
    try:
        amap = acc_nav_map(code)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return f"fail:{type(exc).__name__}", 0
    if not amap:
        return "empty", 0
    payload = [(v, code, d) for d, v in amap.items()]
    cur = conn.executemany(
        "UPDATE fund_nav SET acc_nav=? WHERE fund_code=? AND trade_date=?",
        payload,
    )
    conn.commit()
    return "ok", cur.rowcount


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", default="")
    parser.add_argument("--limit", type=int, default=0)
    ns = parser.parse_args()
    codes = [c for c in ns.codes.split(",") if c.strip()]

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")

    targets = target_codes(conn, codes, ns.limit)
    total = len(targets)
    print(f"[backfill] {total} 只基金待处理 (db={DB_PATH})", flush=True)

    counts = {"ok": 0, "skip": 0, "empty": 0, "fail": 0}
    rows_updated = 0
    t0 = time.time()
    for i, code in enumerate(targets, 1):
        status, n = backfill_one(conn, code)
        key = "fail" if status.startswith("fail") else status
        counts[key] = counts.get(key, 0) + 1
        rows_updated += n
        if status == "ok" or status.startswith("fail") or i % 50 == 0 or i == total:
            elapsed = time.time() - t0
            print(
                f"[{i}/{total}] {code} -> {status} (+{n} 行) | "
                f"ok={counts['ok']} skip={counts['skip']} empty={counts['empty']} "
                f"fail={counts['fail']} | {elapsed:.0f}s",
                flush=True,
            )

    conn.close()
    print(
        f"[backfill] 完成：ok={counts['ok']} skip={counts['skip']} "
        f"empty={counts['empty']} fail={counts['fail']} | 共更新 {rows_updated} 行",
        flush=True,
    )


if __name__ == "__main__":
    sys.exit(main())
