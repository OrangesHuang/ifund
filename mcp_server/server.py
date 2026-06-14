"""iFund MCP 服务器：把后端 HTTP API 以 MCP 工具形式暴露给本机 agent（如 OpenClaw）。

认证模型
--------
agent 只持有一枚长期个人访问令牌（PAT，环境变量 ``IFUND_API_TOKEN``）。
本服务器在首次调用时用 PAT 经 ``/api/auth/token/exchange`` 换取短期 JWT 并缓存；
JWT 过期（业务端点返回 401）时自动重新换取并重试一次。
PAT 绑定具体用户，因此每个 agent 看到的数据与该用户在网页端一致（多用户隔离）。

配置（环境变量）
----------------
- ``IFUND_BASE_URL``  后端地址，默认 ``http://127.0.0.1:8000``
- ``IFUND_API_TOKEN`` 个人访问令牌（在网页端「个人访问令牌」处创建，明文仅显示一次）

以 stdio 方式运行：``python server.py``（OpenClaw 等 MCP 客户端据此拉起子进程）。

注意：本文件刻意不使用 ``from __future__ import annotations``——FastMCP 需要在运行时
读取真实的类型注解对象（字符串化注解会让其工具注册失败），且本服务运行于 Python 3.12，
``list[str] | None`` 等语法原生可用。
"""
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = os.environ.get("IFUND_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API_TOKEN = os.environ.get("IFUND_API_TOKEN", "")
TIMEOUT = 30.0

mcp = FastMCP("ifund")

# 本机直连后端，禁用系统代理（trust_env=False，避免 all_proxy/SOCKS 干扰）
_CLIENT = httpx.Client(trust_env=False, timeout=TIMEOUT)

# 短期 JWT 缓存（首次/过期时由 PAT 换取）
_STATE: dict[str, str] = {"jwt": ""}


def _exchange_jwt() -> str:
    """用 PAT 换取短期 JWT 并写入缓存；PAT 缺失/无效时抛错。"""
    if not API_TOKEN:
        raise RuntimeError("未配置 IFUND_API_TOKEN（个人访问令牌）")
    resp = _CLIENT.post(
        f"{BASE_URL}/api/auth/token/exchange",
        headers={"Authorization": f"Bearer {API_TOKEN}"},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"PAT 换取 JWT 失败（{resp.status_code}）：{resp.text}")
    token = resp.json().get("access_token", "")
    _STATE["jwt"] = token
    return token


def _call(method: str, path: str, *, params: dict | None = None,
          json_body: dict | None = None) -> Any:
    """调用后端 API：自动带 JWT，遇 401 用 PAT 重新换取并重试一次。

    2xx 返回解析后的 JSON；其余返回 ``{"_error": <状态码>, "detail": ...}``，
    便于把 409（已有运行中任务）等业务状态原样透传给 agent。
    """
    if not _STATE["jwt"]:
        _exchange_jwt()

    def _do() -> httpx.Response:
        return _CLIENT.request(
            method, f"{BASE_URL}{path}",
            headers={"Authorization": f"Bearer {_STATE['jwt']}"},
            params=params, json=json_body,
        )

    resp = _do()
    if resp.status_code == 401:
        _exchange_jwt()
        resp = _do()
    if 200 <= resp.status_code < 300:
        return resp.json()
    detail: Any = resp.text
    try:
        detail = resp.json().get("detail", detail)
    except (ValueError, AttributeError):
        pass
    return {"_error": resp.status_code, "detail": detail}


def _conds_to_conditions(conds: list[str]) -> list[dict]:
    """把 ``["field:op:value", ...]`` 转成 filters 里的 conditions 数组。"""
    out: list[dict] = []
    for raw in conds or []:
        parts = raw.split(":")
        if len(parts) == 3:
            out.append({"field": parts[0].strip(), "op": parts[1].strip(),
                        "value": parts[2].strip()})
    return out


def _build_list_params(keyword: str, name_contains: str, fund_types: list[str],
                       conds: list[str]) -> dict[str, str]:
    """把筛选入参拼成 /fund/list 的 query 参数。"""
    params: dict[str, str] = {}
    if keyword:
        params["keyword"] = keyword
    if name_contains:
        params["name_contains"] = name_contains
    if fund_types:
        params["fund_types"] = ",".join(fund_types)
    if conds:
        params["conds"] = ",".join(conds)
    return params


# ---------------------------------------------------------------- 只读工具

@mcp.tool()
def search_funds(keyword: str, limit: int = 20) -> Any:
    """按代码或名称模糊搜索基金（轻量，返回 code/name/type 等基础字段）。

    keyword: 关键词（基金代码或名称片段）。limit: 最多返回条数。
    """
    rows = _call("GET", "/api/fund/search", params={"keyword": keyword})
    if isinstance(rows, list):
        return rows[:limit]
    return rows


@mcp.tool()
def screen_funds(keyword: str = "", name_contains: str = "",
                 fund_types: list[str] | None = None,
                 conds: list[str] | None = None,
                 order_by: str = "", limit: int = 50,
                 with_nav: bool = False) -> Any:
    """按条件筛选基金并返回带详情指标的列表。

    keyword: 代码/名称关键词；name_contains: 名称包含；fund_types: 基金分类列表；
    conds: 数值条件列表，元素形如 ``"sharpe_3y:gte:1"``（字段:操作符:值，
    操作符 gt/gte/lt/lte/eq/neq；可用字段含 scale/return_ytd/sharpe_3y/sharpe_1y/
    drawdown_3y/drawdown_1y/max_drawdown_3y/max_drawdown_1y/position_stock 等）；
    order_by: 排序，形如 ``"scale:desc"``；limit: 返回条数；with_nav: 是否附带净值序列。
    """
    params = _build_list_params(keyword, name_contains, fund_types or [], conds or [])
    params["skip"] = "0"
    params["limit"] = str(limit)
    if order_by:
        params["order_by"] = order_by
    if with_nav:
        params["attach_nav"] = "1"
    return _call("GET", "/api/fund/list", params=params)


@mcp.tool()
def get_fund_detail(code: str) -> Any:
    """取单只基金的完整详情（含各期收益/回撤/夏普指标与前十大持仓）。

    code: 基金代码。
    """
    return _call("GET", f"/api/fund/{code}")


@mcp.tool()
def list_fund_types() -> Any:
    """列出全部基金分类（type_name / category）。"""
    return _call("GET", "/api/fund/types")


@mcp.tool()
def get_trade_calendar(year: str = "") -> Any:
    """取交易日列表，可选按年份过滤。

    year: 形如 ``"2025"``，留空返回全部。
    """
    params = {"year": year} if year else None
    return _call("GET", "/api/trade_calendar/dates", params=params)


@mcp.tool()
def list_presets() -> Any:
    """列出当前用户保存的筛选预设（含 id / name / filters）。"""
    return _call("GET", "/api/fund/presets")


@mcp.tool()
def get_snapshot(preset_id: int) -> Any:
    """取某预设的镜像快照（点位时间保存的筛选结果；无则 snapshot=None）。

    preset_id: 预设 id。
    """
    return _call("GET", f"/api/fund/presets/{preset_id}/snapshot")


# ---------------------------------------------------------------- 写入工具

@mcp.tool()
def create_preset(name: str, keyword: str = "", name_contains: str = "",
                  fund_types: list[str] | None = None,
                  conds: list[str] | None = None) -> Any:
    """新建（或按同名覆盖）一个筛选预设。

    name: 预设名；其余参数同 screen_funds 的筛选条件，将一并保存。
    """
    filters: dict[str, Any] = {}
    if keyword:
        filters["keyword"] = keyword
    if name_contains:
        filters["name_contains"] = name_contains
    if fund_types:
        filters["fund_types"] = fund_types
    conditions = _conds_to_conditions(conds or [])
    if conditions:
        filters["conditions"] = conditions
    return _call("POST", "/api/fund/presets", json_body={"name": name, "filters": filters})


@mcp.tool()
def delete_preset(preset_id: int) -> Any:
    """删除一个筛选预设（仅能删除当前用户自己的）。

    preset_id: 预设 id。
    """
    return _call("DELETE", f"/api/fund/presets/{preset_id}")


@mcp.tool()
def save_snapshot(preset_id: int, limit: int = 500) -> Any:
    """按预设当前条件重新筛选，并把结果存为该预设的镜像快照（替换旧镜像）。

    preset_id: 预设 id；limit: 最多镜像多少只基金。
    """
    presets = _call("GET", "/api/fund/presets")
    if not isinstance(presets, list):
        return presets
    preset = next((p for p in presets if p.get("id") == preset_id), None)
    if not preset:
        return {"_error": 404, "detail": "preset not found"}
    filters = preset.get("filters") or {}
    params = _build_list_params(
        filters.get("keyword", ""), filters.get("name_contains", ""),
        filters.get("fund_types") or [],
        [f"{c['field']}:{c['op']}:{c['value']}" for c in filters.get("conditions") or []],
    )
    params["skip"] = "0"
    params["limit"] = str(limit)
    result = _call("GET", "/api/fund/list", params=params)
    if not isinstance(result, dict) or "items" not in result:
        return result
    return _call("POST", f"/api/fund/presets/{preset_id}/snapshot",
                 json_body={"items": result["items"]})


@mcp.tool()
def fetch_fund_data(module: str, codes: list[str] | None = None,
                    keyword: str = "", fund_types: list[str] | None = None,
                    conds: list[str] | None = None) -> Any:
    """【会写库】发起一次数据拉取任务（详情/持仓/净值），后台异步执行。

    module: 取 ``fund_detail`` / ``fund_holdings`` / ``fund_nav`` 之一。
    codes: 指定基金代码列表（优先）；否则按 keyword/fund_types/conds 选出目标；
    都不给则对全量发起。同类任务同时只允许一个，已有运行中会返回 409 提示。
    返回 ``{"task_id": ...}`` 或 ``{"_error": 409, "detail": "已有运行中的任务"}``。
    """
    if module not in ("fund_detail", "fund_holdings", "fund_nav"):
        return {"_error": 400, "detail": "module 必须是 fund_detail/fund_holdings/fund_nav"}
    params: dict[str, str] = {}
    if codes:
        params["codes"] = ",".join(codes)
    else:
        params = _build_list_params(keyword, "", fund_types or [], conds or [])
    return _call("POST", f"/api/{module}/sync", params=params)


if __name__ == "__main__":
    mcp.run()
