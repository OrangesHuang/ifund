"""用户实盘持仓（``user_holdings`` 表）读写：按 portfolio_id 隔离，每只基金一行。

一个用户可有多个实盘（自己的 + 代管他人的），持仓挂在 ``portfolio_id`` 下；``user_id``
冗余保留便于隔离查询。录入是重活、跨会话保留，故持久化；现金 / 缓冲带 / cap 是即时计算
参数走请求体不落库（持久化会陈旧误导）。``cost`` 为持仓成本（NULL=未提供），盈亏=市值−成本
仅展示不参与决策。

导入支持「按名称」：用户 App 里只看得到基金名（且全是 C 类），故按名称反查代码——
先精确匹配 funds.name，再去份额后缀匹配，匹配不到则用名称本身占位（后续靠名称归类兜底）。
"""
from __future__ import annotations

import datetime

from app import db as database
from app.cluster.algo.dedup import _base_name

TABLE = "user_holdings"


def _now() -> str:
    return datetime.datetime.now().isoformat()


def list_holdings(pid: int) -> list[dict]:
    """该实盘全部持仓，按市值降序。"""
    return database.select(TABLE, {
        "portfolio_id": f"eq.{pid}", "order": "market_value.desc",
    })


def _fund_name(code: str) -> str:
    """从 funds 表取基金名（用于录入时未提供名称的兜底）。"""
    row = database.select_one("funds", {"code": f"eq.{code}"})
    return row.get("name", "") if row else ""


def resolve_by_name(name: str) -> tuple[str, str]:
    """按基金名反查 ``(code, canonical_name)``；查不到返回 ``(name, name)``（用名称占位）。

    1. 精确匹配 ``funds.name``；2. 去份额后缀（A/C/E…）后匹配同主体名的任一只。
    """
    name = (name or "").strip()
    if not name:
        return "", ""
    exact = database.select_one("funds", {"name": f"eq.{name}"})
    if exact:
        return exact["code"], exact["name"]
    base = _base_name(name)
    if base:
        for f in database.select("funds", {"select": "code,name"}):
            if _base_name(f.get("name", "")) == base:
                return f["code"], f["name"]
    return name, name   # 反查不到：用名称占位，分类时靠名称匹配兜底


def upsert_holding(pid: int, uid: int, code: str, name: str, mv: float,
                   cost: float | None = None) -> dict:
    """upsert 单只持仓；name 为空则从 funds 表补。返回该行。"""
    code = (code or "").strip()
    name = (name or "").strip() or _fund_name(code)
    existing = database.select_one(TABLE, {
        "portfolio_id": f"eq.{pid}", "fund_code": f"eq.{code}",
    })
    # 快照金额变了，份额基准随之失效：清空 base_shares 让合成时按最新净值重新派生冻结
    fields = {"fund_name": name, "market_value": mv, "cost": cost,
              "base_shares": None, "base_date": None, "updated_at": _now()}
    if existing:
        database.update(TABLE, {"portfolio_id": pid, "fund_code": code}, fields)
        return {**existing, **fields}
    return database.insert(TABLE, {
        "portfolio_id": pid, "user_id": uid, "fund_code": code, **fields,
    })


def bulk_replace(pid: int, uid: int, rows: list[dict]) -> int:
    """全量替换该实盘持仓：先删后批量插入。

    rows 每项 ``{fund_code?, fund_name?, market_value, cost?}``；只给名称时反查代码。
    同一 code 取最后一条（去重）。返回写入行数。
    """
    cleaned: dict[str, dict] = {}
    for r in rows:
        code = str(r.get("fund_code") or "").strip()
        name = str(r.get("fund_name") or "").strip()
        if not code and name:
            code, name = resolve_by_name(name)
        if not code:
            continue
        try:
            mv = float(r.get("market_value") or 0)
        except (TypeError, ValueError):
            continue
        cost = r.get("cost")
        try:
            cost = float(cost) if cost is not None and cost != "" else None
        except (TypeError, ValueError):
            cost = None
        cleaned[code] = {"fund_code": code, "market_value": mv,
                         "fund_name": name, "cost": cost}

    database.delete(TABLE, {"portfolio_id": pid})
    if not cleaned:
        return 0
    now = _now()
    payload = [{
        "portfolio_id": pid, "user_id": uid, "fund_code": c,
        "fund_name": v["fund_name"] or _fund_name(c),
        "market_value": v["market_value"], "cost": v["cost"], "updated_at": now,
    } for c, v in cleaned.items()]
    database.batch_insert(TABLE, payload)
    return len(payload)


def delete_holding(pid: int, code: str) -> None:
    """删除该实盘的一只持仓。"""
    database.delete(TABLE, {"portfolio_id": pid, "fund_code": (code or "").strip()})


def clear_holdings(pid: int) -> None:
    """清空该实盘全部持仓。"""
    database.delete(TABLE, {"portfolio_id": pid})
