"""乖离度（择时）：当前净值相对 MA20/MA60 的偏离百分比。

用于「高景气但已涨多 → 适度收手；高景气且回踩 → 加码」的择时微调。
"""
from __future__ import annotations

import numpy as np  # pylint: disable=import-error

MA_SHORT = 20
MA_LONG = 60
W_SHORT = 0.6
W_LONG = 0.4


def deviation(series: list[float]) -> dict:
    """返回 ``{d20, d60, combined}``（百分比）；数据不足回退 0。"""
    arr = np.asarray(series, dtype=float)
    if arr.size < MA_SHORT:
        return {"d20": 0.0, "d60": 0.0, "combined": 0.0}
    nav = float(arr[-1])
    ma20 = float(arr[-MA_SHORT:].mean())
    ma60 = float(arr[-MA_LONG:].mean()) if arr.size >= MA_LONG else ma20
    d20 = (nav / ma20 - 1.0) * 100.0 if ma20 > 0 else 0.0
    d60 = (nav / ma60 - 1.0) * 100.0 if ma60 > 0 else 0.0
    combined = W_SHORT * d20 + W_LONG * d60
    return {"d20": round(d20, 2), "d60": round(d60, 2), "combined": round(combined, 2)}
