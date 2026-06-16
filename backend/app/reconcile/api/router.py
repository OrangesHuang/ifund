"""实盘对账蓝图：持仓 CRUD + 对账计算。全部按 user_id 隔离。

链路：用户持仓（``user_holdings``）+ 可投现金 → 复用 ③仓位的目标权重与聚类簇 →
``reconcile`` 按赛道对齐算每笔加/减/建/清金额。持仓持久化；现金/缓冲带/cap 走请求体不落库。
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app import preset_access
from app.position.api.router import compute_position
from app.position.algo import optimize
from app.reconcile.algo import reconcile as recon_algo
from app.reconcile.crud import holdings_store
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


@bp.get("/holdings")
@jwt_required()
def get_holdings():
    """列出当前用户的实盘持仓。"""
    uid = preset_access.current_user_id()
    return jsonify({"items": holdings_store.list_holdings(uid)})


@bp.post("/holdings")
@jwt_required()
def upsert_holding():
    """新增/更新一只持仓。body: ``{fund_code, fund_name?, market_value}``。"""
    uid = preset_access.current_user_id()
    body = request.get_json(silent=True) or {}
    code = str(body.get("fund_code") or "").strip()
    if not code:
        return jsonify({"detail": "fund_code required"}), 400
    try:
        mv = float(body.get("market_value") or 0)
    except (TypeError, ValueError):
        return jsonify({"detail": "market_value invalid"}), 400
    cost = body.get("cost")
    try:
        cost = float(cost) if cost is not None and cost != "" else None
    except (TypeError, ValueError):
        cost = None
    row = holdings_store.upsert_holding(uid, code, body.get("fund_name", ""), mv, cost)
    return jsonify(row)


@bp.post("/holdings/bulk")
@jwt_required()
def bulk_holdings():
    """全量替换持仓。body: ``{rows:[{fund_code, market_value, fund_name?}]}``。"""
    uid = preset_access.current_user_id()
    body = request.get_json(silent=True) or {}
    rows = body.get("rows") or []
    count = holdings_store.bulk_replace(uid, rows)
    return jsonify({"count": count})


@bp.delete("/holdings/<code>")
@jwt_required()
def delete_holding(code: str):
    """删除一只持仓。"""
    uid = preset_access.current_user_id()
    holdings_store.delete_holding(uid, code)
    return jsonify({"ok": True})


@bp.delete("/holdings")
@jwt_required()
def clear_holdings():
    """清空全部持仓。"""
    uid = preset_access.current_user_id()
    holdings_store.clear_holdings(uid)
    return jsonify({"ok": True})


@bp.post("/run")
@jwt_required()
def run():
    """对账。body: ``{preset_id, cap?, cash?, band?}``。返回 ``{rows, summary, meta}``。"""
    items, error = preset_access.resolve_items("rows")
    if error:
        payload, status = error
        return jsonify(payload), status

    uid = preset_access.current_user_id()
    holdings = holdings_store.list_holdings(uid)
    if not holdings:
        return jsonify({"rows": None, "reason": "尚未导入任何实盘持仓，请先在「持仓录入」录入"})

    body = request.get_json(silent=True) or {}
    cap = _clamp(body.get("cap"), CAP_MIN, CAP_MAX, optimize.DEFAULT_CAP)
    band = _clamp(body.get("band"), BAND_MIN, BAND_MAX, recon_algo.DEFAULT_BAND)
    cash = _clamp(body.get("cash"), 0.0, 1e12, 0.0)

    result, clusters = compute_position(items, cap)
    if result is None or not result.get("items"):
        return jsonify({"rows": None, "reason": "有效基金不足（需 ≥3 只含股票持仓的基金），无法生成目标"})

    mode = body.get("mode") if body.get("mode") in ("sleeve", "whole") else "sleeve"
    ind_idx = industry_crud.industry_index()
    recon = recon_algo.reconcile(result["items"], holdings, cash, band, clusters, ind_idx, mode)
    recon["meta"]["cap"] = cap
    recon["meta"]["nav_as_of"] = result["meta"].get("nav_as_of")
    recon["meta"]["holdings_quarter"] = result["meta"].get("holdings_quarter")
    return jsonify(recon)
