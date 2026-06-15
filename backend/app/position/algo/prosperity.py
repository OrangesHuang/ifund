"""簇级景气度（四因子，0–100），输入为各簇 TOP1 基金的累计净值序列。

把「这只代表基金的净值现在走得猛不猛」当作「这个赛道当下热不热」的代理：

- momentum 动量(0.35)：1m/3m/6m 收益按 0.5/0.3/0.2 加权，跨簇 **min-max** 归一（保留差距）。
- risk_adj 风险调整(0.25)：近 60 日 Sharpe-like，跨簇 **rank** 归一（抗极端值）。
- breadth 广度(0.25)：净值站上 MA20/MA60 的程度 + 乖离深度 bonus（单序列自洽）。
- consistency 一致性(0.15)：最近连续正收益月数 / 总月数（单序列自洽）。

数据不足的因子回退中性 50。momentum/risk_adj 因需跨簇归一，统一在 ``compute`` 里处理。
"""
from __future__ import annotations

import numpy as np  # pylint: disable=import-error

MOMENTUM_HORIZONS = (20, 60, 120)        # 1m / 3m / 6m（交易日）
MOMENTUM_WEIGHTS = (0.5, 0.3, 0.2)
RISK_ADJ_WINDOW = 60
MA_SHORT = 20
MA_LONG = 60
MONTH_DAYS = 20
WEIGHTS = {"momentum": 0.35, "risk_adj": 0.25, "breadth": 0.25, "consistency": 0.15}
NEUTRAL = 50.0


def _period_return(series: list[float], days: int):
    if len(series) <= days:
        return None
    past = series[-1 - days]
    if past <= 0:
        return None
    return series[-1] / past - 1.0


def _momentum_raw(series: list[float]):
    """1m/3m/6m 收益加权（原始值）；缺失区间按可用区间重新归权；全缺返回 None。"""
    rets, wts = [], []
    for days, weight in zip(MOMENTUM_HORIZONS, MOMENTUM_WEIGHTS):
        ret = _period_return(series, days)
        if ret is not None:
            rets.append(ret)
            wts.append(weight)
    if not rets:
        return None
    return float(sum(r * w for r, w in zip(rets, wts)) / sum(wts))


def _daily_returns(series: list[float]) -> np.ndarray:
    arr = np.asarray(series, dtype=float)
    if arr.size < 2:
        return np.empty(0)
    return arr[1:] / arr[:-1] - 1.0


def _risk_adj_raw(series: list[float]):
    """近 RISK_ADJ_WINDOW 日 Sharpe-like：mean/std×√252（原始值）；样本不足返回 None。"""
    returns = _daily_returns(series)[-RISK_ADJ_WINDOW:]
    if returns.size < 20:
        return None
    std = float(returns.std())
    if std <= 0:
        return None
    return float(returns.mean() / std * np.sqrt(252))


def _breadth(series: list[float]) -> float:
    """净值站上 MA20/MA60 的程度（0.6/0.4）+ 乖离深度 bonus（±10），0–100。"""
    arr = np.asarray(series, dtype=float)
    if arr.size < MA_SHORT:
        return NEUTRAL
    nav = float(arr[-1])
    ma20 = float(arr[-MA_SHORT:].mean())
    ma60 = float(arr[-MA_LONG:].mean()) if arr.size >= MA_LONG else ma20
    score = 60.0 * (nav > ma20) + 40.0 * (nav > ma60)
    bonus = float(np.clip((nav / ma20 - 1.0) * 100.0, -10.0, 10.0)) if ma20 > 0 else 0.0
    return float(np.clip(score + bonus, 0.0, 100.0))


def _consistency(series: list[float]) -> float:
    """从最近往前数连续正收益月数 / 总月数，0–100。月 = 20 交易日。"""
    arr = np.asarray(series, dtype=float)
    n_months = int(arr.size // MONTH_DAYS)
    if n_months < 2:
        return NEUTRAL
    points = arr[[arr.size - 1 - k * MONTH_DAYS for k in range(n_months)]]  # 最近→过去
    streak = 0
    for k in range(points.size - 1):
        if points[k] > points[k + 1]:
            streak += 1
        else:
            break
    return float(streak / (points.size - 1) * 100.0)


def _minmax(values: list[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    lo, hi = float(arr.min()), float(arr.max())
    if hi - lo <= 1e-12:
        return np.full(arr.shape, NEUTRAL)
    return (arr - lo) / (hi - lo) * 100.0


def _rank_norm(values: list[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.size <= 1:
        return np.full(arr.shape, NEUTRAL)
    ranks = np.argsort(np.argsort(arr)).astype(float)
    return ranks / (arr.size - 1) * 100.0


def _normalize(raw: list, norm_fn) -> list[float]:
    """对非 None 项做跨簇归一，None（数据不足）回填中性 50。"""
    idx = [i for i, v in enumerate(raw) if v is not None]
    out = [NEUTRAL] * len(raw)
    if not idx:
        return out
    normed = norm_fn([raw[i] for i in idx])
    for pos, i in enumerate(idx):
        out[i] = float(normed[pos])
    return out


def compute(series_list: list[list[float]]) -> list[dict]:
    """返回每簇 ``{total, momentum, risk_adj, breadth, consistency}``（均 0–100）。"""
    momentum = _normalize([_momentum_raw(s) for s in series_list], _minmax)
    risk_adj = _normalize([_risk_adj_raw(s) for s in series_list], _rank_norm)
    breadth = [_breadth(s) for s in series_list]
    consistency = [_consistency(s) for s in series_list]

    out = []
    for i in range(len(series_list)):
        total = (WEIGHTS["momentum"] * momentum[i] + WEIGHTS["risk_adj"] * risk_adj[i]
                 + WEIGHTS["breadth"] * breadth[i] + WEIGHTS["consistency"] * consistency[i])
        out.append({
            "total": round(total, 1),
            "momentum": round(momentum[i], 1),
            "risk_adj": round(risk_adj[i], 1),
            "breadth": round(breadth[i], 1),
            "consistency": round(consistency[i], 1),
        })
    return out
