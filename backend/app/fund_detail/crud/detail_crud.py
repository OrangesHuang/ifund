"""基金详情数据访问：过期判定 + 单行 upsert。"""
from __future__ import annotations

import datetime

from app import db as database

EXPIRE_DAYS = 7


def get_detail(fund_code: str) -> dict | None:
    """读取单条详情。"""
    return database.select_one("fund_details", {"fund_code": f"eq.{fund_code}"})


def _fetch_time_expired(row: dict) -> bool:
    """fetch_time 超过 EXPIRE_DAYS 或缺失/无法解析 → 过期。"""
    raw = row.get("fetch_time")
    if not raw:
        return True
    try:
        fetched = datetime.datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return True
    return (datetime.datetime.now() - fetched).days >= EXPIRE_DAYS


def is_expired(fund_code: str, latest_nav_date: str | None) -> bool:
    """详情是否需要刷新。

    任一条件成立即过期：无记录 / fetch_time 超 7 天或无法解析 /
    存储 trade_date 与最新交易日 latest_nav_date 不一致。
    """
    row = get_detail(fund_code)
    if not row:
        return True
    if _fetch_time_expired(row):
        return True
    if latest_nav_date and str(row.get("trade_date") or "") != str(latest_nav_date):
        return True
    if row.get("scale") is None:  # 关键字段缺失（含旧版映射遗留的脏数据），需补全
        return True
    return False


def upsert(fund_code: str, columns: dict) -> None:
    """单行 upsert：存在则 update，否则 insert。"""
    if get_detail(fund_code):
        database.update("fund_details", {"fund_code": fund_code}, columns)
    else:
        payload = dict(columns)
        payload["fund_code"] = fund_code
        database.insert("fund_details", payload)
