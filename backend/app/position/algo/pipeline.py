"""仓位编排：②聚类的簇列表 + 各簇 TOP5 候选净值/持仓 → 选基金 + 行业感知权重 + 推荐 + 组合净值走势。

每簇不再硬取 TOP1，而是从综合分前 TOPK 的候选里选 1 只（``optimize.select_funds``），
在保证质量的前提下尽量降低底层行业集中度；再对选中基金做行业感知的权重再分配
（``optimize.rebalance_weights``，单一行业穿透占比上限 cap），缓解多簇同涨同跌。
"""
from __future__ import annotations

from datetime import date

from app.position.algo import deviation, optimize, prosperity, recommend
from app.stock_industry.crud import industry_crud

MIN_NAV_POINTS = 60      # 低于此点数视为净值不足（动量强度会退化为中性）
RISK_FREE_ANNUAL = 0.0   # 夏普比率的无风险利率（简化为 0，即「收益/波动」口径）


def _industry_vector(holdings: list[dict], ind_idx: dict) -> dict[str, float]:
    """前十大股票按申万行业聚合占净值比例，得到该基金的行业向量（行业→合计%）。"""
    vec: dict[str, float] = {}
    for h in holdings:
        scode = (h.get("asset_code") or "").strip()
        if not scode:
            continue
        lab = industry_crud.label_of(scode, ind_idx)
        vec[lab] = vec.get(lab, 0.0) + (h.get("hold_ratio") or 0.0)
    return vec


def _portfolio_curve(dated_list: list[list[tuple[str, float]]],
                     weights_list: list[float]) -> tuple[list[dict], float]:
    """按权重合成组合净值与回撤曲线。

    各代表基金净值绝对值不同，不能直接加权；先在共同起点 rebase 到 1.0，
    再按归一化权重加权，组合净值从 1.0 起步。回撤 = 当前相对历史峰值的跌幅。

    Args:
        dated_list: 每只代表基金的 ``(trade_date, 累计净值)`` 升序列表
        weights_list: 对应目标权重（∑≈1）

    Returns:
        (``[{"date","nav","drawdown"}]``, 最大回撤)；drawdown 为负百分比（underwater）。
    """
    # 仅保留有净值且权重为正的基金，转成 date→nav 便于按日对齐
    funds = [(dict(dated), w)
             for dated, w in zip(dated_list, weights_list) if dated and w > 0]
    if not funds:
        return [], 0.0

    # 取所有基金共有的交易日（交集），确保每天都能完整加权
    common = set(funds[0][0])
    for nav_map, _ in funds[1:]:
        common &= nav_map.keys()
    dates = sorted(common)
    if len(dates) < 2:
        return [], 0.0

    total_w = sum(w for _, w in funds)
    bases = [nav_map[dates[0]] for nav_map, _ in funds]  # 各基金共同起点净值

    curve: list[dict] = []
    peak = max_dd = 0.0
    for day in dates:
        nav = sum((nav_map[day] / base) * (w / total_w)
                  for (nav_map, w), base in zip(funds, bases))
        peak = max(peak, nav)
        dd = (nav - peak) / peak if peak > 0 else 0.0   # ≤0
        max_dd = min(max_dd, dd)
        curve.append({"date": day, "nav": round(nav, 4), "drawdown": round(dd * 100, 2)})
    return curve, round(-max_dd, 4)


def _portfolio_stats(curve: list[dict]) -> dict:
    """从组合净值曲线算年化收益/年化波动/夏普比率。

    用逐点简单收益率，按实际日期跨度推断「每年观测数」做年化（兼容日频/周频）。
    夏普 = 年化超额收益 / 年化波动，无风险利率见 ``RISK_FREE_ANNUAL``。
    """
    if len(curve) < 2:
        return {"annual_return": 0.0, "annual_vol": 0.0, "sharpe": 0.0}

    navs = [p["nav"] for p in curve]
    rets = [navs[i] / navs[i - 1] - 1 for i in range(1, len(navs))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1) if len(rets) > 1 else 0.0
    std = var ** 0.5

    span_days = (date.fromisoformat(curve[-1]["date"]) - date.fromisoformat(curve[0]["date"])).days or 1
    periods_per_year = len(rets) * 365.25 / span_days
    annual_return = (navs[-1] / navs[0]) ** (365.25 / span_days) - 1
    annual_vol = std * periods_per_year ** 0.5
    sharpe = (annual_return - RISK_FREE_ANNUAL) / annual_vol if annual_vol > 0 else 0.0
    return {"annual_return": round(annual_return, 4),
            "annual_vol": round(annual_vol, 4),
            "sharpe": round(sharpe, 2)}


def _rebase_curve(dated: list[tuple[str, float]]) -> list[dict]:
    """把代表基金净值序列 rebase 到起点 1.0，供前端画迷你走势图（hover 看收益率）。"""
    if not dated:
        return []
    base = dated[0][1]
    if not base:
        return []
    return [{"date": d, "nav": round(v / base, 4)} for d, v in dated]


def _lookthrough(selected: list[dict], weights_list: list[float],
                 holdings_by_code: dict[str, list[dict]], ind_idx: dict) -> dict:
    """把各簇选中基金的前十大股票按目标权重穿透累加，看底层实际持有哪些股票/行业。

    组合对某股票的暴露% = ∑(基金目标权重 × 该基金中此股占净值比例)。
    重叠（被 ≥2 只基金持有）越多，说明底层越集中、代表基金相关性越高。
    再把股票暴露按行业聚合，看组合整体行业占比。仅基于可见的前十大持仓，非完整持仓。

    selected：各簇选中基金 ``{"code","name"}`` 列表，与 weights_list 一一对应。
    """
    agg: dict[str, dict] = {}
    covered = 0
    for fund, w in zip(selected, weights_list):
        code = fund["code"]
        holdings = holdings_by_code.get(code, [])
        if not holdings or w <= 0:
            continue
        covered += 1
        fund_name = fund["name"]
        for h in holdings:
            scode = (h.get("asset_code") or "").strip()
            if not scode:
                continue
            ratio = h.get("hold_ratio") or 0.0
            slot = agg.setdefault(scode, {
                "code": scode, "name": h.get("asset_name") or scode,
                "industry": industry_crud.label_of(scode, ind_idx),
                "exposure": 0.0, "funds": [],
            })
            slot["exposure"] += w * ratio          # w 小数 × 占净值% → 组合中该股 %
            slot["funds"].append({"name": fund_name, "ratio": round(ratio, 2)})

    stocks = sorted(agg.values(), key=lambda s: s["exposure"], reverse=True)
    for s in stocks:
        s["exposure"] = round(s["exposure"], 2)
        s["fund_count"] = len(s["funds"])
    overlap = sum(1 for s in stocks if s["fund_count"] >= 2)
    visible = round(sum(s["exposure"] for s in stocks), 2)

    # 行业聚合：组合穿透后各行业的总仓位 + 该行业下的股票（按穿透仓位降序）
    ind_agg: dict[str, dict] = {}
    for s in stocks:   # stocks 已按 exposure 降序，行业内 stocks 也保持降序
        slot = ind_agg.setdefault(s["industry"], {
            "industry": s["industry"], "exposure": 0.0, "stock_count": 0, "stocks": [],
        })
        slot["exposure"] += s["exposure"]
        slot["stock_count"] += 1
        slot["stocks"].append({"name": s["name"], "exposure": s["exposure"]})
    industries = sorted(ind_agg.values(), key=lambda x: x["exposure"], reverse=True)
    for x in industries:
        x["exposure"] = round(x["exposure"], 2)

    return {"funds_covered": covered, "total_stocks": len(stocks),
            "overlap_stocks": overlap, "visible_position": visible,
            "stocks": stocks, "industries": industries}


def select_representatives(clusters: list[dict], holdings_by_code: dict[str, list[dict]],
                           ind_idx: dict, cap: float):
    """每簇从综合分前 ``optimize.TOPK`` 候选里选 1 只代表基金（行业感知去重）。

    单一出处：``run``（仓位建议）与回测端点都用它，保证「回测的基金集合 = 用户看到的建议」。
    返回 ``(valid, cands, choice, selected)``：valid=有基金的簇；cands=各簇 TOP{TOPK} 候选
    （含行业向量 vec）；choice[i]=选中候选下标（0=TOP1）；selected[i]=选中基金（簇内 fund dict）。
    """
    valid = [c for c in clusters if c.get("funds")]
    if not valid:
        return [], [], [], []
    cands = [[{"code": f["code"], "name": f["name"], "score": f["score"],
               "vec": _industry_vector(holdings_by_code.get(f["code"], []), ind_idx)}
              for f in c["funds"][:optimize.TOPK]]
             for c in valid]
    choice = optimize.select_funds(cands, cap)
    selected = [valid[i]["funds"][choice[i]] for i in range(len(valid))]
    return valid, cands, choice, selected


def run(clusters: list[dict], nav_by_code: dict[str, list[tuple[str, float]]],
        holdings_by_code: dict[str, list[dict]] | None = None,
        detail_by_code: dict[str, dict] | None = None,
        cap: float = optimize.DEFAULT_CAP) -> dict:
    """clusters：cluster pipeline 的簇列表；nav_by_code/holdings_by_code 须覆盖各簇 TOP{TOPK} 候选。

    nav_by_code：code→``(trade_date, 累计净值)`` 升序；holdings_by_code：code→前十大股票持仓；
    detail_by_code：code→fund_details 行（补回撤/夏普）。cap：单一行业穿透占比上限（均衡强度）。

    流程：每簇从综合分前 ``optimize.TOPK`` 候选里选 1 只（行业去重），以等权（1/N）为基准，
    再做行业感知再分配（上限 cap）降相关。返回 ``{"items","portfolio","lookthrough","meta"}``，
    items 按目标权重降序；每项 fund 含 ``cluster_rank``（1=TOP1）标注是否替代了 TOP1。
    """
    holdings_by_code = holdings_by_code or {}
    detail_by_code = detail_by_code or {}
    ind_idx = industry_crud.industry_index()   # 股票代码 → 行业映射，给前十大持仓标行业
    valid = [c for c in clusters if c.get("funds")]
    if not valid:
        return {"items": [], "portfolio": {"curve": [], "max_drawdown": 0.0},
                "lookthrough": {"funds_covered": 0, "total_stocks": 0, "overlap_stocks": 0,
                                "visible_position": 0.0, "stocks": [], "industries": []},
                "meta": {"n_clusters": 0, "base_weight": 0.0, "nav_missing": [], "cap": cap}}

    # 每簇构造 TOP{TOPK} 候选（含行业向量），交给 optimize 选基金（与回测端点同一出处）
    valid, cands, choice, selected = select_representatives(clusters, holdings_by_code, ind_idx, cap)

    dated_list = [nav_by_code.get(f["code"], []) for f in selected]
    series_list = [[nav for _, nav in dated] for dated in dated_list]

    # 动量强度 + 乖离：walk-forward 回测显示动量调权略跑输等权，故不再参与调权，
    # 仅作每簇的观察指标随建议一并展示（追涨择时、仅供参考）。
    pros = prosperity.compute(series_list)
    devs = [deviation.deviation(s) for s in series_list]
    # 权重回归等权基准（1/N）；再做行业感知再分配，仅为把最大单一行业穿透占比压到
    # ≤ cap 做最小调整（降相关），故各簇权重在等权附近，只因行业拥挤度被微调。
    base = round(1.0 / len(valid), 4)
    base_weights = [1.0 / len(valid)] * len(valid)
    vecs = [cands[i][choice[i]]["vec"] for i in range(len(valid))]
    target = optimize.rebalance_weights(base_weights, vecs, cap)

    items, missing = [], []
    for i, cluster in enumerate(valid):
        fund = selected[i]
        detail = detail_by_code.get(fund["code"], {})
        points = len(series_list[i])
        if points < MIN_NAV_POINTS:
            missing.append(fund["code"])
        holdings = [{
            "code": (h.get("asset_code") or "").strip(),
            "name": h.get("asset_name") or h.get("asset_code") or "",
            "ratio": round(h.get("hold_ratio") or 0.0, 2),
            "industry": industry_crud.label_of((h.get("asset_code") or "").strip(), ind_idx),
        } for h in holdings_by_code.get(fund["code"], [])]
        items.append({
            "cluster_id": cluster["cluster_id"],
            "cluster_name": cluster["name"],
            "top_industries": cluster.get("top_industries", []),
            "fund_count": cluster.get("fund_count", 0),
            "fund": {
                "code": fund["code"], "name": fund["name"], "score": fund["score"],
                "sharpe_3y": fund["sharpe_3y"], "scale": fund["scale"],
                "cluster_rank": choice[i] + 1,   # 1=TOP1；>1 表示为降相关性选了次优基金
                "sharpe_1y": detail.get("sharpe_1y"),
                "max_drawdown_3y": detail.get("max_drawdown_3y"),
                "max_drawdown_1y": detail.get("max_drawdown_1y"),
                "return_ytd": detail.get("return_ytd"),
                "drawdown_ytd": detail.get("drawdown_ytd"),
                "position_stock": detail.get("position_stock"),
            },
            "nav_points": points,
            "nav_curve": _rebase_curve(dated_list[i]),
            "holdings": holdings,
            "prosperity": pros[i],
            "deviation": devs[i],
            "base_weight": base,
            "weight": target[i],
            "recommendation": recommend.recommend(
                pros[i]["total"], devs[i]["combined"], target[i], base),
        })
    items.sort(key=lambda x: x["weight"], reverse=True)

    # 按目标权重合成组合净值与回撤走势（rebase 到 1.0 后加权），并算年化/夏普
    curve, max_drawdown = _portfolio_curve(dated_list, target)
    stats = _portfolio_stats(curve)
    lookthrough = _lookthrough(selected, target, holdings_by_code, ind_idx)
    swapped = sum(1 for r in choice if r != 0)

    # 数据时效：净值截止日（选中基金净值序列最后一天的最大值）+ 持仓季度（最新）
    nav_dates = [dated[-1][0] for dated in dated_list if dated]
    nav_as_of = max(nav_dates) if nav_dates else None
    quarters = [h["quarter"] for f in selected
                for h in holdings_by_code.get(f["code"], []) if h.get("quarter")]
    holdings_quarter = max(quarters) if quarters else None

    return {"items": items,
            "portfolio": {"curve": curve, "max_drawdown": max_drawdown, **stats},
            "lookthrough": lookthrough,
            "meta": {"n_clusters": len(valid), "base_weight": base,
                     "nav_missing": missing, "cap": cap, "funds_swapped": swapped,
                     "nav_as_of": nav_as_of, "holdings_quarter": holdings_quarter}}
