"""数据库抽象层基类：定义后端无关的统一接口契约（9 方法）。

业务代码与 worker 只依赖本契约，不关心底层是 SQLite 还是（未来的）MySQL。
新增后端 = 新增一个实现 ``Database`` 的子类，业务代码零改动。
"""
from __future__ import annotations

import abc


class UniqueViolation(Exception):
    """唯一约束冲突（后端无关）。

    各后端在 ``insert`` 中把底层驱动的唯一键冲突异常统一转换为本异常，
    业务层只需 ``except database.UniqueViolation`` 即可处理，无需感知后端。
    """


class Database(abc.ABC):
    """可插拔数据库后端的统一接口。

    ``params`` 取值统一使用 PostgREST 风格的过滤语法（见 ``sqlite`` 模块文档），
    由具体后端翻译成对应方言 SQL。
    """

    @abc.abstractmethod
    def select(self, table: str, params=None) -> list[dict]:
        """按过滤语法查询多行，返回 dict 列表。"""

    def select_one(self, table: str, params: dict | None = None) -> dict | None:
        """取第一条；基类默认实现：复用 ``select`` + ``limit=1``。"""
        merged = dict(params or {})
        merged["limit"] = 1
        rows = self.select(table, merged)
        return rows[0] if rows else None

    @abc.abstractmethod
    def insert(self, table: str, data: dict) -> dict:
        """插入一行，返回插入后的完整记录（含自增 id）。"""

    @abc.abstractmethod
    def batch_insert(self, table: str, rows: list[dict], batch_size: int = 500) -> None:
        """批量插入（重复主键/唯一键则替换）。"""

    @abc.abstractmethod
    def update(self, table: str, filters: dict, data: dict) -> None:
        """按等值条件 ``filters`` 更新 ``data``。"""

    @abc.abstractmethod
    def delete(self, table: str, filters: dict | None = None) -> None:
        """删除；``filters=None`` 时全表删除。"""

    @abc.abstractmethod
    def count(self, table: str, params=None) -> int:
        """按过滤语法计数。"""

    @abc.abstractmethod
    def list_funds_with_details(self, fund_params, detail_params, skip, limit, order_parts):
        """funds ⋈ fund_details 联合查询，返回 ``(total, items)``。"""

    @abc.abstractmethod
    def init_db(self, schema_sql: str) -> None:
        """执行建表脚本（SQLite 用 executescript）。"""
