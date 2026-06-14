"""交易日历数据访问。"""
from __future__ import annotations

from app import db as database


def replace_all(dates: list[str]) -> int:
    """全量替换交易日表。返回写入条数。"""
    database.delete("trade_dates", {})
    rows = [{"trade_date": d} for d in dates]
    if rows:
        database.batch_insert("trade_dates", rows)
    return len(rows)


def list_dates(year: str | None = None) -> list[str]:
    """列出交易日，可按年份过滤。"""
    params: dict = {"order": "trade_date.asc", "limit": "100000"}
    if year:
        params["trade_date"] = f"ilike.{year}-*"
    rows = database.select("trade_dates", params)
    return [r["trade_date"] for r in rows]
