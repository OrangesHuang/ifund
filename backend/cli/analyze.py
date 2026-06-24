"""analyze 组（组合分析）：选预设 → 对镜像聚类算簇级仓位建议 → 看穿透/赛道/表现。

流程：必须选一个预设；选预设后即有仓位建议，可选均衡程度（松/中/紧）；基于该均衡程度
可查看 各赛道仓位建议(weights) / 底层穿透(industry|stock) / 分区间综合表现(perf)。
复用后端 ``compute_position``；表现曲线已在其中算好，这里只做分区间切片。
"""
from __future__ import annotations

import json
import sys

from . import helpers, metrics, output

_BALANCE_CAP = {"松": 0.22, "loose": 0.22, "中": 0.18, "medium": 0.18, "紧": 0.14, "tight": 0.14}
_DEFAULT_CAP = 0.14


def _resolve_cap(balance: str | None, cap: float | None) -> float:
    if cap is not None:
        return min(0.30, max(0.10, float(cap)))
    return _BALANCE_CAP.get((balance or "").strip().lower(),
                            _BALANCE_CAP.get((balance or "").strip(), _DEFAULT_CAP))


def cmd_run(args) -> None:
    from app import preset_access
    from app.position.api.router import compute_position

    pf = helpers.resolve_preset(args.user, args.preset, None)
    if not pf:
        print("未找到该预设", file=sys.stderr)
        sys.exit(1)
    items = preset_access.snapshot_items(pf["id"], args.user)
    if not items:
        print(f"该预设尚无镜像快照，请先 preset snapshot --id {pf['id']}", file=sys.stderr)
        sys.exit(1)
    cap = _resolve_cap(args.balance, args.cap)
    result, _ = compute_position(items, cap)
    if result is None:
        print("有效基金不足（需 ≥3 只含股票持仓的基金）", file=sys.stderr)
        sys.exit(1)

    view = args.view
    curve = result["portfolio"].get("curve") or []
    perf = None
    if view in ("perf", "all") and len(curve) >= 2:
        perf = {label: metrics.interval_metrics(curve, start)
                for label, start in metrics.window_starts(curve).items()}

    if args.json:
        # JSON 模式：按 view 裁剪，避免吐出超大 nav_curve / 每日序列
        slim = {"meta": result["meta"]}
        if view in ("weights", "all"):
            slim["items"] = [{k: v for k, v in it.items() if k != "nav_curve"} for it in result["items"]]
        if view in ("industry", "all"):
            slim["lookthrough_industries"] = result["lookthrough"]["industries"]
        if view in ("stock", "all"):
            slim["lookthrough_stocks"] = result["lookthrough"]["stocks"]
        if view in ("perf", "all"):
            slim["nav_as_of"] = curve[-1]["date"] if curve else None
            slim["performance"] = perf
        print(json.dumps(slim, ensure_ascii=False, separators=(",", ":")))
        return

    m = result["meta"]
    print(f"预设 #{pf['id']} {pf['name']}　均衡 cap={cap}　簇数 {m['n_clusters']}　"
          f"净值截止 {m.get('nav_as_of')}　持仓季度 {m.get('holdings_quarter')}　换基 {m.get('funds_swapped')}")
    if view in ("weights", "all"):
        rows = [[it["cluster_name"], it["fund"]["code"], it["fund"]["name"],
                 output.pct(it["weight"]), it["recommendation"]["tag"],
                 output.num(it["fund"].get("score")), output.num(it["prosperity"]["total"], 1),
                 output.num(it["deviation"]["combined"], 1), it["nav_points"]]
                for it in result["items"]]
        print(output.table(rows, ["赛道", "代码", "基金", "目标权重", "建议", "综合分", "景气", "乖离%", "净值点"]))
    if view in ("perf", "all"):
        if perf is None:
            print("— 组合表现：净值曲线数据不足 —")
        else:
            print(f"— 组合表现（建议组合按目标权重合成，净值截止 {curve[-1]['date']}）—")
            print(output.table(metrics.perf_table_rows(perf), metrics.PERF_HEADERS))
    if view in ("industry", "all"):
        lt = result["lookthrough"]
        print(f"— 建议组合穿透·按行业（可见仓位 {lt['visible_position']}%，重叠股 {lt['overlap_stocks']}）—")
        print(output.table([[x["industry"], f"{x['exposure']}%", x["stock_count"]] for x in lt["industries"]],
                           ["行业", "穿透占比", "股票数"]))
    if view in ("stock", "all"):
        lt = result["lookthrough"]
        print("— 建议组合穿透·按个股 —")
        print(output.table([[s["code"], s["name"], s["industry"], f"{s['exposure']}%", s["fund_count"]]
                            for s in lt["stocks"]], ["代码", "名称", "行业", "穿透占比", "基金数"]))
