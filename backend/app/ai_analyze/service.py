"""AI 定性分析服务：DeepSeek ReAct 模式（Reason + Act 循环，逐维核验后产出 JSON）。

数据流：``build_bundle(code)``（历史穿透数据包）→ 注入用户提示词 + 作为工具 backend →
模型走「思考(reasoning_content) → 调用 inspect_dimension(act) → 返回观察(observation)」循环，
最终输出严格匹配 ``fund_ai_analysis`` 字段的 JSON。分析过程以 SSE 事件流上报给前端浮窗。
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path

import requests

from app import db as database

logger = logging.getLogger(__name__)

# 默认提示词的「单一真相源」= prompts/*.md（版本控制、可 git diff、全新项目自带）。
# app_settings 里的同名 key 只是运行时可选覆盖；删除覆盖即回落到这两个文件。
_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

# 文件缺失时的最小兜底：不让打包疏漏拖垮整个后端启动，但会在日志里报出来。
_FALLBACK_SYSTEM = (
    "你是基金定性分析智能体。使用工具 inspect_dimension 逐维核验数据后，只输出一个 "
    "严格匹配字段定义的 JSON 对象，不要任何解释文字，不要用 markdown 代码块包裹。"
)
_FALLBACK_USER = "请对以下基金做历史穿透定性分析并输出 JSON：\n\n__BUNDLE_JSON__"

_DIMENSION_DESC = (
    "profile(基金档案+业绩指标)、attribution(经理归因)、holdings(持仓漂移/单押判定)、"
    "nav(净值区间表现/当前团队以来收益)、caveats(数据局限)"
)


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


# ---------- DeepSeek 配置 ----------

def _deepseek_config() -> dict:
    """读取 DeepSeek 配置；缺少 API Key 时报错。"""
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY（backend/.env）")
    return {
        "key": key,
        "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
    }


def _chat(cfg: dict, messages: list, tools: list | None = None,
          max_tokens: int = 5000) -> tuple[dict, dict, str]:
    """调用 DeepSeek chat/completions（非流式，单轮），返回 (message, usage, finish_reason)。"""
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    if tools:
        payload["tools"] = tools
    try:
        resp = requests.post(
            f"{cfg['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"},
            json=payload,
            timeout=180,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"DeepSeek 请求失败：{exc}") from exc
    if resp.status_code != 200:
        raise RuntimeError(f"DeepSeek API {resp.status_code}：{resp.text[:200]}")
    data = resp.json()
    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {})
    return message, data.get("usage", {}), choice.get("finish_reason", "")


# ---------- ReAct 工具 ----------

_TOOLS = [{
    "type": "function",
    "function": {
        "name": "inspect_dimension",
        "description": (
            "按维度读取该基金的确定性数据切片，供你逐维核验后再下结论（避免臆造）。"
            f"dimension 取值：{_DIMENSION_DESC}。数据一律来自本工具返回。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "dimension": {
                    "type": "string",
                    "enum": ["profile", "attribution", "holdings", "nav", "caveats"],
                    "description": "要核验的维度",
                }
            },
            "required": ["dimension"],
        },
    },
}]


def _execute_tool(name: str, args: dict, bundle: dict) -> dict:
    """执行工具：返回指定维度的数据切片。"""
    if name != "inspect_dimension":
        return {"detail": f"未知工具 {name}"}
    dim = args.get("dimension")
    slices = {
        "profile": {"meta": bundle.get("meta"), "metrics": bundle.get("metrics")},
        "attribution": {"manager": bundle.get("manager")},
        "holdings": {"holdings": bundle.get("holdings")},
        "nav": {"nav_regime": bundle.get("nav_regime")},
        "caveats": {"data_caveats": bundle.get("data_caveats")},
    }
    return slices.get(dim, {"detail": f"未知维度 {dim}"})


def _summarize_tool_result(result: dict) -> str:
    """把工具返回的数据切片压缩成一行，供浮窗展示。"""
    summary = json.dumps(result, ensure_ascii=False)[:200]
    if not isinstance(result, dict):
        return summary
    if "manager" in result:
        mgr = result["manager"] or {}
        summary = ("经理归因数据不可用" if not mgr.get("available")
                   else f"经理 {mgr.get('current') or '?'}；团队 {mgr.get('exact_team_years')} 年；"
                        f"覆盖 {mgr.get('exact_team_covers')}；任职段数 {mgr.get('segment_count')}")
    elif "holdings" in result:
        hold = result["holdings"] or {}
        quarters = hold.get("quarters") or []
        latest = quarters[-1] if quarters else {}
        summary = ("持仓数据不可用" if not hold.get("available")
                   else f"{latest.get('quarter', '?')} top10_ratio {hold.get('latest_top10_ratio')}；"
                        f"集中趋势 {hold.get('concentration_trend_top10')}；"
                        f"赛道线索 {hold.get('sector_focus')}")
    elif "nav_regime" in result:
        nav = result["nav_regime"] or {}
        summary = ("净值数据不可用" if not nav.get("available")
                   else f"近1y {nav.get('return_last_1y')}；近3y {nav.get('return_last_3y')}；"
                        f"现任以来 {nav.get('return_since_current_team')}")
    elif "meta" in result or "metrics" in result:
        meta = result.get("meta") or {}
        metrics = result.get("metrics") or {}
        summary = (f"{meta.get('name')}｜{meta.get('type')}｜规模 {meta.get('scale_yi')} 亿；"
                   f"3y收益 {metrics.get('return', {}).get('3y')}；"
                   f"3y夏普 {metrics.get('sharpe', {}).get('3y')}")
    elif "data_caveats" in result:
        summary = f"数据局限：{result.get('data_caveats')}"
    return summary


def _extract_json(text: str) -> dict:
    """从模型文本里稳健提取 JSON 对象。"""
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("模型输出中未找到 JSON 对象")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"模型输出 JSON 无法解析: {exc}") from exc


def _react_loop(cfg: dict, bundle: dict, system_prompt: str, user_prompt: str,
                max_rounds: int = 8) -> AsyncIterator[dict]:
    """ReAct 主循环（同步 HTTP 阻塞，供单请求专用事件循环调度）。"""
    user_content = user_prompt.replace(
        "__BUNDLE_JSON__", json.dumps(bundle, ensure_ascii=False))
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    rounds = 0
    tool_calls_seen = 0
    for _ in range(max_rounds):
        message, usage, _finish = _chat(cfg, messages, tools=_TOOLS)
        thought = (message.get("reasoning_content") or "").strip() or (message.get("content") or "").strip()
        tool_calls = message.get("tool_calls")
        if tool_calls:
            rounds += 1
            tool_calls_seen += len(tool_calls)
            messages.append({
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": tool_calls,
            })
            obs_lines: list[str] = []
            for tc in tool_calls:
                fname = tc["function"]["name"]
                try:
                    fargs = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    fargs = {}
                result = _execute_tool(fname, fargs, bundle)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })
                obs_lines.append(f"{fname}({json.dumps(fargs, ensure_ascii=False)})"
                                 f" → {_summarize_tool_result(result)}")
            yield {
                "type": "round",
                "round": rounds,
                "thought": thought[:1000],
                "action": tool_calls[0]["function"]["name"],
                "args": json.loads(tool_calls[0]["function"]["arguments"] or "{}"),
                "observation": "；".join(obs_lines)[:600],
            }
            continue

        content = message.get("content") or ""
        if content.strip():
            try:
                ai = _extract_json(content)
            except ValueError as exc:
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": f"你上次的输出未包含有效 JSON（{exc}）。请只输出一个 JSON 对象，不要解释。",
                })
                continue
            yield {"type": "chunk", "text": content}
            yield {
                "type": "done", "ai": ai, "rounds": rounds,
                "tool_calls": tool_calls_seen, "model": cfg["model"], "usage": usage,
            }
            return
        messages.append({"role": "assistant", "content": ""})
        messages.append({"role": "user", "content": "请输出最终 JSON 对象。"})

    raise RuntimeError(f"超过最大轮数（{max_rounds}）仍未获得最终结果")


# ---------- 落库 ----------

def _txt(value):
    return str(value).strip() if value not in (None, "") and str(value).strip() else None


def _int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _flt(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def save_ai_analysis(code: str, ai: dict) -> None:
    """把 AI 分析结果 upsert 进 fund_ai_analysis。"""
    fields = {
        "manager": _txt(ai.get("manager")),
        "verdict": _txt(ai.get("verdict")),
        "rating": _int(ai.get("rating")),
        "recommend": _int(ai.get("recommend")),
        "skill_score": _int(ai.get("skill_score")),
        "luck_verdict": ai.get("luck_verdict"),
        "skill_reason": _txt(ai.get("skill_reason")),
        "concentration": ai.get("concentration"),
        "concentration_reason": _txt(ai.get("concentration_reason")),
        "fund_kind": ai.get("fund_kind"),
        "hard_thesis": _txt(ai.get("hard_thesis")),
        "tenure_years": _flt(ai.get("tenure_years")),
        "is_original": _int(ai.get("is_original")),
        "is_comanaged": _int(ai.get("is_comanaged")),
        "scale_risk": ai.get("scale_risk"),
        "style_stability": ai.get("style_stability"),
        "turnover_note": _txt(ai.get("turnover_note")),
        "tags": json.dumps(ai.get("tags") or [], ensure_ascii=False),
        "confidence": ai.get("confidence"),
        "model": ai.get("model") or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        "data_basis": _txt(ai.get("data_basis")),
        "analyzed_at": datetime.datetime.now().isoformat(),
        "updated_at": datetime.datetime.now().isoformat(),
    }
    exists = database.select_one("fund_ai_analysis", {"fund_code": f"eq.{code}"})
    if exists:
        database.update("fund_ai_analysis", {"fund_code": code}, fields)
    else:
        database.insert("fund_ai_analysis", {"fund_code": code, **fields})


async def analyze_fund_streaming(code: str) -> AsyncIterator[dict]:
    """流式分析：ReAct 循环，逐轮上报 round/最终 done/error 事件。"""
    try:
        cfg = _deepseek_config()
    except RuntimeError as exc:
        yield {"type": "error", "detail": str(exc)}
        return
    try:
        from cli.bundle import build_bundle  # pylint: disable=import-outside-toplevel
        bundle = build_bundle(code)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("构建数据包失败 %s", code)
        yield {"type": "error", "detail": f"构建数据包失败：{exc}"}
        return
    if not bundle:
        yield {"type": "error", "detail": "该基金数据不足（无详情/无持仓），无法分析"}
        return
    system_prompt = get_prompt("ai_analyze_system", DEFAULT_SYSTEM_PROMPT)
    user_prompt = get_prompt("ai_analyze_user", DEFAULT_USER_PROMPT_TEMPLATE)
    try:
        for item in _react_loop(cfg, bundle, system_prompt, user_prompt):
            if item.get("type") == "done":
                item["ai"]["model"] = cfg["model"]  # 以实际调用模型为准，忽略模型自报
                try:
                    save_ai_analysis(code, item["ai"])
                    logger.info("AI 分析完成 %s（%s 轮）", code, item.get("rounds"))
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logger.exception("保存 AI 分析失败 %s", code)
                    item["save_error"] = str(exc)
            yield item
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("AI 分析异常 %s", code)
        yield {"type": "error", "detail": str(exc)}


def analyze_fund(code: str) -> dict:
    """同步分析（兼容旧调用/CLI）：收集流式事件并返回 ai。"""
    results = []

    async def collect():
        async for item in analyze_fund_streaming(code):
            results.append(item)

    asyncio.run(collect())
    for result in results:
        if result.get("type") == "done":
            return result["ai"]
    raise RuntimeError("分析未完成")
