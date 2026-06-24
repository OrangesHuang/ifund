"""持仓数据访问：按基准交易日缓存判定 + 按基金全量替换。"""
from __future__ import annotations

import datetime

from app import db as database
from app.trade_calendar.crud import calendar_crud


def is_fresh(code: str) -> bool:
    """该基金持仓是否在当前基准交易日内已拉过（同一基准交易日不重复拉）。

    持仓是季度披露数据，但缓存判据与净值/详情统一到「保守基准交易日」：把上次 fetch_time
    归一到它所属的基准交易日，与当前基准交易日相等即视为已拉、跳过；跨交易日才重拉
    （季报多数时候增量为空，成本可控）。无 fetch_time / 无交易日历 → 不新鲜，照常拉。
    """
    row = database.select_one("fund_holdings", {
        "fund_code": f"eq.{code}", "order": "fetch_time.desc",
    })
    if not row or not row.get("fetch_time"):
        return False
    try:
        fetched = datetime.datetime.fromisoformat(row["fetch_time"])
    except (TypeError, ValueError):
        return False
    base_now = calendar_crud.base_trade_date()
    if base_now is None:
        return False
    return calendar_crud.base_trade_date(fetched) == base_now


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


def available_quarters(code: str, holding_type: str = "stock") -> list[str]:
    """该基金某类持仓的全部可用季度（降序，最新在前），供详情页切换历史报告期。"""
    rows = database.select("fund_holdings", [
        ("fund_code", f"eq.{code}"),
        ("holding_type", f"eq.{holding_type}"),
        ("order", "quarter.desc"),
    ])
    seen: set[str] = set()
    out: list[str] = []
    for r in rows:
        q = r.get("quarter")
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out


def top_holdings(code: str, holding_type: str = "stock", limit: int = 10,
                 quarter: str | None = None) -> list[dict]:
    """指定季度（默认最新）的前 N 大持仓（按持仓比例降序），跨季度数据不会混入。"""
    quarter = quarter or latest_quarter(code, holding_type)
    if not quarter:
        return []
    return database.select("fund_holdings", [
        ("fund_code", f"eq.{code}"),
        ("holding_type", f"eq.{holding_type}"),
        ("quarter", f"eq.{quarter}"),
        ("order", "hold_ratio.desc"),
        ("limit", limit),
    ])
