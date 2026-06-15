"""仓位编排：②聚类的簇列表 + 各簇 TOP1 净值 → 景气度/乖离/目标权重/推荐 + 组合净值走势。"""
from __future__ import annotations

from datetime import date

from app.position.algo import deviation, prosperity, recommend, weights
from app.stock_industry.crud import industry_crud

MIN_NAV_POINTS = 60      # 低于此点数视为净值不足（景气度会退化为中性）
RISK_FREE_ANNUAL = 0.0   # 夏普比率的无风险利率（简化为 0，即「收益/波动」口径）


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


def _lookthrough(valid: list[dict], weights_list: list[float],
                 holdings_by_code: dict[str, list[dict]], ind_idx: dict) -> dict:
    """把各簇代表基金的前十大股票按目标权重穿透累加，看底层实际持有哪些股票/行业。

    组合对某股票的暴露% = ∑(基金目标权重 × 该基金中此股占净值比例)。
    重叠（被 ≥2 只基金持有）越多，说明底层越集中、代表基金相关性越高。
    再把股票暴露按行业聚合，看组合整体行业占比。仅基于可见的前十大持仓，非完整持仓。
    """
    agg: dict[str, dict] = {}
    covered = 0
    for cluster, w in zip(valid, weights_list):
        code = cluster["funds"][0]["code"]
        holdings = holdings_by_code.get(code, [])
        if not holdings or w <= 0:
            continue
        covered += 1
        fund_name = cluster["funds"][0]["name"]
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

    # 行业聚合：组合穿透后各行业的总仓位
    ind_agg: dict[str, dict] = {}
    for s in stocks:
        slot = ind_agg.setdefault(s["industry"], {
            "industry": s["industry"], "exposure": 0.0, "stock_count": 0,
        })
        slot["exposure"] += s["exposure"]
        slot["stock_count"] += 1
    industries = sorted(ind_agg.values(), key=lambda x: x["exposure"], reverse=True)
    for x in industries:
        x["exposure"] = round(x["exposure"], 2)

    return {"funds_covered": covered, "total_stocks": len(stocks),
            "overlap_stocks": overlap, "visible_position": visible,
            "stocks": stocks, "industries": industries}


def run(clusters: list[dict], nav_by_code: dict[str, list[tuple[str, float]]],
        holdings_by_code: dict[str, list[dict]] | None = None,
        detail_by_code: dict[str, dict] | None = None) -> dict:
    """clusters：cluster pipeline 的簇列表；nav_by_code：code→``(trade_date, 累计净值)`` 升序。

    holdings_by_code：code→前十大股票持仓（穿透分析用）；detail_by_code：code→fund_details 行（补回撤/夏普）。
    每簇取综合分第一的基金（``funds[0]``）作为代表，算景气度+乖离+目标权重+推荐。
    返回 ``{"items": [...], "portfolio": {...}, "lookthrough": {...}, "meta": {...}}``，items 按目标权重降序。
    """
    holdings_by_code = holdings_by_code or {}
    detail_by_code = detail_by_code or {}
    ind_idx = industry_crud.industry_index()   # 股票代码 → 行业映射，给前十大持仓标行业
    valid = [c for c in clusters if c.get("funds")]
    dated_list = [nav_by_code.get(c["funds"][0]["code"], []) for c in valid]
    series_list = [[nav for _, nav in dated] for dated in dated_list]

    pros = prosperity.compute(series_list)
    devs = [deviation.deviation(s) for s in series_list]
    target = weights.target_weights([p["total"] for p in pros], devs)
    base = round(1.0 / len(valid), 4) if valid else 0.0

    items, missing = [], []
    for i, cluster in enumerate(valid):
        fund = cluster["funds"][0]
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
    lookthrough = _lookthrough(valid, target, holdings_by_code, ind_idx)

    return {"items": items,
            "portfolio": {"curve": curve, "max_drawdown": max_drawdown, **stats},
            "lookthrough": lookthrough,
            "meta": {"n_clusters": len(valid), "base_weight": base, "nav_missing": missing}}
