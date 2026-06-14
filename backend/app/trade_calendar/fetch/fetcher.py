"""交易日历拉取：akshare 新浪历史交易日。"""
from __future__ import annotations


def fetch_trade_dates() -> list[str]:
    """返回全部历史交易日（YYYY-MM-DD 字符串，升序）。"""
    import akshare as ak  # pylint: disable=import-outside-toplevel,import-error

    frame = ak.tool_trade_date_hist_sina()
    dates = []
    for value in frame["trade_date"].tolist():
        dates.append(str(value)[:10])
    return sorted(set(dates))
