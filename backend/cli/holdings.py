"""holdings 组（实盘）：账户列表 / 实际持仓(按赛道簇分组) / 底层穿透 / 分区间表现 / 调仓建议。

实际持仓的录入/编辑/导入放在网页端；CLI 只做查询 + 交易(见 trade.py) + 调仓建议。
簇归属与调仓建议复用对账后端（compute_position 聚类 + classify 归类 + reconcile 算账）。
"""
from __future__ import annotations

import sys

from app import db as database

from . import metrics, output

CAP_MIN, CAP_MAX = 0.10, 0.30
BAND_MIN, BAND_MAX = 0.0, 0.10
_ACTION_CN = {"open": "建仓", "add": "加仓", "trim": "减仓", "hold": "不动",
              "exit": "清仓", "keep": "保留"}


def _clamp(val, lo: float, hi: float, default: float) -> float:
    if val is None:
        return default
    try:
        return min(hi, max(lo, float(val)))
    except (TypeError, ValueError):
        return default


def _portfolio(uid: int, pid: int) -> dict:
    """取并校验实盘归属，失败即退出。"""
    from app.reconcile.crud import portfolios_store
    pf = portfolios_store.get_portfolio(pid, uid)
    if not pf:
        print(f"未找到实盘 #{pid}（或不属于用户 {uid}）", file=sys.stderr)
        sys.exit(1)
    return pf


def cmd_list(args) -> None:
    """列出全部实盘：id / 名称 / 关联预设 / 均衡 cap。"""
    from app.reconcile.crud import portfolios_store
    rows = portfolios_store.list_portfolios(args.user)
    pnames: dict[int, str] = {}
    for r in rows:
        pid_ = r.get("preset_id")
        if pid_ and pid_ not in pnames:
            pr = database.select_one("query_presets", {"id": f"eq.{pid_}", "user_id": f"eq.{args.user}"})
            pnames[pid_] = pr["name"] if pr else "?"
    data = [{"id": r["id"], "name": r["name"], "preset_id": r.get("preset_id"),
             "preset_name": pnames.get(r.get("preset_id")), "cap": r.get("cap")} for r in rows]

    def txt(d):
        rr = [[x["id"], x["name"],
               f'#{x["preset_id"]} {x["preset_name"]}' if x["preset_id"] else "-",
               x["cap"]] for x in d]
        print(output.table(rr, ["id", "名称", "关联预设", "均衡cap"]))
    output.emit(data, args.json, txt)


def _cluster_holdings(pf: dict, uid: int):
    """把实盘实际持仓按赛道(簇)分组。返回 (holdings, grouped|None)。

    grouped = {"n_clusters", "groups":[{seq,cluster_id,label,target_fund,market_value,funds}], "outside":[...]}。
    只认目标组合选中的簇（有目标权重者）；归不进的持仓入「赛道外」。
    未关联预设 / 镜像不足 / 有效基金不足 → grouped=None（调用方平铺展示）。
    """
    from app import preset_access
    from app.position.algo import optimize
    from app.position.api.router import compute_position
    from app.reconcile.algo import classify
    from app.reconcile.crud.holdings_compute import compute_holdings
    from app.stock_industry.crud import industry_crud

    holdings = compute_holdings(pf["id"])
    preset_id = pf.get("preset_id")
    if not preset_id:
        return holdings, None
    items = preset_access.snapshot_items(preset_id, uid)
    if not items:
        return holdings, None
    cap = float(pf.get("cap") or optimize.DEFAULT_CAP)
    result, clusters = compute_position(items, cap)
    if result is None or not clusters:
        return holdings, None

    code2cluster = classify.build_code_to_cluster(clusters)
    name2cluster = classify.build_name_index(clusters)
    cluster_vecs = classify.cluster_vectors(clusters)
    ind_idx = industry_crud.industry_index()
    seq_by_cid, label_by_cid, fund_by_cid = {}, {}, {}
    for seq, it in enumerate(result["items"], start=1):
        cid = it["cluster_id"]
        seq_by_cid[cid] = seq
        label_by_cid[cid] = it.get("cluster_name", "")
        f = it.get("fund") or {}
        fund_by_cid[cid] = {"code": f.get("code", ""), "name": f.get("name", "")}

    groups: dict[int, dict] = {}
    outside: list[dict] = []
    for h in holdings:
        cid, _m, _s = classify.classify_fund(
            h["fund_code"], h.get("fund_name", ""),
            code2cluster, name2cluster, cluster_vecs, ind_idx)
        if cid in seq_by_cid:
            g = groups.setdefault(cid, {"seq": seq_by_cid[cid], "cluster_id": cid,
                                        "label": label_by_cid[cid],
                                        "target_fund": fund_by_cid[cid], "funds": []})
            g["funds"].append(h)
        else:
            outside.append(h)
    group_list = sorted(groups.values(), key=lambda g: g["seq"])
    for g in group_list:
        g["market_value"] = round(sum(f["market_value"] for f in g["funds"]), 2)
    return holdings, {"n_clusters": len(seq_by_cid), "groups": group_list, "outside": outside}


def _hold_row(h: dict, total: float) -> list:
    return [h["fund_code"], h["fund_name"], output.num(h["market_value"]),
            f"{h['market_value'] / total * 100:.1f}%" if total else "-",
            output.num(h.get("pnl")), "" if h.get("valuation_ok") else "估值降级"]


_HOLD_HEADERS = ["代码", "名称", "市值", "占比", "盈亏", "备注"]


def cmd_show(args) -> None:
    """实际持仓，按赛道(簇)分组：共几簇、每簇含哪几只基金。"""
    pf = _portfolio(args.user, args.pid)
    holdings, grouped = _cluster_holdings(pf, args.user)
    total = sum(h["market_value"] for h in holdings)
    total_pnl = sum(h["pnl"] for h in holdings if h.get("pnl") is not None)
    data = {"portfolio_id": pf["id"], "name": pf["name"], "preset_id": pf.get("preset_id"),
            "total_market_value": round(total, 2), "total_pnl": round(total_pnl, 2),
            "n_holdings": len(holdings)}
    if grouped:
        data["n_clusters"] = grouped["n_clusters"]
        data["clusters"] = [{"seq": g["seq"], "cluster_id": g["cluster_id"], "label": g["label"],
                             "target_fund": g["target_fund"], "market_value": g["market_value"],
                             "funds": g["funds"]} for g in grouped["groups"]]
        data["outside"] = grouped["outside"]
    else:
        data["clusters"] = None
        data["items"] = holdings
    if getattr(args, "penetration", False):
        data["penetration"] = _penetration_data(pf["id"], args.by)

    def txt(d):
        head = f"实盘 #{d['portfolio_id']} {d['name']}"
        if d["preset_id"]:
            head += f"　预设 #{d['preset_id']}"
        head += f"　总市值 {d['total_market_value']}　浮盈 {d['total_pnl']}　持仓 {d['n_holdings']} 只"
        print(head)
        if d["clusters"] is None:
            print("（未关联预设或镜像不足，无法按赛道分组，平铺展示）")
            print(output.table([_hold_row(h, total) for h in d["items"]], _HOLD_HEADERS))
            return
        print(f"共 {d['n_clusters']} 簇 + 赛道外 {len(d['outside'])} 只")
        for g in d["clusters"]:
            print(f"\n【簇{g['seq']}】{g['label']}　{len(g['funds'])}只 / {g['market_value']} "
                  f"({g['market_value'] / total * 100:.1f}%)")
            print(output.table([_hold_row(h, total) for h in g["funds"]], _HOLD_HEADERS))
        if d["outside"]:
            ov = sum(h["market_value"] for h in d["outside"])
            print(f"\n【赛道外】{len(d['outside'])}只 / {round(ov, 2)} ({ov / total * 100:.1f}%)")
            print(output.table([_hold_row(h, total) for h in d["outside"]], _HOLD_HEADERS))

    def txt_full(d):
        txt(d)
        if d.get("penetration"):
            print()
            _print_penetration(d["penetration"])
    output.emit(data, args.json, txt_full)


def _penetration_data(pid: int, by: str) -> dict | None:
    """底层持仓穿透：复用后端 holdings_compute.penetrate_holdings，仅附 by 控制文本粒度。"""
    from app.reconcile.crud.holdings_compute import penetrate_holdings
    data = penetrate_holdings(pid)
    if data is None:
        return None
    return {**data, "by": by}


def _print_penetration(d: dict) -> None:
    print(f"— 底层穿透　前十大可见仓位 {d['visible_position_pct']}% —")
    if d["by"] in ("industry", "both"):
        print("· 按行业")
        print(output.table([[x["industry"], f"{x['ratio']}%", x["stock_count"]] for x in d["industries"]],
                           ["行业", "穿透占比", "股票数"]))
    if d["by"] in ("stock", "both"):
        print("· 按个股")
        print(output.table([[s["code"], s["name"], s["industry"], f"{s['ratio']}%", s["fund_count"]]
                            for s in d["stocks"]], ["代码", "名称", "行业", "穿透占比", "基金数"]))


def cmd_penetration(args) -> None:
    """底层持仓穿透（独立命令）。"""
    _portfolio(args.user, args.pid)
    data = _penetration_data(args.pid, args.by)
    if data is None:
        print("该实盘无有效持仓", file=sys.stderr)
        sys.exit(1)

    def txt(d):
        print(f"实盘 #{d['portfolio_id']} 穿透　总市值 {d['total_market_value']}")
        _print_penetration(d)
    output.emit(data, args.json, txt)


def cmd_perf(args) -> None:
    """分区间组合表现（近三月/六月/一年/今年以来/全部 × 累计/年化/最大回撤/夏普）。"""
    from app.fund_nav.crud import nav_crud
    from app.position.algo.pipeline import _portfolio_curve
    from app.reconcile.crud.holdings_compute import compute_holdings

    _portfolio(args.user, args.pid)
    holdings = [h for h in compute_holdings(args.pid)
                if h.get("valuation_ok") and (h.get("market_value") or 0) > 0]
    if not holdings:
        print("该实盘无可估值持仓（净值缺失？先 fetch nav）", file=sys.stderr)
        sys.exit(1)
    total = sum(h["market_value"] for h in holdings)
    weights = [h["market_value"] / total for h in holdings]
    dated_list = [nav_crud.recent_series_dated(h["fund_code"], 900) for h in holdings]
    curve, _ = _portfolio_curve(dated_list, weights)
    if len(curve) < 2:
        print("各基金净值无足够共同交易日，无法合成组合曲线", file=sys.stderr)
        sys.exit(1)
    perf = {label: metrics.interval_metrics(curve, start)
            for label, start in metrics.window_starts(curve).items()}
    data = {"portfolio_id": args.pid, "funds": len(holdings),
            "nav_as_of": curve[-1]["date"], "performance": perf}

    def txt(d):
        print(f"实盘 #{d['portfolio_id']} 组合表现　基金 {d['funds']} 只　净值截止 {d['nav_as_of']}")
        print(output.table(metrics.perf_table_rows(d["performance"]), metrics.PERF_HEADERS))
    output.emit(data, args.json, txt)


def cmd_rebalance(args) -> None:
    """调仓建议：按三旋钮(赛道外可卖/赛道内超配可减/缓冲带)生成操作指南。"""
    from app import preset_access
    from app.position.algo import optimize
    from app.position.api.router import compute_position
    from app.reconcile.algo import reconcile as recon_algo
    from app.reconcile.crud.holdings_compute import compute_holdings
    from app.stock_industry.crud import industry_crud

    pf = _portfolio(args.user, args.pid)
    preset_id = args.preset or pf.get("preset_id")
    if not preset_id:
        print("该实盘未关联预设，请用 --preset 指定", file=sys.stderr)
        sys.exit(1)
    items = preset_access.snapshot_items(preset_id, args.user)
    if not items:
        print(f"预设 #{preset_id} 尚无镜像快照，请先 preset snapshot --id {preset_id}", file=sys.stderr)
        sys.exit(1)
    holdings = compute_holdings(pf["id"])
    if not holdings:
        print("该实盘尚未录入任何持仓（请在网页端录入）", file=sys.stderr)
        sys.exit(1)
    cap = _clamp(args.cap, CAP_MIN, CAP_MAX, float(pf.get("cap") or optimize.DEFAULT_CAP))
    band = _clamp(args.band, BAND_MIN, BAND_MAX, recon_algo.DEFAULT_BAND)
    result, clusters = compute_position(items, cap)
    if result is None or not result.get("items"):
        print("有效基金不足（需 ≥3 只含股票持仓的基金），无法生成目标", file=sys.stderr)
        sys.exit(1)
    ind_idx = industry_crud.industry_index()
    recon = recon_algo.reconcile(result["items"], holdings, clusters, ind_idx,
                                 band=band, sell_outside=args.sell_outside,
                                 trim_overflow=args.trim_overflow)
    recon["meta"]["cap"] = cap
    recon["meta"]["preset_id"] = preset_id

    if args.json:
        # 裁掉每行的 user_funds 明细（show 已可查），保留操作指南核心
        rows = [{k: v for k, v in r.items() if k != "user_funds"} for r in recon["rows"]]
        print(output.dumps({"portfolio_id": pf["id"], "summary": recon["summary"],
                            "meta": recon["meta"], "rows": rows,
                            "transfers": recon["transfers"]}))
        return

    s = recon["summary"]
    print(f"实盘 #{pf['id']} {pf['name']} 调仓建议　预设 #{preset_id}　cap={cap} band={band}　"
          f"赛道外{'可卖' if args.sell_outside else '保留'}　超配{'可减' if args.trim_overflow else '不减'}")
    line = (f"盘子 {s['base_asset']:,.0f}　买入合计 {s['buy_total']:,.0f}　"
            f"卖出合计 {s['sell_total']:,.0f}　需追加现金 {s['cash_needed']:,.0f}")
    if s.get("has_cost"):
        line += f"　（浮盈 {s.get('pnl_total')} / 收益率 {s.get('return_pct')}%）"
    print(line)
    if s.get("scaled"):
        print("⚠ 可动用资金有限，部分低配赛道未完全补到位")

    print("— 赛道动作 —")
    rrows = []
    for r in recon["rows"]:
        rrows.append([r.get("seq") if r.get("seq") is not None else "外", r["cluster_name"],
                      output.num(r["target"]), output.num(r["actual"]),
                      f"{r['actual_ratio'] * 100:.1f}%", _ACTION_CN.get(r["action"], r["action"]),
                      output.num(r["amount"]), r["note"]])
    print(output.table(rrows, ["#", "赛道", "目标", "现额", "现占比", "动作", "金额", "说明"]))

    print("— 换仓清单（操作指南）—")
    if not recon["transfers"]:
        print("（无需换仓）")
        return
    src_cn = {"trim": "超配减仓", "add_cash": "追加现金"}
    for t in recon["transfers"]:
        to_verb = "建仓" if t.get("to_action") == "open" else "加仓"
        dest = f"{t['to_name']}（{t['to_code']}） {to_verb}"
        if t["from_type"] == "add_cash":
            print(f"追加现金 {t['amount']:,.0f} 元 至 {dest}")
        else:
            shares = f" ≈ {t['from_shares']:,.2f} 份" if t.get("from_shares") else ""
            print(f"{src_cn.get(t['from_type'], t['from_type'])} {t['from_name']}（{t['from_code']}） "
                  f"转仓 {t['amount']:,.0f} 元{shares} 至 {dest}")
