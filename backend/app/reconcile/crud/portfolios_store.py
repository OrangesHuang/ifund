"""实盘账户（``portfolios`` 表）读写：按 user_id 隔离。

一个用户可有多个实盘（自己的资金 + 代管他人的资金），每个实盘可关联一套仓位建议
（预设 ``preset_id``，NULL=未关联）。持仓挂在 ``user_holdings.portfolio_id`` 下。
"""
from __future__ import annotations

from app import db as database

TABLE = "portfolios"


def list_portfolios(uid: int) -> list[dict]:
    """该用户全部实盘，按创建时间升序。"""
    return database.select(TABLE, {
        "user_id": f"eq.{uid}", "order": "id.asc",
    })


def get_portfolio(pid: int, uid: int) -> dict | None:
    """取一个实盘并校验归属；不属于该用户则返回 None。"""
    row = database.select_one(TABLE, {"id": f"eq.{pid}"})
    if not row or int(row.get("user_id", -1)) != int(uid):
        return None
    return row


def create_portfolio(uid: int, name: str, preset_id: int | None = None) -> dict:
    """新建实盘。"""
    name = (name or "").strip() or "未命名实盘"
    return database.insert(TABLE, {
        "user_id": uid, "name": name, "preset_id": preset_id, "cap": 0.18,
    })


def update_portfolio(pid: int, uid: int, *, name: str | None = None,
                     preset_id: int | None = None, set_preset: bool = False,
                     cap: float | None = None) -> dict | None:
    """改名 / 关联预设 / 均衡强度；需校验归属。

    ``set_preset=True`` 时才更新 preset_id（允许显式置空为「取消关联」）；
    ``cap`` 非空时更新均衡强度上限；否则仅在 name 非空时改名。
    """
    row = get_portfolio(pid, uid)
    if not row:
        return None
    fields: dict = {}
    if name is not None and name.strip():
        fields["name"] = name.strip()
    if set_preset:
        fields["preset_id"] = preset_id
    if cap is not None:
        fields["cap"] = cap
    if not fields:
        return row
    database.update(TABLE, {"id": pid}, fields)
    return {**row, **fields}


def delete_portfolio(pid: int, uid: int) -> bool:
    """删除实盘及其全部持仓；需校验归属。返回是否删除成功。"""
    row = get_portfolio(pid, uid)
    if not row:
        return False
    database.delete("user_holdings", {"portfolio_id": pid})
    database.delete(TABLE, {"id": pid})
    return True


def ensure_default(uid: int) -> dict:
    """保证该用户至少有一个实盘；没有则建「我的实盘」。返回第一个实盘。"""
    rows = list_portfolios(uid)
    if rows:
        return rows[0]
    return create_portfolio(uid, "我的实盘")
