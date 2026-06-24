# iFund MCP 服务器

把 iFund 数据能力以 **单个 MCP 工具** 暴露给「只能走 MCP」的本机 agent（如 OpenClaw）。

> 2026-06 重构：旧版把后端 HTTP API 拆成 33 个 MCP 工具，每轮对话固定注入全部 schema
> （~8k token 开销）。现折叠为**一个** `ifund` 工具——内部直接 exec 本机 CLI
> （`backend/ifund_cli.py`，直连 `data.db`、复用后端 crud/算法层），不再走 HTTP/PAT/JWT。
> 旧实现备份在 `server.py.33tools.bak`。
> 能跑 shell 的 agent（Qoder 等）应按 `AGENTS.md` **直接调 CLI**，无需经 MCP。

## 唯一工具：`ifund(args)`

`args` 是命令行参数数组（不含 `ifund_cli.py`），返回 CLI 的文本输出。任意子命令加 `-h` 自查参数；
加 `--json` 得紧凑 JSON；默认用户 `user_id=1`（`--user N` 可改）。命令面：

- `preset   list | show --id N（或 --name X）| snapshot --id N | funds --id N [--code C][--keyword K][--ai] | ai-set --code N --data '{...}'`
- `fetch    calendar | industry --mode sw|em [--codes ..] | detail|holdings|nav [--codes ..] [--types ..]`
- `analyze  run --preset N [--balance 松|中|紧 | --cap 0.10~0.30] [--view weights|industry|stock|perf|all]`
- `holdings list | show --pid N（实际持仓按赛道簇分组，加 --penetration 附穿透）| penetration | perf | rebalance --pid N [--sell-outside] [--no-trim-overflow] [--band B]（调仓建议）`
- `holdings buy|sell --pid N --fund 代码/名称 --amount A | transfer --from .. --to .. --amount A | txns --pid N | txn-del --pid N --id T`（实盘交易）

示例：

```python
ifund(["holdings", "perf", "--pid", "6", "--json"])
ifund(["analyze", "run", "--preset", "2", "--balance", "中", "--view", "all"])
```

出错时返回 `{"_error": "exit=N", "stderr": ..., "stdout": ...}`，便于 agent 据 stderr 自纠。
输出已主动裁掉超大序列（每日 nav 曲线 / 组合每日净值与回撤）以省 Token。

## 配置

| 环境变量 | 说明 | 默认 |
| --- | --- | --- |
| `IFUND_PYTHON` | 运行 CLI 的 Python | `backend/venv/bin/python` |
| `IFUND_CLI_TIMEOUT` | 单次 CLI 超时（秒） | `1800`（fetch 联网慢，留宽裕） |

无需令牌——CLI 直连本机 `data.db`，不经登录认证。

## 安装依赖

与后端共用同一个 venv（`backend/venv`）：

```bash
cd /Users/huangcheng/Desktop/ifund
backend/venv/bin/python -m pip install -r mcp_server/requirements.txt
```

## 在 OpenClaw 中接入

stdio server（用后端 venv 的 Python）：

```json
{
  "mcpServers": {
    "ifund": {
      "command": "/Users/huangcheng/Desktop/ifund/backend/venv/bin/python",
      "args": ["/Users/huangcheng/Desktop/ifund/mcp_server/server.py"]
    }
  }
}
```

## 本地手动测试

```bash
cd /Users/huangcheng/Desktop/ifund
./backend/venv/bin/python mcp_server/server.py
```

（stdio 模式会等待 MCP 客户端通过标准输入输出通信，直接运行不会有可见输出。）
