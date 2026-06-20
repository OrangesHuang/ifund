"""交易日历数据访问。"""
from __future__ import annotations

import datetime

from app import db as database

# 净值发布截止时刻（小时，本地时间）：交易日当天的净值/区间收益通常要当晚才在
# 数据源（akshare）出现，再叠加同步滞后。保守起见，只有过了这个时刻才把「今天」
# 计入拉取基准；否则当天反复拉只会空转（请求发出但增量为空）。可按数据源实况调。
NAV_PUBLISH_HOUR = 20


def replace_all(dates: list[str]) -> int:
    """全量替换交易日表。返回写入条数。"""
    database.delete("trade_dates", {})
    rows = [{"trade_date": d} for d in dates]
    if rows:
        database.batch_insert("trade_dates", rows)
    return len(rows)


def prev_trade_date(date: str) -> str | None:
    """严格早于 ``date`` 的最近交易日；无则 None。"""
    row = database.select_one(
        "trade_dates", {"trade_date": f"lt.{date}", "order": "trade_date.desc"})
    return row["trade_date"] if row else None


def base_trade_date(now: datetime.datetime | None = None) -> str | None:
    """拉取缓存的**保守基准交易日**：``now`` 时刻数据应已可得的最近交易日。

    所有「是否需要重新拉取」的判据都归到这个基准上——同一基准交易日内已拉过就不再拉，
    跨基准交易日才重拉。取 ≤ 今天的最近交易日；若它正是今天、且当前还没过净值发布
    时刻 :data:`NAV_PUBLISH_HOUR`，则回退到上一交易日，避免追当天尚未发布的数据而空转。

    与 :func:`app.fund_nav.crud.nav_crud.latest_trade_date` 区分：后者给估值/展示用，
    要的是真实最近交易日 T；本函数专供拉取缓存，宁可保守取 T-1 也不空拉。
    交易日历为空时返回 None（调用方据此降级为「照常拉」，避免首次空库永不拉取）。
    """
    now = now or datetime.datetime.now()
    today = now.date().isoformat()
    row = database.select_one(
        "trade_dates", {"trade_date": f"lte.{today}", "order": "trade_date.desc"})
    if not row:
        return None
    latest = row["trade_date"]
    if latest == today and now.hour < NAV_PUBLISH_HOUR:
        return prev_trade_date(today)
    return latest


def list_dates(year: str | None = None) -> list[str]:
    """列出交易日，可按年份过滤。"""
    params: dict = {"order": "trade_date.asc", "limit": "100000"}
    if year:
        params["trade_date"] = f"ilike.{year}-*"
    rows = database.select("trade_dates", params)
    return [r["trade_date"] for r in rows]
