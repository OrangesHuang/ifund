"""仓位编排：②聚类的簇列表 + 各簇 TOP1 净值 → 景气度/乖离/目标权重/推荐 + 组合净值走势。"""
from __future__ import annotations

import math

from app.position.algo import deviation, prosperity, recommend, weights

MIN_NAV_POINTS = 60      # 低于此点数视为净值不足（景气度会退化为中性）


def _compute_portfolio_nav(series_list: list[list[float]], weights_list: list[float]) -> tuple[list[float], float]:
  """计算组合净值和最大回撤。

  Args:
    series_list: 各基金的净值序列（升序）
    weights_list: 各基金的目标权重

  Returns:
    (组合净值序列, 最大回撤)
  """
  if not series_list or all(not s for s in series_list):
    return [], 0.0

  # 找最长序列，用最新 nav 点数对齐
  max_len = max(len(s) for s in series_list) if series_list else 0
  if max_len == 0:
    return [], 0.0

  portfolio = []
  for i in range(max_len):
    weighted_nav = 0.0
    for j, series in enumerate(series_list):
      # 对齐：用最新点后向填充
      idx = max(0, i - (max_len - len(series)))
      weighted_nav += series[idx] * weights_list[j]
    portfolio.append(weighted_nav)

  # 计算最大回撤
  max_drawdown = 0.0
  running_max = portfolio[0]
  for nav in portfolio:
    running_max = max(running_max, nav)
    drawdown = (running_max - nav) / running_max if running_max > 0 else 0
    max_drawdown = max(max_drawdown, drawdown)

  return portfolio, max_drawdown


def run(clusters: list[dict], nav_by_code: dict[str, list[float]]) -> dict:
    """clusters：cluster pipeline 的簇列表；nav_by_code：code→累计净值序列（升序）。

    每簇取综合分第一的基金（``funds[0]``）作为代表，算景气度+乖离+目标权重+推荐。
    返回 ``{"items": [...], "meta": {...}}``，items 按目标权重降序。
    """
    valid = [c for c in clusters if c.get("funds")]
    series_list = [nav_by_code.get(c["funds"][0]["code"], []) for c in valid]

    pros = prosperity.compute(series_list)
    devs = [deviation.deviation(s) for s in series_list]
    target = weights.target_weights([p["total"] for p in pros], devs)
    base = round(1.0 / len(valid), 4) if valid else 0.0

    items, missing = [], []
    for i, cluster in enumerate(valid):
        fund = cluster["funds"][0]
        points = len(series_list[i])
        if points < MIN_NAV_POINTS:
            missing.append(fund["code"])
        items.append({
            "cluster_id": cluster["cluster_id"],
            "cluster_name": cluster["name"],
            "top_industries": cluster.get("top_industries", []),
            "fund_count": cluster.get("fund_count", 0),
            "fund": {
                "code": fund["code"], "name": fund["name"], "score": fund["score"],
                "sharpe_3y": fund["sharpe_3y"], "scale": fund["scale"],
            },
            "nav_points": points,
            "prosperity": pros[i],
            "deviation": devs[i],
            "base_weight": base,
            "weight": target[i],
            "recommendation": recommend.recommend(
                pros[i]["total"], devs[i]["combined"], target[i], base),
        })
    items.sort(key=lambda x: x["weight"], reverse=True)

    # 计算组合净值走势和最大回撤
    portfolio_nav, max_drawdown = _compute_portfolio_nav(series_list, target)

    return {"items": items,
            "portfolio_nav": portfolio_nav,
            "max_drawdown": round(max_drawdown, 4),
            "meta": {"n_clusters": len(valid), "base_weight": base, "nav_missing": missing}}
