# iFund · 公募基金筛选、组合分析与实盘对账系统

一套**自托管**的公募基金投研工具：从公开数据源拉取基金名单、详情指标、持仓与历史净值，在此之上完成 **筛选 → 预设镜像 → 行业暴露聚类 → 簇级仓位建议 → 实盘对账/再平衡** 的完整闭环，并通过 **MCP** 把全部核心能力开放给本机 AI agent（如 OpenClaw），让 agent 在你不在电脑前时也能帮你管理基金。

> 想了解完整的技术架构、数据模型与设计决策，见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

## 🧭 这套系统在做什么

它把"选基金 → 定仓位 → 对实盘"串成一条可复用的链路，每一步的产物都是下一步的输入：

```
拉取基金数据 ──► 条件筛选 ──► 存为「预设」并镜像快照 ──► 行业暴露聚类（分赛道）
                                          │
                                          ├──► 簇级仓位建议（每个赛道配一只代表基金 + 目标比例）
                                          │
                                          └──► 实盘对账：把目标比例落到你的真实持仓，
                                                算出「该买/该卖/该转多少钱」的操作指南
```

- **预设 + 镜像快照**是主干：筛选条件存成预设，某一时点的筛选结果存成"镜像"，聚类/仓位/对账都基于这份镜像，保证口径一致、可复现。
- **实盘是独立下游**：你可以建多个实盘（自己的 + 代管别人的），各自关联一套仓位建议；持仓由「初始快照 + 交易记录」按基金会计原则（份额 × 净值、移动平均成本）合成，而非手填死数。

## ✨ 功能特性

- **基金数据管理**：基金名单同步、详情指标（收益/回撤/夏普/规模/仓位等）、前十大持仓、净值走势迷你图；详情/持仓/净值通过子进程异步拉取（akshare），带任务进度，同类任务全局互斥防并发。
- **高级筛选**：关键词、名称包含/排除、分类、代码排除，数值区间与比较条件（夏普、回撤、规模、仓位、今年收益等），排序分页。
- **筛选预设与镜像**：保存常用条件；每个预设可存"镜像快照"与"最新实时筛选"对比，直观看出新增/剔除的基金。
- **行业映射**：持仓股票 → 申万三级（主）+ 东财（兜底）行业映射，是聚类赛道标签的基础，带覆盖率统计与未覆盖定位。
- **行业暴露聚类**：按持仓行业把口味相近的基金聚成"赛道"（簇），给出行业暴露 / 实际资金暴露 / 代表股票三层视角。
- **簇级仓位建议**：每个赛道选综合分第一的代表基金，按景气度 + 乖离度合成目标权重（∑=100%），给出加码/标配/减码推荐；均衡强度可调（松/中/紧）。
- **实盘对账与再平衡**：把目标比例落到真实持仓，按赛道对齐 + 金额化，算出每笔加/减/建/清与"换仓配对"操作指南；缓冲带抗噪，两个开关（赛道外可卖 / 超配可减）覆盖四类操作意图，现金缺口由系统反推。建议可一键落成交易记录。
- **多用户隔离**：预设、镜像、实盘、访问令牌均按用户隔离。
- **对外集成（MCP）**：通过个人访问令牌（PAT）把上述全部能力安全暴露给本机 agent。

## 🧱 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.12 · Flask 3.1 · flask-jwt-extended · bcrypt · pydantic · akshare · waitress |
| 数据 | SQLite（多后端抽象层，预留 MySQL）|
| 前端 | React 18 · TypeScript · Ant Design 5 · Vite 5 · Tailwind |
| 集成 | MCP（官方 Python SDK / FastMCP）· httpx |

## 📁 目录结构

```
ifund/
├── backend/            后端 Flask 应用
│   ├── app/            应用工厂 + 各业务模块（见下）
│   ├── schema_sqlite.sql   SQLite 建表脚本
│   ├── requirements.txt    后端 + waitress + mcp 依赖
│   └── .env            本地配置（不入库）
│       app/ 业务模块：fund(筛选/预设/镜像) · fund_detail/fund_holdings/fund_nav(拉取)
│              · trade_calendar(交易日历) · stock_industry(行业映射)
│              · cluster(聚类) · position(仓位建议) · reconcile(实盘对账)
│              · routers/auth(登录 + PAT) · db(数据库抽象) · common(worker/任务)
├── frontend/           前端 React + Vite（基金/筛选/聚类/仓位/行业/实盘/交易日历/令牌）
├── mcp_server/         MCP 服务器（把核心能力暴露给 OpenClaw 等 agent，共 32 工具）
├── ARCHITECTURE.md     高保真架构文档
├── start.sh            一键启动（调试：热重载后端 :8000 + 前端 dev :9000）
├── service.sh          常驻服务管理（生产：launchd + waitress，开机自启 + 崩溃自愈）
└── pyproject.toml      pylint 配置
```

## 🚀 快速开始

### 环境要求

- **Python 3.12+**（官方 MCP SDK 需要 3.10+）
- **Node.js 18+**

### 一键启动（调试 / 开发）

```bash
./start.sh
```

脚本会自动：创建后端 venv 并装依赖 → 安装前端依赖并构建 → 启动后端（:8000，热重载）与前端开发服务（:9000，热更新）。
后端已把 `npm run build` 的前端产物从 `backend/static` 单端口（:8000）直接提供，所以**只需后端就能访问完整网页**；:9000 仅开发热更新用。

### 手动启动

```bash
cd backend
python3.12 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/flask --app app.main run --port 8000
```

## 🔁 长期常驻运行（生产）

日常调试用 `start.sh`（热重载）；想让后端**关终端、合盖、重启都不掉线**（OpenClaw 随时可连），用 `service.sh` 装成 macOS launchd 常驻服务（waitress 生产 WSGI，开机自启 + 崩溃自动重启）：

```bash
./service.sh install     # 一次性安装并启动常驻（开机自启）
./service.sh status      # 查看状态 + 探测 :8000
./service.sh logs        # 跟踪日志
./service.sh restart     # 改了后端代码后让常驻生效
./service.sh stop        # 停常驻（腾出 :8000）
./service.sh uninstall   # 卸载常驻
```

> **常驻与调试只是占用同一个 `:8000` 端口，同一时刻只能开一个**。调试流程：
> `./service.sh stop` → `./start.sh`（照常热重载）→ 调完 Ctrl-C → `./service.sh start`。
> 两者跑的是**同一份代码、同一个 `backend/data.db`**，数据不会分叉；但别让两个后端同时写（SQLite 并发写会 `database is locked`）。

## ⚙️ 配置

在 `backend/.env` 中配置（可参考 `backend/.env.example`）：

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `SECRET_KEY` | JWT 签名密钥，**启用 PAT / 对外集成前必须设强随机值** | `dev-secret`（仅开发） |
| `DB_BACKEND` | 数据库后端 | `sqlite` |
| `DB_PATH` | SQLite 数据库文件路径 | `backend/data.db` |

> ⚠️ **安全**：`SECRET_KEY` 必须 ≥32 字节随机值，否则 JWT 可被伪造（启动时对弱密钥告警）。生成：
> ```bash
> python3 -c "import secrets; print('SECRET_KEY='+secrets.token_hex(32))" >> backend/.env
> ```
> 后端应保持绑定 `127.0.0.1`，不要直接暴露到公网。

## 🤖 MCP / OpenClaw 集成

后端核心能力通过 MCP 服务器（`mcp_server/`）开放给本机 agent，**共 32 个工具，分四大能力组**：

1. **基础**：基金查询/详情、统一拉取入口（详情/持仓/净值/交易日历/行业映射）、拉取任务查询与终止、行业覆盖率/未覆盖定位。
2. **条件预设**：预设增删改查、镜像快照查询与更新。
3. **组合分析**：行业暴露聚类、簇级仓位建议（均衡强度 松/中/紧）。
4. **实盘**：实盘 CRUD、持仓快照（按金额+收益，名称可反查代码）、交易记录 CRUD、对账生成操作指南（赛道外可卖 / 超配可减 / 缓冲带 / 均衡强度均有默认值）、建议一键落账。

认证用**个人访问令牌（PAT）**：在网页端「访问令牌」页创建（明文仅显示一次），MCP 服务器自动用 PAT 换短期 JWT 调用后端，绑定用户实现多用户隔离。MCP 与后端共用 `backend/venv`。

完整配置、工具签名与示例见 [mcp_server/README.md](./mcp_server/README.md)。

## 🛠️ 开发约定

- **后端 lint**：`./backend/venv/bin/pylint app`，须保持 `10.00/10`。
- **前端类型检查**：`cd frontend && npx tsc --noEmit`；**前端 lint**：`npm run lint`。
- 后端业务文件统一使用 `from __future__ import annotations`（`mcp_server/server.py` 例外，原因见其文件头注释）。

## 📄 文档

- [ARCHITECTURE.md](./ARCHITECTURE.md) — 完整技术架构、数据模型、接口契约、从零复原步骤
- [mcp_server/README.md](./mcp_server/README.md) — MCP 服务器配置与 32 工具清单
