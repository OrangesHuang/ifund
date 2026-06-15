"""仓位编排：②聚类的簇列表 + 各簇 TOP1 净值 → 景气度/乖离/目标权重/推荐。"""
from __future__ import annotations

from app.position.algo import deviation, prosperity, recommend, weights

MIN_NAV_POINTS = 60      # 低于此点数视为净值不足（景气度会退化为中性）


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
    return {"items": items,
            "meta": {"n_clusters": len(valid), "base_weight": base, "nav_missing": missing}}
