"""申万2021行业分类静态同步（权威源）。

数据由申万宏源官方(swsresearch)直接提供，一次性、权威、且不像 legulegu 那样被限流：
- ``ak.stock_industry_clf_hist_sw`` ：每只股票的申万2021行业代码（含变更历史，取最新一期）；
- ``ak.stock_industry_category_cninfo("申银万国行业分类标准")`` ：行业代码→名称的分级树
  （一级/二级/三级，共 31 / 134 / 346 个）。

股票代码(6位数字)与巨潮分级树的编码是同构的，只是差一个 ``S`` 前缀：
``110101`` ↔ ``S110101``，故按 ``S + code[:2] / [:4] / [:6]`` 取三级名称。
本模块把「股票→(申万一级/二级/三级名)」权威映射落库，替代/校准 legulegu 采集。
"""
from __future__ import annotations

import re

from app import db as database
from app.stock_industry.crud import industry_crud

# 申万2021 里部分二级/三级名带 Ⅱ/Ⅲ 后缀（如「白酒Ⅱ」「股份制银行Ⅲ」，用于跨级区分同名）。
# 本项目聚类标签用纯名称，故统一去掉结尾罗马数字后缀，保持历史一致。
_ROMAN = re.compile(r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+$")


def _strip(name) -> str | None:
    """去名称结尾的罗马数字后缀（Ⅱ/Ⅲ…），空值回 None。"""
    s = _ROMAN.sub("", str(name or "")).strip()
    return s or None


def _load():
    """拉取并组装 (分级名表, 股票名表, 每股最新行业码)。akshare 延迟 import。"""
    import akshare as ak  # pylint: disable=import-outside-toplevel

    tree_df = ak.stock_industry_category_cninfo(symbol="申银万国行业分类标准")
    tree = {str(r["类目编码"]): str(r["类目名称"]) for _, r in tree_df.iterrows()}

    name_map: dict[str, str] = {}
    try:
        names = ak.stock_info_a_code_name()
        # 交易所缩写名常带对齐用空格（如「万  科Ａ」），统一去空白，便于展示/检索。
        name_map = {str(r["code"]): re.sub(r"\s+", "", str(r["name"]))
                    for _, r in names.iterrows()}
    except Exception:  # pylint: disable=broad-exception-caught
        name_map = {}

    hist = ak.stock_industry_clf_hist_sw()
    latest = hist.sort_values("start_date").groupby("symbol").tail(1)
    return tree, name_map, latest


def sync_sw2021() -> dict:
    """把申万2021「股票→三级」映射 upsert 进 stock_industry，返回统计。"""
    tree, name_map, latest = _load()
    inserted = updated = skipped = 0
    for _, row in latest.iterrows():
        code = str(row["symbol"]).strip()
        icode = str(row["industry_code"]).strip()
        l1 = tree.get("S" + icode[:2])
        l2 = tree.get("S" + icode[:4])
        l3 = tree.get("S" + icode)
        if not (l1 and l2 and l3):
            skipped += 1
            continue
        existing = database.select_one("stock_industry", {"stock_code": f"eq.{code}"})
        industry_crud.upsert_industry(
            code,
            name_map.get(code),
            market=industry_crud.classify_market(code),
            sw=(_strip(l1), _strip(l2), _strip(l3)),
            source="sw2021",
        )
        if existing:
            updated += 1
        else:
            inserted += 1
    return {
        "total": len(latest),
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
    }
