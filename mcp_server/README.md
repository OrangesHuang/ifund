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

## 安装依赖

MCP 服务器与后端共用同一个 venv（`backend/venv`），首次需安装依赖（会一并带来 httpx）：

```bash
cd /Users/huangcheng/Desktop/ifund
backend/venv/bin/python -m pip install -r mcp_server/requirements.txt
```

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

## 提供的工具（共 33 个，按四大能力组）

`conds` 元素形如 `"sharpe_3y:gte:1"`（字段:操作符:值；操作符 `gt/gte/lt/lte/eq/neq`）。
标 **【会写库】** 的工具会改动数据；拉取类任务同类互斥，已有运行中返回 `{"_error":409}`。

### 1) 基础能力

- `search_funds(keyword, limit)` — 按代码/名称模糊搜索
- `screen_funds(keyword, name_contains, fund_types, conds, name_excludes, order_by, limit, with_nav, with_holdings)` — 条件筛选（带详情指标）
- `get_fund_detail(code)` — 单只基金完整详情 + 前十大持仓
- `list_fund_types()` — 基金分类（供 `fund_types` 取值）
- `get_trade_calendar(year)` — 交易日列表（确定交易记录该填哪天）
- `fetch_data(target, codes, keyword, fund_types, conds)` — **【会写库】** 统一拉取入口，
  `target ∈ fund_detail / fund_holdings / fund_nav / trade_calendar / industry_sw / industry_em`
- `list_tasks()` — 汇总各模块运行中的拉取任务 + 交易日历最近一次状态
- `terminate_task(task_id, module)` — 终止某拉取任务
- `get_industry_coverage()` — 股票→行业映射覆盖率统计（聚类前据此判断是否补采）
- `list_stock_industry(market, label, status, keyword, page, page_size)` — 行业映射明细（`status=uncovered` 定位「行业不存在」）

### 2) 条件预设

- `list_presets()` — 当前用户的筛选预设
- `create_preset(name, ...)` — 新建/覆盖预设
- `update_preset(preset_id, name, ..., replace_filters)` — 改名 / 替换筛选条件（`replace_filters=True` 时整体替换 filters）
- `delete_preset(preset_id)` — 删除预设
- `get_snapshot(preset_id)` — 取预设的镜像快照
- `save_snapshot(preset_id, limit)` — **【会写库】** 按预设条件重新筛选并更新镜像（聚类/仓位/对账的输入）

### 3) 组合分析

- `run_clustering(preset_id)` — 对预设镜像做行业暴露聚类（行业暴露 / 实际资金暴露 / 代表股票 + 簇内基金）
- `run_position(preset_id, balance, cap)` — 簇级仓位建议；`balance` 均衡强度 `松`(22%)/`中`(18%)/`紧`(14%,默认)，或 `cap` 直接给上限

### 4) 实盘

- `list_portfolios()` — 全部实盘（自有 + 代管，含关联预设 id）
- `create_portfolio(name, preset_id)` — **【会写库】** 新建实盘
- `update_portfolio(portfolio_id, name, preset_id, unlink_preset)` — **【会写库】** 改名 / 改关联预设
- `delete_portfolio(portfolio_id)` — **【会写库】** 删实盘（含持仓与交易）
- `get_holdings(portfolio_id)` — 实际持仓（快照+交易合成）+ 每只基金所属赛道（簇）+ 总市值/浮盈
- `set_holding(portfolio_id, market_value, fund_name/fund_code, profit)` — **【会写库】** 录入/调整单只初始持仓快照（按金额+收益）
- `import_holdings(portfolio_id, rows)` — **【会写库】** 批量录入初始快照（**全量替换**）
- `remove_holding(portfolio_id, fund_code)` — **【会写库】** 删除单只快照
- `list_txns(portfolio_id)` — 交易记录列表
- `add_txn(portfolio_id, kind, trade_date, amount, ...)` — **【会写库】** 记一笔 买入/卖出/转仓
- `update_txn(portfolio_id, txn_id, ...)` — **【会写库】** 改一条买/卖记录
- `delete_txn(portfolio_id, txn_id)` — **【会写库】** 删一条交易记录
- `run_reconcile(portfolio_id, balance, cap, band, sell_outside, trim_overflow, preset_id)` — 生成调仓操作指南（四个旋钮均有默认值）
- `apply_rebalance(portfolio_id, transfers, trade_date)` — **【会写库】** 把 `run_reconcile` 的换仓建议一键落成交易记录
- `get_portfolio_penetration(portfolio_id)` — 实盘底层持仓穿透：前十大持仓按目标权重穿透累加、按申万三级行业聚合（行业/股票穿透占比 + 来源基金 + 未覆盖股票）

## 本地手动测试

```bash
cd /Users/huangcheng/Desktop/ifund
IFUND_API_TOKEN=ifd_xxx ./backend/venv/bin/python mcp_server/server.py
```

（stdio 模式会等待 MCP 客户端通过标准输入输出通信，直接运行不会有可见输出。）
