"""跨命令共享小工具：预设解析、镜像计数、csv 解析。"""
from __future__ import annotations

from app import db as database


def csv_list(s: str | None) -> list[str]:
    """逗号分隔串 → 去空列表。"""
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def resolve_preset(uid: int, pid: int | None, name: str | None) -> dict | None:
    """按 id 或 name 解析当前用户的预设行；都没给则 None。"""
    if pid is not None:
        return database.select_one("query_presets", {"id": f"eq.{pid}", "user_id": f"eq.{uid}"})
    if name:
        return database.select_one("query_presets", {"name": f"eq.{name}", "user_id": f"eq.{uid}"})
    return None


def snapshot_count(uid: int, pid: int) -> int:
    """某预设镜像快照里的基金数（无快照→0）。"""
    row = database.select_one("fund_snapshots", {"user_id": f"eq.{uid}", "preset_id": f"eq.{pid}"})
    return int(row.get("fund_count") or 0) if row else 0
