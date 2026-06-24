"""实盘对账核心：把③簇级目标权重落到用户真实持仓上，按赛道算每笔加/减/建多少钱，
并产出「卖 A → 买 B」换仓清单 + 「加满还差多少现金」。

设计取向（用户拍板）：
- **极致还原「目标标的 + 目标比例」**：每条赛道（簇）不仅总仓位要对齐，簇内还必须收敛到
  ③选出的**目标基金（代表基金）**。簇内持有的非目标基金（底层不同的另一只基金）即便收益更高，
  也一律卖出换成目标基金。判定"是不是目标基金"按**去份额后缀的主体名**：与代表基金同名的
  A/C 份额（底层同一只）视为已达标、不强制换份额；只有底层真不同的才算非目标、要替换。
- **标的归一与「量」正交**：是不是目标基金（标的）与赛道仓位够不够（量）分开处理——
    · 标的：簇内非目标基金**无条件清空**，不受缓冲带 / 超配开关影响；
    · 量  ：赛道总仓位仍按缓冲带 + 两开关判定加/减，缓冲带只抗"量"的噪声。
- **两个正交开关 + 现金兜底**，覆盖用户对"量"的四类操作意图：
    · ``sell_outside``  赛道外基金动不动（保留 / 可卖去补缺口）
    · ``trim_overflow`` 赛道内超配减不减（不减只能往上加 / 可减则削峰填谷）
  现金永远是最后兜底（尽量不用现金），且**数额由系统反推**（"加满还差多少"），不需用户预填。
- **目标盘子 BASE 由「超配减不减」决定**：
    · 可减 → BASE = 赛道内现额 (+ 若赛道外可卖则叠加赛道外)  —— 削峰填谷，理论零追加
    · 不减 → BASE = max(各赛道现额 ÷ 目标比)               —— 放大到最超配赛道达标
- **资金来源优先级**（尽量不用现金）：赛道内超配减仓（先卖非目标基金、再动正主）→ 赛道外卖出
  （小额优先）→ 追加现金兜底。簇内剩余的非目标基金等额换成本簇目标基金（不出簇、不改簇总仓位）。
- **盈亏只展示不参与决策**：成本入库后逐赛道/整体算未实现盈亏与收益率，但目标权重、加减判断、
  标的替换完全不看盈亏（避免「赚了落袋、亏了死扛」的处置效应，也避免"非目标但赚钱就留着"）。
"""
from __future__ import annotations

import math

from app.cluster.algo.dedup import _base_name
from app.reconcile.algo import classify

DEFAULT_BAND = 0.03      # 缓冲带：盘子的 3 个百分点（绝对），对「按金额」最直观；仅约束"量"
MIN_TRADE_YUAN = 100.0   # 小于此金额的动作忽略（抗噪 + 申赎门槛）


def _pnl(mv: float, cost) -> float | None:
    """未实现盈亏 = 市值 − 成本；成本缺失返回 None。"""
    if cost is None:
        return None
    return round(mv - float(cost), 2)


def _is_target(f: dict, rep_code: str, rep_base: str) -> bool:
    """该持仓是否就是簇的目标基金：代码命中代表基金，或去份额后缀的主体名相同
    （A/C 份额，底层同一只 → 视为已达标，不强制换份额）。"""
    return f["code"] == rep_code or (bool(rep_base) and _base_name(f["name"]) == rep_base)


def reconcile(target_items: list[dict], holdings: list[dict],
              clusters: list[dict], ind_idx: dict,
              band: float = DEFAULT_BAND,
              sell_outside: bool = False, trim_overflow: bool = True) -> dict:
    """对账。见模块文档。返回 ``{"rows", "summary", "meta", "transfers"}``。"""
    code2cluster = classify.build_code_to_cluster(clusters)
    name2cluster = classify.build_name_index(clusters)
    cluster_vecs = classify.cluster_vectors(clusters)
    # 簇内 top3 行业（带占比）：供前端在赛道列逐行业展示「名称+占比」
    cid2industries = {
        c["cluster_id"]: [{"label": i["label"], "ratio": i["ratio"]}
                          for i in (c.get("top_industries") or [])[:3]]
        for c in clusters
    }

    # 1. 归类：每只持仓 → 赛道（A/C 同基金落同一赛道、市值/成本相加），失败入 outside
    per_actual: dict[int, float] = {}
    per_cost: dict[int, float] = {}        # 该赛道有成本的部分累计
    per_cost_full: dict[int, bool] = {}    # 该赛道是否每只都有成本
    cluster_user_funds: dict[int, list[dict]] = {}
    outside: list[dict] = []
    nav_by_code: dict[str, float] = {}     # 转出基金最新单位净值 → 估算转出份额
    match_counts = {"exact": 0, "name": 0, "similar": 0, "outside": 0, "no_data": 0}
    held_total = cost_total = pnl_known_mv = 0.0
    has_any_cost = False

    for h in holdings:
        code = str(h.get("fund_code") or "").strip()
        mv = float(h.get("market_value") or 0.0)
        cost = h.get("cost")
        cost = float(cost) if cost is not None else None
        name = h.get("fund_name") or ""
        nav = h.get("latest_nav")
        if code and nav:
            nav_by_code[code] = float(nav)
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

    weights = {it["cluster_id"]: float(it.get("weight") or 0.0) for it in target_items}

    # 2. 目标盘子 BASE
    if trim_overflow:
        # 可减：削峰填谷。盘子=赛道内现额(+赛道外可卖则叠加)，理论无需追加现金
        base_asset = matched_total + (outside_value if sell_outside else 0.0)
    else:
        # 不减：放大到「最超配赛道正好达标」，其余靠买入补齐
        ratios = [per_actual.get(cid, 0.0) / w for cid, w in weights.items() if w > 0]
        base_asset = max([matched_total, *ratios]) if ratios else matched_total
    band_yuan = band * base_asset

    # 3. 逐赛道：定目标盘子 + 把簇内持仓拆「目标基金 / 非目标基金」。
    #    量（缺口 needs / 超配 trims）按簇总市值 + 缓冲带判定；非目标基金一律要清空（与量正交）。
    cluster_rows: dict[int, dict] = {}
    needs: list[dict] = []
    trims: list[dict] = []
    info: dict[int, dict] = {}     # 逐簇暂存：目标基金落点 + 非目标列表 + 超配额度，供第 4 步资金流用
    for seq, it in enumerate(target_items, start=1):
        cid = it["cluster_id"]
        weight = weights[cid]
        target = weight * base_asset
        actual = per_actual.get(cid, 0.0)
        diff = target - actual
        rep = it.get("fund") or {}
        rep_code = (rep.get("code") or "").strip()
        rep_base = _base_name(rep.get("name") or "")
        user_funds = sorted(cluster_user_funds.get(cid, []),
                            key=lambda x: x["market_value"], reverse=True)
        target_held = [f for f in user_funds if _is_target(f, rep_code, rep_base)]
        nontarget = [f for f in user_funds if not _is_target(f, rep_code, rep_base)]
        target_held_mv = sum(f["market_value"] for f in target_held)
        # 加仓/建仓落点：已持目标份额 → 加到它（与代表同码优先，否则任一 A/C，不换份额）；
        # 簇内完全没有目标基金 → 用代表基金建仓（即便簇内有非目标基金、它们将被卖出）。
        if target_held:
            add_to = next((f for f in target_held if f["code"] == rep_code), target_held[0])
            to_code, to_name = add_to["code"], add_to["name"]
            to_match, to_sim, is_open = add_to.get("match"), add_to.get("sim"), False
        else:
            to_code, to_name = rep_code, rep.get("name", "")
            to_match, to_sim, is_open = "exact", 1.0, True
        cl_pnl = round(actual - per_cost[cid], 2) if per_cost_full.get(cid) else None
        name = it.get("cluster_name", "")
        row = {
            "cluster_id": cid, "cluster_name": name, "seq": seq,
            "industries": cid2industries.get(cid, []),
            "weight": round(weight, 4), "target": round(target, 2),
            "actual": round(actual, 2),
            "actual_ratio": round(actual / held_total, 4) if held_total else 0.0,
            "pnl": cl_pnl, "user_funds": user_funds,
            "target_fund": {"code": to_code, "name": to_name},
            "match": to_match, "sim": to_sim,
            "action": "hold", "amount": 0.0,
            "note": "已在目标 ± 缓冲带内，保持不动（抗噪）",
        }
        cluster_rows[cid] = row
        info[cid] = {"to_code": to_code, "to_name": to_name, "is_open": is_open,
                     "cluster_name": name, "nontarget": nontarget,
                     "rep_code": rep_code, "rep_name": rep.get("name", ""),
                     "target_held_mv": target_held_mv, "surplus": 0.0}
        in_band = abs(diff) <= band_yuan or abs(diff) < MIN_TRADE_YUAN
        if diff > 0 and not in_band:
            needs.append({"cid": cid, "gap": diff, "is_open": is_open,
                          "to_code": to_code, "to_name": to_name, "cluster_name": name})
        elif diff < 0 and not in_band and trim_overflow:
            info[cid]["surplus"] = -diff
            trims.append({"cid": cid, "surplus": -diff, "cluster_name": name})
        # 否则量上不动（hold）；簇内非目标基金仍会在第 4/6 步被替换

    # 4. 供血队列（优先级，尽量不用现金）：超配簇卖出(先非目标、后正主) → 赛道外(小额优先) → 现金兜底。
    #    每只非目标基金登记「可借出额 cap」（仅超配簇、且在超配额度内）；配对后未借出的回退为簇内替换。
    sources: list[dict] = []
    all_nontarget: list[dict] = []
    for t in sorted(trims, key=lambda x: -x["surplus"]):
        cid = t["cid"]; d = info[cid]
        budget = t["surplus"]      # 该簇要减出的总额，优先由非目标基金提供
        for f in sorted(d["nontarget"], key=lambda x: -x["market_value"]):
            mv = f["market_value"]
            if mv <= 0:
                continue
            cap = min(mv, budget)
            budget = max(0.0, budget - cap)
            nt = {"cid": cid, "from_code": f["code"], "from_name": f["name"],
                  "to_code": d["to_code"], "to_name": d["to_name"], "is_open": d["is_open"],
                  "cluster_name": d["cluster_name"], "total": mv, "borrowed": 0.0}
            all_nontarget.append(nt)
            if cap >= MIN_TRADE_YUAN:
                sources.append({"type": "trim", "cid": cid, "code": f["code"], "name": f["name"],
                                "cluster": d["cluster_name"], "avail": cap, "nt": nt})
        # 非目标基金不足以覆盖超配额度 → 减用户实际持有的那只目标份额（A/C 不换份额，故用 to_code
        # 而非代表基金代码；此分支必有 target_held，否则非目标已足够覆盖 surplus、budget 归零）
        if budget >= MIN_TRADE_YUAN:
            sources.append({"type": "trim", "cid": cid, "code": d["to_code"], "name": d["to_name"],
                            "cluster": d["cluster_name"], "avail": budget, "nt": None})
    # 非超配簇（标配/低配）的非目标基金：不供血，全额等额换成本簇目标基金
    trim_cids = {t["cid"] for t in trims}
    for cid, d in info.items():
        if cid in trim_cids:
            continue
        for f in d["nontarget"]:
            if f["market_value"] <= 0:
                continue
            all_nontarget.append({
                "cid": cid, "from_code": f["code"], "from_name": f["name"],
                "to_code": d["to_code"], "to_name": d["to_name"], "is_open": d["is_open"],
                "cluster_name": d["cluster_name"], "total": f["market_value"], "borrowed": 0.0})
    if sell_outside:
        for o in sorted(outside, key=lambda x: x["market_value"]):
            if o["market_value"] >= MIN_TRADE_YUAN:
                sources.append({"type": "outside", "cid": None, "code": o["code"], "name": o["name"],
                                "cluster": "赛道外", "avail": o["market_value"], "nt": None})
    # 不减超配时（情况3/4），剩余缺口全靠追加现金兜底（无限源，用多少即"加满需要多少"）
    if not trim_overflow:
        sources.append({"type": "add_cash", "cid": None, "code": "", "name": "建议追加现金",
                        "cluster": "追加现金", "avail": math.inf, "nt": None})

    # 5. 配对：缺口大者优先，从来源队列顺序取钱，逐笔记 transfer
    transfers: list[dict] = []
    used_outside: dict[str, float] = {}
    used_trim: dict[int, float] = {}     # 超配簇借出（卖非目标 + 卖正主）合计 → row.trim / from_trim
    used_add_cash = 0.0
    si = 0
    for need in sorted(needs, key=lambda x: -x["gap"]):
        remain = need["gap"]
        while remain >= MIN_TRADE_YUAN and si < len(sources):
            s = sources[si]
            take = min(remain, s["avail"])
            if take >= MIN_TRADE_YUAN:
                amount = round(take, 2)
                tr = {
                    "from_type": s["type"], "from_code": s["code"], "from_name": s["name"],
                    "from_cluster": s["cluster"], "to_code": need["to_code"],
                    "to_name": need["to_name"], "to_cluster": need["cluster_name"],
                    "to_action": "open" if need["is_open"] else "add", "amount": amount,
                }
                # 转出份额（券商「基金转换」按份额操作）：金额 ÷ 转出基金最新单位净值。
                from_nav = nav_by_code.get(s["code"])
                if s["code"] and from_nav:
                    tr["from_nav"] = round(from_nav, 4)
                    tr["from_shares"] = round(amount / from_nav, 2)
                transfers.append(tr)
                if s["type"] == "outside":
                    used_outside[s["code"]] = used_outside.get(s["code"], 0.0) + take
                elif s["type"] == "trim":
                    used_trim[s["cid"]] = used_trim.get(s["cid"], 0.0) + take
                    if s["nt"] is not None:
                        s["nt"]["borrowed"] += take
                else:
                    used_add_cash += take
                remain -= take
                s["avail"] -= take
            if s["avail"] < MIN_TRADE_YUAN:
                si += 1
        need["filled"] = round(need["gap"] - remain, 2)

    # 6. 簇内标的替换：每只非目标基金未借出的部分，等额换成本簇目标基金（不出簇、不改簇总仓位）
    replace_internal = 0.0
    has_replace: dict[int, bool] = {}
    for nt in all_nontarget:
        left = round(nt["total"] - nt["borrowed"], 2)
        if left < MIN_TRADE_YUAN or nt["from_code"] == nt["to_code"]:
            continue
        tr = {
            "from_type": "replace", "from_code": nt["from_code"], "from_name": nt["from_name"],
            "from_cluster": nt["cluster_name"], "to_code": nt["to_code"], "to_name": nt["to_name"],
            "to_cluster": nt["cluster_name"], "to_action": "open" if nt["is_open"] else "add",
            "amount": left,
        }
        from_nav = nav_by_code.get(nt["from_code"])
        if from_nav:
            tr["from_nav"] = round(from_nav, 4)
            tr["from_shares"] = round(left / from_nav, 2)
        transfers.append(tr)
        replace_internal += left
        has_replace[nt["cid"]] = True

    # 7. 回填 needs / trims 的 action/amount，并对有标的替换的簇补一句说明
    any_underfill = False
    for need in needs:
        cid = need["cid"]; row = cluster_rows[cid]
        filled = need["filled"]
        if filled < MIN_TRADE_YUAN:
            row["action"] = "hold"; row["amount"] = 0.0
            row["note"] = "低配，但本轮可动用资金已用尽，暂缓补仓"
            any_underfill = True
            continue
        row["action"] = "open" if need["is_open"] else "add"
        row["amount"] = filled
        verb = "建仓" if need["is_open"] else "加仓"
        row["note"] = f"低配，建议{verb}「{need['to_name']}」"
        if filled < need["gap"] - 1:
            short = round(need["gap"] - filled, 2)
            row["note"] += f"（资金有限，距目标还差约 {short:,.0f} 元，未完全到位）"
            any_underfill = True
    for t in trims:
        cid = t["cid"]; row = cluster_rows[cid]
        used = used_trim.get(cid, 0.0)
        if used >= MIN_TRADE_YUAN:
            row["action"] = "trim"; row["amount"] = round(-used, 2)
            row["note"] = "超配，减仓（先卖非目标基金）用于补低配赛道"
        else:
            row["action"] = "hold"; row["amount"] = 0.0
            row["note"] = "超配，但低配已被其它资金补足，本轮暂不减"
    # 量上不动（hold）但簇内有非目标替换的，覆盖说明；有加减的则追加一句
    for cid, row in cluster_rows.items():
        if not has_replace.get(cid):
            continue
        tn = info[cid]["to_name"]
        if row["action"] == "hold" and row["amount"] == 0.0:
            row["note"] = f"簇内非目标基金已换成目标基金「{tn}」，总仓位不变"
        else:
            row["note"] += f"；并把簇内剩余非目标基金换成「{tn}」"

    rows = list(cluster_rows.values())

    # 8. 赛道外行：被动用的标卖出（部分/全部），未动用的保留
    for o in outside:
        sold = used_outside.get(o["code"], 0.0)
        full = sold >= o["market_value"] - 1
        if o["match"] == "no_data":
            base_note = "库中无该基金持仓数据，无法归类"
        else:
            base_note = f"不属于本组合任一赛道（最高相似度 {o['sim']}）"
        if sold >= MIN_TRADE_YUAN:
            action = "exit" if full else "trim"
            amount = round(-sold, 2)
            note = base_note + f"，{'清仓' if full else '部分卖出'}用于补低配赛道"
        else:
            action, amount = "keep", 0.0
            note = base_note + ("，保留不动" if not sell_outside else "，本轮无需动用，保留不动")
        rows.append({
            "cluster_id": None, "cluster_name": "赛道外", "seq": None, "industries": [],
            "weight": 0.0, "target": 0.0,
            "actual": o["market_value"],
            "actual_ratio": round(o["market_value"] / held_total, 4) if held_total else 0.0,
            "pnl": o["pnl"],
            "target_fund": {"code": o["code"], "name": o["name"]},
            "user_funds": [o], "match": o["match"], "sim": o["sim"],
            "action": action, "amount": amount, "note": note,
        })

    # 9. 汇总
    from_trim = round(sum(used_trim.values()), 2)
    from_outside = round(sum(used_outside.values()), 2)
    cash_needed = round(used_add_cash, 2)
    # buy_total：真正补低配赛道的外部买入（不含簇内等额替换），与 sell_total + cash 守恒
    buy_total = round(sum(t["amount"] for t in transfers if t["from_type"] != "replace"), 2)
    sell_total = round(from_trim + from_outside, 2)
    replace_total = round(replace_internal, 2)        # 簇内标的替换（等额换手）总额
    counts = {"open": 0, "add": 0, "trim": 0, "hold": 0, "exit": 0, "keep": 0}
    for r in rows:
        counts[r["action"]] = counts.get(r["action"], 0) + 1

    summary = {
        "sell_outside": sell_outside,
        "trim_overflow": trim_overflow,
        "base_asset": round(base_asset, 2),         # 目标分配盘子
        "total_asset": round(held_total + cash_needed, 2),   # 加满后总资产
        "held_total": round(held_total, 2),
        "matched_total": round(matched_total, 2),
        "outside_value": round(outside_value, 2),
        "buy_total": buy_total, "sell_total": sell_total,
        "from_trim": from_trim, "from_outside": from_outside,
        "cash_needed": cash_needed,                 # 系统反推「加满还差多少现金」
        "replace_total": replace_total,             # 簇内标的替换（卖非目标→买目标，等额）总额
        "band": band, "scaled": any_underfill,
        **pnl_ctx,                                  # 有成本部分的未实现盈亏/收益率（仅展示）
        "counts": counts,
    }
    meta = {
        "n_target_clusters": len(target_items),
        "match_counts": match_counts,
        "outside_count": len(outside),
        "transfer_count": len(transfers),
        "replace_count": sum(1 for t in transfers if t["from_type"] == "replace"),
    }
    return {"rows": rows, "summary": summary, "meta": meta, "transfers": transfers}
