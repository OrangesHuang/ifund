"""AI 定性分析服务：流式分析已停用（qoder-agent-sdk 要求 Python >=3.10，已随降级移除）；
保留 fund_ai_analysis 表与提示词管理，OpenClaw 仍可通过 CLI `ai-set` 写入分析数据。"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from app import db as database

logger = logging.getLogger(__name__)

# 默认提示词的「单一真相源」= prompts/*.md（版本控制、可 git diff、全新项目自带）。
# app_settings 里的同名 key 只是运行时可选覆盖；删除覆盖即回落到这两个文件。
# 这样避免了「UI 抽屉里改的提示词只落 DB、换机器/重建库就丢、回落到过时硬编码」的漂移。
_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

# 文件缺失时的最小兜底：不让打包疏漏拖垮整个后端启动，但会在日志里报出来。
_FALLBACK_SYSTEM = "你是基金定性分析助手，只输出一个严格匹配字段定义的 JSON 对象。"
_FALLBACK_USER = "请对以下基金做历史穿透定性分析并输出 JSON：\n\n__BUNDLE_JSON__"


def _load_prompt_file(name: str, fallback: str) -> str:
    """从 prompts/ 读取提示词文件；缺失时回落到最小兜底并告警。"""
    try:
        return (_PROMPT_DIR / name).read_text(encoding="utf-8")
    except OSError:
        logger.error("提示词文件缺失：%s，已回落到最小兜底", _PROMPT_DIR / name)
        return fallback


DEFAULT_SYSTEM_PROMPT = _load_prompt_file("system.md", _FALLBACK_SYSTEM)
DEFAULT_USER_PROMPT_TEMPLATE = _load_prompt_file("user.md", _FALLBACK_USER)


def get_prompt(key: str, default: str) -> str:
    """读提示词：app_settings 覆盖优先，否则用 default（= prompts/*.md 文件默认值）。"""
    row = database.select_one("app_settings", {"key": f"eq.{key}"})
    return row["value"] if row else default


def set_prompt(key: str, value: str) -> None:
    """写入/更新 app_settings 中的提示词覆盖。"""
    exists = database.select_one("app_settings", {"key": f"eq.{key}"})
    if exists:
        database.update("app_settings", {"key": key}, {"value": value})
    else:
        database.insert("app_settings", {"key": key, "value": value})


def reset_prompt(key: str) -> None:
    """删除 app_settings 中的覆盖，使该提示词回落到 prompts/*.md 文件默认值。"""
    database.delete("app_settings", {"key": f"eq.{key}"})


async def analyze_fund_streaming(code: str) -> AsyncIterator[dict]:
    """流式分析：qoder-agent-sdk 已随 Python 3.9 降级移除，直接报错。"""
    raise RuntimeError(
        "AI 分析功能已停用：qoder-agent-sdk 要求 Python >=3.10，已随 Python 3.9 降级一并移除"
    )


def analyze_fund(code: str) -> dict:
    """同步分析（兼容旧调用）。"""
    results = []
    async def collect():
        async for item in analyze_fund_streaming(code):
            results.append(item)
    asyncio.run(collect())
    for r in results:
        if r.get("type") == "done":
            return r["ai"]
    raise RuntimeError("分析未完成")
