"""实盘对账蓝图：实盘 CRUD + 持仓 CRUD + 对账计算。全部按 user_id 隔离。

一个用户可有多个实盘（自己的 + 代管他人的），每个实盘关联一套仓位建议（预设）。
链路：选实盘 → 实盘的持仓 + 关联预设 → 复用 ③仓位的目标权重与聚类簇 →
``reconcile`` 按赛道对齐算每笔加/减/建/清金额。持仓持久化；现金/缓冲带/cap 走请求体不落库。
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app import preset_access
from app.fund_nav.crud import nav_crud
from app.position.api.router import compute_position
from app.position.algo import optimize
from app.reconcile.algo import classify
from app.reconcile.algo import reconcile as recon_algo
from app.reconcile.crud import holdings_compute, holdings_store, portfolios_store, txn_store
from app.stock_industry.crud import industry_crud

bp = Blueprint("reconcile", __name__, url_prefix="/api/reconcile")

CAP_MIN, CAP_MAX = 0.10, 0.30
BAND_MIN, BAND_MAX = 0.005, 0.10


def _clamp(val, lo, hi, default):
    try:
        v = float(val)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, v))


def _resolve_portfolio(uid: int):
    """从 query/body 取 portfolio_id 并校验归属；缺省则用默认实盘。

    返回 ``(portfolio, error)``：error 为 ``(payload, status)`` 或 None。
    """
    pid = request.args.get("portfolio_id")
    if pid is None:
        body = request.get_json(silent=True) or {}
        pid = body.get("portfolio_id")
    if pid is None:
        return portfolios_store.ensure_default(uid), None
    pf = portfolios_store.get_portfolio(int(pid), uid)
    if not pf:
        return None, ({"detail": "portfolio not found"}, 404)
    return pf, None


# ── 实盘账户 CRUD ──────────────────────────────────────────────

@bp.get("/portfolios")
@jwt_required()
def list_portfolios():
    """列出当前用户的全部实盘（保证至少有一个默认实盘）。"""
    uid = preset_access.current_user_id()
    portfolios_store.ensure_default(uid)
    return jsonify({"items": portfolios_store.list_portfolios(uid)})


@bp.post("/portfolios")
@jwt_required()
def create_portfolio():
    """新建实盘。body: ``{name, preset_id?}``。"""
    uid = preset_access.current_user_id()
    body = request.get_json(silent=True) or {}
    pf = portfolios_store.create_portfolio(uid, body.get("name", ""), body.get("preset_id"))
    return jsonify(pf)


@bp.patch("/portfolios/<int:pid>")
@jwt_required()
def update_portfolio(pid: int):
    """改名 / 关联预设。body: ``{name?, preset_id?}``（含 preset_id 键即更新，可置空取消关联）。"""
    uid = preset_access.current_user_id()
    body = request.get_json(silent=True) or {}
    set_preset = "preset_id" in body
    pf = portfolios_store.update_portfolio(
        pid, uid, name=body.get("name"),
        preset_id=body.get("preset_id"), set_preset=set_preset,
    )
    if not pf:
        return jsonify({"detail": "portfolio not found"}), 404
    return jsonify(pf)


@bp.delete("/portfolios/<int:pid>")
@jwt_required()
def delete_portfolio(pid: int):
    """删除实盘及其持仓。"""
    uid = preset_access.current_user_id()
    if not portfolios_store.delete_portfolio(pid, uid):
        return jsonify({"detail": "portfolio not found"}), 404
    return jsonify({"ok": True})


# ── 持仓 CRUD（按 portfolio_id 隔离）──────────────────────────

@bp.get("/holdings")
@jwt_required()
def get_holdings():
    """列出某实盘的**实际持仓**（快照 + 交易合成）。query: ``?portfolio_id=``（缺省用默认实盘）。"""
    uid = preset_access.current_user_id()
    pf, error = _resolve_portfolio(uid)
    if error:
        payload, status = error
        return jsonify(payload), status
    return jsonify({"portfolio_id": pf["id"], "items": holdings_compute.compute_holdings(pf["id"])})


@bp.get("/holdings/snapshot")
@jwt_required()
def get_snapshot():
    """列出某实盘的**初始化快照**原始行（供快照编辑用）。query: ``?portfolio_id=``。"""
    uid = preset_access.current_user_id()
    pf, error = _resolve_portfolio(uid)
    if error:
        payload, status = error
        return jsonify(payload), status
    return jsonify({"portfolio_id": pf["id"], "items": holdings_store.list_holdings(pf["id"])})


@bp.get("/holdings/clusters")
@jwt_required()
def get_holdings_clusters():
    """实际持仓基金 → 所属赛道（簇）映射（需实盘已关联预设）。query: ``?portfolio_id=``。

    返回 ``{has_preset, map: {fund_code: cluster_id|null}, clusters: {cluster_id: {seq, label, industries}}}``。
    ``seq`` 为簇序号（簇1、簇2…，按目标权重降序）；``industries`` 为带占比的申万三级行业 top3。
    归类失败的基金 map 值为 null（赛道外）。复用对账同款聚类与归类逻辑，仅用于展示。
    """
    uid = preset_access.current_user_id()
    pf, error = _resolve_portfolio(uid)
    if error:
        payload, status = error
        return jsonify(payload), status
    preset_id = pf.get("preset_id")
    if not preset_id:
        return jsonify({"has_preset": False, "map": {}, "clusters": {}})
    items = preset_access.snapshot_items(preset_id, uid)
    if items is None:
        return jsonify({"has_preset": True, "map": {}, "clusters": {}})
    result, clusters = compute_position(items, optimize.DEFAULT_CAP)
    if result is None or not result.get("items"):
        return jsonify({"has_preset": True, "map": {}, "clusters": {}})
    code2cluster = classify.build_code_to_cluster(clusters)
    name2cluster = classify.build_name_index(clusters)
    cluster_vecs = classify.cluster_vectors(clusters)
    cid2cluster = {c["cluster_id"]: c for c in clusters}
    # 簇序号：按目标 items 顺序（权重降序）从 1 开始编号
    clusters_out: dict[str, dict] = {}
    for seq, it in enumerate(result["items"], start=1):
        cid = it["cluster_id"]
        c = cid2cluster.get(cid, {})
        industries = [{"label": i["label"], "ratio": i["ratio"]}
                      for i in (c.get("top_industries") or [])[:3]]
        clusters_out[str(cid)] = {
            "seq": seq,
            "label": it.get("cluster_name", ""),
            "industries": industries,
        }
    ind_idx = industry_crud.industry_index()
    out: dict[str, int | None] = {}
    for h in holdings_compute.compute_holdings(pf["id"]):
        cid, _match, _sim = classify.classify_fund(
            h["fund_code"], h.get("fund_name", ""),
            code2cluster, name2cluster, cluster_vecs, ind_idx)
        out[h["fund_code"]] = cid if (cid is not None and str(cid) in clusters_out) else None
    return jsonify({"has_preset": True, "map": out, "clusters": clusters_out})


@bp.post("/holdings")
@jwt_required()
def upsert_holding():
    """新增/更新一只快照持仓。body: ``{portfolio_id?, fund_code, fund_name?, market_value, cost?}``。"""
    uid = preset_access.current_user_id()
    pf, error = _resolve_portfolio(uid)
    if error:
        payload, status = error
        return jsonify(payload), status
    body = request.get_json(silent=True) or {}
    code = str(body.get("fund_code") or "").strip()
    name = str(body.get("fund_name") or "").strip()
    if not code and name:   # 只给名称时反查代码（与交易记录录入一致，便于 App 复制名称）
        code, name = holdings_store.resolve_by_name(name)
    if not code:
        return jsonify({"detail": "fund_code or fund_name required"}), 400
    try:
        mv = float(body.get("market_value") or 0)
    except (TypeError, ValueError):
        return jsonify({"detail": "market_value invalid"}), 400
    cost = body.get("cost")
    try:
        cost = float(cost) if cost is not None and cost != "" else None
    except (TypeError, ValueError):
        cost = None
    row = holdings_store.upsert_holding(pf["id"], uid, code, name, mv, cost)
    return jsonify(row)


@bp.post("/holdings/bulk")
@jwt_required()
def bulk_holdings():
    """全量替换某实盘持仓。body: ``{portfolio_id?, rows:[{fund_code, market_value, fund_name?, cost?}]}``。"""
    uid = preset_access.current_user_id()
    pf, error = _resolve_portfolio(uid)
    if error:
        payload, status = error
        return jsonify(payload), status
    body = request.get_json(silent=True) or {}
    rows = body.get("rows") or []
    count = holdings_store.bulk_replace(pf["id"], uid, rows)
    return jsonify({"count": count})


@bp.delete("/holdings/<code>")
@jwt_required()
def delete_holding(code: str):
    """删除一只持仓。query: ``?portfolio_id=``。"""
    uid = preset_access.current_user_id()
    pf, error = _resolve_portfolio(uid)
    if error:
        payload, status = error
        return jsonify(payload), status
    holdings_store.delete_holding(pf["id"], code)
    return jsonify({"ok": True})


@bp.delete("/holdings")
@jwt_required()
def clear_holdings():
    """清空某实盘全部持仓。query: ``?portfolio_id=``。"""
    uid = preset_access.current_user_id()
    pf, error = _resolve_portfolio(uid)
    if error:
        payload, status = error
        return jsonify(payload), status
    holdings_store.clear_holdings(pf["id"])
    return jsonify({"ok": True})


# ── 交易记录 CRUD（按 portfolio_id 隔离）──────────────────────

@bp.get("/txns")
@jwt_required()
def get_txns():
    """列出某实盘的交易记录（按交易日升序）。query: ``?portfolio_id=``。"""
    uid = preset_access.current_user_id()
    pf, error = _resolve_portfolio(uid)
    if error:
        payload, status = error
        return jsonify(payload), status
    return jsonify({"portfolio_id": pf["id"], "items": txn_store.list_txns(pf["id"])})


@bp.post("/txns")
@jwt_required()
def add_txn():
    """记一笔交易。body: ``{portfolio_id?, kind, trade_date, amount, ...}``。

    ``kind=buy/sell``：``{fund_code|fund_name, trade_date, amount}``；
    ``kind=transfer``：``{from_code|from_name, to_code|to_name, trade_date, amount}``。
    落账时锁定当日单位净值并折算份额。
    """
    uid = preset_access.current_user_id()
    pf, error = _resolve_portfolio(uid)
    if error:
        payload, status = error
        return jsonify(payload), status
    body = request.get_json(silent=True) or {}
    kind = body.get("kind") or body.get("txn_type")
    date = str(body.get("trade_date") or "").strip()
    if not date:
        return jsonify({"detail": "trade_date required"}), 400
    try:
        amount = float(body.get("amount") or 0)
    except (TypeError, ValueError):
        return jsonify({"detail": "amount invalid"}), 400
    if amount <= 0:
        return jsonify({"detail": "amount must be positive"}), 400
    note = body.get("note", "")
    try:
        if kind == "transfer":
            res = txn_store.add_transfer(
                pf["id"], uid, body.get("from_code", ""), body.get("from_name", ""),
                body.get("to_code", ""), body.get("to_name", ""), date, amount, note)
            return jsonify(res)
        if kind in ("buy", "sell"):
            row = txn_store.add_txn(pf["id"], uid, body.get("fund_code", ""),
                                    body.get("fund_name", ""), kind, date, amount, note)
            return jsonify(row)
    except ValueError as e:
        return jsonify({"detail": str(e)}), 400
    return jsonify({"detail": f"bad kind: {kind}"}), 400


@bp.patch("/txns/<int:txn_id>")
@jwt_required()
def update_txn(txn_id: int):
    """修改一条交易记录（买入/卖出）。body: ``{portfolio_id?, kind?, fund_code/fund_name?, trade_date?, amount?}``。

    改了金额/日期/基金会按新交易日重新锁定单位净值并折算份额。
    """
    uid = preset_access.current_user_id()
    pf, error = _resolve_portfolio(uid)
    if error:
        payload, status = error
        return jsonify(payload), status
    body = request.get_json(silent=True) or {}
    amount = body.get("amount")
    if amount is not None:
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return jsonify({"detail": "amount invalid"}), 400
        if amount <= 0:
            return jsonify({"detail": "amount must be positive"}), 400
    try:
        row = txn_store.update_txn(
            pf["id"], txn_id,
            code=body.get("fund_code", ""), name=body.get("fund_name", ""),
            txn_type=body.get("kind") or body.get("txn_type"),
            date=(str(body.get("trade_date")).strip() if body.get("trade_date") else None),
            amount=amount)
    except ValueError as e:
        return jsonify({"detail": str(e)}), 400
    if row is None:
        return jsonify({"detail": "txn not found"}), 404
    return jsonify(row)


@bp.delete("/txns/<int:txn_id>")
@jwt_required()
def delete_txn(txn_id: int):
    """删除一条交易记录。query: ``?portfolio_id=``。"""
    uid = preset_access.current_user_id()
    pf, error = _resolve_portfolio(uid)
    if error:
        payload, status = error
        return jsonify(payload), status
    txn_store.delete_txn(pf["id"], txn_id)
    return jsonify({"ok": True})


@bp.post("/txns/bulk-delete")
@jwt_required()
def bulk_delete_txns():
    """批量删除交易记录。body: ``{portfolio_id?, ids:[...]}``。"""
    uid = preset_access.current_user_id()
    pf, error = _resolve_portfolio(uid)
    if error:
        payload, status = error
        return jsonify(payload), status
    body = request.get_json(silent=True) or {}
    count = txn_store.delete_txns(pf["id"], body.get("ids") or [])
    return jsonify({"count": count})


@bp.post("/txns/from-rebalance")
@jwt_required()
def txns_from_rebalance():
    """把一次对账的转仓建议批量落成交易记录。

    body: ``{portfolio_id?, trade_date?, transfers:[{from_code,from_name,to_code,to_name,amount}]}``。
    每条转仓拆成「源卖出 + 目标买入」两条共享 transfer_id；trade_date 缺省取最近交易日。
    """
    uid = preset_access.current_user_id()
    pf, error = _resolve_portfolio(uid)
    if error:
        payload, status = error
        return jsonify(payload), status
    body = request.get_json(silent=True) or {}
    date = str(body.get("trade_date") or "").strip() or nav_crud.latest_trade_date()
    transfers = body.get("transfers") or []
    saved = 0
    for t in transfers:
        try:
            amount = float(t.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        from_code = str(t.get("from_code") or "").strip()
        to_code = str(t.get("to_code") or "").strip()
        if from_code and to_code:
            txn_store.add_transfer(pf["id"], uid, from_code, t.get("from_name", ""),
                                   to_code, t.get("to_name", ""), date, amount,
                                   note="对账批量落账")
            saved += 1
        elif to_code:  # 纯加仓
            txn_store.add_txn(pf["id"], uid, to_code, t.get("to_name", ""),
                              "buy", date, amount, note="对账批量落账")
            saved += 1
        elif from_code:  # 纯减仓
            txn_store.add_txn(pf["id"], uid, from_code, t.get("from_name", ""),
                              "sell", date, amount, note="对账批量落账")
            saved += 1
    return jsonify({"count": saved, "trade_date": date})


@bp.post("/run")
@jwt_required()
def run():
    """对账。body: ``{portfolio_id, cap?, band?, sell_outside?, trim_overflow?, preset_id?}``。

    预设默认取自实盘的关联（``preset_id`` 可临时覆盖）。两个正交开关覆盖四类操作意图；
    现金由系统反推（"加满还差多少"）。返回 ``{rows, summary, meta, transfers}``。
    """
    uid = preset_access.current_user_id()
    pf, error = _resolve_portfolio(uid)
    if error:
        payload, status = error
        return jsonify(payload), status

    body = request.get_json(silent=True) or {}
    preset_id = body.get("preset_id") or pf.get("preset_id")
    if not preset_id:
        return jsonify({"rows": None, "reason": "该实盘尚未关联仓位建议，请先在上方选择一个预设"})
    if not preset_access.owned_preset(preset_id, uid):
        return jsonify({"detail": "preset not found"}), 404
    items = preset_access.snapshot_items(preset_id, uid)
    if items is None:
        return jsonify({"rows": None, "reason": "该预设尚无镜像快照，请先在筛选页保存镜像"})

    holdings = holdings_compute.compute_holdings(pf["id"])
    if not holdings:
        return jsonify({"rows": None, "reason": "该实盘尚未录入任何持仓，请先在上方录入"})

    cap = _clamp(body.get("cap"), CAP_MIN, CAP_MAX, optimize.DEFAULT_CAP)
    band = _clamp(body.get("band"), BAND_MIN, BAND_MAX, recon_algo.DEFAULT_BAND)
    sell_outside = bool(body.get("sell_outside"))
    trim_overflow = body.get("trim_overflow")
    trim_overflow = True if trim_overflow is None else bool(trim_overflow)

    result, clusters = compute_position(items, cap)
    if result is None or not result.get("items"):
        return jsonify({"rows": None, "reason": "有效基金不足（需 ≥3 只含股票持仓的基金），无法生成目标"})

    ind_idx = industry_crud.industry_index()
    recon = recon_algo.reconcile(result["items"], holdings, clusters, ind_idx,
                                 band=band, sell_outside=sell_outside, trim_overflow=trim_overflow)
    recon["meta"]["cap"] = cap
    recon["meta"]["preset_id"] = preset_id
    recon["meta"]["nav_as_of"] = result["meta"].get("nav_as_of")
    recon["meta"]["holdings_quarter"] = result["meta"].get("holdings_quarter")
    return jsonify(recon)
