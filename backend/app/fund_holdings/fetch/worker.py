#!/usr/bin/env python3
"""fund_holdings worker：拉取股票/债券持仓，按基金全量替换。"""
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
import re

import akshare as ak  # pylint: disable=import-error

from app.common import worker_base
from app.fund_holdings.crud import holdings_crud

_QUARTER_RE = re.compile(r"(\d{4}).*?([1-4])\s*季度")


def _normalize_quarter(text: str) -> str:
    """「2024年1季度」→「2024Q1」。"""
    match = _QUARTER_RE.search(text or "")
    return f"{match.group(1)}Q{match.group(2)}" if match else (text or "").strip()


def _stock_rows(code, year, now):
    try:
        frame = ak.fund_portfolio_hold_em(symbol=code, date=str(year))
    except Exception:  # pylint: disable=broad-exception-caught
        return []
    rows = []
    for _, row in frame.iterrows():
        rows.append({
            "fund_code": code,
            "quarter": _normalize_quarter(str(row.get("季度", ""))),
            "holding_type": "stock",
            "asset_code": str(row.get("股票代码", "")).strip(),
            "asset_name": str(row.get("股票名称", "")).strip(),
            "hold_ratio": worker_base.safe_float(row.get("占净值比例")),
            "hold_amount": worker_base.safe_float(row.get("持股数")),
            "hold_market_value": worker_base.safe_float(row.get("持仓市值")),
            "raw_data": "{}",
            "fetch_time": now,
        })
    return rows


def _bond_rows(code, year, now):
    try:
        frame = ak.fund_portfolio_bond_hold_em(symbol=code, date=str(year))
    except Exception:  # pylint: disable=broad-exception-caught
        return []
    rows = []
    for _, row in frame.iterrows():
        rows.append({
            "fund_code": code,
            "quarter": _normalize_quarter(str(row.get("季度", ""))),
            "holding_type": "bond",
            "asset_code": str(row.get("债券代码", "")).strip(),
            "asset_name": str(row.get("债券名称", "")).strip(),
            "hold_ratio": worker_base.safe_float(row.get("占净值比例")),
            "hold_amount": None,  # 债券行强制置 None
            "hold_market_value": worker_base.safe_float(row.get("持仓市值")),
            "raw_data": "{}",
            "fetch_time": now,
        })
    return rows


def _dedup(rows):
    seen = {}
    for row in rows:
        key = (row["fund_code"], row["quarter"], row["holding_type"], row["asset_code"])
        seen[key] = row
    return list(seen.values())


def _process_one(code):
    if holdings_crud.is_fresh(code):
        return "skip"
    now = datetime.datetime.now().isoformat()
    year = datetime.date.today().year
    rows = []
    for target_year in (year - 1, year):
        rows += _stock_rows(code, target_year, now)
        rows += _bond_rows(code, target_year, now)
    holdings_crud.upsert(code, _dedup(rows))
    return "success"


if __name__ == "__main__":
    worker_base.main(_process_one)
