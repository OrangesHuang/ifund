"""股票→行业映射数据访问：多源融合 upsert、覆盖率统计、行业聚合、人工修正。

数据是静态元数据：申万三级（legulegu）为主标签，东财行业（eastmoney）兜底港股/缺口。
``manual=1`` 的行表示人工修正过，采集不再覆盖。统计/聚合均针对 fund_holdings
里实际出现过的持仓股票（聚类真正要用的集合）。
"""
from __future__ import annotations

import datetime
import time

from app import db as database

TABLE = "stock_industry"

# 派生集合（持仓全集 / 行业映射索引）的进程内 TTL 缓存。
# 行业映射页一次开页会并发打 stats / breakdown / list 三个接口，各自要算同样的 held/idx；
# 缓存把这一阵突发请求收敛成一次计算。持仓变动靠 TTL 自动失效，人工修正即时清缓存。
_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 30.0  # 秒


def _cached(key: str, build):
    hit = _CACHE.get(key)
    if hit is not None and (time.monotonic() - hit[0]) < _CACHE_TTL:
        return hit[1]
    val = build()
    _CACHE[key] = (time.monotonic(), val)
    return val


def _invalidate_cache() -> None:
    """映射数据变动后清空派生缓存（人工修正 / 采集 upsert 调用）。"""
    _CACHE.clear()


def held_codes() -> list[str]:
    """fund_holdings 里去重的股票持仓代码（聚类标的全集）。"""
    def build() -> list[str]:
        rows = database.select("fund_holdings", {
            "holding_type": "eq.stock", "select": "DISTINCT asset_code",
        })
        return [r["asset_code"] for r in rows if r.get("asset_code")]
    return _cached("held_codes", build)


def held_names() -> dict[str, str]:
    """持仓股票代码 → 简称（取任意一条，用于补全无映射记录的名称）。"""
    def build() -> dict[str, str]:
        rows = database.select("fund_holdings", {
            "holding_type": "eq.stock", "select": "DISTINCT asset_code, asset_name",
        })
        out: dict[str, str] = {}
        for r in rows:
            code = r.get("asset_code")
            if code and code not in out:
                out[code] = r.get("asset_name") or ""
        return out
    return _cached("held_names", build)


def classify_market(code: str) -> str:
    """按代码形态粗判市场：6 位数字=A 股，5 位数字=港股，其余=海外/其他。

    注意：韩国 KRX 代码同为 6 位数字（如 005930 三星），仅凭形态会误判为 A 股；
    精确市场以 ``stock_industry.market`` 字段为准（采集时用 A 股全集校正后写入）。
    """
    if code.isdigit() and len(code) == 6:
        return "A"
    if code.isdigit() and len(code) == 5:
        return "HK"
    return "OTHER"


def market_of(code: str, idx: dict[str, dict] | None = None) -> str:
    """精确市场：优先用已存的 market 字段（采集时校正过），否则回退代码形态粗判。"""
    idx = idx if idx is not None else _index_by_code()
    stored = (idx.get(code) or {}).get("market")
    return stored or classify_market(code)


def _now() -> str:
    return datetime.datetime.now().isoformat()


def upsert_industry(code, name, *, market=None, sw=None, em=None, source=""):
    """按字段 upsert 单只股票：保留另一来源字段，``manual=1`` 的记录跳过。

    ``sw`` 为 ``(l1, l2, l3)`` 三元组（申万采集时给），``em`` 为东财行业名（兜底时给）。
    """
    existing = database.select_one(TABLE, {"stock_code": f"eq.{code}"})
    if existing and existing.get("manual"):
        return  # 人工修正过，采集不覆盖
    fields = {"updated_at": _now()}
    if name:
        fields["stock_name"] = name
    if market:
        fields["market"] = market
    if sw is not None:
        fields["sw_l1"], fields["sw_l2"], fields["sw_l3"] = sw
    if em is not None:
        fields["em_industry"] = em
    if source:
        fields["source"] = source
    if existing:
        database.update(TABLE, {"stock_code": code}, fields)
    else:
        database.insert(TABLE, {"stock_code": code, "manual": 0, **fields})
    _invalidate_cache()


def sw_covered_l3() -> set[str]:
    """已采到 legulegu 来源记录的申万三级名集合（worker 续采时跳过已采行业）。"""
    rows = database.select(TABLE, {
        "source": "eq.legulegu", "select": "DISTINCT sw_l3",
    })
    return {r["sw_l3"] for r in rows if r.get("sw_l3")}


def uncovered_held(held: list[str], markets: tuple[str, ...] = ("A", "HK")) -> list[str]:
    """持仓股票里尚无任何行业标签（申万 + 东财都为空）的代码（东财兜底的目标）。

    默认仅返回 A 股缺口 + 港股；海外（OTHER）东财查不到、按约定归「其他」，故排除。
    市场以已存 market 字段为准（校正过的韩股已是 OTHER，不会再被当 A 股目标）。
    """
    idx = _index_by_code()
    have = {c for c, r in idx.items() if r.get("sw_l3") or r.get("em_industry")}
    return [c for c in held
            if c not in have and market_of(c, idx) in markets]


def set_manual(code: str, fields: dict) -> None:
    """人工修正：写入指定字段并打 ``manual=1`` + ``source=manual``。"""
    payload = {k: v for k, v in fields.items()
               if k in ("stock_name", "market", "sw_l1", "sw_l2", "sw_l3", "em_industry")}
    payload.update({"manual": 1, "source": "manual", "updated_at": _now()})
    if database.select_one(TABLE, {"stock_code": f"eq.{code}"}):
        database.update(TABLE, {"stock_code": code}, payload)
    else:
        database.insert(TABLE, {"stock_code": code, **payload})
    _invalidate_cache()


def _label(row: dict) -> str:
    """聚类标签取值优先级：申万三级 → 申万二级 → 东财行业 → 其他。"""
    return (row.get("sw_l3") or row.get("sw_l2")
            or row.get("em_industry") or "其他")


def _index_by_code() -> dict[str, dict]:
    return _cached("index", lambda: {r["stock_code"]: r for r in database.select(TABLE)})


def industry_index() -> dict[str, dict]:
    """股票代码 → 行业映射行（公开封装，供聚类等外部模块复用，避免触碰内部函数）。"""
    return _index_by_code()


def label_of(code: str, idx: dict[str, dict] | None = None) -> str:
    """单只股票的聚类标签（申万三级→二级→东财→其他）；无记录返回「其他」。"""
    idx = idx if idx is not None else _index_by_code()
    row = idx.get(code)
    return _label(row) if row else "其他"


def stats() -> dict:
    """覆盖率统计（针对持仓股票）：分市场统计已覆盖 / 未覆盖数量与比例。"""
    held = held_codes()
    idx = _index_by_code()
    a_share = [c for c in held if market_of(c, idx) == "A"]
    hk = [c for c in held if market_of(c, idx) == "HK"]
    other = [c for c in held if market_of(c, idx) == "OTHER"]
    a_sw = [c for c in a_share if idx.get(c, {}).get("sw_l3")]
    a_only_em = [c for c in a_share
                 if not idx.get(c, {}).get("sw_l3") and idx.get(c, {}).get("em_industry")]
    hk_em = [c for c in hk if idx.get(c, {}).get("em_industry") or idx.get(c, {}).get("sw_l3")]
    covered = [c for c in held
               if idx.get(c, {}).get("sw_l3") or idx.get(c, {}).get("em_industry")]
    return {
        "held_total": len(held),
        "a_total": len(a_share), "hk_total": len(hk), "other_total": len(other),
        "a_sw_covered": len(a_sw), "a_em_covered": len(a_only_em),
        "a_uncovered": len(a_share) - len(a_sw) - len(a_only_em),
        "hk_covered": len(hk_em), "hk_uncovered": len(hk) - len(hk_em),
        "covered_total": len(covered),
        "coverage_pct": round(len(covered) / len(held) * 100, 1) if held else 0.0,
        "a_sw_pct": round(len(a_sw) / len(a_share) * 100, 1) if a_share else 0.0,
        "sw_l3_count": len({r.get("sw_l3") for r in idx.values() if r.get("sw_l3")}),
        "table_rows": len(idx),
    }


def breakdown(top: int = 0) -> list[dict]:
    """持仓股票按聚类标签聚合计数（降序），用于直观看各细分行业的标的数量。"""
    held = held_codes()
    idx = _index_by_code()
    counter: dict[str, dict] = {}
    for code in held:
        row = idx.get(code, {})
        label = _label(row) if row else "未覆盖"
        slot = counter.setdefault(label, {"label": label, "count": 0,
                                          "sw_l1": row.get("sw_l1", "") if row else ""})
        slot["count"] += 1
    items = sorted(counter.values(), key=lambda x: x["count"], reverse=True)
    return items[:top] if top else items


def list_page(*, market="", label_kw="", status="", keyword="", skip=0, limit=50):
    """分页列出持仓股票的行业映射（过滤/排序/分页下沉 SQL，见 db.list_industry_mapping）。

    status: ``covered`` 仅已覆盖 / ``uncovered`` 仅未覆盖 / 空=全部。
    """
    total, rows = database.list_industry_mapping(
        market=market, label_kw=label_kw, status=status, keyword=keyword, skip=skip, limit=limit)
    for r in rows:
        r["covered"] = bool(r["covered"])  # SQL 返回 0/1，前端按布尔渲染
    return total, rows
