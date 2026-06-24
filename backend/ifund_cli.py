#!/usr/bin/env python3
"""iFund CLI 薄壳：直连 data.db 的命令行数据工具（替代 MCP，省 Token）。

实现已拆分到 ``cli/`` 包（output/helpers/preset/fetch/position/holdings）。
此文件仅作入口，便于 ``./venv/bin/python3 ifund_cli.py ...`` 调用；
等价于 ``./venv/bin/python3 -m cli ...``。命令总览见 ``ifund_cli.py -h``。
"""
from cli.__main__ import main

if __name__ == "__main__":
    main()
