"""preset 组：预设列表 / 详情 / 重建镜像快照。"""
from __future__ import annotations

import json
import sys

from app import db as database

from . import helpers, output


def cmd_list(args) -> None:
    rows = database.select("query_presets", {"user_id": f"eq.{args.user}", "order": "id.asc"})
    data = [{"id": r["id"], "name": r["name"],
             "snapshot_funds": helpers.snapshot_count(args.user, r["id"]),
             "created_at": r.get("created_at")} for r in rows]

    def txt(d):
        print(output.table([[x["id"], x["name"], x["snapshot_funds"], x["created_at"]] for x in d],
                           ["id", "名称", "镜像基金数", "创建时间"]))
    output.emit(data, args.json, txt)


def cmd_show(args) -> None:
    pf = helpers.resolve_preset(args.user, args.id, args.name)
    if not pf:
        print("未找到该预设", file=sys.stderr)
        sys.exit(1)
    filters = json.loads(pf.get("filters_json") or "{}")
    snap = database.select_one("fund_snapshots",
                               {"user_id": f"eq.{args.user}", "preset_id": f"eq.{pf['id']}"})
    items = json.loads(snap.get("items_json") or "[]") if snap else []
    data = {"id": pf["id"], "name": pf["name"], "filters": filters,
            "snapshot_funds": len(items),
            "snapshot_created_at": snap.get("created_at") if snap else None,
            "funds": [{"code": it.get("code"), "name": it.get("name")} for it in items]}

    def txt(d):
        print(f"#{d['id']} {d['name']}　镜像 {d['snapshot_funds']} 只"
              f"（{d['snapshot_created_at'] or '无快照'}）")
        print("筛选条件:", json.dumps(d["filters"], ensure_ascii=False))
        if d["funds"]:
            print(output.table([[f["code"], f["name"]] for f in d["funds"]], ["代码", "名称"]))
    output.emit(data, args.json, txt)


# fund_ai_analysis 可写字段及其约束（OpenClaw 经 `preset ai-set --data` 填充）
_AI_ENUMS = {
    "luck_verdict": {"solid", "mixed", "luck"},
    "concentration": {"single_bet", "focused", "diversified"},
    "fund_kind": {"subjective", "rotation", "sector"},
    "scale_risk": {"tiny", "small", "ok", "large"},
    "style_stability": {"stable", "volatile", "unproven"},
    "confidence": {"high", "medium", "low"},
}
_AI_INT_RANGE = {  # 字段: (最小, 最大)
    "rating": (0, 3), "recommend": (0, 1), "skill_score": (0, 100),
    "is_original": (0, 1), "is_comanaged": (0, 1),
}
_AI_TEXT = {"manager", "verdict", "skill_reason", "concentration_reason", "hard_thesis",
            "turnover_note", "model", "data_basis", "analyzed_at"}
_AI_FLOAT = {"tenure_years"}
_LUCK_CN = {"solid": "实力", "mixed": "中性", "luck": "运气"}
_CONC_CN = {"single_bet": "单押", "focused": "集中", "diversified": "分散"}
_KIND_CN = {"subjective": "主观", "rotation": "轮动", "sector": "赛道"}


def _coerce_ai_field(key: str, val):
    """按字段类型校验/归一一个 AI 分析字段；非法抛 ValueError。返回落库值。"""
    if key in _AI_ENUMS:
        if val not in _AI_ENUMS[key]:
            raise ValueError(f"{key} 取值须为 {sorted(_AI_ENUMS[key])}，收到 {val!r}")
        return val
    if key in _AI_INT_RANGE:
        lo, hi = _AI_INT_RANGE[key]
        iv = int(bool(val)) if isinstance(val, bool) else int(val)
        if not lo <= iv <= hi:
            raise ValueError(f"{key} 须在 [{lo},{hi}]，收到 {iv}")
        return iv
    if key in _AI_FLOAT:
        return float(val)
    if key == "tags":
        if isinstance(val, str):
            val = [val]
        if not isinstance(val, list):
            raise ValueError("tags 须为字符串数组")
        return json.dumps([str(t) for t in val], ensure_ascii=False)
    if key in _AI_TEXT:
        return None if val is None else str(val)
    raise ValueError(f"未知字段 {key!r}（允许：枚举{sorted(_AI_ENUMS)} / 整数{sorted(_AI_INT_RANGE)} / "
                     f"小数{sorted(_AI_FLOAT)} / 文本{sorted(_AI_TEXT)} / tags）")


def _read_data_arg(raw: str) -> dict:
    """--data 取 JSON：`-` 读 stdin，`@路径` 读文件，否则按字面 JSON 串解析。"""
    if raw == "-":
        raw = sys.stdin.read()
    elif raw.startswith("@"):
        with open(raw[1:], encoding="utf-8") as fh:
            raw = fh.read()
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("--data 顶层须是 JSON 对象")
    return obj


def cmd_ai_set(args) -> None:
    """写入/更新某基金的 AI 定性分析（部分字段 upsert：只改提供的字段，余者保留）。"""
    import datetime
    try:
        payload = _read_data_arg(args.data)
        fields = {k: _coerce_ai_field(k, v) for k, v in payload.items()}
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"数据无效：{exc}", file=sys.stderr)
        sys.exit(1)
    fields["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    fields.setdefault("analyzed_at", fields["updated_at"])

    exists = database.select_one("fund_ai_analysis", {"fund_code": f"eq.{args.code}"})
    if exists:
        database.update("fund_ai_analysis", {"fund_code": args.code}, fields)
    else:
        database.insert("fund_ai_analysis", {"fund_code": args.code, **fields})
    row = database.select_one("fund_ai_analysis", {"fund_code": f"eq.{args.code}"})

    def txt(d):
        print(f"✓ {args.code} AI 分析已{'更新' if exists else '写入'}"
              f"（{len(payload)} 字段）：{d.get('verdict') or '(无结论)'}")
    output.emit(row, args.json, txt)


_NA_LIKE = {"", "<na>", "nan", "none", "null", "n/a", "--"}


def _clean(v):
    """归一 NA：把 fetch 残留的 '<NA>'/'nan'/空串等当缺失返回 None。"""
    if v is None:
        return None
    if isinstance(v, str) and v.strip().lower() in _NA_LIKE:
        return None
    return v


def cmd_funds(args) -> None:
    """基于预设查询基金：列出该预设镜像内的基金 + 基础信息，可按 --code/--keyword 过滤。"""
    pf = helpers.resolve_preset(args.user, args.id, args.name)
    if not pf:
        print("未找到该预设", file=sys.stderr)
        sys.exit(1)
    snap = database.select_one("fund_snapshots",
                               {"user_id": f"eq.{args.user}", "preset_id": f"eq.{pf['id']}"})
    items = json.loads(snap.get("items_json") or "[]") if snap else []

    # 在预设镜像范围内过滤：--code 精确（逗号多只）、--keyword 模糊匹配名称/代码
    codes = set(helpers.csv_list(args.code))
    if codes:
        items = [it for it in items if it.get("code") in codes]
    kw = (args.keyword or "").strip().lower()
    if kw:
        items = [it for it in items
                 if kw in (it.get("name") or "").lower() or kw in (it.get("code") or "").lower()]

    # 一次性取这些基金的基础信息（无 detail 行的留空）
    detail_by_code: dict[str, dict] = {}
    item_codes = [it["code"] for it in items if it.get("code")]
    if item_codes:
        rows = database.select("fund_details",
                               {"fund_code": f"in.({','.join(item_codes)})"})
        detail_by_code = {r["fund_code"]: r for r in rows}

    # 可选附 AI 定性分析（--ai）：一次性取这些基金的 fund_ai_analysis 行
    ai_by_code: dict[str, dict] = {}
    if getattr(args, "ai", False) and item_codes:
        ai_rows = database.select("fund_ai_analysis",
                                  {"fund_code": f"in.({','.join(item_codes)})"})
        ai_by_code = {r["fund_code"]: r for r in ai_rows}

    funds = []
    for it in items:
        d = detail_by_code.get(it.get("code"), {})
        f = {
            "code": it.get("code"), "name": it.get("name") or _clean(d.get("fund_name")),
            "fund_type": _clean(d.get("fund_type")), "scale": _clean(d.get("scale")),
            "fund_manager": _clean(d.get("fund_manager")), "fund_company": _clean(d.get("fund_company")),
            "establish_date": _clean(d.get("establish_date")),
            "fund_rating": _clean(d.get("fund_rating")), "rating_agency": _clean(d.get("rating_agency")),
        }
        if getattr(args, "ai", False):
            ai = ai_by_code.get(it.get("code"))
            f["ai"] = {k: v for k, v in ai.items() if k not in ("id", "fund_code")} if ai else None
        funds.append(f)
    data = {"preset_id": pf["id"], "name": pf["name"], "count": len(funds), "funds": funds}

    def txt(d):
        head = f"#{d['preset_id']} {d['name']}　匹配 {d['count']} 只"
        if not snap:
            head += "（无镜像快照，先 preset snapshot）"
        print(head)
        if not d["funds"]:
            return
        base_headers = ["代码", "名称", "类型", "规模(亿)", "经理", "公司", "成立日", "评级"]
        rows = []
        for f in d["funds"]:
            row = [f["code"], f["name"] or "-", f["fund_type"] or "-",
                   output.num(f["scale"], 2) if f["scale"] is not None else "-",
                   f["fund_manager"] or "-", f["fund_company"] or "-",
                   f["establish_date"] or "-",
                   (f["fund_rating"] or "-") + (f"({f['rating_agency']})" if f.get("rating_agency") else "")]
            if getattr(args, "ai", False):
                ai = f.get("ai") or {}
                row += [("★" * ai["rating"]) if ai.get("rating") else "-",
                        ai.get("skill_score") if ai.get("skill_score") is not None else "-",
                        _LUCK_CN.get(ai.get("luck_verdict"), "-"),
                        _CONC_CN.get(ai.get("concentration"), "-"),
                        _KIND_CN.get(ai.get("fund_kind"), "-"),
                        ai.get("verdict") or "-"]
            rows.append(row)
        headers = base_headers + (["AI★", "实力", "运气", "集中", "类型", "结论"] if getattr(args, "ai", False)
                                  else [])
        print(output.table(rows, headers))
    output.emit(data, args.json, txt)


def _build_list_params(filters: dict) -> dict[str, str]:
    """预设 filters → /fund/list 风格 query 参数（复刻 MCP _build_list_params）。"""
    params: dict[str, str] = {}
    if filters.get("keyword"):
        params["keyword"] = filters["keyword"]
    if filters.get("name_contains"):
        params["name_contains"] = filters["name_contains"]
    if filters.get("fund_types"):
        params["fund_types"] = ",".join(filters["fund_types"])
    conds = filters.get("conditions") or []
    if conds:
        params["conds"] = ",".join(f"{c['field']}:{c['op']}:{c['value']}" for c in conds)
    if filters.get("name_excludes"):
        params["name_excludes"] = ",".join(filters["name_excludes"])
    if filters.get("exclude_codes"):
        params["exclude_codes"] = ",".join(str(c) for c in filters["exclude_codes"])
    return params


def cmd_snapshot(args) -> None:
    """按预设当前条件重筛 → 附前十大持仓 → 存为该预设镜像（替换旧镜像）。"""
    from werkzeug.datastructures import MultiDict
    from app.fund.api import router as fund_router

    pf = helpers.resolve_preset(args.user, args.id, args.name)
    if not pf:
        print("未找到该预设", file=sys.stderr)
        sys.exit(1)
    filters = json.loads(pf.get("filters_json") or "{}")
    margs = MultiDict([(k, v) for k, v in _build_list_params(filters).items()])
    fund_params, detail_params = fund_router.parse_fund_filter_args(margs)
    _total, items = database.list_funds_with_details(fund_params, detail_params, 0, args.limit, [])
    fund_router._attach_holdings(items)  # 附前十大，镜像方可用于聚类/仓位
    database.delete("fund_snapshots", {"user_id": args.user, "preset_id": pf["id"]})
    database.insert("fund_snapshots", {
        "user_id": args.user, "preset_id": pf["id"],
        "items_json": json.dumps(items, ensure_ascii=False), "fund_count": len(items)})
    out = {"preset_id": pf["id"], "name": pf["name"], "fund_count": len(items)}
    output.emit(out, args.json,
                lambda d: print(f"✓ 预设 #{d['preset_id']} {d['name']} 镜像已刷新：{d['fund_count']} 只"))
