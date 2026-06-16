"""净值/累计收益率数据访问（增量）。"""
from __future__ import annotations

import datetime

from app import db as database


def latest_trade_date() -> str:
    """交易日历最大日期；无则今天。"""
    row = database.select_one("trade_dates", {"order": "trade_date.desc"})
    return row["trade_date"] if row else datetime.date.today().isoformat()


def stored_latest(code: str, table: str):
    """某基金在指定表中已存的最新 trade_date。"""
    row = database.select_one(table, {"fund_code": f"eq.{code}", "order": "trade_date.desc"})
    return row["trade_date"] if row else None


def insert_rows(table: str, rows: list[dict]) -> None:
    """批量插入增量行（空则跳过）。"""
    if rows:
        database.batch_insert(table, rows)


def unit_nav_on(code: str, date: str) -> tuple[str, float] | None:
    """某基金 ``date`` 当日或之前最近一个交易日的 ``(trade_date, 单位净值)``；无则 None。

    份额折算（金额 ÷ 净值）必须用**单位净值 nav**——累计净值 acc_nav 含分红会高估份额。
    用户填的交易日可能是非交易日/停牌日，故取 ``trade_date <= date`` 的最近一条。
    """
    row = database.select_one("fund_nav", [
        ("fund_code", f"eq.{code}"),
        ("trade_date", f"lte.{date}"),
        ("order", "trade_date.desc"),
    ])
    if row and row.get("nav") is not None:
        return row["trade_date"], row["nav"]
    return None


def latest_unit_nav(code: str) -> tuple[str, float] | None:
    """某基金最新一个交易日的 ``(trade_date, 单位净值)``；无则 None（合成当前市值用）。"""
    row = database.select_one("fund_nav", [
        ("fund_code", f"eq.{code}"),
        ("order", "trade_date.desc"),
    ])
    if row and row.get("nav") is not None:
        return row["trade_date"], row["nav"]
    return None


def recent_series(code: str, limit: int = 120) -> list[float]:
    """最近 limit 个交易日的累计净值序列（缺失回退单位净值），按时间升序。

    用于列表内的迷你净值走势图：取最近一段并升序，方便前端直接绘制。
    """
    return [nav for _, nav in recent_series_dated(code, limit)]


def recent_series_dated(code: str, limit: int = 120) -> list[tuple[str, float]]:
    """最近 limit 个交易日的 ``(trade_date, 累计净值)`` 列表（缺失回退单位净值），按时间升序。

    组合净值/回撤走势需要按日期对齐多只基金，故保留交易日。
    """
    rows = database.select("fund_nav", [
        ("fund_code", f"eq.{code}"),
        ("order", "trade_date.desc"),
        ("limit", limit),
    ])
    rows.reverse()  # desc 取最近 N 条后再反转为时间升序
    series: list[tuple[str, float]] = []
    for row in rows:
        value = row.get("acc_nav")
        if value is None:
            value = row.get("nav")
        if value is not None:
            series.append((row["trade_date"], value))
    return series
