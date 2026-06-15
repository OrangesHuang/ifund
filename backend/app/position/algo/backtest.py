"""动量调权 vs 等权的 walk-forward 回测：验证「按动量/乖离调权」这一步是否真的有用。

固定一组代表基金（与③仓位建议同一批），在历史每个调仓点用**截至当时**的净值重算
动量四因子+乖离→目标权重（``weights.target_weights``，纯净值、无未来数据泄漏），持有到
下个调仓点（持有期内 buy-and-hold 不再平衡），逐段拼成净值曲线；同时用等权（1/N）跑一条
对照曲线。两条曲线的差距 = 动量调权相对等权的净增量。

刻意**不含**行业感知再分配（``optimize.rebalance_weights`` 依赖当下持仓，历史调仓点用
当下持仓会构成未来数据泄漏；且它是横截面风险约束，不是择时收益来源）。市场基准（沪深300
等）暂缺净值数据，故第一版只做「调权 vs 等权」这一核心对照。
"""
from __future__ import annotations

from datetime import date

from app.position.algo import deviation, prosperity, weights

WARMUP = 120        # 第一个调仓点前至少留的共同交易日数（够算 6m 动量 / MA60）
STEP = 21           # 调仓间隔（约 1 个月的交易日）
MIN_TOTAL = WARMUP + STEP + 2   # 共同交易日不足则无法回测


def _max_drawdown(curve: list[dict]) -> float:
    """净值曲线的最大回撤（正小数，如 0.23 表示 -23%）。"""
    peak = mdd = 0.0
    for p in curve:
        peak = max(peak, p["nav"])
        if peak > 0:
            mdd = min(mdd, p["nav"] / peak - 1.0)
    return round(-mdd, 4)


def _stats(curve: list[dict]) -> dict:
    """从净值曲线算年化收益/年化波动/夏普/最大回撤（口径同 pipeline._portfolio_stats）。"""
    if len(curve) < 2:
        return {"annual_return": 0.0, "annual_vol": 0.0, "sharpe": 0.0, "max_drawdown": 0.0}
    navs = [p["nav"] for p in curve]
    rets = [navs[i] / navs[i - 1] - 1 for i in range(1, len(navs))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1) if len(rets) > 1 else 0.0
    std = var ** 0.5
    span = (date.fromisoformat(curve[-1]["date"]) - date.fromisoformat(curve[0]["date"])).days or 1
    ppy = len(rets) * 365.25 / span
    annual_return = (navs[-1] / navs[0]) ** (365.25 / span) - 1
    annual_vol = std * ppy ** 0.5
    sharpe = annual_return / annual_vol if annual_vol > 0 else 0.0
    return {"annual_return": round(annual_return, 4), "annual_vol": round(annual_vol, 4),
            "sharpe": round(sharpe, 2), "max_drawdown": _max_drawdown(curve)}


def run_backtest(funds: list[dict],
                 dated_by_code: dict[str, list[tuple[str, float]]],
                 step: int = STEP, warmup: int = WARMUP) -> dict | None:
    """funds：代表基金 ``[{"code","name"}]``；dated_by_code：code→``(date, 累计净值)`` 升序。

    返回 ``{"strategy","equal","meta","funds","rebalances"}``，strategy/equal 各含
    ``{curve,annual_return,annual_vol,sharpe,max_drawdown}``，曲线均从首个调仓点 rebase 到 1.0。
    数据不足返回 None。
    """
    codes = [f["code"] for f in funds]
    series_full = {c: dated_by_code.get(c, []) for c in codes}
    maps = {c: dict(series_full[c]) for c in codes}
    n = len(codes)
    if n < 2:
        return None

    # 所有基金共有的交易日（交集），保证每个调仓点都能完整合成
    date_sets = [set(maps[c].keys()) for c in codes if maps[c]]
    if len(date_sets) < n:        # 有基金完全没净值，回测口径不可靠
        return None
    common = sorted(set.intersection(*date_sets))
    if len(common) < MIN_TOTAL:
        return None

    rpts = list(range(warmup, len(common) - 1, step))
    if not rpts:
        return None
    boundaries = rpts + [len(common) - 1]

    start_date = common[rpts[0]]
    strat = [{"date": start_date, "nav": 1.0}]
    equal = [{"date": start_date, "nav": 1.0}]
    rebalances: list[dict] = []
    eq_w = [1.0 / n] * n

    for k, s in enumerate(rpts):
        e = boundaries[k + 1]
        cutoff = common[s]
        # 截至 cutoff 的各基金净值子序列（用各自完整历史，非仅共同交易日，动量更准）
        cut = [[nav for d, nav in series_full[c] if d <= cutoff] for c in codes]
        pros = prosperity.compute(cut)
        devs = [deviation.deviation(x) for x in cut]
        w = weights.target_weights([p["total"] for p in pros], devs)
        rebalances.append({"date": cutoff,
                           "weights": [round(x, 4) for x in w],
                           "prosperity": [p["total"] for p in pros]})
        base = [maps[c][cutoff] for c in codes]            # 持有段起点净值
        prev_s, prev_e = strat[-1]["nav"], equal[-1]["nav"]
        for di in range(s + 1, e + 1):                     # 跳过段起点（与上段末点重合）
            day = common[di]
            ms = sum(w[i] * (maps[codes[i]][day] / base[i]) for i in range(n))
            me = sum(eq_w[i] * (maps[codes[i]][day] / base[i]) for i in range(n))
            strat.append({"date": day, "nav": round(prev_s * ms, 4)})
            equal.append({"date": day, "nav": round(prev_e * me, 4)})

    return {
        "strategy": {"curve": strat, **_stats(strat)},
        "equal": {"curve": equal, **_stats(equal)},
        "meta": {"start": start_date, "end": common[-1], "n_funds": n,
                 "n_rebalances": len(rpts), "step_days": step, "warmup_days": warmup,
                 "common_days": len(common)},
        "funds": [{"code": f["code"], "name": f["name"]} for f in funds],
        "rebalances": rebalances,
    }
