"""组合净值曲线的分区间指标：近三月/六月/一年/今年以来/全部。analyze 与 holdings 共用。

输入 curve 是按日升序的 ``[{"date": "YYYY-MM-DD", "nav": float, ...}]``（多余字段忽略）。
"""
from __future__ import annotations

import datetime

from . import output


def minus_months(d: datetime.date, months: int) -> datetime.date:
    """d 往前推 months 个月（末日溢出则取目标月最后一天）。"""
    y, m = d.year, d.month - months
    while m <= 0:
        m += 12
        y -= 1
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    last_day = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return datetime.date(y, m, min(d.day, last_day))


def window_starts(curve: list[dict]) -> dict[str, str]:
    """据曲线最后一天，给出五个区间的起始 ISO 日期（顺序固定）。"""
    last = datetime.date.fromisoformat(curve[-1]["date"])
    return {
        "近三月": minus_months(last, 3).isoformat(),
        "近六月": minus_months(last, 6).isoformat(),
        "近一年": minus_months(last, 12).isoformat(),
        "今年以来": f"{last.year}-01-01",
        "全部": curve[0]["date"],
    }


def interval_metrics(curve: list[dict], start_iso: str) -> dict | None:
    """从组合净值曲线截取 [start, end]，重算累计/年化/最大回撤/夏普（不足 2 点→None）。"""
    from app.position.algo.pipeline import _portfolio_stats
    sub = [p for p in curve if p["date"] >= start_iso]
    if len(sub) < 2:
        return None
    base = sub[0]["nav"]
    rb = [{"date": p["date"], "nav": p["nav"] / base} for p in sub]
    peak = mdd = 0.0
    for p in rb:
        peak = max(peak, p["nav"])
        mdd = min(mdd, (p["nav"] - peak) / peak if peak else 0.0)
    stats = _portfolio_stats(rb)
    return {"cum_return": round(rb[-1]["nav"] - 1, 4), "annual_return": stats["annual_return"],
            "max_drawdown": round(-mdd, 4), "sharpe": stats["sharpe"],
            "start": sub[0]["date"], "end": sub[-1]["date"], "points": len(sub)}


def perf_table_rows(perf: dict) -> list[list]:
    """把 {区间标签: interval_metrics结果|None} 渲染为文本表行（供 output.table）。"""
    rows = []
    for label, mt in perf.items():
        if mt is None:
            rows.append([label, "数据不足", "", "", "", ""])
        else:
            rows.append([label, output.pct(mt["cum_return"]), output.pct(mt["annual_return"]),
                         output.pct(mt["max_drawdown"]), output.num(mt["sharpe"]), mt["start"]])
    return rows


PERF_HEADERS = ["区间", "累计收益", "年化收益", "最大回撤", "夏普", "起始日"]
