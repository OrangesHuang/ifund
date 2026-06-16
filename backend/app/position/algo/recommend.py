"""根据「等权基准 vs 行业降相关后权重」生成持仓标签与中文理由。

权重已回归等权（1/N），仅因行业感知再分配（降相关）而在等权附近微调：
行业相对分散的簇被增配、底层行业拥挤的簇被压低。动量强度仅作观察附注，不参与调权。
"""
from __future__ import annotations

REL_BAND = 0.005       # 相对等权 ±0.5% 内视为标配


def recommend(pros: float, dev: float, weight: float, base: float) -> dict:
    """返回 ``{tag, reason}``：tag ∈ {加码, 标配, 减码}，由「权重 − 等权」的偏离方向决定。

    pros（动量强度）、dev（乖离）不参与判定，仅作中文理由里的观察附注。
    """
    rel = weight - base
    note = f"（动量强度 {pros:.0f}，仅供参考）"
    if rel > REL_BAND:
        return {"tag": "加码",
                "reason": f"底层行业相对分散，降相关时增配至 {weight * 100:.1f}%"
                          f"（等权基准 {base * 100:.1f}%）。{note}"}
    if rel < -REL_BAND:
        return {"tag": "减码",
                "reason": f"底层行业较拥挤，为降低组合相关性压低至 {weight * 100:.1f}%"
                          f"（等权基准 {base * 100:.1f}%）。{note}"}
    return {"tag": "标配", "reason": f"行业拥挤度适中，等权标配 {weight * 100:.1f}%。{note}"}
