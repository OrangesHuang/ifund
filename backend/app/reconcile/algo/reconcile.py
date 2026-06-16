"""实盘对账核心：把③簇级目标权重落到用户真实持仓上，按赛道算每笔加/减/建多少钱。

设计取向（用户拍板）：
- **按赛道（簇）对齐**，不按基金代码精确匹配——只看每个赛道总仓位够不够，不强制把手里的
  基金换成系统选的代表基金（低换手、连贯，契合「不折腾」哲学）。
- **子仓位模式（默认）**：把所选预设当成账户里的一个「子仓位 / sleeve」。只在能对上赛道的
  基金里做加/减/建；**赛道外的基金保留不动（keep），不建议清仓**（用户的真实账户通常比
  单个预设镜像更宽，强行清仓太粗暴）。目标按「子仓位内市值 + 可投现金」分配。
- **金额化 + 缓冲带抗噪**：偏离在 ``band×子仓位资产`` 或 ``MIN_TRADE`` 以内就保持不动。
- **现金配平不借钱**：买入需求 > 可投（现金 + 减仓释放）时所有买入等比缩减，缩到不足起投
  门槛的降级「暂缓」，summary 标 scaled。
- **盈亏只展示不参与决策**：成本入库后，逐赛道/整体算未实现盈亏与收益率，但目标权重与加减
  判断完全不看盈亏（避免「赚了落袋、亏了死扛」的处置效应）。

``mode="whole"`` 为可选的「整盘迁移」口径：赛道外建议清仓（exit）、目标按全账户分配——
本期默认 sleeve，保留该分支以备后续需要。
"""
from __future__ import annotations

from app.reconcile.algo import classify

DEFAULT_BAND = 0.03      # 缓冲带：子仓位资产的 3 个百分点（绝对），对「按金额」最直观
MIN_TRADE_YUAN = 100.0   # 小于此金额的动作忽略（抗噪 + 申赎门槛）


def _pnl(mv: float, cost) -> float | None:
    """未实现盈亏 = 市值 − 成本；成本缺失返回 None。"""
    if cost is None:
        return None
    return round(mv - float(cost), 2)


def reconcile(target_items: list[dict], holdings: list[dict], cash: float,
              band: float, clusters: list[dict], ind_idx: dict,
              mode: str = "sleeve") -> dict:
    """对账。见模块文档。返回 ``{"rows", "summary", "meta"}``。"""
    code2cluster = classify.build_code_to_cluster(clusters)
    name2cluster = classify.build_name_index(clusters)
    cluster_vecs = classify.cluster_vectors(clusters)

    cash = max(0.0, float(cash or 0.0))

    # 1. 归类：每只持仓 → 赛道（A/C 同基金落同一赛道、市值/成本相加），失败入 outside
    per_actual: dict[int, float] = {}
    per_cost: dict[int, float] = {}        # 该赛道有成本的部分累计
    per_cost_full: dict[int, bool] = {}    # 该赛道是否每只都有成本
    cluster_user_funds: dict[int, list[dict]] = {}
    outside: list[dict] = []
    match_counts = {"exact": 0, "name": 0, "similar": 0, "outside": 0, "no_data": 0}
    held_total = cost_total = pnl_known_mv = 0.0
    has_any_cost = False

    for h in holdings:
        code = str(h.get("fund_code") or "").strip()
        mv = float(h.get("market_value") or 0.0)
        cost = h.get("cost")
        cost = float(cost) if cost is not None else None
        name = h.get("fund_name") or ""
        held_total += mv
        if cost is not None:
            has_any_cost = True
            cost_total += cost
            pnl_known_mv += mv

        cid, match, sim = classify.classify_fund(
            code, name, code2cluster, name2cluster, cluster_vecs, ind_idx)
        match_counts[match] = match_counts.get(match, 0) + 1
        entry = {"code": code, "name": name, "market_value": round(mv, 2),
                 "cost": round(cost, 2) if cost is not None else None,
                 "pnl": _pnl(mv, cost), "match": match, "sim": sim}
        if cid is None:
            outside.append(entry)
        else:
            per_actual[cid] = per_actual.get(cid, 0.0) + mv
            per_cost[cid] = per_cost.get(cid, 0.0) + (cost or 0.0)
            per_cost_full[cid] = per_cost_full.get(cid, True) and (cost is not None)
            cluster_user_funds.setdefault(cid, []).append(entry)

    matched_total = sum(per_actual.values())
    outside_value = sum(o["market_value"] for o in outside)

    pnl_total = round(pnl_known_mv - cost_total, 2) if has_any_cost else None
    return_pct = (round(pnl_total / cost_total * 100, 2)
                  if has_any_cost and cost_total > 0 else None)
    pnl_ctx = {"has_cost": has_any_cost, "pnl_total": pnl_total,
               "return_pct": return_pct, "cost_covered_mv": round(pnl_known_mv, 2)}

    # 智能换仓：sleeve 口径定目标，按「现金→赛道外→超配减仓」优先级配对资金，生成换仓流水
    if mode == "swap":
        return _reconcile_swap(
            target_items, per_actual, per_cost, per_cost_full, cluster_user_funds,
            outside, cash, band, held_total, matched_total, outside_value,
            match_counts, pnl_ctx)

    # 2. 目标基准：子仓位=匹配市值+现金；整盘=全账户+现金（赛道外会被清仓释放）
    base_asset = (matched_total + cash) if mode == "sleeve" else (held_total + cash)
    band_yuan = band * base_asset

    rows: list[dict] = []
    buys: list[tuple[int, float]] = []   # (rows 下标, 期望买入金额)，供现金不足时等比缩减
    sell_total = 0.0

    # 3. 逐目标赛道：目标金额 = weight×基准，与实际差额按缓冲带判加/减/建/不动
    for it in target_items:
        cid = it["cluster_id"]
        weight = float(it.get("weight") or 0.0)
        target = weight * base_asset
        actual = per_actual.get(cid, 0.0)
        diff = target - actual
        user_funds = sorted(cluster_user_funds.get(cid, []),
                            key=lambda x: x["market_value"], reverse=True)
        rep = it.get("fund") or {}

        cl_pnl = round(actual - per_cost[cid], 2) if per_cost_full.get(cid) else None

        if user_funds:
            biggest = user_funds[0]
            act_fund = {"code": biggest["code"], "name": biggest["name"]}
            match, sim = biggest["match"], biggest["sim"]
        else:
            act_fund = {"code": rep.get("code", ""), "name": rep.get("name", "")}
            match, sim = None, None

        row = {
            "cluster_id": cid, "cluster_name": it.get("cluster_name", ""),
            "weight": round(weight, 4), "target": round(target, 2),
            "actual": round(actual, 2), "pnl": cl_pnl,
            "target_fund": act_fund, "user_funds": user_funds,
            "match": match, "sim": sim,
        }

        if abs(diff) <= band_yuan or abs(diff) < MIN_TRADE_YUAN:
            row["action"] = "hold"
            row["amount"] = 0.0
            row["note"] = "已在目标 ± 缓冲带内，保持不动（抗噪）"
        elif diff > 0:
            row["amount"] = round(diff, 2)
            if actual < MIN_TRADE_YUAN:   # 空仓 → 建仓买代表基金
                row["action"] = "open"
                row["target_fund"] = {"code": rep.get("code", ""), "name": rep.get("name", "")}
                row["note"] = f"该赛道当前空仓，建议买入代表基金「{rep.get('name', '')}」建仓"
            else:
                row["action"] = "add"
                row["note"] = f"低配，建议加仓「{act_fund['name']}」"
            buys.append((len(rows), diff))
        else:   # diff < 0 → 减仓
            row["action"] = "trim"
            row["amount"] = round(diff, 2)   # 负数
            row["note"] = f"超配，建议减仓「{act_fund['name']}」"
            sell_total += -diff
        rows.append(row)

    # 4. 赛道外：子仓位模式 → 保留不动（keep）；整盘模式 → 清仓（exit）
    for o in outside:
        if o["match"] == "no_data":
            base_note = "库中无该基金持仓数据，无法归类"
        else:
            base_note = f"不属于本组合任一赛道（最高相似度 {o['sim']}）"
        if mode == "sleeve":
            action, amount = "keep", 0.0
            note = base_note + "，子仓位模式下保留不动（如属其它策略请在对应预设里管理）"
        else:
            action, amount = "exit", round(-o["market_value"], 2)
            note = base_note + "，整盘模式建议清仓释放现金"
            sell_total += o["market_value"]
        rows.append({
            "cluster_id": None, "cluster_name": "赛道外",
            "weight": 0.0, "target": 0.0, "actual": o["market_value"], "pnl": o["pnl"],
            "target_fund": {"code": o["code"], "name": o["name"]},
            "user_funds": [o], "match": o["match"], "sim": o["sim"],
            "action": action, "amount": amount, "note": note,
        })

    # 5. 现金配平：买入需求 > 可投（现金 + 卖出释放）时，所有买入等比缩减（不借钱）
    available = cash + sell_total
    want_buy = sum(amt for _, amt in buys)
    scaled = False
    buy_total = 0.0
    if want_buy > available + 1e-6 and want_buy > 0:
        scaled = True
        scale = available / want_buy
        for idx, amt in buys:
            new_amt = round(amt * scale, 2)
            if new_amt < MIN_TRADE_YUAN:   # 缩到不足起投 → 暂缓
                rows[idx]["action"] = "hold"
                rows[idx]["amount"] = 0.0
                rows[idx]["note"] += "（本轮资金不足，暂缓建/加仓）"
            else:
                rows[idx]["amount"] = new_amt
                buy_total += new_amt
    else:
        for idx, amt in buys:
            rows[idx]["amount"] = round(amt, 2)
            buy_total += rows[idx]["amount"]

    leftover_cash = round(available - buy_total, 2)

    counts = {"open": 0, "add": 0, "trim": 0, "hold": 0, "exit": 0, "keep": 0}
    for r in rows:
        counts[r["action"]] = counts.get(r["action"], 0) + 1

    summary = {
        "mode": mode,
        "base_asset": round(base_asset, 2),     # 目标分配基准（子仓位=匹配+现金）
        "total_asset": round(held_total + cash, 2),
        "held_total": round(held_total, 2),
        "matched_total": round(matched_total, 2),
        "cash": round(cash, 2),
        "outside_value": round(outside_value, 2),
        "buy_total": round(buy_total, 2),
        "sell_total": round(sell_total, 2),
        "leftover_cash": leftover_cash,
        "band": band, "scaled": scaled,
        **pnl_ctx,                       # 有成本部分的未实现盈亏/收益率（仅展示）
        "counts": counts,
    }
    meta = {
        "n_target_clusters": len(target_items),
        "match_counts": match_counts,
        "outside_count": len(outside),
    }
    return {"rows": rows, "summary": summary, "meta": meta}


def _reconcile_swap(target_items, per_actual, per_cost, per_cost_full, cluster_user_funds,
                    outside, cash, band, held_total, matched_total, outside_value,
                    match_counts, pnl_ctx) -> dict:
    """智能换仓：sleeve 口径定各赛道目标，按「现金→赛道外(小额优先)→超配减仓」优先级把
    低配缺口逐笔配对到资金来源，产出「卖 A → 买 B」换仓流水（transfers）。

    取向：尽量不动赛道内已有持仓——超配赛道仅在现金+赛道外不足以补低配时才减；赛道外按
    小额优先卖（顺带清理零碎仓、保留大额底仓），够补即止、不强制全清。
    """
    base_asset = matched_total + cash
    band_yuan = band * base_asset

    # 1. 逐赛道定目标，拆出「低配缺口(needs)」与「超配可减(trims)」，先全部建为 hold 行
    cluster_rows: dict[int, dict] = {}
    needs: list[dict] = []
    trims: list[dict] = []
    for it in target_items:
        cid = it["cluster_id"]
        weight = float(it.get("weight") or 0.0)
        target = weight * base_asset
        actual = per_actual.get(cid, 0.0)
        diff = target - actual
        user_funds = sorted(cluster_user_funds.get(cid, []),
                            key=lambda x: x["market_value"], reverse=True)
        rep = it.get("fund") or {}
        biggest = user_funds[0] if user_funds else None
        cl_pnl = round(actual - per_cost[cid], 2) if per_cost_full.get(cid) else None
        name = it.get("cluster_name", "")
        row = {
            "cluster_id": cid, "cluster_name": name,
            "weight": round(weight, 4), "target": round(target, 2),
            "actual": round(actual, 2), "pnl": cl_pnl, "user_funds": user_funds,
            "target_fund": {"code": (biggest or rep).get("code", ""),
                            "name": (biggest or rep).get("name", "")},
            "match": biggest["match"] if biggest else None,
            "sim": biggest["sim"] if biggest else None,
            "action": "hold", "amount": 0.0,
            "note": "已在目标 ± 缓冲带内，保持不动（抗噪）",
        }
        cluster_rows[cid] = row
        if abs(diff) <= band_yuan or abs(diff) < MIN_TRADE_YUAN:
            continue
        if diff > 0:
            is_open = actual < MIN_TRADE_YUAN
            to = rep if is_open else biggest
            if is_open:
                row["target_fund"] = {"code": rep.get("code", ""), "name": rep.get("name", "")}
            needs.append({"cid": cid, "gap": diff, "is_open": is_open,
                          "to_code": to.get("code", ""), "to_name": to.get("name", ""),
                          "cluster_name": name})
        else:
            trims.append({"cid": cid, "surplus": -diff, "cluster_name": name,
                          "from_code": biggest["code"], "from_name": biggest["name"]})

    # 2. 来源队列（优先级）：现金 → 赛道外(小额优先) → 超配减仓(超配多者优先)
    sources: list[dict] = []
    if cash >= MIN_TRADE_YUAN:
        sources.append({"type": "cash", "code": "", "name": "可投现金",
                        "cluster": "现金", "avail": cash})
    for o in sorted(outside, key=lambda x: x["market_value"]):
        if o["market_value"] >= MIN_TRADE_YUAN:
            sources.append({"type": "outside", "code": o["code"], "name": o["name"],
                            "cluster": "赛道外", "avail": o["market_value"]})
    for t in sorted(trims, key=lambda x: -x["surplus"]):
        sources.append({"type": "trim", "code": t["from_code"], "name": t["from_name"],
                        "cluster": t["cluster_name"], "avail": t["surplus"], "cid": t["cid"]})

    # 3. 配对：缺口大者优先，从来源队列顺序取钱，逐笔记 transfer
    transfers: list[dict] = []
    used_cash = 0.0
    used_outside: dict[str, float] = {}
    used_trim: dict[int, float] = {}
    si = 0
    for need in sorted(needs, key=lambda x: -x["gap"]):
        remain = need["gap"]
        while remain >= MIN_TRADE_YUAN and si < len(sources):
            s = sources[si]
            take = min(remain, s["avail"])
            if take >= MIN_TRADE_YUAN:
                transfers.append({
                    "from_type": s["type"], "from_code": s["code"], "from_name": s["name"],
                    "from_cluster": s["cluster"], "to_code": need["to_code"],
                    "to_name": need["to_name"], "to_cluster": need["cluster_name"],
                    "to_action": "open" if need["is_open"] else "add", "amount": round(take, 2),
                })
                if s["type"] == "cash":
                    used_cash += take
                elif s["type"] == "outside":
                    used_outside[s["code"]] = used_outside.get(s["code"], 0.0) + take
                else:
                    used_trim[s["cid"]] = used_trim.get(s["cid"], 0.0) + take
                remain -= take
                s["avail"] -= take
            if s["avail"] < MIN_TRADE_YUAN:
                si += 1
        need["filled"] = round(need["gap"] - remain, 2)

    # 4. 回填 needs/trims 的 action/amount
    filled_by_cid = {n["cid"]: n for n in needs}
    for cid, n in filled_by_cid.items():
        row = cluster_rows[cid]
        if n["filled"] < MIN_TRADE_YUAN:
            row["action"] = "hold"
            row["amount"] = 0.0
            row["note"] = "低配，但本轮可动用资金已用尽，暂缓补仓"
            continue
        row["action"] = "open" if n["is_open"] else "add"
        row["amount"] = n["filled"]
        verb = "建仓" if n["is_open"] else "加仓"
        row["note"] = f"低配，建议{verb}「{n['to_name']}」"
        if n["filled"] < n["gap"] - 1:
            short = round(n["gap"] - n["filled"], 2)
            row["note"] += f"（资金有限，距目标还差约 {short:,.0f} 元，未完全到位）"
    for t in trims:
        cid = t["cid"]
        row = cluster_rows[cid]
        used = used_trim.get(cid, 0.0)
        if used >= MIN_TRADE_YUAN:
            row["action"] = "trim"
            row["amount"] = round(-used, 2)
            row["note"] = f"超配，且现金/赛道外不足，减仓「{t['from_name']}」补低配"
        else:
            row["action"] = "hold"
            row["amount"] = 0.0
            row["note"] = "超配，但已用现金/赛道外补足低配，暂不减（尽量不动赛道内）"

    rows = list(cluster_rows.values())

    # 5. 赛道外行：被动用的标卖出（部分/全部），未动用的保留
    for o in outside:
        sold = used_outside.get(o["code"], 0.0)
        full = sold >= o["market_value"] - 1
        if sold >= MIN_TRADE_YUAN:
            action = "exit" if full else "trim"
            note = (f"赛道外，{'清仓' if full else '部分卖出'}用于补低配赛道"
                    f"（优先动用赛道外）")
            amount = round(-sold, 2)
        else:
            action, amount = "keep", 0.0
            note = "赛道外，本轮无需动用，保留不动"
        rows.append({
            "cluster_id": None, "cluster_name": "赛道外", "weight": 0.0, "target": 0.0,
            "actual": o["market_value"], "pnl": o["pnl"],
            "target_fund": {"code": o["code"], "name": o["name"]},
            "user_funds": [o], "match": o["match"], "sim": o["sim"],
            "action": action, "amount": amount, "note": note,
        })

    # 6. 汇总
    from_cash = round(used_cash, 2)
    from_outside = round(sum(used_outside.values()), 2)
    from_trim = round(sum(used_trim.values()), 2)
    buy_total = round(sum(t["amount"] for t in transfers), 2)
    sell_total = round(from_outside + from_trim, 2)
    leftover_cash = round(cash - from_cash, 2)
    counts = {"open": 0, "add": 0, "trim": 0, "hold": 0, "exit": 0, "keep": 0}
    for r in rows:
        counts[r["action"]] = counts.get(r["action"], 0) + 1

    summary = {
        "mode": "swap",
        "base_asset": round(base_asset, 2),
        "total_asset": round(held_total + cash, 2),
        "held_total": round(held_total, 2),
        "matched_total": round(matched_total, 2),
        "cash": round(cash, 2),
        "outside_value": round(outside_value, 2),
        "buy_total": buy_total, "sell_total": sell_total,
        "leftover_cash": leftover_cash,
        "from_cash": from_cash, "from_outside": from_outside, "from_trim": from_trim,
        "band": band, "scaled": False,
        **pnl_ctx, "counts": counts,
    }
    meta = {
        "n_target_clusters": len(target_items),
        "match_counts": match_counts,
        "outside_count": len(outside),
        "transfer_count": len(transfers),
    }
    return {"rows": rows, "summary": summary, "meta": meta, "transfers": transfers}
