#!/usr/bin/env python3
"""fund_detail worker：拉取雪球四接口，映射为 fund_details 单行 upsert。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND_DIR = os.getenv("IFUND_BACKEND_DIR") or str(Path(__file__).resolve().parents[3])
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
os.chdir(_BACKEND_DIR)

# pylint: disable=wrong-import-position
import akshare as ak  # pylint: disable=import-error

from app.common import worker_base
from app.fund_detail.crud import detail_crud
from app.fund_detail.fetch import mapper
from app.fund_nav.crud import nav_crud


def _try(func, code):
    try:
        return func(symbol=code)
    except Exception:  # pylint: disable=broad-exception-caught
        return None


def _process_one(code):
    latest = nav_crud.latest_trade_date()
    if not detail_crud.is_expired(code, latest):
        return "skip"
    basic = _try(ak.fund_individual_basic_info_xq, code)
    hold = _try(ak.fund_individual_detail_hold_xq, code)
    analysis = _try(ak.fund_individual_analysis_xq, code)
    achievement = _try(ak.fund_individual_achievement_xq, code)
    if basic is None and analysis is None and achievement is None:
        return "fail"
    columns = mapper.map_all(basic, hold, analysis, achievement, latest)
    detail_crud.upsert(code, columns)
    return "success"


if __name__ == "__main__":
    worker_base.main(_process_one)
