"""根据景气度 + 乖离 + 相对基准权重，生成持仓推荐标签与中文理由。"""
from __future__ import annotations

STRONG = 60.0          # 景气度强阈值
WEAK = 40.0            # 景气度弱阈值
DEV_HOT = 8.0          # 涨多（追高）阈值
DEV_PULLBACK = -5.0    # 回踩阈值
REL_BAND = 0.01        # 相对基准 ±1% 内视为标配


def recommend(pros: float, dev: float, weight: float, base: float) -> dict:
    """返回 ``{tag, reason}``：tag ∈ {加码, 标配, 减码}。"""
    rel = weight - base
    if pros >= STRONG and dev <= DEV_PULLBACK:
        return {"tag": "加码",
                "reason": f"景气度高（{pros:.0f}）且净值回踩均线（乖离 {dev:.1f}%），"
                          "高景气回调，建议逢低加配。"}
    if pros >= STRONG:
        over = rel > REL_BAND
        return {"tag": "加码" if over else "标配",
                "reason": f"景气度高（{pros:.0f}），趋势确立，建议{'超配' if over else '标配'}。"}
    if pros <= WEAK and dev >= DEV_HOT:
        return {"tag": "减码",
                "reason": f"景气度偏弱（{pros:.0f}）却已涨多（乖离 {dev:.1f}%），"
                          "追高风险大，建议减配。"}
    if pros <= WEAK:
        under = rel < -REL_BAND
        return {"tag": "减码" if under else "标配",
                "reason": f"景气度偏弱（{pros:.0f}），建议{'低配观望' if under else '标配'}。"}
    return {"tag": "标配", "reason": f"景气度中等（{pros:.0f}），按基准权重标配。"}
