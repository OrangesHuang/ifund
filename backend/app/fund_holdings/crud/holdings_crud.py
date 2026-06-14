"""持仓数据访问：7 天缓存判定 + 按基金全量替换。"""
from __future__ import annotations

import datetime

from app import db as database

CACHE_DAYS = 7


def is_fresh(code: str) -> bool:
    """该基金持仓是否在 7 天缓存内。"""
    row = database.select_one("fund_holdings", {
        "fund_code": f"eq.{code}", "order": "fetch_time.desc",
    })
    if not row or not row.get("fetch_time"):
        return False
    try:
        fetched = datetime.datetime.fromisoformat(row["fetch_time"])
    except (TypeError, ValueError):
        return False
    return (datetime.datetime.now() - fetched).days < CACHE_DAYS


def upsert(code: str, rows: list[dict]) -> None:
    """按基金全量替换：delete by fund_code → batch_insert。"""
    database.delete("fund_holdings", {"fund_code": code})
    if rows:
        database.batch_insert("fund_holdings", rows)


def latest_quarter(code: str, holding_type: str = "stock") -> str | None:
    """该基金某类持仓的最新季度（quarter 形如 2025Q1，字符串降序即时间序）。"""
    row = database.select_one("fund_holdings", {
        "fund_code": f"eq.{code}", "holding_type": f"eq.{holding_type}",
        "order": "quarter.desc",
    })
    return row["quarter"] if row else None


def top_holdings(code: str, holding_type: str = "stock", limit: int = 10) -> list[dict]:
    """最新季度的前 N 大持仓（按持仓比例降序），跨季度数据不会混入。"""
    quarter = latest_quarter(code, holding_type)
    if not quarter:
        return []
    return database.select("fund_holdings", [
        ("fund_code", f"eq.{code}"),
        ("holding_type", f"eq.{holding_type}"),
        ("quarter", f"eq.{quarter}"),
        ("order", "hold_ratio.desc"),
        ("limit", limit),
    ])
