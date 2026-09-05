"""异步拉取模块的共享 HTTP 层：任务防重、目标解析、终止（含分布式）、蓝图工厂。

三个 worker 模块（fund_detail / fund_holdings / fund_nav）的 4 个端点结构一致，
统一由 ``make_task_blueprint`` 生成，避免重复代码。
"""
from __future__ import annotations

import re
import requests
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app import db as database
from app.common import sync_launcher, task_runner


def get_running(task_type: str):
    """返回该 task_type 当前 running 任务（无则 None）。"""
    return database.select_one("fetch_tasks", {
        "task_type": f"eq.{task_type}", "status": "eq.running",
    })


def resolve_targets(args, json_body=None):
    """解析筛选条件 → (codes, fund_types)。

    codes 显式给出则优先（支持 JSON body 数组、query string 逗号分隔的 6 位代码）；
    keyword 仅在形如基金代码（6 位数字）时当作单码快速拉取——否则它是"名称/代码
    搜索词"（如 "C"），必须走下方筛选条件路径，绝不能把搜索词本身当代码传给 worker，
    否则会去拉代码为 "C" 的基金而必失败；
    按筛选条件查 list_funds_with_details 得 codes 子集；
    都没有则返回 ([], []) 表示全量。
    """
    # 1) JSON body 里的 codes（前端 POST 时传的）
    if json_body:
        codes_raw = json_body.get("codes")
        if codes_raw:
            if isinstance(codes_raw, list):
                return [c.strip() for c in codes_raw if c.strip()], []
            return [c.strip() for c in str(codes_raw).split(",") if c.strip()], []

    # 2) URL query string 里的 codes（显式代码列表）
    codes_raw = args.get("codes")
    if codes_raw:
        segs = [c.strip() for c in codes_raw.split(",") if c.strip()]
        if segs and all(re.fullmatch(r"\d{6}", s) for s in segs):
            return segs, []

    # 3) keyword：仅在纯 6 位数字（含逗号分隔）时视为代码；其余视为搜索词走筛选路径
    kw = (args.get("keyword") or "").strip()
    if kw:
        kw_segs = [k.strip() for k in kw.split(",") if k.strip()]
        if kw_segs and all(re.fullmatch(r"\d{6}", k) for k in kw_segs):
            return kw_segs, []

    # 4) 筛选条件（需要 request.args 对象以支持 getlist）
    # pylint: disable=import-outside-toplevel
    from app.fund.api.router import parse_fund_filter_args
    fund_params, detail_params = parse_fund_filter_args(args)
    if fund_params or detail_params:
        _, items = database.list_funds_with_details(fund_params, detail_params, 0, 100000, [])
        return [i["code"] for i in items], []
    return [], []


def terminate_flow(module_name: str, task_id: int):
    """本地终止 + 跨机转发 + 置 status=terminated。"""
    task = database.select_one("fetch_tasks", {"id": f"eq.{task_id}"})
    if not task:
        return jsonify({"detail": "not found"}), 404
    task_runner.terminate_task(task_id)
    executor_ip = task.get("executor_ip") or ""
    if executor_ip and executor_ip != task_runner.get_local_ip():
        try:
            requests.post(
                f"http://{executor_ip}:8000/api/{module_name}/terminate",
                json={"pid": task.get("executor_thread")}, timeout=5,
            )
        except requests.RequestException:
            pass
    database.update("fetch_tasks", {"id": task_id}, {"status": "terminated"})
    return jsonify({"ok": True})


def remote_terminate():
    """远程终止接收端：按 PID 杀进程并把对应 running 任务置 terminated。"""
    data = request.get_json(silent=True) or {}
    pid = str(data.get("pid", ""))
    if pid:
        task_runner.terminate_by_pid(pid)
        task = database.select_one("fetch_tasks", {
            "executor_thread": f"eq.{pid}", "status": "eq.running",
        })
        if task:
            database.update("fetch_tasks", {"id": task["id"]}, {"status": "terminated"})
    return jsonify({"ok": True})


def make_task_blueprint(module_name: str, task_type: str, worker_script: str) -> Blueprint:
    """生成含 4 个标准端点的蓝图：/sync、/task/running、/task/<id>/terminate、/terminate。"""
    blueprint = Blueprint(module_name, __name__, url_prefix=f"/api/{module_name}")

    @blueprint.post("/sync")
    @jwt_required()
    def sync():
        # 快速路径：已有 running 任务则直接拒绝（友好提示）
        if get_running(task_type):
            return jsonify({"detail": "已有运行中的任务"}), 409
        codes, fund_types = resolve_targets(request.args, request.get_json(silent=True))
        try:
            # 唯一索引兜底：并发竞态下第二个 insert 会触发 UniqueViolation
            task_id = sync_launcher.start_sync_task(
                task_type, worker_script, codes=codes, fund_types=fund_types,
            )
        except database.UniqueViolation:
            return jsonify({"detail": "已有运行中的任务"}), 409
        return jsonify({"task_id": task_id})

    @blueprint.get("/task/running")
    def task_running():
        return jsonify(get_running(task_type))

    @blueprint.post("/task/<int:task_id>/terminate")
    @jwt_required()
    def terminate(task_id):
        return terminate_flow(module_name, task_id)

    @blueprint.post("/terminate")
    def remote():
        return remote_terminate()

    return blueprint
