"""雪球四接口 → fund_details 列的防御式映射。

雪球返回的字段名在不同版本/不同基金间不稳定，这里统一用
「item/value 关键字扫描」的方式提取，缺字段时安全跳过（置 None）。
"""
from __future__ import annotations

import datetime
import re

from app.common.worker_base import safe_float

# 从带单位文本中提取第一个数字（如 "35.17亿" -> 35.17）
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _parse_scale(value) -> float | None:
    """解析规模文本：基准单位「亿」，「X万」折算为亿（/10000）。"""
    if value is None:
        return None
    text = str(value)
    match = _NUM_RE.search(text)
    if not match:
        return None
    num = float(match.group())
    if "万" in text and "亿" not in text:
        return num / 10000.0
    return num


def _label_col(cols):
    """周期所在列：优先含「周期」的列，否则回退首列。"""
    for col in cols:
        if "周期" in str(col):
            return col
    return cols[0]

# 周期关键字 → 列后缀
_PERIOD_SUFFIX = [
    ("成立以来", "since_inception"), ("今年以来", "ytd"),
    ("近一月", "1m"), ("近1月", "1m"),
    ("近三月", "3m"), ("近3月", "3m"),
    ("近六月", "6m"), ("近6月", "6m"),
    ("近一年", "1y"), ("近1年", "1y"),
    ("近三年", "3y"), ("近3年", "3y"),
    ("近五年", "5y"), ("近5年", "5y"),
]
# 风险指标周期（雪球 analysis 仅 1y/3y/5y）
_RISK_PERIOD = [("近一年", "1y"), ("近1年", "1y"),
                ("近三年", "3y"), ("近3年", "3y"),
                ("近五年", "5y"), ("近5年", "5y")]


def _pairs(frame) -> dict[str, str]:
    """把 item/value 形态的 DataFrame 压成 dict（首列为 key，次列为 value）。"""
    out: dict[str, str] = {}
    if frame is None or getattr(frame, "empty", True):
        return out
    cols = list(frame.columns)
    if len(cols) < 2:
        return out
    key_col, val_col = cols[0], cols[1]
    for _, row in frame.iterrows():
        out[str(row.get(key_col, "")).strip()] = row.get(val_col)
    return out


def _find(pairs: dict, *keywords: str):
    """返回第一个 key 含任一关键字的 value。"""
    for key, value in pairs.items():
        if any(kw in key for kw in keywords):
            return value
    return None


def _map_basic(pairs: dict, columns: dict) -> None:
    columns["fund_name"] = _opt_str(_find(pairs, "基金简称", "基金名称"))
    columns["fund_full_name"] = _opt_str(_find(pairs, "基金全称"))
    columns["establish_date"] = _opt_str(_find(pairs, "成立时间", "成立日期"))
    columns["scale"] = _parse_scale(_find(pairs, "最新规模", "资产规模", "基金规模"))
    columns["fund_company"] = _opt_str(_find(pairs, "基金公司", "管理人"))
    columns["fund_manager"] = _opt_str(_find(pairs, "基金经理"))
    columns["custodian_bank"] = _opt_str(_find(pairs, "托管"))
    columns["fund_type"] = _opt_str(_find(pairs, "基金类型"))
    columns["rating_agency"] = _opt_str(_find(pairs, "评级机构"))
    columns["fund_rating"] = _opt_str(_find(pairs, "基金评级", "评级"))
    columns["invest_strategy"] = _opt_str(_find(pairs, "投资策略"))
    columns["invest_target"] = _opt_str(_find(pairs, "投资目标"))
    columns["benchmark"] = _opt_str(_find(pairs, "业绩比较基准", "基准"))


def _opt_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _map_hold(frame, columns: dict) -> None:
    """持仓配置：股票/债券/现金/其他 仓位百分比。"""
    pairs = _pairs(frame)
    columns["position_stock"] = safe_float(_find(pairs, "股票"))
    columns["position_bond"] = safe_float(_find(pairs, "债券"))
    columns["position_cash"] = safe_float(_find(pairs, "现金"))
    columns["position_other"] = safe_float(_find(pairs, "其他", "其它"))


def _row_period_suffix(label: str, table) -> str | None:
    for keyword, suffix in table:
        if keyword in label:
            return suffix
    return None


def _map_analysis(frame, columns: dict) -> None:
    """风险指标：每行一个周期，列含 风险收益比/抗风险/波动率/夏普/最大回撤。"""
    if frame is None or getattr(frame, "empty", True):
        return
    label_col = _label_col(list(frame.columns))
    for _, row in frame.iterrows():
        suffix = _row_period_suffix(str(row.get(label_col, "")), _RISK_PERIOD)
        if not suffix:
            continue
        _set_risk(columns, suffix, row)


def _set_risk(columns: dict, suffix: str, row) -> None:
    columns[f"risk_return_ratio_{suffix}"] = safe_float(_col(row, "风险收益比"))
    columns[f"anti_risk_ratio_{suffix}"] = safe_float(_col(row, "抗风险", "抗风险能力"))
    columns[f"volatility_{suffix}"] = safe_float(_col(row, "波动率", "标准差"))
    columns[f"sharpe_{suffix}"] = safe_float(_col(row, "夏普"))
    columns[f"max_drawdown_{suffix}"] = safe_float(_col(row, "最大回撤", "最大回撒"))


def _col(row, *keywords):
    """按关键字匹配 DataFrame 行的列。"""
    for key in row.index:
        if any(kw in str(key) for kw in keywords):
            return row.get(key)
    return None


def _map_achievement(frame, columns: dict) -> None:
    """业绩表现：每行一个周期，列含 涨跌幅/最大回撤/同类排名。"""
    if frame is None or getattr(frame, "empty", True):
        return
    label_col = _label_col(list(frame.columns))
    for _, row in frame.iterrows():
        suffix = _row_period_suffix(str(row.get(label_col, "")), _PERIOD_SUFFIX)
        if not suffix:
            continue
        columns[f"return_{suffix}"] = safe_float(_col(row, "涨跌幅", "收益率", "区间收益"))
        rank = _opt_str(_col(row, "同类排名", "排名"))
        if rank is not None:
            columns[f"rank_{suffix}"] = rank
        draw = safe_float(_col(row, "最大回撤", "最大回撒"))
        if f"drawdown_{suffix}" in _DRAWDOWN_COLS and draw is not None:
            columns[f"drawdown_{suffix}"] = draw


# 含 drawdown 列的周期（1m 无 drawdown 列）
_DRAWDOWN_COLS = {
    "drawdown_since_inception", "drawdown_ytd", "drawdown_3m", "drawdown_6m",
    "drawdown_1y", "drawdown_3y", "drawdown_5y",
}


def map_all(basic, hold, analysis, achievement, trade_date: str | None) -> dict:
    """汇总四接口结果为 fund_details 列字典。"""
    columns: dict = {
        "fetch_time": datetime.datetime.now().isoformat(),
        "trade_date": trade_date,
    }
    _map_basic(_pairs(basic), columns)
    _map_hold(hold, columns)
    _map_analysis(analysis, columns)
    _map_achievement(achievement, columns)
    return columns
