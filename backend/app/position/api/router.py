"""簇级仓位权重蓝图：基于②聚类结果，对每簇做③仓位建议（TOP5 候选交叉选基金 + 行业感知权重）。

链路：预设镜像 → cluster.pipeline 聚类 → 取每簇 TOP5 候选净值/持仓 →
组合优化选基金（行业去重）→ 景气度(净值四因子) + 乖离度 → 行业感知目标权重(∑=100%) + 持仓推荐。
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app import db as database
from app import preset_access
from app.cluster.algo import pipeline as cluster_pipeline
from app.fund_holdings.crud import holdings_crud
from app.fund_nav.crud import nav_crud
from app.position.algo import pipeline as position_pipeline

bp = Blueprint("position", __name__, url_prefix="/api/position")

NAV_LOOKBACK = 260      # 取最近约 13 个月净值，够算 6m 动量 / MA60 / 一致性
CAP_MIN, CAP_MAX = 0.10, 0.30   # 单一行业上限可调区间（前端均衡强度档位）


def _resolve_cap() -> float:
    """从请求体读取均衡强度 cap（单一行业穿透占比上限），缺省/越界回退到默认值。"""
    body = request.get_json(silent=True) or {}
    try:
        cap = float(body.get("cap"))
    except (TypeError, ValueError):
        return position_pipeline.optimize.DEFAULT_CAP
    return min(CAP_MAX, max(CAP_MIN, cap))


@bp.post("/run")
@jwt_required()
def run():
    """对预设镜像聚类并算簇级仓位建议。body: ``{"preset_id": int, "cap"?: float}``。"""
    items, error = preset_access.resolve_items("items")
    if error:
        payload, status = error
        return jsonify(payload), status

    cluster_result = cluster_pipeline.run(items, preset_access.build_metrics(items))
    if cluster_result is None:
        return jsonify({"items": None, "reason": "有效基金不足（需 ≥3 只含股票持仓的基金）"})

    clusters = cluster_result["clusters"]
    # 每簇取综合分前 TOPK 候选（供组合优化交叉选基金），需覆盖它们全部的净值/持仓/明细
    cand_codes = sorted({f["code"]
                         for c in clusters if c.get("funds")
                         for f in c["funds"][:position_pipeline.optimize.TOPK]})
    nav_by_code = {code: nav_crud.recent_series_dated(code, NAV_LOOKBACK) for code in cand_codes}
    holdings_by_code = {code: holdings_crud.top_holdings(code, "stock") for code in cand_codes}
    detail_by_code = {}
    for code in cand_codes:
        detail = database.select_one("fund_details", {"fund_code": f"eq.{code}"})
        if detail:
            detail_by_code[code] = detail
    result = position_pipeline.run(clusters, nav_by_code, holdings_by_code,
                                   detail_by_code, cap=_resolve_cap())
    result["cluster_meta"] = cluster_result["meta"]
    return jsonify(result)
