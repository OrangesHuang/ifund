"""基金列表蓝图：筛选/排序/分页、搜索、详情、同步、预设 CRUD。"""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app import db as database
from app.fund.crud import fund_crud
from app.fund.fetch import fetcher
from app.fund_holdings.crud import holdings_crud
from app.fund_nav.crud import nav_crud

bp = Blueprint("fund", __name__, url_prefix="/api/fund")

# 排序白名单（全为 fund_details 列）
ALLOWED_SORT_FIELDS = {
    "scale", "return_ytd", "drawdown_ytd", "sharpe_3y", "sharpe_1y",
    "max_drawdown_3y", "position_stock",
}
# 区间筛选字段（detail 列）
RANGE_FIELDS = {
    "scale", "sharpe_3y", "sharpe_1y", "drawdown_3y", "drawdown_1y",
    "position_stock", "position_bond", "position_other",
    "return_ytd", "max_drawdown_3y", "max_drawdown_1y",
}
# 比较条件允许的操作符 → DSL 前缀
COMPARE_OPS = {"gt", "gte", "lt", "lte", "eq", "neq"}


def _csv(value: str) -> str:
    """把逗号分隔串去空后重新拼接。"""
    return ",".join(x.strip() for x in value.split(",") if x.strip())


def _parse_range_params(args, detail_params: list) -> None:
    for field in RANGE_FIELDS:
        vmin = args.get(f"{field}_min")
        vmax = args.get(f"{field}_max")
        if vmin not in (None, ""):
            detail_params.append((field, f"gte.{vmin}"))
        if vmax not in (None, ""):
            detail_params.append((field, f"lte.{vmax}"))


def _parse_conditions(args, detail_params: list) -> None:
    """解析 conds 参数：``field:op:value`` 逗号分隔，同字段多条件即 AND 交集。"""
    raw = args.get("conds")
    if not raw:
        return
    for item in raw.split(","):
        parts = item.split(":")
        if len(parts) != 3:
            continue
        field, op, value = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if field in RANGE_FIELDS and op in COMPARE_OPS and value != "":
            detail_params.append((field, f"{op}.{value}"))


def parse_fund_filter_args(args):
    """把 query 参数解析成 (fund_params, detail_params)。"""
    fund_params: list = []
    detail_params: list = []
    keyword = args.get("keyword")
    if keyword:
        fund_params.append(("or", f"(code.ilike.*{keyword}*,name.ilike.*{keyword}*)"))
    name_contains = args.get("name_contains")
    if name_contains:
        fund_params.append(("name", f"ilike.*{name_contains}*"))
    fund_types = args.get("fund_types")
    if fund_types and _csv(fund_types):
        fund_params.append(("type", f"in.({_csv(fund_types)})"))
    exclude_codes = args.get("exclude_codes")
    if exclude_codes and _csv(exclude_codes):
        fund_params.append(("code", f"not.in.({_csv(exclude_codes)})"))
    # name_excludes 支持重复参数或单个逗号分隔串
    for raw in args.getlist("name_excludes"):
        for kw in raw.split(","):
            if kw.strip():
                fund_params.append(("name", f"not.ilike.*{kw.strip()}*"))
    _parse_range_params(args, detail_params)
    _parse_conditions(args, detail_params)
    return fund_params, detail_params


def _parse_order_by(order_by):
    if not order_by:
        return []
    parts = []
    for seg in order_by.split(","):
        field, _, direction = seg.partition(":")
        field = field.strip()
        if field in ALLOWED_SORT_FIELDS:
            parts.append((field, (direction or "asc").strip().lower()))
    return parts


def _attach_holdings(items: list) -> None:
    # 同时附加股票与债券前十大，前端按 holding_type 分两列展示
    for item in items:
        item["holdings"] = (holdings_crud.top_holdings(item["code"], "stock")
                            + holdings_crud.top_holdings(item["code"], "bond"))


def _attach_nav(items: list) -> None:
    for item in items:
        item["nav_series"] = nav_crud.recent_series(item["code"])


def _current_user_id() -> int:
    user = database.select_one("users", {"username": f"eq.{get_jwt_identity()}"})
    return user["id"] if user else 0


def _owned_preset(preset_id: int, user_id: int):
    """返回属于该用户的预设行；不属于（或不存在）则 None。"""
    return database.select_one("query_presets", {
        "id": f"eq.{preset_id}", "user_id": f"eq.{user_id}",
    })


@bp.get("/list")
def list_funds():
    """筛选 + 排序 + 分页。"""
    args = request.args
    fund_params, detail_params = parse_fund_filter_args(args)
    skip = int(args.get("skip", 0))
    limit = int(args.get("limit", 20))
    order_parts = _parse_order_by(args.get("order_by"))
    total, items = database.list_funds_with_details(fund_params, detail_params, skip, limit, order_parts)
    if args.get("attach_holdings") in ("1", "true", "True"):
        _attach_holdings(items)
    if args.get("attach_nav") in ("1", "true", "True"):
        _attach_nav(items)
    return jsonify({"total": total, "items": items})


@bp.get("/search")
def search():
    """按名称/代码模糊搜索。"""
    keyword = request.args.get("keyword", "")
    if not keyword:
        return jsonify([])
    rows = database.select("funds", [
        ("or", f"(code.ilike.*{keyword}*,name.ilike.*{keyword}*)"),
        ("limit", 50),
    ])
    return jsonify(rows)


@bp.get("/search_by_codes")
def search_by_codes():
    """按代码集合批量取。"""
    codes = _csv(request.args.get("codes", ""))
    if not codes:
        return jsonify([])
    return jsonify(database.select("funds", {"code": f"in.({codes})"}))


@bp.get("/types")
def types():
    """基金分类列表。"""
    return jsonify(database.select("fund_types", {"order": "type_name.asc"}))


@bp.post("/sync")
@jwt_required()
def sync():
    """同步全量替换基金名单（请求线程内拉取，无 worker）。"""
    funds = fetcher.fetch_all_funds()
    fund_crud.replace_all(funds)
    return jsonify({"count": len(funds)})


@bp.get("/presets")
@jwt_required()
def list_presets():
    """当前用户的查询预设列表。"""
    rows = database.select("query_presets", {
        "user_id": f"eq.{_current_user_id()}", "order": "created_at.desc",
    })
    for row in rows:
        row["filters"] = json.loads(row.get("filters_json") or "{}")
    return jsonify(rows)


@bp.post("/presets")
@jwt_required()
def create_preset():
    """新建或按 (user, name) 覆盖预设。"""
    user_id = _current_user_id()
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not name:
        return jsonify({"detail": "name required"}), 400
    filters_json = json.dumps(data.get("filters", {}), ensure_ascii=False)
    existing = database.select_one("query_presets", {
        "user_id": f"eq.{user_id}", "name": f"eq.{name}",
    })
    if existing:
        database.update("query_presets", {"id": existing["id"]}, {"filters_json": filters_json})
        return jsonify({"id": existing["id"]})
    row = database.insert("query_presets", {
        "user_id": user_id, "name": name, "filters_json": filters_json,
    })
    return jsonify({"id": row["id"]}), 201


@bp.put("/presets/<int:preset_id>")
@jwt_required()
def update_preset(preset_id):
    """更新预设（按 owner 隔离）。"""
    user_id = _current_user_id()
    data = request.get_json(silent=True) or {}
    fields = {}
    if "name" in data:
        fields["name"] = data["name"]
    if "filters" in data:
        fields["filters_json"] = json.dumps(data["filters"], ensure_ascii=False)
    if fields:
        database.update("query_presets", {"id": preset_id, "user_id": user_id}, fields)
    return jsonify({"id": preset_id})


@bp.delete("/presets/<int:preset_id>")
@jwt_required()
def delete_preset(preset_id):
    """删除预设（按 owner 隔离）。"""
    database.delete("query_presets", {"id": preset_id, "user_id": _current_user_id()})
    return jsonify({"ok": True})


@bp.get("/presets/<int:preset_id>/snapshot")
@jwt_required()
def get_snapshot(preset_id):
    """取该预设的镜像快照（每预设仅留最新一份；无则返回 snapshot=None）。"""
    user_id = _current_user_id()
    if not _owned_preset(preset_id, user_id):
        return jsonify({"detail": "preset not found"}), 404
    row = database.select_one("fund_snapshots", {
        "user_id": f"eq.{user_id}", "preset_id": f"eq.{preset_id}",
    })
    if not row:
        return jsonify({"snapshot": None})
    return jsonify({"snapshot": {
        "id": row["id"],
        "created_at": row.get("created_at"),
        "fund_count": row.get("fund_count", 0),
        "items": json.loads(row.get("items_json") or "[]"),
    }})


@bp.post("/presets/<int:preset_id>/snapshot")
@jwt_required()
def save_snapshot(preset_id):
    """把当前筛选结果存为该预设的镜像（替换旧镜像）。"""
    user_id = _current_user_id()
    if not _owned_preset(preset_id, user_id):
        return jsonify({"detail": "preset not found"}), 404
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    items_json = json.dumps(items, ensure_ascii=False)
    database.delete("fund_snapshots", {"user_id": user_id, "preset_id": preset_id})
    row = database.insert("fund_snapshots", {
        "user_id": user_id, "preset_id": preset_id,
        "items_json": items_json, "fund_count": len(items),
    })
    return jsonify({"id": row["id"], "fund_count": len(items)}), 201


@bp.get("/<code>/nav")
def get_nav(code):
    """某基金最近 N 个交易日的累计净值序列（带日期），供净值走势图。

    返回 ``{items:[{date, nav}]}``，按时间升序；前端按区间切片绘图。
    """
    try:
        limit = int(request.args.get("limit", 750))
    except (TypeError, ValueError):
        limit = 750
    limit = max(2, min(limit, 2000))
    series = nav_crud.recent_series_dated(code, limit)
    return jsonify({"items": [{"date": d, "nav": v} for d, v in series]})


@bp.get("/<code>")
def get_one(code):
    """单只基金 + 详情（详情列扁平化合并）+ top-10 股票持仓。"""
    fund = database.select_one("funds", {"code": f"eq.{code}"})
    if not fund:
        return jsonify({"detail": "not found"}), 404
    detail = database.select_one("fund_details", {"fund_code": f"eq.{code}"}) or {}
    merged = {**detail, **fund}  # funds 的 code/name 优先，其余取详情列
    merged["holdings"] = holdings_crud.top_holdings(code)
    return jsonify(merged)
