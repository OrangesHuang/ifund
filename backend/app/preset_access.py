"""预设 / 镜像快照的共享访问助手。

cluster（②聚类）、position（③仓位）等分析模块都以「某预设的镜像快照」为输入，
鉴权与指标组装逻辑一致，集中在此避免重复。
"""
from __future__ import annotations

import json

from flask import request
from flask_jwt_extended import get_jwt_identity

from app import db as database


def current_user_id() -> int:
    """从 JWT 身份取当前用户 id；查不到返回 0。"""
    user = database.select_one("users", {"username": f"eq.{get_jwt_identity()}"})
    return user["id"] if user else 0


def owned_preset(preset_id: int, user_id: int):
    """该预设若属于此用户则返回其行，否则 None（用于 404 隔离）。"""
    return database.select_one("query_presets", {
        "id": f"eq.{preset_id}", "user_id": f"eq.{user_id}",
    })


def snapshot_items(preset_id: int, user_id: int) -> list[dict] | None:
    """返回该预设镜像的 items 列表；无镜像返回 None。"""
    snapshot = database.select_one("fund_snapshots", {
        "user_id": f"eq.{user_id}", "preset_id": f"eq.{preset_id}",
    })
    if not snapshot:
        return None
    return json.loads(snapshot.get("items_json") or "[]")


def resolve_items(none_key: str):
    """校验当前请求 body 的 preset_id（归属隔离）并加载镜像 items。

    返回 ``(items, error)``：成功时 items 为 list、error 为 None；失败时 items 为 None、
    error 为 ``(payload_dict, status_code)``，由调用方 ``jsonify`` 后返回。
    ``none_key`` 是「无镜像」降级响应里的占位键（cluster→"clusters"，position→"items"）。
    """
    user_id = current_user_id()
    data = request.get_json(silent=True) or {}
    preset_id = data.get("preset_id")
    if not preset_id:
        return None, ({"detail": "preset_id required"}, 400)
    if not owned_preset(preset_id, user_id):
        return None, ({"detail": "preset not found"}, 404)
    items = snapshot_items(preset_id, user_id)
    if items is None:
        return None, ({none_key: None, "reason": "该预设尚无镜像快照，请先在筛选页保存镜像"}, 200)
    return items, None


def build_metrics(items: list[dict]) -> dict[str, dict]:
    """每只基金的展示/评分指标：快照内字段 + fund_details 补 risk_return/成立日期。"""
    metrics: dict[str, dict] = {}
    for it in items:
        code = it.get("code")
        if code:
            metrics[code] = {
                "name": it.get("name", ""),
                "sharpe_3y": it.get("sharpe_3y"),
                "scale": it.get("scale"),
            }
    for code, metric in metrics.items():
        detail = database.select_one("fund_details", {"fund_code": f"eq.{code}"})
        if detail:
            metric["risk_return_ratio_3y"] = detail.get("risk_return_ratio_3y")
            metric["establish_date"] = detail.get("establish_date")
    return metrics
