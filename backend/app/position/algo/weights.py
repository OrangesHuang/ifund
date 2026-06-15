"""簇级目标权重：base(1/N) × 景气因子 × 乖离因子 → cap[3%,25%] → 迭代再分配 → ∑=100%。

- 景气因子：按池内 z-score 拉开，封顶 ±50%。
- 乖离因子：景气强→无论涨跌都视为趋势确立、适度加码；景气弱→涨多减码、跌深小幅减
  （弱势不抄底）；|乖离|≤3% 中性。tanh 软饱和。
- cap：单簇权重限制在 [3%, 25%]，超出/不足部分按未触顶簇的现有权重比例迭代摊派。
"""
from __future__ import annotations

import numpy as np  # pylint: disable=import-error

MIN_W = 0.03
MAX_W = 0.25
K_PROS = 0.30
K_DEV_STRONG = 0.25        # 景气强时加码强度
K_DEV_WEAK_UP = 0.25       # 景气弱、涨多时减码强度
K_DEV_WEAK_DOWN = 0.125    # 景气弱、跌深时小幅减
DEV_BAND = 3.0             # |乖离|≤该值视为中性
PROS_STRONG = 50.0
CAP_ITERS = 10


def _pros_factor(pros: float, mean: float, std: float) -> float:
    if std <= 1e-9:
        return 1.0
    return float(np.clip(1.0 + K_PROS * (pros - mean) / std, 0.5, 1.5))


def _dev_factor(pros: float, dev: float) -> float:
    if abs(dev) <= DEV_BAND:
        return 1.0
    if pros >= PROS_STRONG:
        return float(1.0 + K_DEV_STRONG * np.tanh(abs(dev) / 5.0))
    if dev > DEV_BAND:
        return float(1.0 - K_DEV_WEAK_UP * np.tanh(dev / 5.0))
    return float(1.0 - K_DEV_WEAK_DOWN * np.tanh(abs(dev) / 5.0))


def _cap_redistribute(raw: list[float]) -> np.ndarray:
    """归一后按 [MIN_W, MAX_W] 截断，超额按未触顶簇权重占比迭代摊派。"""
    w = np.asarray(raw, dtype=float)
    n = w.size
    if n == 0:
        return w
    total = w.sum()
    w = w / total if total > 0 else np.full(n, 1.0 / n)
    for _ in range(CAP_ITERS):
        capped = np.clip(w, MIN_W, MAX_W)
        excess = float(w.sum() - capped.sum())  # >0：压顶让出；<0：托底吸收
        free = (capped > MIN_W) & (capped < MAX_W)
        free_sum = float(capped[free].sum())
        if abs(excess) < 1e-6 or free_sum <= 0:
            w = capped
            break
        w = capped.copy()
        w[free] += excess * (capped[free] / free_sum)
    final = w.sum()
    return w / final if final > 0 else w


def target_weights(pros_list: list[float], dev_list: list[dict]) -> list[float]:
    """景气度列表 + 乖离列表 → 各簇目标权重（∑=1，四舍五入到 4 位）。"""
    n = len(pros_list)
    if n == 0:
        return []
    base = 1.0 / n
    pros = np.asarray(pros_list, dtype=float)
    mean, std = float(pros.mean()), float(pros.std())
    raw = [base * _pros_factor(pros[i], mean, std)
           * _dev_factor(float(pros[i]), dev_list[i]["combined"]) for i in range(n)]
    return [round(float(x), 4) for x in _cap_redistribute(raw)]
