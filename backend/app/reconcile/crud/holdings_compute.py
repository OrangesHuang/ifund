"""实际持仓合成引擎：初始化快照(user_holdings) + 交易回放(holding_txns) → 当前持仓。

会计模型（移动平均成本）：
- 快照：用户填市值 + 盈亏，存为 ``market_value`` + ``cost``(=市值−盈亏)。份额基准
  ``base_shares = market_value ÷ 基准日单位净值``，首次合成时惰性派生并回写冻结（快照是
  时点状态，冻结后不随净值漂移）。
- 交易按 ``trade_date`` 升序回放：买入 ``shares += amount÷nav, cost += amount``；
  卖出 ``avg = cost÷shares, cost -= avg×卖出份额, shares -= 卖出份额``。
- 当前市值 = 合成份额 × 最新单位净值；未实现盈亏 = 当前市值 − 合成成本。
- 净值缺失退化：无份额口径时 ``市值 = 快照市值 + Σ买入 − Σ卖出``，``valuation_ok=False``。

输出与旧持仓**同形状**（``fund_code/fund_name/market_value/cost``，供对账与前端复用），
额外带 ``shares/latest_nav/nav_date/pnl/valuation_ok``。
"""
from __future__ import annotations

import datetime

from app import db as database
from app.fund_nav.crud import nav_crud
from app.reconcile.crud import holdings_store, txn_store


def _ensure_base_shares(snap: dict) -> dict:
    """快照惰性派生并冻结 base_shares：用最新单位净值把快照市值折成份额，回写一次。

    旧实盘行（无 base_shares）首次合成时补算；无净值则保持 None（走退化口径）。
    """
    if snap.get("base_shares") is not None:
        return snap
    mv = snap.get("market_value") or 0
    if mv <= 0:
        return snap
    hit = nav_crud.latest_unit_nav(snap["fund_code"])
    if not hit:
        return snap
    trade_date, nav = hit
    shares = mv / nav if nav > 0 else None
    if shares is None:
        return snap
    database.update("user_holdings",
                    {"portfolio_id": snap["portfolio_id"], "fund_code": snap["fund_code"]},
                    {"base_shares": shares, "base_date": trade_date,
                     "updated_at": datetime.datetime.now().isoformat()})
    return {**snap, "base_shares": shares, "base_date": trade_date}


def compute_holdings(pid: int) -> list[dict]:
    """合成某实盘的实际持仓（快照 + 交易回放），按当前市值降序。"""
    snaps = {s["fund_code"]: _ensure_base_shares(s) for s in holdings_store.list_holdings(pid)}
    txns = txn_store.list_txns(pid)

    txns_by_code: dict[str, list[dict]] = {}
    for t in txns:
        txns_by_code.setdefault(t["fund_code"], []).append(t)

    codes = list(snaps.keys())
    for code in txns_by_code:
        if code not in snaps:
            codes.append(code)

    out: list[dict] = []
    for code in codes:
        snap = snaps.get(code, {})
        name = snap.get("fund_name") or ""
        base_shares = snap.get("base_shares")
        base_cost = snap.get("cost")
        base_mv = snap.get("market_value") or 0.0

        ts = sorted(txns_by_code.get(code, []), key=lambda t: (t["trade_date"], t["id"]))
        # 是否能走份额口径：快照有份额（或无快照）且所有交易都成功折算了份额
        share_mode = (not snap or base_shares is not None) and all(
            t.get("shares") is not None for t in ts)

        if share_mode:
            shares = base_shares or 0.0
            cost = base_cost if base_cost is not None else (base_mv if snap else 0.0)
            for t in ts:
                if not t.get("fund_name") or not name:
                    name = name or t.get("fund_name") or ""
                if t["txn_type"] == "buy":
                    shares += t["shares"]
                    cost += t["amount"]
                else:  # sell
                    if shares > 0:
                        avg = cost / shares
                        sold = min(t["shares"], shares)
                        cost -= avg * sold
                        shares -= sold
            hit = nav_crud.latest_unit_nav(code)
            if hit:
                nav_date, latest_nav = hit
                mv = shares * latest_nav
                out.append({
                    "fund_code": code, "fund_name": name,
                    "market_value": round(mv, 2), "cost": round(cost, 2) if cost is not None else None,
                    "shares": round(shares, 4), "latest_nav": latest_nav, "nav_date": nav_date,
                    "pnl": round(mv - cost, 2) if cost is not None else None,
                    "valuation_ok": True,
                })
                continue
            # 有份额但取不到最新净值：退化
        # 退化口径：按金额累计
        for t in ts:
            name = name or t.get("fund_name") or ""
        buy_amt = sum(t["amount"] for t in ts if t["txn_type"] == "buy")
        sell_amt = sum(t["amount"] for t in ts if t["txn_type"] == "sell")
        mv = base_mv + buy_amt - sell_amt
        cost = ((base_cost if base_cost is not None else base_mv) + buy_amt - sell_amt) if snap or ts else None
        out.append({
            "fund_code": code, "fund_name": name,
            "market_value": round(mv, 2), "cost": round(cost, 2) if cost is not None else None,
            "shares": None, "latest_nav": None, "nav_date": None,
            "pnl": round(mv - cost, 2) if cost is not None else None,
            "valuation_ok": False,
        })

    out.sort(key=lambda h: h["market_value"], reverse=True)
    return out
