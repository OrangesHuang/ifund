"""实盘对账核心：把③簇级目标权重落到用户真实持仓上，按赛道算每笔加/减/建多少钱，
并产出「卖 A → 买 B」换仓清单 + 「加满还差多少现金」。

设计取向（用户拍板）：
- **按赛道（簇）对齐**，不按基金代码精确匹配——只看每个赛道总仓位够不够，不强制把手里的
  基金换成系统选的代表基金（低换手、连贯，契合「不折腾」哲学）。
- **两个正交开关 + 现金兜底**，覆盖用户的四类操作意图：
    · ``sell_outside``  赛道外基金动不动（保留 / 可卖去补缺口）
    · ``trim_overflow`` 赛道内超配减不减（不减只能往上加 / 可减则削峰填谷）
  现金永远是最后兜底（尽量不用现金），且**数额由系统反推**（"加满还差多少"），不需用户预填。
- **目标盘子 BASE 由「超配减不减」决定**：
    · 可减 → BASE = 赛道内现额 (+ 若赛道外可卖则叠加赛道外)  —— 削峰填谷，理论零追加
    · 不减 → BASE = max(各赛道现额 ÷ 目标比)               —— 放大到最超配赛道达标
  ⚠️ 严重超配时「不减」会把盘子撑得很大、追加现金需求很高，这正是要明白展示给用户的信号。
- **资金来源优先级**（尽量不用现金）：赛道内超配减仓 → 赛道外卖出（小额优先）→ 追加现金兜底。
- **盈亏只展示不参与决策**：成本入库后逐赛道/整体算未实现盈亏与收益率，但目标权重与加减判断
  完全不看盈亏（避免「赚了落袋、亏了死扛」的处置效应）。

四类组合 = 两开关的 2×2：
    情况1 不动赛道外 + 超配可减 → 内部削峰填谷（最省，集中度不变）
    情况2 可卖赛道外 + 超配可减 → 赛道外全投入 + 削峰填谷
    情况3 不动赛道外 + 超配不减 → 纯加现金加满
    情况4 可卖赛道外 + 超配不减 → 卖赛道外补，超配不碰，不足加现金
"""
from __future__ import annotations

import math

from app.reconcile.algo import classify

DEFAULT_BAND = 0.03      # 缓冲带：盘子的 3 个百分点（绝对），对「按金额」最直观
MIN_TRADE_YUAN = 100.0   # 小于此金额的动作忽略（抗噪 + 申赎门槛）

# 与预设的贴近程度：代码命中 > 名称命中（A/C 份额）> 行业相似（杂牌）。值越小越「正主」。
MATCH_RANK = {"exact": 0, "name": 1, "similar": 2, "outside": 3}


def _pnl(mv: float, cost) -> float | None:
    """未实现盈亏 = 市值 − 成本；成本缺失返回 None。"""
    if cost is None:
        return None
    return round(mv - float(cost), 2)


def _pick_fund(funds: list[dict], prefer_aligned: bool) -> dict | None:
    """从赛道内持仓里选一只「操作基金」（向预设收敛，不看盈亏）。

    ``prefer_aligned=True``  → 选最贴近预设的正主（代码/名称命中优先），用于加仓/代表；
    ``prefer_aligned=False`` → 优先动相似度凑进来的杂牌，用于减仓资金来源（保住正主）。
    同一贴近档内按市值大优先（可动额度大、换手少）。
    """
    if not funds:
        return None
    def rank(f: dict) -> int:
        return MATCH_RANK.get(f.get("match"), 3)
    if prefer_aligned:
        return min(funds, key=lambda f: (rank(f), -f["market_value"]))
    return min(funds, key=lambda f: (-rank(f), -f["market_value"]))


def reconcile(target_items: list[dict], holdings: list[dict],
              clusters: list[dict], ind_idx: dict,
              band: float = DEFAULT_BAND,
              sell_outside: bool = False, trim_overflow: bool = True) -> dict:
    """对账。见模块文档。返回 ``{"rows", "summary", "meta", "transfers"}``。"""
    code2cluster = classify.build_code_to_cluster(clusters)
    name2cluster = classify.build_name_index(clusters)
    cluster_vecs = classify.cluster_vectors(clusters)

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

    # 3. 逐赛道定目标，拆出「低配缺口(needs)」与「超配可减(trims)」，先全部建为 hold 行
    cluster_rows: dict[int, dict] = {}
    needs: list[dict] = []
    trims: list[dict] = []
    for it in target_items:
        cid = it["cluster_id"]
        weight = weights[cid]
        target = weight * base_asset
        actual = per_actual.get(cid, 0.0)
        diff = target - actual
        user_funds = sorted(cluster_user_funds.get(cid, []),
                            key=lambda x: x["market_value"], reverse=True)
        rep = it.get("fund") or {}
        # 向预设收敛：加仓/代表选正主（add_target），减仓优先动杂牌（trim_source）
        add_target = _pick_fund(user_funds, prefer_aligned=True)
        trim_source = _pick_fund(user_funds, prefer_aligned=False)
        cl_pnl = round(actual - per_cost[cid], 2) if per_cost_full.get(cid) else None
        name = it.get("cluster_name", "")
        row = {
            "cluster_id": cid, "cluster_name": name,
            "weight": round(weight, 4), "target": round(target, 2),
            "actual": round(actual, 2), "pnl": cl_pnl, "user_funds": user_funds,
            "target_fund": {"code": (add_target or rep).get("code", ""),
                            "name": (add_target or rep).get("name", "")},
            "match": add_target["match"] if add_target else None,
            "sim": add_target["sim"] if add_target else None,
            "action": "hold", "amount": 0.0,
            "note": "已在目标 ± 缓冲带内，保持不动（抗噪）",
        }
        cluster_rows[cid] = row
        if abs(diff) <= band_yuan or abs(diff) < MIN_TRADE_YUAN:
            continue
        if diff > 0:
            is_open = actual < MIN_TRADE_YUAN
            to = rep if is_open else add_target
            if is_open:
                row["target_fund"] = {"code": rep.get("code", ""), "name": rep.get("name", "")}
            needs.append({"cid": cid, "gap": diff, "is_open": is_open,
                          "to_code": to.get("code", ""), "to_name": to.get("name", ""),
                          "cluster_name": name})
        elif trim_overflow:   # 超配且允许减 → 优先减杂牌（trim_source），保住正主
            row["target_fund"] = {"code": trim_source["code"], "name": trim_source["name"]}
            row["match"], row["sim"] = trim_source.get("match"), trim_source.get("sim")
            trims.append({"cid": cid, "surplus": -diff, "cluster_name": name,
                          "from_code": trim_source["code"], "from_name": trim_source["name"]})
        # diff<0 且 trim_overflow=False：base 已放大到不会超配，理论不会到这里，保持 hold

    # 4. 来源队列（优先级，尽量不用现金）：超配减仓(超配多者优先) → 赛道外(小额优先) → 追加现金兜底
    sources: list[dict] = []
    if trim_overflow:
        for t in sorted(trims, key=lambda x: -x["surplus"]):
            sources.append({"type": "trim", "code": t["from_code"], "name": t["from_name"],
                            "cluster": t["cluster_name"], "avail": t["surplus"], "cid": t["cid"]})
    if sell_outside:
        for o in sorted(outside, key=lambda x: x["market_value"]):
            if o["market_value"] >= MIN_TRADE_YUAN:
                sources.append({"type": "outside", "code": o["code"], "name": o["name"],
                                "cluster": "赛道外", "avail": o["market_value"]})
    # 不减超配时（情况3/4），剩余缺口全靠追加现金兜底（无限源，用多少即"加满需要多少"）
    if not trim_overflow:
        sources.append({"type": "add_cash", "code": "", "name": "建议追加现金",
                        "cluster": "追加现金", "avail": math.inf})

    # 5. 配对：缺口大者优先，从来源队列顺序取钱，逐笔记 transfer
    transfers: list[dict] = []
    used_outside: dict[str, float] = {}
    used_trim: dict[int, float] = {}
    used_add_cash = 0.0
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
                if s["type"] == "outside":
                    used_outside[s["code"]] = used_outside.get(s["code"], 0.0) + take
                elif s["type"] == "trim":
                    used_trim[s["cid"]] = used_trim.get(s["cid"], 0.0) + take
                else:
                    used_add_cash += take
                remain -= take
                s["avail"] -= take
            if s["avail"] < MIN_TRADE_YUAN:
                si += 1
        need["filled"] = round(need["gap"] - remain, 2)

    # 6. 回填 needs / trims 的 action/amount
    any_underfill = False
    filled_by_cid = {n["cid"]: n for n in needs}
    for cid, n in filled_by_cid.items():
        row = cluster_rows[cid]
        if n["filled"] < MIN_TRADE_YUAN:
            row["action"] = "hold"
            row["amount"] = 0.0
            row["note"] = "低配，但本轮可动用资金已用尽，暂缓补仓"
            any_underfill = True
            continue
        row["action"] = "open" if n["is_open"] else "add"
        row["amount"] = n["filled"]
        verb = "建仓" if n["is_open"] else "加仓"
        row["note"] = f"低配，建议{verb}「{n['to_name']}」"
        if n["filled"] < n["gap"] - 1:
            short = round(n["gap"] - n["filled"], 2)
            row["note"] += f"（资金有限，距目标还差约 {short:,.0f} 元，未完全到位）"
            any_underfill = True
    for t in trims:
        cid = t["cid"]
        row = cluster_rows[cid]
        used = used_trim.get(cid, 0.0)
        if used >= MIN_TRADE_YUAN:
            row["action"] = "trim"
            row["amount"] = round(-used, 2)
            row["note"] = f"超配，减仓「{t['from_name']}」用于补低配赛道"
        else:
            row["action"] = "hold"
            row["amount"] = 0.0
            row["note"] = "超配，但低配已被其它资金补足，本轮暂不减"

    rows = list(cluster_rows.values())

    # 7. 赛道外行：被动用的标卖出（部分/全部），未动用的保留
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
            "cluster_id": None, "cluster_name": "赛道外", "weight": 0.0, "target": 0.0,
            "actual": o["market_value"], "pnl": o["pnl"],
            "target_fund": {"code": o["code"], "name": o["name"]},
            "user_funds": [o], "match": o["match"], "sim": o["sim"],
            "action": action, "amount": amount, "note": note,
        })

    # 8. 汇总
    from_trim = round(sum(used_trim.values()), 2)
    from_outside = round(sum(used_outside.values()), 2)
    cash_needed = round(used_add_cash, 2)
    buy_total = round(sum(t["amount"] for t in transfers), 2)
    sell_total = round(from_trim + from_outside, 2)
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
        "band": band, "scaled": any_underfill,
        **pnl_ctx,                                  # 有成本部分的未实现盈亏/收益率（仅展示）
        "counts": counts,
    }
    meta = {
        "n_target_clusters": len(target_items),
        "match_counts": match_counts,
        "outside_count": len(outside),
        "transfer_count": len(transfers),
    }
    return {"rows": rows, "summary": summary, "meta": meta, "transfers": transfers}
