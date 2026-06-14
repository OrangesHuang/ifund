"""基金名单同步拉取（同步，在请求线程内调用 akshare）。"""
from __future__ import annotations

# 偏股基金的候选 type
STOCK_TYPES = {"股票型", "混合型-偏股", "混合型-灵活"}


def _classify(name: str, fund_type: str) -> str:
    """偏股判定：type 命中候选集 且 名称无指数/ETF 且 含 C 不含 A。"""
    if (fund_type in STOCK_TYPES and "指数" not in name and "ETF" not in name
            and "C" in name and "A" not in name):
        return "stock"
    return "non_stock"


def fetch_all_funds() -> list[dict]:
    """调 ak.fund_name_em() 拿全部基金并分类。"""
    import akshare as ak  # pylint: disable=import-outside-toplevel,import-error

    data_frame = ak.fund_name_em()
    funds = []
    for _, row in data_frame.iterrows():
        code = str(row["基金代码"]).strip()
        name = str(row["基金简称"]).strip()
        fund_type = str(row["基金类型"]).strip()
        funds.append({
            "code": code,
            "name": name,
            "type": fund_type,
            "fund_type": _classify(name, fund_type),
            "pinyin_abbr": str(row.get("拼音缩写", "") or ""),
            "pinyin_full": str(row.get("拼音全称", "") or ""),
        })
    return funds
