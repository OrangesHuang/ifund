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
from app.position.algo import backtest as position_backtest
from app.position.algo import pipeline as position_pipeline
from app.stock_industry.crud import industry_crud

bp = Blueprint("position", __name__, url_prefix="/api/position")

NAV_LOOKBACK = 260      # 取最近约 13 个月净值，够算 6m 动量 / MA60 / 一致性
BACKTEST_LOOKBACK = 900  # 回测取更长净值（约 3.5 年），覆盖多个调仓点
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


@bp.post("/backtest")
@jwt_required()
def backtest():
    """对当前代表基金集合做 walk-forward 回测：动量调权 vs 等权。body: ``{"preset_id", "cap"?}``。

    复用 ③ 仓位建议的「聚类 + 选代表基金」得到同一批基金，再用各自更长净值跑回测，
    验证「按动量/乖离调权」是否相对等权产生净增量。返回 backtest.run_backtest 的结构。
    """
    items, error = preset_access.resolve_items("items")
    if error:
        payload, status = error
        return jsonify(payload), status

    cluster_result = cluster_pipeline.run(items, preset_access.build_metrics(items))
    if cluster_result is None:
        return jsonify({"result": None, "reason": "有效基金不足（需 ≥3 只含股票持仓的基金）"})

    clusters = cluster_result["clusters"]
    cand_codes = sorted({f["code"]
                         for c in clusters if c.get("funds")
                         for f in c["funds"][:position_pipeline.optimize.TOPK]})
    holdings_by_code = {code: holdings_crud.top_holdings(code, "stock") for code in cand_codes}
    ind_idx = industry_crud.industry_index()
    _, _, _, selected = position_pipeline.select_representatives(
        clusters, holdings_by_code, ind_idx, _resolve_cap())
    if len(selected) < 2:
        return jsonify({"result": None, "reason": "代表基金不足 2 只，无法回测"})

    dated_by_code = {f["code"]: nav_crud.recent_series_dated(f["code"], BACKTEST_LOOKBACK)
                     for f in selected}
    result = position_backtest.run_backtest(selected, dated_by_code)
    if result is None:
        return jsonify({"result": None,
                        "reason": "代表基金共同净值历史不足，无法回测（需更长净值序列）"})
    return jsonify({"result": result})
