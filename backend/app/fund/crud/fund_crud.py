"""基金名单数据访问：全量替换 + 派生分类表。"""
from __future__ import annotations

from app import db as database


def _sync_fund_types(funds: list[dict]) -> None:
    """从 funds 的 type 派生 fund_types，stock 类别优先（集合差集，一个 type 只归一类）。"""
    database.delete("fund_types")
    stock_types = {f["type"] for f in funds if f.get("fund_type") == "stock" and f.get("type")}
    all_types = {f["type"] for f in funds if f.get("type")}
    non_stock_types = all_types - stock_types
    rows = [{"type_name": t, "category": "stock"} for t in sorted(stock_types)]
    rows += [{"type_name": t, "category": "non_stock"} for t in sorted(non_stock_types)]
    if rows:
        database.batch_insert("fund_types", rows)


def replace_all(funds: list[dict]) -> None:
    """全量替换 funds：DELETE all → batch_insert → 同步 fund_types。"""
    database.delete("funds")
    if funds:
        database.batch_insert("funds", funds)
    _sync_fund_types(funds)
