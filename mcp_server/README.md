# iFund MCP 服务器

把 iFund 后端的数据能力以 [MCP](https://modelcontextprotocol.io) 工具形式暴露给本机 agent（如 OpenClaw）。

## 认证

- agent 只持有一枚**长期个人访问令牌（PAT）**，通过环境变量 `IFUND_API_TOKEN` 注入。
- 服务器内部用 PAT 经 `/api/auth/token/exchange` 换取短期 JWT 并缓存，过期自动续；agent 无需感知。
- PAT 在网页端「个人访问令牌」处创建，**明文仅显示一次**，请妥善保存；可随时吊销。
- PAT 绑定具体用户，因此 agent 看到的预设、镜像等数据与该用户网页端完全一致（多用户隔离）。

## 配置

| 环境变量 | 说明 | 默认 |
| --- | --- | --- |
| `IFUND_BASE_URL` | 后端地址 | `http://127.0.0.1:8000` |
| `IFUND_API_TOKEN` | 个人访问令牌（必填） | 无 |

## 在 OpenClaw 中接入

在 OpenClaw 的 MCP 配置中新增一个 stdio server（用后端 venv 的 Python）：

```json
{
  "mcpServers": {
    "ifund": {
      "command": "/Users/huangcheng/Desktop/ifund/backend/venv/bin/python",
      "args": ["/Users/huangcheng/Desktop/ifund/mcp_server/server.py"],
      "env": {
        "IFUND_BASE_URL": "http://127.0.0.1:8000",
        "IFUND_API_TOKEN": "ifd_你的令牌"
      }
    }
  }
}
```

## 提供的工具

只读：

- `search_funds(keyword, limit)` — 按代码/名称模糊搜索
- `screen_funds(keyword, name_contains, fund_types, conds, order_by, limit, with_nav)` — 条件筛选（带详情指标）
- `get_fund_detail(code)` — 单只基金完整详情 + 前十大持仓
- `list_fund_types()` — 基金分类
- `get_trade_calendar(year)` — 交易日历
- `list_presets()` — 当前用户的筛选预设
- `get_snapshot(preset_id)` — 预设的镜像快照

写入：

- `create_preset(name, ...)` — 新建/覆盖预设
- `delete_preset(preset_id)` — 删除预设
- `save_snapshot(preset_id, limit)` — 按预设重新筛选并存镜像
- `fetch_fund_data(module, ...)` — **会写库**，发起详情/持仓/净值拉取任务（同类任务互斥，已有运行中返回 409）

`conds` 元素形如 `"sharpe_3y:gte:1"`（字段:操作符:值；操作符 `gt/gte/lt/lte/eq/neq`）。

## 本地手动测试

```bash
cd /Users/huangcheng/Desktop/ifund
IFUND_API_TOKEN=ifd_xxx ./backend/venv/bin/python mcp_server/server.py
```

（stdio 模式会等待 MCP 客户端通过标准输入输出通信，直接运行不会有可见输出。）
