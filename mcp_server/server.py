"""iFund MCP 服务器：把 iFund CLI 以**单个透传工具**暴露给本机 agent（如 OpenClaw）。

设计（2026-06 重构）
--------------------
旧版把后端 HTTP API 拆成 33 个 MCP 工具，每轮对话都注入全部工具 schema（~8k token 固定开销）。
现折叠为**一个** ``ifund`` 工具：内部直接 exec 本机 CLI（``backend/ifund_cli.py``，直连 data.db、
复用后端 crud/算法层），不再走 HTTP/PAT/JWT。schema 从 33→1，Token 成本基本消除，
且 CLI 是唯一真相源——MCP 只是给「只能走 MCP」的 agent 的一层薄桥；能跑 shell 的 agent
（Qoder 等）应按 AGENTS.md 直接调 CLI。

命令面全部由 CLI 提供，任何子命令加 ``-h`` 可自查参数（见下方工具 docstring）。

运行：以 stdio 方式 ``python server.py``（OpenClaw 等 MCP 客户端据此拉起子进程）。
旧的 33 工具实现保留在 ``server.py.33tools.bak``。

注意：本文件刻意不使用 ``from __future__ import annotations``——FastMCP 需在运行时读取真实
类型注解对象（字符串化注解会让工具注册失败）；本服务运行于 Python 3.12，原生语法可用。
"""
import os
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# 路径相对本文件推导，OpenClaw 工作目录不在本仓库也能用绝对路径调起
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
_PYTHON = os.environ.get("IFUND_PYTHON") or str(_BACKEND_DIR / "venv" / "bin" / "python")
_CLI = str(_BACKEND_DIR / "ifund_cli.py")
# 拉取(fetch)联网较慢，给较宽超时；大批量请用 --codes 限定范围
_TIMEOUT = float(os.environ.get("IFUND_CLI_TIMEOUT", "1800"))

mcp = FastMCP("ifund")


@mcp.tool()
def ifund(args: list[str]) -> Any:
    """运行 iFund 数据 CLI（直连本机 data.db，无需后端服务/登录），返回其文本输出。

    args 是命令行参数数组（不要含 "ifund_cli.py"），例如：
      ["holdings", "perf", "--pid", "6", "--json"]
      ["analyze", "run", "--preset", "2", "--balance", "中", "--view", "all"]
    任意命令加 "-h" 自查参数。加 "--json" 得到紧凑 JSON 便于解析。默认用户 user_id=1（--user N 可改）。

    命令面：
      preset   list | show --id N（或 --name X）| snapshot --id N | funds --id N [--code C][--keyword K][--ai] | ai-set --code N --data '{...}'
               预设/镜像快照（snapshot=重建镜像；funds=查镜像内基金+基础信息，--ai 附 AI 定性分析列；
               ai-set=写入基金 AI 定性分析，部分字段 upsert，回答靠运气/单押赛道/硬实力三问）
      fetch    calendar | industry --mode sw|em [--codes ..] | detail|holdings|nav [--codes ..] [--types ..]
               数据拉取（联网，慢；自带「同交易日已拉则跳过」缓存；大批量务必用 --codes 限范围）
      analyze  run --preset N [--balance 松|中|紧 | --cap 0.10~0.30] [--view weights|industry|stock|perf|all]
               组合分析：必选预设→簇级仓位建议（默认紧 cap=0.14）；view 选 各赛道权重/底层穿透/分区间表现
      holdings list | show --pid N [--penetration] | penetration | perf | rebalance --pid N [--sell-outside] [--no-trim-overflow] [--band B]
               实盘查询：账户列表 / 实际持仓(按赛道簇分组,可加--penetration附穿透) / 底层穿透 / 分区间表现 / 调仓建议(操作指南)
      holdings buy|sell --pid N --fund 代码或名称 --amount A | transfer --from .. --to .. --amount A | txns | txn-del --id T
               实盘交易：买入/卖出/转仓 + 交易记录列表/删除（持仓录入在网页端，不走 CLI）

    输出已主动裁掉超大序列（仓位建议的每日 nav 曲线、组合每日净值/回撤不返回）以省 Token。
    """
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return {"_error": "args 必须是字符串数组，如 ['preset','list']"}
    try:
        proc = subprocess.run(
            [_PYTHON, _CLI, *args],
            cwd=str(_BACKEND_DIR), capture_output=True, text=True,
            timeout=_TIMEOUT, check=False,
        )
    except FileNotFoundError:
        return {"_error": f"找不到 Python 或 CLI：{_PYTHON} / {_CLI}"}
    except subprocess.TimeoutExpired:
        return {"_error": f"CLI 执行超时（>{_TIMEOUT:.0f}s）。大批量 fetch 请用 --codes 限定范围。"}
    out = proc.stdout.rstrip("\n")
    if proc.returncode != 0:
        # 把退出码与 stderr 一并回传，便于 agent 自我纠错（如参数错误）
        return {"_error": f"exit={proc.returncode}", "stderr": proc.stderr.strip(), "stdout": out}
    return out


if __name__ == "__main__":
    mcp.run()
