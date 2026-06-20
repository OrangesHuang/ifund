#!/usr/bin/env python3
"""fund_nav worker：增量拉取单位净值走势 + 累计收益率走势。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND_DIR = os.getenv("IFUND_BACKEND_DIR") or str(Path(__file__).resolve().parents[3])
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
os.chdir(_BACKEND_DIR)

# pylint: disable=wrong-import-position
import datetime

import akshare as ak  # pylint: disable=import-error

from app.common import worker_base
from app.fund_nav.crud import nav_crud
from app.trade_calendar.crud import calendar_crud


def _acc_nav_map(code):
    """累计净值走势 → ``{trade_date: 累计净值}``。

    累计净值（复权口径，分红除息日不断崖）在「累计净值走势」接口里，
    「单位净值走势」接口**不返回**该列，故需单独拉一次按日期对齐。
    接口异常时返回空表，降级为只存单位净值。
    """
    try:
        frame = ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势")
    except Exception:  # pylint: disable=broad-exception-caught
        return {}
    return {
        str(row["净值日期"]): worker_base.safe_float(row.get("累计净值"))
        for _, row in frame.iterrows()
    }


def _nav_rows(code, stored, now):
    frame = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
    acc_map = _acc_nav_map(code)
    rows = []
    for _, row in frame.iterrows():
        day = str(row["净值日期"])
        if stored and day <= stored:
            continue
        rows.append({
            "fund_code": code, "trade_date": day,
            "nav": worker_base.safe_float(row.get("单位净值")),
            "acc_nav": acc_map.get(day),
            "daily_return": worker_base.safe_float(row.get("日增长率")),
            "fetch_time": now,
        })
    return rows


def _cum_rows(code, stored, now):
    frame = ak.fund_open_fund_info_em(symbol=code, indicator="累计收益率走势")
    rows = []
    for _, row in frame.iterrows():
        day = str(row["日期"])
        if stored and day <= stored:
            continue
        rows.append({
            "fund_code": code, "trade_date": day,
            "cum_return": worker_base.safe_float(row.get("累计收益率")),
            "fetch_time": now,
        })
    return rows


def _process_one(code):
    base = calendar_crud.base_trade_date()  # 保守基准交易日：当天未发布则取 T-1，不空拉
    nav_stored = nav_crud.stored_latest(code, "fund_nav")
    if base and nav_stored and nav_stored >= base:
        return "skip"
    now = datetime.datetime.now().isoformat()
    nav_crud.insert_rows("fund_nav", _nav_rows(code, nav_stored, now))
    cum_stored = nav_crud.stored_latest(code, "fund_cum_return")
    nav_crud.insert_rows("fund_cum_return", _cum_rows(code, cum_stored, now))
    return "success"


if __name__ == "__main__":
    worker_base.main(_process_one)
