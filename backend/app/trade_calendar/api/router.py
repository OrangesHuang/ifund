"""交易日历蓝图：同步拉取（无 worker 子进程）。"""
from __future__ import annotations

import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app import db as database
from app.trade_calendar.crud import calendar_crud
from app.trade_calendar.fetch import fetcher

bp = Blueprint("trade_calendar", __name__, url_prefix="/api/trade_calendar")

TASK_TYPE = "fetch_trade_calendar"


@bp.get("/dates")
def get_dates():
    """列出交易日，可选 ?year= 过滤。"""
    year = request.args.get("year")
    return jsonify({"dates": calendar_crud.list_dates(year)})


@bp.get("/task/latest")
def latest_task():
    """最近一次同步任务状态。"""
    row = database.select_one("fetch_tasks", {
        "task_type": f"eq.{TASK_TYPE}", "order": "id.desc",
    })
    return jsonify(row or {})


@bp.post("/sync")
@jwt_required()
def sync():
    """同步拉取交易日历并全量替换。"""
    now = datetime.datetime.now().isoformat()
    task = database.insert("fetch_tasks", {
        "task_type": TASK_TYPE, "status": "running",
        "created_at": now, "updated_at": now,
    })
    task_id = task["id"]
    try:
        dates = fetcher.fetch_trade_dates()
        count = calendar_crud.replace_all(dates)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        database.update("fetch_tasks", {"id": task_id}, {
            "status": "failed", "updated_at": datetime.datetime.now().isoformat(),
        })
        return jsonify({"error": str(exc), "task_id": task_id}), 500
    database.update("fetch_tasks", {"id": task_id}, {
        "status": "done", "target_count": count, "success_count": count,
        "current_count": count, "updated_at": datetime.datetime.now().isoformat(),
    })
    return jsonify({"task_id": task_id, "count": count})
