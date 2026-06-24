"""输出工具：紧凑文本表 / JSON 出口 / 数值格式化。无后端依赖。"""
from __future__ import annotations

import json


def dumps(obj) -> str:
    """紧凑 JSON 字符串（无空格、保留中文）。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def emit(obj, as_json: bool, text_fn) -> None:
    """统一出口：--json 走紧凑 JSON，否则走 text_fn 打印。"""
    if as_json:
        print(dumps(obj))
    else:
        text_fn(obj)


def table(rows: list[list], headers: list[str]) -> str:
    """等宽左对齐文本表。rows 元素已是字符串/可 str()。"""
    cells = [[str(c) for c in r] for r in rows]
    widths = [len(h) for h in headers]
    for r in cells:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(c))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    out = [line]
    for r in cells:
        out.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(r)))
    return "\n".join(out)


def pct(x, digits: int = 2) -> str:
    """小数 → 百分比字符串（None→'-'）。"""
    if x is None:
        return "-"
    return f"{x * 100:.{digits}f}%"


def num(x, digits: int = 2) -> str:
    if x is None:
        return "-"
    return f"{x:.{digits}f}"
