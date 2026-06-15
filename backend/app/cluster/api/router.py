"""基金行业暴露聚类蓝图：对某预设的镜像快照做②聚类分析。"""
from __future__ import annotations

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from app import preset_access
from app.cluster.algo import pipeline

bp = Blueprint("cluster", __name__, url_prefix="/api/cluster")


@bp.post("/run")
@jwt_required()
def run():
    """对预设的镜像快照聚类。body: ``{"preset_id": int}``。"""
    items, error = preset_access.resolve_items("clusters")
    if error:
        payload, status = error
        return jsonify(payload), status

    result = pipeline.run(items, preset_access.build_metrics(items))
    if result is None:
        return jsonify({"clusters": None, "reason": "有效基金不足（需 ≥3 只含股票持仓的基金）"})
    return jsonify(result)
