"""trade 命令：实盘交易写操作（买入 / 卖出 / 转仓）+ 交易记录列表 / 删除。

复用 reconcile 后端 ``txn_store``：买卖按交易日锁定单位净值并折算份额；转仓拆成
「源卖出 + 目标买入」两条共享 transfer_id。删除按 id；删转仓任一条会连带删除其配对。
基金标的用 ``--fund/--from/--to`` 接收：6 位数字按代码、否则按名称反查代码。
"""
from __future__ import annotations

import sys

from app import db as database

from . import output


def _split_fund(s: str) -> tuple[str, str]:
    """标的串 → (code, name)：纯 6 位数字判为代码，否则判为名称。"""
    s = (s or "").strip()
    if s.isdigit() and len(s) == 6:
        return s, ""
    return "", s


def _portfolio(uid: int, pid: int) -> dict:
    from app.reconcile.crud import portfolios_store
    pf = portfolios_store.get_portfolio(pid, uid)
    if not pf:
        print(f"未找到实盘 #{pid}（或不属于用户 {uid}）", file=sys.stderr)
        sys.exit(1)
    return pf


def _trade_date(date: str | None) -> str:
    from app.fund_nav.crud import nav_crud
    return (date or "").strip() or nav_crud.latest_trade_date()


def _do_buysell(args, kind: str) -> None:
    from app.reconcile.crud import txn_store
    pf = _portfolio(args.user, args.pid)
    code, name = _split_fund(args.fund)
    date = _trade_date(args.date)
    if args.amount <= 0:
        print("amount 必须为正", file=sys.stderr)
        sys.exit(1)
    try:
        row = txn_store.add_txn(pf["id"], args.user, code, name, kind, date, float(args.amount))
    except ValueError as e:
        print(f"录入失败：{e}（基金名/代码可能无法识别）", file=sys.stderr)
        sys.exit(1)
    cn = "买入" if kind == "buy" else "卖出"
    data = {"ok": True, "txn": row}

    def txt(_d):
        nav = f"净值 {row['nav']} → ≈{row['shares']:,.2f} 份" if row.get("nav") else "（无净值，份额未折算）"
        print(f"✓ {cn} {row['fund_name']}({row['fund_code']}) {row['amount']:,.0f} 元"
              f" @ {row['trade_date']}　{nav}　txn#{row['id']}")
    output.emit(data, args.json, txt)


def cmd_buy(args) -> None:
    """买入一笔。"""
    _do_buysell(args, "buy")


def cmd_sell(args) -> None:
    """卖出一笔。"""
    _do_buysell(args, "sell")


def cmd_transfer(args) -> None:
    """转仓：源卖出 + 目标买入（原子，共享 transfer_id）。"""
    from app.reconcile.crud import txn_store
    pf = _portfolio(args.user, args.pid)
    fc, fn = _split_fund(args.from_)
    tc, tn = _split_fund(args.to)
    date = _trade_date(args.date)
    if args.amount <= 0:
        print("amount 必须为正", file=sys.stderr)
        sys.exit(1)
    try:
        res = txn_store.add_transfer(pf["id"], args.user, fc, fn, tc, tn, date, float(args.amount))
    except ValueError as e:
        print(f"转仓失败：{e}（基金名/代码可能无法识别）", file=sys.stderr)
        sys.exit(1)
    data = {"ok": True, **res}

    def txt(_d):
        sell, buy = res["sell"], res["buy"]
        sh = f"≈{sell['shares']:,.2f} 份" if sell.get("shares") else "（无净值）"
        print(f"✓ 转仓 {args.amount:,.0f} 元 @ {date}")
        print(f"  卖出 {sell['fund_name']}({sell['fund_code']}) {sh}　txn#{sell['id']}")
        print(f"  买入 {buy['fund_name']}({buy['fund_code']})　txn#{buy['id']}")
    output.emit(data, args.json, txt)


def cmd_txns(args) -> None:
    """列出交易记录（按交易日升序）。"""
    from app.reconcile.crud import txn_store
    _portfolio(args.user, args.pid)
    rows = txn_store.list_txns(args.pid)

    def txt(d):
        if not d:
            print("（无交易记录）")
            return
        rr = [[t["id"], t["trade_date"], t["txn_type"], t["fund_code"], t["fund_name"],
               output.num(t["amount"]), output.num(t.get("nav"), 4),
               output.num(t.get("shares")), "转" if t.get("transfer_id") else ""]
              for t in d]
        print(output.table(rr, ["id", "日期", "类型", "代码", "名称", "金额", "净值", "份额", "转仓"]))
    output.emit(rows, args.json, txt)


def cmd_txn_del(args) -> None:
    """删除一条交易记录（属转仓则连带删除其配对条）。"""
    from app.reconcile.crud import txn_store
    _portfolio(args.user, args.pid)
    row = database.select_one("holding_txns", {"portfolio_id": f"eq.{args.pid}", "id": f"eq.{args.id}"})
    if not row:
        print(f"未找到交易记录 #{args.id}", file=sys.stderr)
        sys.exit(1)
    tid = row.get("transfer_id")
    if tid:
        mates = database.select("holding_txns",
                                {"portfolio_id": f"eq.{args.pid}", "transfer_id": f"eq.{tid}"})
        ids = [m["id"] for m in mates]
        deleted = txn_store.delete_txns(args.pid, ids)
        msg = f"已删除转仓 {deleted} 条（txn {ids}）"
    else:
        txn_store.delete_txn(args.pid, args.id)
        deleted, ids = 1, [args.id]
        msg = f"已删除交易 #{args.id}"
    output.emit({"ok": True, "deleted": deleted, "ids": ids}, args.json, lambda _d: print("✓ " + msg))
