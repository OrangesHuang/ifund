"""iFund CLI 包：直连本地 data.db 的命令行数据工具（替代 MCP，省 Token）。

直接 import 后端 crud/算法层（DB 是进程级单例，无需 Flask app context），
不走 HTTP/JWT/登录。入口见 ``cli.__main__`` 或 backend 根目录的 ``ifund_cli.py`` 薄壳。

模块划分：
    output    输出工具（紧凑文本表 / JSON / 数值格式化）
    helpers   跨命令共享小工具（预设解析、csv 解析、镜像计数）
    preset    预设与镜像快照命令
    fetch     数据拉取命令
    position  仓位建议命令
    holdings  实盘分析命令
"""
import sys
from pathlib import Path

# 让 `from app import ...` 在任意 cwd 下都能工作（backend 目录入 path）
_BACKEND_DIR = str(Path(__file__).resolve().parents[1])
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
