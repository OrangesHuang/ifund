"""数据库抽象层入口：按 ``DB_BACKEND`` 选后端，暴露模块级函数（业务代码后端无关）。

业务代码与 worker 统一 ``from app.db import select, insert, ...`` 调用，无需感知后端类型。
``get_db()`` 返回进程级单例；新增 MySQL 后端时只需在此分发，业务代码零改动。
"""
from __future__ import annotations

import os
from pathlib import Path

from .base import Database, UniqueViolation
from .sqlite import SqliteDatabase

__all__ = ["Database", "UniqueViolation", "SqliteDatabase", "get_db"]

_STATE: dict[str, Database] = {}


def get_db() -> Database:
    """返回进程级数据库单例。"""
    db = _STATE.get("db")
    if db is None:
        backend = os.getenv("DB_BACKEND", "sqlite").lower()
        if backend == "sqlite":
            default_path = str(Path(__file__).resolve().parents[2] / "data.db")
            db = SqliteDatabase(os.getenv("DB_PATH") or default_path)
        elif backend == "mysql":
            raise NotImplementedError("MySQL 后端尚未实现（规划中）")
        else:
            raise ValueError(f"未知 DB_BACKEND: {backend}")
        _STATE["db"] = db
    return db


def select(table: str, params=None) -> list[dict]:
    """委托单例：按过滤条件查询多行。"""
    return get_db().select(table, params)


def select_one(table: str, params: dict | None = None) -> dict | None:
    """委托单例：查询单行（无则 None）。"""
    return get_db().select_one(table, params)


def insert(table: str, data: dict) -> dict:
    """委托单例：插入一行并返回含主键的完整行。"""
    return get_db().insert(table, data)


def batch_insert(table: str, rows: list[dict], batch_size: int = 500) -> None:
    """委托单例：分批批量插入。"""
    get_db().batch_insert(table, rows, batch_size)


def update(table: str, filters: dict, data: dict) -> None:
    """委托单例：按过滤条件更新。"""
    get_db().update(table, filters, data)


def delete(table: str, filters: dict | None = None) -> None:
    """委托单例：按过滤条件删除（无 filters 则清空）。"""
    get_db().delete(table, filters)


def count(table: str, params=None) -> int:
    """委托单例：按过滤条件计数。"""
    return get_db().count(table, params)


def list_funds_with_details(fund_params, detail_params, skip, limit, order_parts):
    """委托单例：funds 与 fund_details JOIN 查询，返回 (total, items)。"""
    return get_db().list_funds_with_details(fund_params, detail_params, skip, limit, order_parts)


def list_industry_mapping(*, market="", label_kw="", status="", keyword="", skip=0, limit=50):
    """委托单例：持仓股票 ⋈ 行业映射的分页查询，返回 (total, items)。"""
    return get_db().list_industry_mapping(
        market=market, label_kw=label_kw, status=status, keyword=keyword, skip=skip, limit=limit)


def init_db(schema_sql: str) -> None:
    """委托单例：执行建表脚本（幂等）。"""
    get_db().init_db(schema_sql)
