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


def recent_series(code: str, limit: int = 120) -> list[float]:
    """最近 limit 个交易日的累计净值序列（缺失回退单位净值），按时间升序。

    用于列表内的迷你净值走势图：取最近一段并升序，方便前端直接绘制。
    """
    rows = database.select("fund_nav", [
        ("fund_code", f"eq.{code}"),
        ("order", "trade_date.desc"),
        ("limit", limit),
    ])
    rows.reverse()  # desc 取最近 N 条后再反转为时间升序
    series: list[float] = []
    for row in rows:
        value = row.get("acc_nav")
        if value is None:
            value = row.get("nav")
        if value is not None:
            series.append(value)
    return series
