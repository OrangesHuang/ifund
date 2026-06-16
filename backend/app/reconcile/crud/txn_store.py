"""实盘交易记录（``holding_txns`` 表）读写：买入/卖出/转仓，按 portfolio_id 隔离。

交易遵循基金原则：金额 + 当日单位净值 → 折算份额。落账时锁定当日单位净值
（``nav_crud.unit_nav_on``，取 ≤ 交易日的最近交易日单位净值），并把折算份额存档，
之后净值变动不影响历史交易。转仓拆成「源卖出 + 目标买入」两条，共享 ``transfer_id``。

实际持仓的市值/盈亏不在本模块算——由 ``holdings_compute`` 把快照 + 交易回放合成。
"""
from __future__ import annotations

import datetime
import uuid

from app import db as database
from app.fund_nav.crud import nav_crud
from app.reconcile.crud import holdings_store

TABLE = "holding_txns"


def _now() -> str:
    return datetime.datetime.now().isoformat()


def list_txns(pid: int) -> list[dict]:
    """该实盘全部交易记录，按交易日升序（同日按录入顺序）。"""
    return database.select(TABLE, {
        "portfolio_id": f"eq.{pid}", "order": "trade_date.asc,id.asc",
    })


def _resolve(code: str, name: str) -> tuple[str, str]:
    """补全 ``(code, name)``：只给名称时反查代码，只给代码时补名称。"""
    code = (code or "").strip()
    name = (name or "").strip()
    if not code and name:
        code, name = holdings_store.resolve_by_name(name)
    if code and not name:
        name = holdings_store._fund_name(code) or code
    return code, name


def add_txn(pid: int, uid: int, code: str, name: str, txn_type: str,
            date: str, amount: float, note: str = "",
            transfer_id: str | None = None) -> dict:
    """记一笔买入/卖出：按交易日锁定单位净值并折算份额，落库返回该行。

    ``txn_type`` 为 ``buy`` / ``sell``；查不到净值时 nav/shares 存 NULL（估值不可用）。
    """
    code, name = _resolve(code, name)
    if not code:
        raise ValueError("fund_code required")
    if txn_type not in ("buy", "sell"):
        raise ValueError(f"bad txn_type: {txn_type}")
    hit = nav_crud.unit_nav_on(code, date)
    nav = hit[1] if hit else None
    shares = (amount / nav) if (nav and nav > 0) else None
    return database.insert(TABLE, {
        "portfolio_id": pid, "user_id": uid, "fund_code": code, "fund_name": name,
        "txn_type": txn_type, "trade_date": date, "amount": amount,
        "nav": nav, "shares": shares, "transfer_id": transfer_id,
        "note": note or "", "created_at": _now(),
    })


def add_transfer(pid: int, uid: int, from_code: str, from_name: str,
                 to_code: str, to_name: str, date: str, amount: float,
                 note: str = "") -> dict:
    """转仓：原子的「源卖出 + 目标买入」，两条共享 ``transfer_id``。返回 ``{transfer_id, sell, buy}``。"""
    tid = uuid.uuid4().hex
    sell = add_txn(pid, uid, from_code, from_name, "sell", date, amount,
                   note=note, transfer_id=tid)
    buy = add_txn(pid, uid, to_code, to_name, "buy", date, amount,
                  note=note, transfer_id=tid)
    return {"transfer_id": tid, "sell": sell, "buy": buy}


def bulk_add_txns(pid: int, uid: int, rows: list[dict]) -> int:
    """批量落账（调仓建议「批量保存」用）。

    rows 每项 ``{txn_type, fund_code/fund_name, trade_date, amount, transfer_id?, note?}``。
    逐条折算净值/份额后一次性插入；返回写入条数。
    """
    now = _now()
    payload: list[dict] = []
    for r in rows:
        code, name = _resolve(r.get("fund_code", ""), r.get("fund_name", ""))
        if not code:
            continue
        ttype = r.get("txn_type")
        if ttype not in ("buy", "sell"):
            continue
        try:
            amount = float(r.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        date = str(r.get("trade_date") or "").strip()
        if not date:
            continue
        hit = nav_crud.unit_nav_on(code, date)
        nav = hit[1] if hit else None
        shares = (amount / nav) if (nav and nav > 0) else None
        payload.append({
            "portfolio_id": pid, "user_id": uid, "fund_code": code, "fund_name": name,
            "txn_type": ttype, "trade_date": date, "amount": amount,
            "nav": nav, "shares": shares, "transfer_id": r.get("transfer_id"),
            "note": r.get("note") or "", "created_at": now,
        })
    if not payload:
        return 0
    database.batch_insert(TABLE, payload)
    return len(payload)


def update_txn(pid: int, txn_id: int, *, code: str = "", name: str = "",
               txn_type: str | None = None, date: str | None = None,
               amount: float | None = None) -> dict | None:
    """修改一条交易记录：按新交易日重新锁定单位净值并折算份额。返回更新后的行。

    只改传入的字段；改了金额/日期/基金则重算 nav/shares。``transfer_id`` 保留不变
    （编辑转仓的单条不破坏其配对标识，但两条需各自修改）。
    """
    existing = database.select_one(TABLE, {"portfolio_id": f"eq.{pid}", "id": f"eq.{txn_id}"})
    if not existing:
        return None
    new_code = (code or "").strip() or existing["fund_code"]
    new_name = (name or "").strip()
    if code or name:
        new_code, new_name = _resolve(code or new_code, name)
    new_name = new_name or existing.get("fund_name") or ""
    new_type = txn_type or existing["txn_type"]
    if new_type not in ("buy", "sell"):
        raise ValueError(f"bad txn_type: {new_type}")
    new_date = (date or existing["trade_date"])
    new_amount = existing["amount"] if amount is None else amount
    hit = nav_crud.unit_nav_on(new_code, new_date)
    nav = hit[1] if hit else None
    shares = (new_amount / nav) if (nav and nav > 0) else None
    fields = {
        "fund_code": new_code, "fund_name": new_name, "txn_type": new_type,
        "trade_date": new_date, "amount": new_amount, "nav": nav, "shares": shares,
    }
    database.update(TABLE, {"portfolio_id": pid, "id": txn_id}, fields)
    return {**existing, **fields}


def delete_txn(pid: int, txn_id: int) -> None:
    """删除一条交易记录（限本实盘）。转仓的两条需各删一次。"""
    database.delete(TABLE, {"portfolio_id": pid, "id": txn_id})


def delete_txns(pid: int, ids: list[int]) -> int:
    """批量删除交易记录（限本实盘）。返回删除条数。"""
    n = 0
    for tid in ids:
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            continue
        database.delete(TABLE, {"portfolio_id": pid, "id": tid})
        n += 1
    return n
