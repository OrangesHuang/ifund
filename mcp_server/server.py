"""iFund MCP 服务器：把后端 HTTP API 以 MCP 工具形式暴露给本机 agent（如 OpenClaw）。

四大能力组（与网页端一致，按 PAT 绑定的用户隔离）：
  1) 基础：基金查询/详情、数据拉取（详情/持仓/净值/交易日历/行业映射）、拉取任务查询与终止。
  2) 条件预设：查询/保存/更新/删除 + 镜像快照的查询与更新。
  3) 组合分析：行业暴露聚类、簇级仓位建议（均衡强度 松/中/紧）。
  4) 实盘：实盘 CRUD、初始持仓录入/调整、交易记录 CRUD、实际持仓（含所属赛道）查询、
     基于关联预设生成调仓操作指南（四个可调旋钮均有默认值）、并可一键把建议落成交易记录。

认证模型
--------
agent 只持有一枚长期个人访问令牌（PAT，环境变量 ``IFUND_API_TOKEN``）。
本服务器在首次调用时用 PAT 经 ``/api/auth/token/exchange`` 换取短期 JWT 并缓存；
JWT 过期（业务端点返回 401）时自动重新换取并重试一次。
PAT 绑定具体用户，因此每个 agent 看到的数据与该用户在网页端一致（多用户隔离）。

配置（环境变量）
----------------
- ``IFUND_BASE_URL``  后端地址，默认 ``http://127.0.0.1:8000``
- ``IFUND_API_TOKEN`` 个人访问令牌（在网页端「访问令牌」处创建，明文仅显示一次）

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

# 均衡强度 → 单一行业穿透占比上限 cap（越小越分散）。默认「紧」。
_BALANCE_CAP = {
    "松": 0.22, "loose": 0.22,
    "中": 0.18, "medium": 0.18,
    "紧": 0.14, "tight": 0.14,
}
_DEFAULT_CAP = 0.14


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
                       conds: list[str],
                       name_excludes: list[str] | None = None) -> dict[str, str]:
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
    if name_excludes:
        params["name_excludes"] = ",".join(name_excludes)
    return params


def _resolve_cap(balance: str, cap: float | None) -> float:
    """均衡强度档位/原始 cap → 数值 cap（默认「紧」0.14）。"""
    if cap is not None:
        try:
            return float(cap)
        except (TypeError, ValueError):
            return _DEFAULT_CAP
    return _BALANCE_CAP.get((balance or "").strip().lower(),
                            _BALANCE_CAP.get((balance or "").strip(), _DEFAULT_CAP))


def _industry_index() -> dict[str, dict]:
    """全量拉取股票→行业映射，建 ``stock_code → 行（含 sw_l3/stock_name）`` 索引。

    穿透按申万三级聚合用；list 接口不支持按代码批量查，故一次性分页拉全量（page_size 500）
    在本地建索引，避免逐股查询的 N×10 次往返。
    """
    idx: dict[str, dict] = {}
    page = 1
    while True:
        res = _call("GET", "/api/stock_industry/list",
                    params={"page": str(page), "page_size": "500"})
        rows = res.get("items") if isinstance(res, dict) else None
        if not isinstance(rows, list) or not rows:
            break
        for r in rows:
            code = r.get("stock_code")
            if code:
                idx[code] = r
        if len(rows) < 500:
            break
        page += 1
    return idx


# ════════════════════════════════════════════════ 1) 基础能力

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
                 name_excludes: list[str] | None = None,
                 order_by: str = "", limit: int = 50,
                 with_nav: bool = False,
                 with_holdings: bool = False) -> Any:
    """按条件筛选基金并返回带详情指标的列表。

    keyword: 代码/名称关键词；name_contains: 名称包含；fund_types: 基金分类列表；
    conds: 数值条件列表，元素形如 ``"sharpe_3y:gte:1"``（字段:操作符:值，
    操作符 gt/gte/lt/lte/eq/neq；可用字段含 scale/return_ytd/sharpe_3y/sharpe_1y/
    drawdown_3y/drawdown_1y/max_drawdown_3y/max_drawdown_1y/position_stock 等）；
    name_excludes: 名称排除关键词列表；
    order_by: 排序，形如 ``"scale:desc"``；limit: 返回条数；
    with_nav: 是否附带净值序列；with_holdings: 是否附带前十大持仓。
    """
    params = _build_list_params(keyword, name_contains, fund_types or [],
                                conds or [], name_excludes)
    params["skip"] = "0"
    params["limit"] = str(limit)
    if order_by:
        params["order_by"] = order_by
    if with_nav:
        params["attach_nav"] = "1"
    if with_holdings:
        params["attach_holdings"] = "1"
    return _call("GET", "/api/fund/list", params=params)


@mcp.tool()
def get_fund_detail(code: str) -> Any:
    """取单只基金的完整详情（含各期收益/回撤/夏普指标与前十大持仓）。

    code: 基金代码。
    """
    return _call("GET", f"/api/fund/{code}")


@mcp.tool()
def list_fund_types() -> Any:
    """列出全部基金分类（type_name / category），用于 screen_funds 的 fund_types 取值。"""
    return _call("GET", "/api/fund/types")


@mcp.tool()
def get_trade_calendar(year: str = "") -> Any:
    """查询交易日列表（可选按年份过滤）。用于确定交易记录该填哪个交易日。

    year: 形如 ``"2025"``，留空返回全部。仅查询，不触发拉取；拉取用 fetch_data。
    """
    params = {"year": year} if year else None
    return _call("GET", "/api/trade_calendar/dates", params=params)


_FETCH_TARGETS = {
    "fund_detail":   ("POST", "/api/fund_detail/sync", "filter"),
    "fund_holdings": ("POST", "/api/fund_holdings/sync", "filter"),
    "fund_nav":      ("POST", "/api/fund_nav/sync", "filter"),
    "trade_calendar": ("POST", "/api/trade_calendar/sync", "none"),
    "industry_sw":   ("POST", "/api/stock_industry/sync/sw", "codes"),
    "industry_em":   ("POST", "/api/stock_industry/sync/em", "none"),
}


@mcp.tool()
def fetch_data(target: str, codes: list[str] | None = None,
               keyword: str = "", fund_types: list[str] | None = None,
               conds: list[str] | None = None) -> Any:
    """【会写库】发起一次后台数据拉取任务。统一入口，按 target 分派。

    target 取值：
    - ``fund_detail`` / ``fund_holdings`` / ``fund_nav``：基金详情/前十大持仓/净值。
      可用 codes 指定基金代码列表（优先），否则按 keyword/fund_types/conds 选目标，
      都不给则对全量发起。
    - ``trade_calendar``：拉取交易日历并全量替换（同步执行，立即返回 count，无需轮询）。
    - ``industry_sw``：申万三级行业映射采集（legulegu）。codes 可选=只重采指定**行业代码**。
    - ``industry_em``：东财兜底行业映射采集（补申万未覆盖的持仓股票，主要港股）。

    同类任务同时只允许一个，已有运行中会返回 ``{"_error":409,...}``。异步任务返回
    ``{"task_id":...}``，用 list_tasks 查进度、terminate_task 终止。
    """
    spec = _FETCH_TARGETS.get(target)
    if not spec:
        return {"_error": 400,
                "detail": f"target 必须是 {', '.join(_FETCH_TARGETS)} 之一"}
    method, path, mode = spec
    params: dict[str, str] = {}
    if mode == "filter":
        if codes:
            params["codes"] = ",".join(codes)
        else:
            params = _build_list_params(keyword, "", fund_types or [], conds or [])
    elif mode == "codes" and codes:
        params["codes"] = ",".join(codes)
    return _call(method, path, params=params or None)


_TASK_MODULES = ["fund_detail", "fund_holdings", "fund_nav"]


@mcp.tool()
def list_tasks() -> Any:
    """查询各拉取任务的运行状态（汇总所有模块）。

    返回 ``{"running": [{module, task_id, ...}], "trade_calendar_latest": {...}}``。
    running 列表里每项带 ``module``（fund_detail/fund_holdings/fund_nav/stock_industry）
    与 ``task_id``，可直接传给 terminate_task。trade_calendar 为同步任务，仅给最近一次状态。
    """
    running: list[dict] = []
    for mod in _TASK_MODULES:
        row = _call("GET", f"/api/{mod}/task/running")
        if isinstance(row, dict) and row.get("id"):
            running.append({"module": mod, "task_id": row["id"], **row})
    for source in ("sw", "em"):
        row = _call("GET", "/api/stock_industry/task/running", params={"type": source})
        if isinstance(row, dict) and row.get("id"):
            running.append({"module": "stock_industry", "source": source,
                            "task_id": row["id"], **row})
    cal = _call("GET", "/api/trade_calendar/task/latest")
    return {"running": running, "trade_calendar_latest": cal}


@mcp.tool()
def terminate_task(task_id: int, module: str) -> Any:
    """终止一个正在运行的拉取任务。

    task_id / module 取自 list_tasks 的 running 项。
    module 取 ``fund_detail`` / ``fund_holdings`` / ``fund_nav`` / ``stock_industry``。
    （trade_calendar 为同步任务，无需也无法终止。）
    """
    if module not in (*_TASK_MODULES, "stock_industry"):
        return {"_error": 400,
                "detail": "module 必须是 fund_detail/fund_holdings/fund_nav/stock_industry"}
    return _call("POST", f"/api/{module}/task/{task_id}/terminate")


@mcp.tool()
def get_industry_coverage() -> Any:
    """股票→行业映射的覆盖率统计（聚类标签的基础；聚类前可据此判断是否需补采）。

    分 A股/港股/海外统计申万三级与东财行业的覆盖数量与比例，含申万三级行业总数。
    覆盖不足会影响聚类质量；可用 fetch_data(industry_sw/industry_em) 补采。
    """
    return _call("GET", "/api/stock_industry/stats")


@mcp.tool()
def list_stock_industry(market: str = "", label: str = "", status: str = "",
                        keyword: str = "", page: int = 1, page_size: int = 50) -> Any:
    """分页查询持仓股票的行业映射明细（代码/名称/市场/申万一二三级/东财行业）。

    用 ``status="uncovered"`` 可定位「行业不存在/未覆盖」的股票，再针对性补采。
    market: ``A`` / ``HK`` / ``OTHER``；label: 行业名关键词；
    status: ``covered`` / ``uncovered`` / 空=全部；keyword: 股票代码或名称片段；
    page/page_size: 分页（page_size 上限 500）。
    """
    params = {"page": str(page), "page_size": str(page_size)}
    if market:
        params["market"] = market
    if label:
        params["label"] = label
    if status:
        params["status"] = status
    if keyword:
        params["keyword"] = keyword
    return _call("GET", "/api/stock_industry/list", params=params)


# ════════════════════════════════════════════════ 2) 条件预设

@mcp.tool()
def list_presets() -> Any:
    """列出当前用户保存的筛选预设（含 id / name / filters）。"""
    return _call("GET", "/api/fund/presets")


@mcp.tool()
def create_preset(name: str, keyword: str = "", name_contains: str = "",
                  fund_types: list[str] | None = None,
                  conds: list[str] | None = None,
                  name_excludes: list[str] | None = None) -> Any:
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
    if name_excludes:
        filters["name_excludes"] = name_excludes
    conditions = _conds_to_conditions(conds or [])
    if conditions:
        filters["conditions"] = conditions
    return _call("POST", "/api/fund/presets", json_body={"name": name, "filters": filters})


@mcp.tool()
def update_preset(preset_id: int, name: str = "", keyword: str = "",
                  name_contains: str = "", fund_types: list[str] | None = None,
                  conds: list[str] | None = None,
                  name_excludes: list[str] | None = None,
                  replace_filters: bool = False) -> Any:
    """更新一个筛选预设的名称和/或筛选条件（仅本人）。

    name: 非空则改名；其余筛选参数同 create_preset。
    replace_filters: 默认 False 只改名、不动既有筛选条件；置 True 时用传入的筛选参数
    **整体替换** filters（未传的筛选参数视为清空）。仅改名场景保持 False 即可。
    """
    body: dict[str, Any] = {}
    if name:
        body["name"] = name
    if replace_filters:
        filters: dict[str, Any] = {}
        if keyword:
            filters["keyword"] = keyword
        if name_contains:
            filters["name_contains"] = name_contains
        if fund_types:
            filters["fund_types"] = fund_types
        if name_excludes:
            filters["name_excludes"] = name_excludes
        conditions = _conds_to_conditions(conds or [])
        if conditions:
            filters["conditions"] = conditions
        body["filters"] = filters
    if not body:
        return {"_error": 400, "detail": "未提供 name，且 replace_filters=False，无可更新内容"}
    return _call("PUT", f"/api/fund/presets/{preset_id}", json_body=body)


@mcp.tool()
def delete_preset(preset_id: int) -> Any:
    """删除一个筛选预设（仅能删除当前用户自己的）。preset_id: 预设 id。"""
    return _call("DELETE", f"/api/fund/presets/{preset_id}")


@mcp.tool()
def get_snapshot(preset_id: int) -> Any:
    """取某预设的镜像快照（点位时间保存的筛选结果；无则 snapshot=None）。preset_id: 预设 id。"""
    return _call("GET", f"/api/fund/presets/{preset_id}/snapshot")


@mcp.tool()
def save_snapshot(preset_id: int, limit: int = 500) -> Any:
    """按预设当前条件重新筛选，并把结果存为该预设的镜像快照（更新镜像，替换旧镜像）。

    会自动附带前十大持仓（attach_holdings=1），确保镜像可用于聚类/仓位/对账。
    聚类与仓位建议、实盘对账都基于此镜像，更新预设条件后应重新 save_snapshot。
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
        filters.get("name_excludes") or [],
    )
    params["skip"] = "0"
    params["limit"] = str(limit)
    params["attach_holdings"] = "1"
    result = _call("GET", "/api/fund/list", params=params)
    if not isinstance(result, dict) or "items" not in result:
        return result
    return _call("POST", f"/api/fund/presets/{preset_id}/snapshot",
                 json_body={"items": result["items"]})


# ════════════════════════════════════════════════ 3) 组合分析

@mcp.tool()
def run_clustering(preset_id: int) -> Any:
    """对某预设的镜像快照做行业暴露聚类（按持仓把口味相近的基金聚成簇）。

    需先用 save_snapshot 为该预设保存镜像。每个簇返回三层股票视角：行业暴露（占比平权）、
    实际资金暴露（规模加权重仓市值）、代表股票（含重叠基金数），以及簇内基金（按临时综合分
    降序，附前十大持仓与申万三级）。无镜像或可聚类基金 < 3 时返回 ``{"clusters": null, "reason": ...}``。
    若结果中行业大量缺失，先用 get_industry_coverage 检查、fetch_data(industry_*) 补采后重跑。
    """
    return _call("POST", "/api/cluster/run", json_body={"preset_id": preset_id})


@mcp.tool()
def run_position(preset_id: int, balance: str = "紧",
                 cap: float | None = None) -> Any:
    """基于预设镜像的聚类结果，给出簇级仓位建议（每簇只配综合分第一的代表基金）。

    对每簇 TOP1 基金用其净值估计景气度（动量/风险调整/广度/一致性四因子）与乖离度，
    合成目标权重（等权基准 × 景气因子 × 乖离因子 → 截断后归一到 100%），并给出加码/标配/减码
    推荐与理由。无镜像或可聚类基金 < 3 时返回 ``{"items": null, "reason": ...}``。

    balance: 均衡强度档位——``松``(单行业上限22%,更集中)/``中``(18%)/``紧``(14%,默认,更分散)。
    cap: 直接给单一行业穿透占比上限（0.10~0.30），给了则覆盖 balance。
    """
    return _call("POST", "/api/position/run",
                 json_body={"preset_id": preset_id, "cap": _resolve_cap(balance, cap)})


# ════════════════════════════════════════════════ 4) 实盘

@mcp.tool()
def list_portfolios() -> Any:
    """列出当前用户的全部实盘（自有 + 代管），含 id / name / preset_id（关联的仓位建议）。

    其余实盘工具都需要 portfolio_id；先用本工具拿到 id。系统保证至少有一个默认实盘。
    """
    return _call("GET", "/api/reconcile/portfolios")


@mcp.tool()
def create_portfolio(name: str, preset_id: int | None = None) -> Any:
    """新建一个实盘。name: 实盘名；preset_id: 可选，关联的仓位建议（预设）id。"""
    body: dict[str, Any] = {"name": name}
    if preset_id is not None:
        body["preset_id"] = preset_id
    return _call("POST", "/api/reconcile/portfolios", json_body=body)


@mcp.tool()
def update_portfolio(portfolio_id: int, name: str = "",
                     preset_id: int | None = None,
                     unlink_preset: bool = False) -> Any:
    """修改实盘：改名 和/或 关联的仓位建议（预设）。

    name: 非空则改名；preset_id: 给出则关联到该预设；unlink_preset=True 取消关联（置空）。
    preset_id 与 unlink_preset 二选一。
    """
    body: dict[str, Any] = {}
    if name:
        body["name"] = name
    if unlink_preset:
        body["preset_id"] = None
    elif preset_id is not None:
        body["preset_id"] = preset_id
    if not body:
        return {"_error": 400, "detail": "无可更新内容（需提供 name 或 preset_id/unlink_preset）"}
    return _call("PATCH", f"/api/reconcile/portfolios/{portfolio_id}", json_body=body)


@mcp.tool()
def delete_portfolio(portfolio_id: int) -> Any:
    """删除一个实盘及其全部持仓与交易记录（仅本人）。portfolio_id: 实盘 id。"""
    return _call("DELETE", f"/api/reconcile/portfolios/{portfolio_id}")


@mcp.tool()
def get_holdings(portfolio_id: int) -> Any:
    """查询某实盘的实际持仓（初始快照 + 交易记录综合算出），并附每只基金的所属赛道（簇）。

    每只基金返回：fund_code/fund_name、market_value（当前市值=份额×最新单位净值）、shares、
    cost（移动平均成本）、pnl（浮动盈亏）、latest_nav/nav_date、valuation_ok（false=无净值退化估值），
    以及 cluster（若实盘已关联预设：``{seq:簇序号, label:申万三级行业拼接, industries:[{label,ratio}]}``，
    赛道外为 null）。返回 ``{portfolio_id, has_preset, holdings:[...], total_market_value, total_pnl}``。
    """
    res = _call("GET", "/api/reconcile/holdings", params={"portfolio_id": portfolio_id})
    holdings = res.get("items", []) if isinstance(res, dict) else res
    if not isinstance(holdings, list):
        return res
    clu = _call("GET", "/api/reconcile/holdings/clusters",
                params={"portfolio_id": portfolio_id})
    has_preset = bool(clu.get("has_preset")) if isinstance(clu, dict) else False
    cmap = clu.get("map", {}) if isinstance(clu, dict) else {}
    cmeta = clu.get("clusters", {}) if isinstance(clu, dict) else {}
    for h in holdings:
        cid = cmap.get(h.get("fund_code"))
        h["cluster"] = cmeta.get(str(cid)) if cid is not None else None
    total_mv = round(sum(h.get("market_value") or 0 for h in holdings), 2)
    total_pnl = round(sum(h.get("pnl") or 0 for h in holdings
                          if h.get("pnl") is not None), 2)
    return {"portfolio_id": portfolio_id, "has_preset": has_preset,
            "holdings": holdings, "total_market_value": total_mv, "total_pnl": total_pnl}


@mcp.tool()
def set_holding(portfolio_id: int, market_value: float,
                fund_name: str = "", fund_code: str = "",
                profit: float | None = None) -> Any:
    """录入/调整一只「初始持仓快照」（按金额 + 收益记账，不含交易明细）。

    用于首次建仓的单只录入，或单独调整某只的原始初始仓位（按 fund_code/名称 upsert）。
    fund_name 或 fund_code 至少给一个（只给名称会自动反查代码；App 里常只看得到 C 类名称）。
    market_value: 该基金总金额（元）；profit: 持有收益（元，可负，可省）。
    收益→成本换算：成本 = 市值 − 收益（成本仅展示，不参与调仓决策）。
    注意：这是「初始快照」；建仓后的加/减/转仓请用 add_txn 记成交易记录。
    """
    body: dict[str, Any] = {"portfolio_id": portfolio_id, "market_value": market_value}
    if fund_code:
        body["fund_code"] = fund_code
    if fund_name:
        body["fund_name"] = fund_name
    if profit is not None:
        body["cost"] = market_value - profit
    return _call("POST", "/api/reconcile/holdings", json_body=body)


@mcp.tool()
def import_holdings(portfolio_id: int, rows: list[dict]) -> Any:
    """批量录入初始持仓快照（**全量替换**该实盘的所有快照持仓）。用于首次成批建仓。

    rows 每项：``{fund_name 或 fund_code, market_value, profit?}``。
    profit=持有收益（元，可负，可省）；内部换算成本=市值−收益。只给名称会自动反查代码。
    返回 ``{count: 写入条数}``。后续单只调整用 set_holding，移除单只用 remove_holding。
    """
    out: list[dict] = []
    for r in rows or []:
        row: dict[str, Any] = {"market_value": r.get("market_value")}
        if r.get("fund_code"):
            row["fund_code"] = r["fund_code"]
        if r.get("fund_name"):
            row["fund_name"] = r["fund_name"]
        if r.get("profit") is not None:
            try:
                row["cost"] = float(r["market_value"]) - float(r["profit"])
            except (TypeError, ValueError):
                pass
        out.append(row)
    return _call("POST", "/api/reconcile/holdings/bulk",
                 json_body={"portfolio_id": portfolio_id, "rows": out})


@mcp.tool()
def remove_holding(portfolio_id: int, fund_code: str) -> Any:
    """从初始持仓快照里删除一只基金。portfolio_id / fund_code。"""
    return _call("DELETE", f"/api/reconcile/holdings/{fund_code}",
                 params={"portfolio_id": portfolio_id})


@mcp.tool()
def list_txns(portfolio_id: int) -> Any:
    """列出某实盘的全部交易记录（买入/卖出，转仓为共享 transfer_id 的一买一卖；按交易日升序）。"""
    return _call("GET", "/api/reconcile/txns", params={"portfolio_id": portfolio_id})


@mcp.tool()
def add_txn(portfolio_id: int, kind: str, trade_date: str, amount: float,
            fund_name: str = "", fund_code: str = "",
            from_name: str = "", from_code: str = "",
            to_name: str = "", to_code: str = "", note: str = "") -> Any:
    """记一笔交易（建仓后的加/减/转仓）。按交易日锁定当日单位净值并折算份额。

    kind=``buy``(买入/加仓) 或 ``sell``(卖出/减仓)：给 fund_name 或 fund_code。
    kind=``transfer``(转仓)：给 from_*(转出) 与 to_*(转入)；拆成共享 transfer_id 的一卖一买。
    trade_date: ``YYYY-MM-DD``（须为交易日，可用 get_trade_calendar 确认）；amount: 金额（元，>0）。
    只给名称会自动反查代码。
    """
    body: dict[str, Any] = {"portfolio_id": portfolio_id, "kind": kind,
                            "trade_date": trade_date, "amount": amount, "note": note}
    if kind == "transfer":
        body.update({"from_code": from_code, "from_name": from_name,
                     "to_code": to_code, "to_name": to_name})
    else:
        body.update({"fund_code": fund_code, "fund_name": fund_name})
    return _call("POST", "/api/reconcile/txns", json_body=body)


@mcp.tool()
def update_txn(portfolio_id: int, txn_id: int, kind: str = "",
               trade_date: str = "", amount: float | None = None,
               fund_name: str = "", fund_code: str = "") -> Any:
    """修改一条买入/卖出交易记录（只改传入的字段）。改了金额/日期/基金会按新交易日重折份额。

    txn_id 取自 list_txns。转仓的两条需各自按其方向（buy/sell）分别修改。
    kind: ``buy``/``sell``；其余字段留空表示不改。
    """
    body: dict[str, Any] = {"portfolio_id": portfolio_id}
    if kind:
        body["kind"] = kind
    if trade_date:
        body["trade_date"] = trade_date
    if amount is not None:
        body["amount"] = amount
    if fund_code:
        body["fund_code"] = fund_code
    if fund_name:
        body["fund_name"] = fund_name
    return _call("PATCH", f"/api/reconcile/txns/{txn_id}", json_body=body)


@mcp.tool()
def delete_txn(portfolio_id: int, txn_id: int) -> Any:
    """删除一条交易记录。txn_id 取自 list_txns。转仓的配对另一条需另删。"""
    return _call("DELETE", f"/api/reconcile/txns/{txn_id}",
                 params={"portfolio_id": portfolio_id})


@mcp.tool()
def run_reconcile(portfolio_id: int, balance: str = "紧", cap: float | None = None,
                  band: float = 0.03, sell_outside: bool = False,
                  trim_overflow: bool = True, preset_id: int | None = None) -> Any:
    """基于实盘关联的仓位建议生成「调仓操作指南」：把目标比例落到真实持仓，按赛道对齐算每笔加/减/建/清。

    返回 ``{rows, summary, meta, transfers}``：rows=按赛道的目标vs实际与建议动作；
    transfers=具体「从X转Y元到Z」的换仓配对（可直接传给 apply_rebalance 落账）；
    summary 含追加现金反推等。现金由系统反推（"加满还差多少"），不用手填。

    四个可调旋钮（均有默认值）：
    - balance 均衡强度：``松``(22%)/``中``(18%)/``紧``(14%,默认)；或用 cap 直接给上限(0.10~0.30)。
    - band 缓冲带：默认 0.03（盘子的 3 个百分点，抗噪；越大越少触发小额调仓）。
    - sell_outside 赛道外是否可卖：默认 False（不动赛道外持仓）。
    - trim_overflow 赛道内超配是否可减：默认 True（允许把超配的赛道减下来腾资金）。
    preset_id: 可临时覆盖实盘关联的预设。
    """
    body: dict[str, Any] = {
        "portfolio_id": portfolio_id, "cap": _resolve_cap(balance, cap),
        "band": band, "sell_outside": sell_outside, "trim_overflow": trim_overflow,
    }
    if preset_id is not None:
        body["preset_id"] = preset_id
    return _call("POST", "/api/reconcile/run", json_body=body)


@mcp.tool()
def apply_rebalance(portfolio_id: int, transfers: list[dict],
                    trade_date: str = "") -> Any:
    """把 run_reconcile 给出的换仓建议一键落成真实交易记录（建议→账本）。

    transfers: 直接传 run_reconcile 返回的 ``transfers`` 数组
    （每项含 from_code/from_name/to_code/to_name/amount）。纯加仓只有 to_*、纯减仓只有 from_*。
    trade_date: ``YYYY-MM-DD``，缺省取最近交易日。返回 ``{count, trade_date}``。
    落账前建议先与用户确认指南内容。
    """
    body: dict[str, Any] = {"portfolio_id": portfolio_id, "transfers": transfers}
    if trade_date:
        body["trade_date"] = trade_date
    return _call("POST", "/api/reconcile/txns/from-rebalance", json_body=body)


@mcp.tool()
def get_portfolio_penetration(portfolio_id: int) -> Any:
    """计算实盘的底层持仓穿透：前十大持仓 → 按申万三级行业聚合，看组合真实押在哪些行业/股票。

    遍历该实盘所有有效持仓（market_value>0），对每只基金按其在组合中的权重，把前十大股票
    持仓穿透累加：``某股票穿透仓位 = 基金权重 × 该股在基金中的占净值比例``；再按申万三级（sw_l3）
    聚合。同一股票被多只基金持有会累加并记录各来源基金。无法映射到申万三级的股票归入
    ``uncovered_stocks``（可用 fetch_data(industry_*) 补采后重算）。

    复用 get_holdings / get_fund_detail / list_stock_industry 三个能力的同源后端数据。
    返回 ``{portfolio_id, total_market_value, visible_market_value, penetration, uncovered_stocks}``：
    - total_market_value：组合有效持仓总市值；visible_market_value：能取到前十大持仓的基金市值合计。
    - penetration：按 total_ratio 降序的行业列表，每项 ``{industry, total_ratio(占整个组合的小数,
      如 0.0885=8.85%), visible_ratio(占已映射行业之和), stock_count, stocks:[{stock_code, stock_name,
      ratio(该股穿透占比), funds:[{fund_code, fund_name, fund_weight, stock_ratio_in_fund(%)}]}]}``。
    - uncovered_stocks：未映射到申万三级的股票（含穿透占比），按 ratio 降序。
    """
    res = _call("GET", "/api/reconcile/holdings", params={"portfolio_id": portfolio_id})
    holdings = res.get("items") if isinstance(res, dict) else res
    if not isinstance(holdings, list):
        return res
    funds = [h for h in holdings if (h.get("market_value") or 0) > 0]
    total_mv = sum(h.get("market_value") or 0 for h in funds)
    empty = {"portfolio_id": portfolio_id, "total_market_value": round(total_mv, 2),
             "visible_market_value": 0.0, "penetration": [], "uncovered_stocks": []}
    if total_mv <= 0:
        return empty

    idx = _industry_index()
    stock_agg: dict[str, dict] = {}
    visible_mv = 0.0
    for h in funds:
        fcode = h.get("fund_code")
        weight = (h.get("market_value") or 0) / total_mv
        detail = _call("GET", f"/api/fund/{fcode}")
        rows = detail.get("holdings") if isinstance(detail, dict) else None
        stocks = [s for s in (rows or [])
                  if s.get("holding_type") == "stock" and (s.get("asset_code") or "").strip()]
        if not stocks:
            continue
        visible_mv += h.get("market_value") or 0
        for s in stocks:
            scode = s["asset_code"].strip()
            hold_ratio = s.get("hold_ratio") or 0.0       # 占净值比例（百分比，如 8.5）
            slot = stock_agg.setdefault(scode, {
                "stock_code": scode, "stock_name": s.get("asset_name") or scode,
                "ratio": 0.0, "funds": []})
            slot["ratio"] += weight * hold_ratio / 100.0   # 穿透占比（相对整个组合的小数）
            slot["funds"].append({
                "fund_code": fcode, "fund_name": h.get("fund_name") or fcode,
                "fund_weight": round(weight, 6),
                "stock_ratio_in_fund": round(hold_ratio, 2)})

    industry_agg: dict[str, dict] = {}
    uncovered: list[dict] = []
    for s in stock_agg.values():
        s["ratio"] = round(s["ratio"], 6)
        s["funds"].sort(key=lambda f: f["stock_ratio_in_fund"], reverse=True)
        sw_l3 = (idx.get(s["stock_code"]) or {}).get("sw_l3")
        if not sw_l3:
            uncovered.append({"stock_code": s["stock_code"],
                              "stock_name": s["stock_name"], "ratio": s["ratio"]})
            continue
        slot = industry_agg.setdefault(sw_l3, {"industry": sw_l3, "total_ratio": 0.0, "stocks": []})
        slot["total_ratio"] += s["ratio"]
        slot["stocks"].append(s)

    covered_sum = sum(g["total_ratio"] for g in industry_agg.values())
    penetration = []
    for g in industry_agg.values():
        g["stocks"].sort(key=lambda x: x["ratio"], reverse=True)
        penetration.append({
            "industry": g["industry"],
            "total_ratio": round(g["total_ratio"], 6),
            "visible_ratio": round(g["total_ratio"] / covered_sum, 6) if covered_sum else 0.0,
            "stock_count": len(g["stocks"]),
            "stocks": g["stocks"],
        })
    penetration.sort(key=lambda x: x["total_ratio"], reverse=True)
    uncovered.sort(key=lambda x: x["ratio"], reverse=True)

    return {"portfolio_id": portfolio_id,
            "total_market_value": round(total_mv, 2),
            "visible_market_value": round(visible_mv, 2),
            "penetration": penetration,
            "uncovered_stocks": uncovered}


if __name__ == "__main__":
    mcp.run()
