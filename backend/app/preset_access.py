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


def exclude_rules(preset_id: int, user_id: int) -> tuple[set[str], list[str]]:
    """从预设 filters 解析「过滤名单」：精确排除代码集合 + 名称排除关键字。

    过滤名单与基金查询页的「排除代码/排除名称」复用同一份 ``filters.exclude_codes`` /
    ``filters.name_excludes``，故工作台移入过滤 = 改预设这两个字段。
    """
    preset = owned_preset(preset_id, user_id)
    filters = json.loads(preset.get("filters_json") or "{}") if preset else {}
    codes = {str(c) for c in (filters.get("exclude_codes") or [])}
    name_kws = [str(k) for k in (filters.get("name_excludes") or []) if str(k).strip()]
    return codes, name_kws


def apply_exclude(items: list[dict], codes: set[str], name_kws: list[str]) -> list[dict]:
    """剔除命中过滤名单的基金（代码精确 / 名称含关键字），与 /fund/list 排除语义一致。"""
    def keep(it: dict) -> bool:
        if it.get("code") in codes:
            return False
        name = it.get("name") or ""
        return not any(kw in name for kw in name_kws)
    return [it for it in items if keep(it)]


def snapshot_items(preset_id: int, user_id: int, with_exclude: bool = True) -> list[dict] | None:
    """返回该预设镜像的 items 列表；无镜像返回 None。

    ``with_exclude=True``（默认，聚类/仓位等下游用）时，按预设过滤名单实时剔除——
    这样在工作台把基金移入过滤名单后，无需重建镜像即可让下游分析立刻不含该基金。
    """
    snapshot = database.select_one("fund_snapshots", {
        "user_id": f"eq.{user_id}", "preset_id": f"eq.{preset_id}",
    })
    if not snapshot:
        return None
    items = json.loads(snapshot.get("items_json") or "[]")
    if with_exclude:
        codes, name_kws = exclude_rules(preset_id, user_id)
        items = apply_exclude(items, codes, name_kws)
    return items


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


def ai_public(row: dict | None) -> dict | None:
    """剥离 fund_ai_analysis 的内部列（id/fund_code），返回前端可用的子对象。"""
    if not row:
        return None
    return {k: v for k, v in row.items() if k not in ("id", "fund_code")}


def ai_by_codes(codes: list[str]) -> dict[str, dict]:
    """批量取一批基金的 AI 定性分析：返回 ``{code: public_ai_dict}``，未分析的不在 dict 内。

    与基金列表页 ``_attach_ai`` 同源，供仓位建议等下游就地展示 AI 评价。
    """
    uniq = sorted({str(c) for c in codes if c})
    if not uniq:
        return {}
    rows = database.select("fund_ai_analysis", {"fund_code": f"in.({','.join(uniq)})"})
    return {r["fund_code"]: ai_public(r) for r in rows}


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
