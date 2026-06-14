# iFund 高保真架构复原文档

> 本文档目标：在不依赖原始代码的情况下，使另一个工程师（或另一个 Claude Code 实例）能够**高保真复原** iFund 的整体技术架构、设计实现与业务规则。
>
> 文档覆盖：技术架构、数据模型、接口契约、子进程拉取机制、前端状态流、业务规则、运维约束、从零复原步骤。
>
> 编写时项目状态：分支 `main`，最近提交 `feat: worker 并发拉取 + 前端轮询优化`。
>
> **数据源策略**：系统采用**多数据源（可插拔后端）设计**——业务代码与具体数据库解耦，通过统一接口访问。**当前阶段仅实现 SQLite 后端**；待 SQLite 全链路稳定后，再按相同接口契约接入 **MySQL** 后端。本文档中凡涉及"未来 MySQL"之处均明确标注，复原时**先把 SQLite 做完做对**即可。

---

## 目录

1. [项目概述与技术栈](#1-项目概述与技术栈)
2. [目录结构总览](#2-目录结构总览)
3. [数据库 Schema（完整 DDL）](#3-数据库-schema完整-ddl)
4. [数据库抽象层（核心）](#4-数据库抽象层核心)
5. [Worker 子进程架构](#5-worker-子进程架构)
6. [后端业务模块详解](#6-后端业务模块详解)
7. [认证模块](#7-认证模块)
8. [前端架构](#8-前端架构)
9. [配置与基础设施](#9-配置与基础设施)
10. [业务规则汇总](#10-业务规则汇总)
11. [关键约束与 Gotchas](#11-关键约束与-gotchas)
12. [从零复原步骤](#12-从零复原步骤)

---

## 1. 项目概述与技术栈

iFund 是一个**公募基金筛选与数据管理系统**。核心能力：

- 从 akshare（东方财富 / 新浪 / 雪球数据源）拉取基金名单、详情、持仓、净值、交易日历
- 多维度筛选基金（规模、夏普比率、回撤、仓位、名称关键词等）+ 多列排序 + 分页
- 后台异步批量拉取（子进程隔离），前端实时轮询进度，可终止
- 查询条件保存为「预设」，并可驱动批量拉取
- 用户认证（JWT）

### 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 后端框架 | **Flask 3.1**（**非** FastAPI，README 过时） | 应用工厂模式 + Blueprint |
| 后端语言 | Python ≥ 3.13 | |
| ORM | **无 ORM 运行时**。装了 flask-sqlalchemy 但仅用于声明模型（文档化用途），实际数据访问全部走**原生 SQL** | |
| 数据库 | **可插拔后端**：**SQLite**（当前唯一实现，默认）/ **MySQL**（规划中，未实现） | 由 `DB_BACKEND` 环境变量切换 |
| 数据源 | **akshare** | 必须在子进程调用（见 §5） |
| 认证 | flask-jwt-extended + bcrypt | Bearer Token |
| 前端框架 | React 18 + TypeScript | |
| 前端 UI | Ant Design 5（暗色主题）+ Tailwind CSS | |
| 前端构建 | Vite 5 | dev :9000，build 输出到 `backend/static` |

### 核心设计约束（必须牢记）

1. **akshare 网络调用与 Flask 线程的 socket fd 冲突** → 所有 akshare 调用必须运行在独立子进程（worker.py），不能在 Flask 请求线程内直接调。
2. **Pylint 必须 10.00/10**，`pyproject.toml` 的 `disable = []` 保持为空；不可避免的告警只能用**行内** `# pylint: disable=xxx`。
3. **业务代码后端无关**：所有数据访问通过统一接口 + 统一过滤语法（见 §4.3），由具体后端（当前 SQLite）负责把该语法翻译成对应 SQL。新增后端（MySQL）时业务代码零改动。

---

## 2. 目录结构总览

```
ifund/
├── start.sh                      # 一键启动（venv + 依赖 + build + 双服务）
├── pyproject.toml                # Python 元数据 + pylint 配置（disable=[]）
├── README.md                     # 部分过时（写的是 FastAPI，实为 Flask）
├── .gitignore
├── uv.lock
├── docs/
│   └── ARCHITECTURE.md           # 本文档
├── backend/
│   ├── schema_sqlite.sql         # SQLite 建表脚本（启动时自动执行）
│   ├── requirements.txt
│   ├── .env / .env.example
│   ├── data.db                   # SQLite 数据文件（gitignore）
│   └── app/
│       ├── __init__.py           # 空
│       ├── main.py               # Flask 应用工厂 create_app()
│       ├── database.py           # SQLAlchemy 全局实例 db（仅声明模型用）
│       ├── models.py             # User 模型
│       ├── schemas.py            # Pydantic schema（User/Token）
│       ├── db/                   # ★ 数据库抽象层（可插拔后端，见 §4）
│       │   ├── __init__.py       # DB_BACKEND 分发 + get_db() 单例 + 模块级函数委托
│       │   ├── base.py           # Database ABC（9 方法契约 + select_one 默认实现）
│       │   └── sqlite.py         # SqliteDatabase（统一过滤语法→SQL 解析）
│       │   # mysql.py            # （规划中，未实现）MysqlDatabase
│       ├── routers/
│       │   └── auth.py           # /api/auth 注册/登录/me
│       ├── common/
│       │   └── task_runner.py    # launch_worker/terminate_task/terminate_by_pid
│       ├── fund/                 # 基金列表
│       │   ├── models.py         # Fund / FundType / QueryPreset
│       │   ├── api/router.py
│       │   ├── crud/fund_crud.py
│       │   └── fetch/fetcher.py  # 同步拉取（无 worker）
│       ├── fund_detail/          # 基金详情
│       │   ├── models.py         # FundDetail / FetchTask
│       │   ├── api/router.py
│       │   ├── crud/detail_crud.py
│       │   └── fetch/{fetcher.py, worker.py}
│       ├── fund_holdings/        # 持仓
│       │   ├── api/router.py
│       │   ├── crud/holdings_crud.py
│       │   └── fetch/{fetcher.py, worker.py}
│       ├── fund_nav/             # 净值 + 累计收益率
│       │   ├── api/router.py
│       │   ├── crud/nav_crud.py
│       │   └── fetch/{fetcher.py, worker.py}
│       └── trade_calendar/       # 交易日历
│           ├── models.py         # TradeDate
│           ├── api/router.py
│           ├── crud/calendar_crud.py
│           └── fetch/fetcher.py  # 同步拉取（无 worker）
└── frontend/
    ├── package.json
    ├── vite.config.ts            # proxy /api→:8000, build→../backend/static
    ├── tsconfig.json
    ├── tailwind.config.js / postcss.config.js / eslint.config.js
    ├── index.html
    └── src/
        ├── main.tsx              # 入口 + ConfigProvider(darkAlgorithm, zhCN)
        ├── App.tsx               # 路由
        ├── index.css             # Tailwind + 全局暗色
        ├── api/request.ts        # axios 实例 + JWT 拦截器
        └── pages/
            ├── Login.tsx
            ├── Dashboard.tsx     # Header + Sider + Content
            ├── TradeCalendar.tsx
            └── fund/
                ├── FundPage.tsx
                ├── FundQueryCard.tsx
                ├── types.ts
                ├── index.ts
                ├── hooks/useFundData.ts   # ★ 前端状态中枢
                └── components/
                    ├── DataTaskCard.tsx
                    ├── FundDetailModal.tsx
                    ├── PresetBar.tsx
                    ├── MultiCompareFilter.tsx
                    └── FundExcludeSelect.tsx
```

**模块约定**：每个后端业务域遵循 `app/{module}/{api,crud,fetch}/` 三段式：
- `api/router.py` — Flask Blueprint，HTTP 端点
- `crud/*.py` — 数据访问封装（调用统一 DB 接口）
- `fetch/fetcher.py` — 启动拉取（同步或起 worker）
- `fetch/worker.py` — 独立子进程脚本（仅异步拉取模块有）

---

## 3. 数据库 Schema（完整 DDL）

当前仅维护一份 SQLite schema。

- SQLite：启动时 `init_db()` 执行 `schema_sqlite.sql`（`CREATE TABLE IF NOT EXISTS`，重启自动建表）。
- **未来接入 MySQL** 时新增 `schema_mysql.sql`，字段语义须与 SQLite 版**逐字段对齐**，仅类型/语法不同（见 §3.2）；届时两份 schema 须同步维护。

### 3.1 SQLite 版（`backend/schema_sqlite.sql`）完整 DDL

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS funds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    type TEXT DEFAULT '',
    fund_type TEXT DEFAULT '',
    pinyin_abbr TEXT DEFAULT '',
    pinyin_full TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_funds_code ON funds (code);
CREATE INDEX IF NOT EXISTS ix_funds_fund_type ON funds (fund_type);

CREATE TABLE IF NOT EXISTS fund_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type_name TEXT NOT NULL UNIQUE,
    category TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS query_presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    filters_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE (user_id, name)
);
CREATE INDEX IF NOT EXISTS ix_query_presets_user_id ON query_presets (user_id);

CREATE TABLE IF NOT EXISTS fund_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code TEXT NOT NULL UNIQUE,
    detail_json TEXT DEFAULT '{}',
    fetch_time TEXT,                 -- 缓存更新时刻，过期判断依据
    trade_date TEXT,                 -- NAV 结算日（缓存校验用）
    fund_name TEXT,
    fund_full_name TEXT,
    establish_date TEXT,
    scale REAL,                      -- 规模（万元）
    fund_company TEXT,
    fund_manager TEXT,
    custodian_bank TEXT,
    fund_type TEXT,
    rating_agency TEXT,
    fund_rating TEXT,
    invest_strategy TEXT,
    invest_target TEXT,
    benchmark TEXT,
    -- 仓位（%）
    position_stock REAL, position_bond REAL, position_cash REAL, position_other REAL,
    -- 风险（近1y/3y/5y）
    risk_return_ratio_1y REAL, anti_risk_ratio_1y REAL, volatility_1y REAL, sharpe_1y REAL, max_drawdown_1y REAL,
    risk_return_ratio_3y REAL, anti_risk_ratio_3y REAL, volatility_3y REAL, sharpe_3y REAL, max_drawdown_3y REAL,
    risk_return_ratio_5y REAL, anti_risk_ratio_5y REAL, volatility_5y REAL, sharpe_5y REAL, max_drawdown_5y REAL,
    -- 业绩（区间收益/最大回撤/同类排名）
    return_since_inception REAL, drawdown_since_inception REAL, rank_since_inception TEXT,
    return_ytd REAL, drawdown_ytd REAL, rank_ytd TEXT,
    return_1m REAL, rank_1m TEXT,
    return_3m REAL, drawdown_3m REAL, rank_3m TEXT,
    return_6m REAL, drawdown_6m REAL, rank_6m TEXT,
    return_1y REAL, drawdown_1y REAL, rank_1y TEXT,
    return_3y REAL, drawdown_3y REAL, rank_3y TEXT,
    return_5y REAL, drawdown_5y REAL, rank_5y TEXT,
    -- 历年（2015–2025），每年三列
    return_2015 REAL, drawdown_2015 REAL, rank_2015 TEXT,
    return_2016 REAL, drawdown_2016 REAL, rank_2016 TEXT,
    return_2017 REAL, drawdown_2017 REAL, rank_2017 TEXT,
    return_2018 REAL, drawdown_2018 REAL, rank_2018 TEXT,
    return_2019 REAL, drawdown_2019 REAL, rank_2019 TEXT,
    return_2020 REAL, drawdown_2020 REAL, rank_2020 TEXT,
    return_2021 REAL, drawdown_2021 REAL, rank_2021 TEXT,
    return_2022 REAL, drawdown_2022 REAL, rank_2022 TEXT,
    return_2023 REAL, drawdown_2023 REAL, rank_2023 TEXT,
    return_2024 REAL, drawdown_2024 REAL, rank_2024 TEXT,
    return_2025 REAL, drawdown_2025 REAL, rank_2025 TEXT
);
CREATE INDEX IF NOT EXISTS ix_fund_details_fund_code ON fund_details (fund_code);
CREATE INDEX IF NOT EXISTS ix_fund_details_trade_date ON fund_details (trade_date);

CREATE TABLE IF NOT EXISTS fetch_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,          -- fetch_fund_detail / fetch_fund_holdings / fetch_fund_nav / fetch_trade_calendar
    status TEXT NOT NULL DEFAULT 'running',  -- running / finished / terminated
    target_count INTEGER DEFAULT 0,   -- 目标基金数
    success_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    current_count INTEGER DEFAULT 0,  -- 已处理数
    executor_ip TEXT DEFAULT '',      -- 执行机 IP（分布式终止用）
    executor_thread TEXT DEFAULT '',  -- worker 进程 PID（字符串）
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_fetch_tasks_task_type ON fetch_tasks (task_type);

CREATE TABLE IF NOT EXISTS trade_dates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS ix_trade_dates_trade_date ON trade_dates (trade_date);

CREATE TABLE IF NOT EXISTS fund_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code TEXT NOT NULL,
    quarter TEXT NOT NULL,            -- 报告期 YYYYQN（如 2024Q1）
    holding_type TEXT NOT NULL DEFAULT 'stock',  -- stock / bond
    asset_code TEXT NOT NULL,         -- 股票/债券代码
    asset_name TEXT NOT NULL DEFAULT '',
    hold_ratio REAL,                  -- 占净值比例（%）
    hold_amount REAL,                 -- 持股数（债券为 NULL）
    hold_market_value REAL,           -- 持仓市值
    raw_data TEXT DEFAULT '{}',       -- akshare 原始行 JSON
    fetch_time TEXT,
    UNIQUE (fund_code, quarter, holding_type, asset_code)
);
CREATE INDEX IF NOT EXISTS ix_fund_holdings_fund_code ON fund_holdings (fund_code);
CREATE INDEX IF NOT EXISTS ix_fund_holdings_quarter ON fund_holdings (quarter);

CREATE TABLE IF NOT EXISTS fund_nav (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code VARCHAR(10) NOT NULL,
    trade_date VARCHAR(10) NOT NULL,
    nav FLOAT,                        -- 单位净值
    acc_nav FLOAT,                    -- 累计净值
    daily_return FLOAT,               -- 日增长率（%）
    fetch_time TEXT,
    UNIQUE (fund_code, trade_date)
);
CREATE INDEX IF NOT EXISTS ix_fund_nav_fund_code ON fund_nav (fund_code);
CREATE INDEX IF NOT EXISTS ix_fund_nav_trade_date ON fund_nav (trade_date);

CREATE TABLE IF NOT EXISTS fund_cum_return (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code VARCHAR(10) NOT NULL,
    trade_date VARCHAR(10) NOT NULL,
    cum_return FLOAT,                 -- 累计收益率（%）
    fetch_time TEXT,
    UNIQUE (fund_code, trade_date)
);
CREATE INDEX IF NOT EXISTS ix_fund_cum_return_fund_code ON fund_cum_return (fund_code);
CREATE INDEX IF NOT EXISTS ix_fund_cum_return_trade_date ON fund_cum_return (trade_date);
```

### 3.2 未来 MySQL 版（`backend/schema_mysql.sql`）类型映射约定

> 尚未实现，仅作接入指引。字段语义须与 SQLite 完全一致，仅类型/语法不同：

| SQLite | MySQL |
|---|---|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `INT AUTO_INCREMENT PRIMARY KEY` |
| `TEXT`（短字段） | `VARCHAR(10/20/50/80/100/200)`（按语义定长） |
| `TEXT`（长文本：detail_json/invest_strategy/raw_data 等） | `TEXT` / `LONGTEXT` |
| `REAL` / `FLOAT` | `DOUBLE` |
| `TEXT DEFAULT (datetime('now'))` | `DATETIME DEFAULT CURRENT_TIMESTAMP` |
| `fetch_time TEXT` | `fetch_time DATETIME` |

接入 MySQL 时还须注意：建表统一 `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`；`UNIQUE (...)` 约束需显式命名；模糊匹配的大小写行为由排序规则（collation）决定，须与 SQLite 的 `COLLATE NOCASE` 语义对齐（见 §4.3）。

### 3.3 表用途速查

| 表 | 用途 | 唯一约束 | 同步策略 |
|---|---|---|---|
| `users` | 账户 | username | — |
| `funds` | 基金名单 | code | **全量替换**（DELETE all → batch_insert） |
| `fund_types` | 基金分类派生表 | type_name | 随 funds 全量替换 |
| `query_presets` | 用户筛选预设 | (user_id, name) | CRUD |
| `fund_details` | 详情 + 业绩/风险指标 | fund_code | upsert（7 天缓存） |
| `fund_holdings` | 持仓明细 | (fund_code, quarter, holding_type, asset_code) | **按基金全量替换**（7 天缓存） |
| `fund_nav` | 单位/累计净值时序 | (fund_code, trade_date) | **增量**（只插更新行） |
| `fund_cum_return` | 累计收益率时序 | (fund_code, trade_date) | **增量** |
| `trade_dates` | 交易日历 | trade_date | **全量替换** |
| `fetch_tasks` | 异步任务进度追踪 | — | INSERT + 持续 update |

---

## 4. 数据库抽象层（核心）

> 本层是**多数据源（可插拔后端）设计**的落点：业务代码与 worker 只依赖统一接口，不关心底层是 SQLite 还是（未来的）MySQL。新增后端 = 新增一个实现 `Database` 契约的类，业务代码零改动。

### 4.1 包结构与分层

```
app/db/ 包
├── __init__.py   读 DB_BACKEND（默认 sqlite）→ get_db() 进程级单例
│                 → 模块级函数委托：select = _db.select, insert = _db.insert, ...
├── base.py       Database(ABC)：9 方法契约；select_one 在基类给默认实现（复用 select）
└── sqlite.py     SqliteDatabase：统一过滤语法 → SQL 解析 + 执行
#   mysql.py      （规划中）MysqlDatabase：相同契约，统一过滤语法 → MySQL 方言
```

调用层关系：

```
业务代码 / worker
   │  from app.db import select, insert, batch_insert, update, delete, count, ...
   ▼
app/db/__init__.py   ──(模块级函数委托)──►  get_db() 单例
                                              │ DB_BACKEND 选择
                                              ▼
                                       SqliteDatabase   （未来： MysqlDatabase）
```

- **调用风格**：业务代码统一 `from app.db import select, ...` 调用模块级函数；无需感知后端类型。
- **单例**：`get_db()` 返回进程级单例（主进程与每个 worker 子进程各持有自己的连接/单例）。
- **唯一实现源**：主进程与子进程都只通过 `app/db` 接口访问数据库，**不允许**任何模块/worker 内联第二套 DB 实现。

### 4.2 统一接口契约（9 个方法）

`Database` ABC 定义如下签名，所有后端实现必须一致，业务代码后端无关：

```python
def select(table: str, params=None) -> list[dict]
    # params: dict 或 list[tuple(key,val)]；值用统一过滤语法（§4.3）
def select_one(table: str, params: dict | None = None) -> dict | None
    # 等价于 select(...) + limit=1，取第一条；在基类 base.py 给默认实现（复用 select）
def insert(table: str, data: dict) -> dict
    # 插入一行，返回插入后的完整记录（含自增 id）
def batch_insert(table: str, rows: list[dict], batch_size=...) -> None
    # 批量插入；SQLite 用 INSERT OR REPLACE（未来 MySQL 用 INSERT ... ON DUPLICATE KEY UPDATE）
def update(table: str, filters: dict, data: dict) -> None
    # filters 为等值条件 {col: val}（内部转 eq.）
def delete(table: str, filters: dict | None = None) -> None
    # filters=None 时全表删除
def count(table: str, params=None) -> int
def list_funds_with_details(fund_params, detail_params, skip, limit, order_parts) -> tuple[int, list[dict]]
    # 特化：funds ⋈ fund_details，返回 (total, items)
def init_db(schema_sql: str) -> None
    # SQLite: executescript(schema_sql)（未来 MySQL：按需执行/迁移）
```

### 4.3 统一过滤语法（业务层统一查询语言）

业务代码用一套 **PostgREST 风格的字符串 DSL** 构造查询，由具体后端解析成对应方言 SQL。这是多后端设计的"中间表示"——业务层只写 DSL，后端负责翻译。SQLite 由 `_parse_filter` 翻译成 SQL：

| 语法 | 含义 | SQL 等价 |
|---|---|---|
| `("col", "eq.v")` | 等于 | `col = ?` |
| `("col", "neq.v")` | 不等 | `col != ?` |
| `("col", "gt.v")` / `gte.` | 大于 / ≥ | `col > ?` / `>=` |
| `("col", "lt.v")` / `lte.` | 小于 / ≤ | `col < ?` / `<=` |
| `("col", "ilike.*kw*")` | 模糊（不分大小写） | `col LIKE ? COLLATE NOCASE`（`*`→`%`） |
| `("col", "not.ilike.*kw*")` | 模糊取反 | `col NOT LIKE ?` |
| `("col", "in.(a,b,c)")` | 在集合内 | `col IN (?,?,?)` |
| `("col", "not.in.(a,b,c)")` | 不在集合内 | `col NOT IN (?,?,?)` |
| `("or", "(c1.eq.a,c2.ilike.*b*)")` | OR 组合 | `(c1=? OR c2 LIKE ?)` |
| `("select", "a,b,c")` | 投影列 | `SELECT a,b,c` |
| `("order", "col.desc,col2.asc")` | 排序 | `ORDER BY col DESC, col2 ASC` |
| `("limit", n)` / `("offset", n)` | 分页 | `LIMIT n` / `OFFSET n` |

SQLite 翻译关键实现（`sqlite.py`）：`_parse_filter(col, val)` 逐前缀匹配操作符；`_parse_or` 用正则 `,(?=[^()]*(?:\(|$))` 切分 OR 子句；`_build_where` 统一组装 select/order/limit/offset/where。所有值走参数化绑定（防注入）。`_quote_col` 处理 `table.field` 形式（JOIN 用）。

> 未来 MySQL 后端须实现同一套 DSL 的完整解析（含 `neq/gt/lt/not.in/or`），并把 `ilike`/`COLLATE NOCASE` 映射到对应的大小写不敏感比较（如 utf8mb4 的 `_ci` 排序规则）。

### 4.4 `list_funds_with_details` 实现（重点）

这是 funds 与 fund_details 的联合查询，支持「按 detail 列筛选 + 排序 + 分页」。可排序的 detail 列白名单：

```python
{"scale", "return_ytd", "drawdown_ytd", "sharpe_3y", "sharpe_1y",
 "max_drawdown_3y", "max_drawdown_1y", "position_stock"}
```

**SQLite 实现**：单条 SQL `funds f LEFT JOIN fund_details d ON f.code = d.fund_code`，WHERE 由 `_build_fund_where`（前缀 `f.`）+ `_build_detail_where`（前缀 `d.`）拼接，`ORDER BY` 走 `_build_join_order`（默认 `f.code`），DB 层原子分页 `LIMIT/OFFSET`。返回 `(total, rows)`。

> 因 SQLite 与 MySQL 均原生支持 JOIN，该方法在两后端都可用**单条 JOIN SQL** 实现（仅方言差异），无需应用层两步合并。返回结构必须一致——`items` 每项含 `id, code, name, type, fund_type, scale, sharpe_3y, sharpe_1y, max_drawdown_3y, max_drawdown_1y, position_stock, return_ytd, drawdown_ytd`。

---

## 5. Worker 子进程架构

### 5.1 为什么用子进程

akshare 底层网络请求与 Flask 线程持有的 socket fd 冲突，在请求线程内直接调用会出错。解决方案：把每次批量拉取放进**独立 Python 进程**（`worker.py`），进程内 socket 状态干净。

### 5.2 启动与追踪流程

```
POST /api/{module}/sync
   │  ① 检查是否已有同 task_type 的 running 任务（有→409）
   │  ② （可选）解析筛选条件 → list_funds_with_details → fund_codes 子集
   ▼
fetcher.start_sync_task(...)
   ▼
common/task_runner.launch_worker(worker_script, task_type, extra_args=...)
   │  ③ insert fetch_tasks (status=running, executor_ip=本机IP)
   │  ④ subprocess.Popen([python, worker.py, task_id, --codes/--fund-types ...])
   │  ⑤ update fetch_tasks.executor_thread = 子进程 PID
   ▼
worker.py 子进程
   │  ⑥ 确定基金集合（--codes 优先；否则按 --fund-types 查 funds；否则全量）
   │  ⑦ update target_count
   │  ⑧ ThreadPoolExecutor(max_workers=8) 并发处理每只基金
   │  ⑨ 每完成一只：检查 fetch_tasks.status 是否被置 terminated（是→取消其余 future）
   │  ⑩ update current_count/success_count/fail_count
   │  ⑪ finally: status = terminated / finished
   ▲
前端每 3s 轮询 GET /api/{module}/task/running 读进度
用户点终止 → POST /api/{module}/task/{id}/terminate
```

### 5.3 `common/task_runner.py`（共享工具，82 行）

```python
_processes: dict[int, subprocess.Popen] = {}   # 内存中 task_id → 进程句柄

def get_local_ip() -> str
    # UDP connect 8.8.8.8 取本机出口 IP；失败回退 127.0.0.1

def launch_worker(worker_script, task_type, *, extra_args=None,
                  python_exe=None, env=None, stderr=subprocess.DEVNULL) -> int:
    # insert fetch_tasks → Popen → 回填 PID → 返回 task_id
    # cmd = [python_exe, worker_script, str(task_id)] + (extra_args or [])

def terminate_task(task_id: int):
    # 本地进程 proc.terminate()，5s 超时则 kill()

def terminate_by_pid(pid: str):
    # os.kill(int(pid), SIGTERM)；用于跨机远程终止
```

### 5.4 三个 worker 的 DB 访问

三个异步拉取模块各有 worker，统一通过 `from app.db import ...` 访问数据库，**不内联任何 DB 实现**：

| Worker | DB 访问方式 |
|---|---|
| `fund_nav/fetch/worker.py` | `from app.db import select, select_one, update, batch_insert` |
| `fund_holdings/fetch/worker.py` | `from app.db import select, select_one, update, delete, batch_insert` |
| `fund_detail/fetch/worker.py` | `from app.db import select, select_one, update, delete, batch_insert` |

> 历史上 `fund_detail` worker 曾内联一套简化的 DB 实现（filter 解析缺 `neq/gt/lt/not.in/or`），是维护隐患与潜在 bug 来源。复原时**禁止**重蹈覆辙——所有 worker 与业务代码共用 `app/db` 的唯一实现。

### 5.5 子进程 sys.path 与打包（PyInstaller）

worker 是独立脚本，需自行把 backend 根目录加入 `sys.path` 才能 `import app.*`：

- 普通运行：`backend_dir = Path(__file__).resolve().parents[3]`，`sys.path.insert(0, backend_dir)` + `os.chdir(backend_dir)`。
- 打包运行（仅 `fund_detail` 链路支持）：`fetcher.start_sync_task` 检测 `sys.frozen`，设置 `PYTHONPATH=sys._MEIPASS` 和 `IFUND_BACKEND_DIR=_MEIPASS`，用系统 `python3` 起 worker（因为 app 包被编进 PYZ，_MEIPASS 仅含 akshare/pandas 等）。worker 启动时若读到 `IFUND_BACKEND_DIR` 就用它，否则用默认相对路径。

### 5.6 终止机制（含分布式）

`POST /api/{module}/task/{id}/terminate`：
1. 查 fetch_tasks 取 `executor_ip`。
2. 本地 `terminate_task(task_id)`（SIGTERM 进程）。
3. 若 `executor_ip != 本机IP`：HTTP `POST http://{executor_ip}:8000/api/{module}/terminate {"pid": executor_thread}` 让远程机终止。
4. update `status=terminated`。

`POST /api/{module}/terminate`（远程接收端）：取 `pid` → `terminate_by_pid(pid)` → 把对应 running 任务置 `terminated`。

worker 内部每完成一只基金会查 `fetch_tasks.status`，发现 `terminated` 就 cancel 剩余 future 并退出（协作式终止）。

---

## 6. 后端业务模块详解

所有 Blueprint 都以 `/api/{module}` 为前缀。下表为端点总览，详情见各小节。

| 模块 | Blueprint 前缀 | 数据源 akshare API | 拉取方式 |
|---|---|---|---|
| `fund` | `/api/fund` | `ak.fund_name_em()` | 同步（请求线程内） |
| `fund_detail` | `/api/fund_detail` | `fund_individual_basic_info_xq` / `_detail_hold_xq` / `_analysis_xq` / `_achievement_xq` | worker 子进程 |
| `fund_holdings` | `/api/fund_holdings` | `fund_portfolio_hold_em` + `fund_portfolio_bond_hold_em` | worker 子进程 |
| `fund_nav` | `/api/fund_nav` | `fund_open_fund_info_em`（单位净值走势 / 累计收益率走势） | worker 子进程 |
| `trade_calendar` | `/api/trade_calendar` | `tool_trade_date_hist_sina()` | 同步（请求线程内） |

### 6.1 `fund` 模块（基金列表，核心筛选）

**`fetch/fetcher.py`**（39 行，同步）：`fetch_all_funds()` 调 `ak.fund_name_em()` 拿全部基金 → `_classify` 分类：
- `stock`（偏股）类判定：`type ∈ {股票型, 混合型-偏股, 混合型-灵活}` **且** 名称不含「指数/ETF」**且** 名称含「C」**且** 不含「A」。
- 否则归 `non_stock`。
- 返回行含 `code, name, type, fund_type(stock/non_stock), pinyin_abbr, pinyin_full`。

**`crud/fund_crud.py`**（42 行）：`replace_all(funds)`：
1. `delete("funds")` 全表删除
2. `batch_insert("funds", funds)`
3. `_sync_fund_types`：`delete("fund_types")` → 从 funds 的 type 集合派生 → stock 类别优先（用集合差集保证一个 type 只归一类）→ batch_insert。

**`api/router.py`**（~246 行，最复杂）：

`parse_fund_filter_args(args)` → `(fund_params, detail_params)`：
- `keyword` → `("or", "(code.ilike.*kw*,name.ilike.*kw*)")`
- `name_contains` → `("name", "ilike.*kw*")`
- `fund_types`（逗号分隔）→ `("type", "in.(...)")`
- `exclude_codes` → `("code", "not.in.(...)")`
- `name_excludes`（可多个）→ 多个 `("name", "not.ilike.*kw*")`
- `_parse_range_params`：对 `scale / sharpe_3y / sharpe_1y / drawdown_3y / drawdown_1y / position_stock / position_bond / position_other` 的 `_min`/`_max` → detail_params 的 `gte.`/`lte.`

端点：
- `GET /list` — query：筛选参数 + `skip` + `limit` + `order_by`（`field:asc|desc`）。`allowed_sort_fields = {scale, return_ytd, drawdown_ytd, sharpe_3y, sharpe_1y, max_drawdown_3y, position_stock}`（全是 detail 列）。调 `list_funds_with_details` → `(total, items)`。可选 `_attach_holdings` 给每只附 top-10 股票持仓。
- `GET /search?keyword=` — 名称/代码模糊。
- `GET /search_by_codes?codes=` — 按代码集合批量取。
- `GET /types` — 返回 fund_types 列表。
- `GET /<code>` — 单只详情。
- `POST /sync` — **同步**全量替换（请求线程内拉取 + replace_all），无 worker。
- `GET/POST/PUT/DELETE /presets` — 查询预设 CRUD（按当前 JWT 用户隔离）。

> 排序陷阱：按 `fund_details` 列排序时不能用 funds 表的过滤语法直接 sort，必须走 `list_funds_with_details` 的 JOIN 路径。

### 6.2 `fund_detail` 模块（详情，4 个雪球 API）

**`crud/detail_crud.py`**：`EXPIRE_DAYS = 7`。`is_expired(fund_code)` 基于 `fetch_time`（**不是** trade_date）：无记录 / 无 fetch_time / `now - fetch_time > 7天` / 解析失败 → 过期。

**`fetch/worker.py`**（最大）：
- 4 个雪球 API：`fund_individual_basic_info_xq`（基础信息）、`fund_individual_detail_hold_xq`（仓位）、`fund_individual_analysis_xq`（风险指标）、`fund_individual_achievement_xq`（业绩/历年/排名）。
- `_map_detail_to_columns` 把四份返回拍平成约 100 个 DB 列。
- `_CONCURRENCY = 8` 的 ThreadPoolExecutor。
- 缓存校验：存储的 `trade_date` 与最新 nav_date 一致即视为有效（跳过）。
- DB 访问统一走 `app.db`（见 §5.4）。

端点（`api/router.py`）：`POST /sync`（按筛选条件或全量起 worker）、`GET /task/running`、`POST /task/{id}/terminate`、`POST /terminate`（远程终止接收端）。

### 6.3 `fund_holdings` 模块（持仓）

**`fetch/worker.py`**（229 行）：
- `ak.fund_portfolio_hold_em(code, year)`（股票）+ `ak.fund_portfolio_bond_hold_em(code, year)`（债券），年份范围 `current_year-1 .. current_year`。
- `_normalize_quarter`：「2024年1季度」→「2024Q1」。
- `_dedup_rows` 按 `(fund_code, quarter, holding_type, asset_code)` 去重。
- 债券行 `hold_amount` 强制置 None。
- `_upsert_fund_holdings`：先 `delete(fund_holdings, {fund_code})` → `batch_insert`（**按基金全量替换**）。
- `CACHE_DAYS = 7`，`_CONCURRENCY = 8`。

### 6.4 `fund_nav` 模块（净值 + 累计收益率，增量）

**`fetch/worker.py`**（201 行）：
- `ak.fund_open_fund_info_em(symbol, indicator="单位净值走势")` → fund_nav（nav/acc_nav/daily_return）。
- `indicator="累计收益率走势"` → fund_cum_return（cum_return）。
- **增量同步**：`_get_stored_latest_date(code)` 取已存最新日期；若 `stored_date >= latest_trade_date` 直接 `skip`；否则只插 `trade_date > stored_date` 的行。
- `latest_trade_date` 来自 `trade_dates` 表最大值（无则今天）。
- `_safe_float` 处理 NaN/None/非数。
- `_CONCURRENCY = 8`，协作式终止（每完成一只查 status）。
- CLI：`worker.py <task_id> [--fund-types a,b] [--codes x,y]`。

### 6.5 `trade_calendar` 模块（交易日历，同步）

- `fetch/fetcher.py`：`fetch_trade_dates()` 调 `ak.tool_trade_date_hist_sina()`。
- `crud/calendar_crud.py`：`replace_all`（DELETE 全部 + batch_insert）。
- `api/router.py`：`GET /dates?year=`（可选 year LIKE 过滤）、`POST /sync`（**同步**，请求线程内建 fetch_tasks 行 + replace_all，无 worker）、`GET /task/latest`。

---

## 7. 认证模块（`app/routers/auth.py`）

- 密码：`bcrypt.hashpw` / `bcrypt.checkpw`。
- Token：`create_access_token(identity=username)`（flask-jwt-extended）。
- 端点：
  - `POST /api/auth/register` — 建用户（username 唯一）。
  - `POST /api/auth/login` — 接受 JSON 或 form；返回 `{access_token}`。
  - `GET /api/auth/me` — `@jwt_required`，返回当前用户名。
- 配置（main.py）：`JWT_SECRET_KEY = SECRET_KEY 环境变量（默认 dev-secret）`，`JWT_TOKEN_LOCATION=["headers"]`，`JWT_HEADER_TYPE="Bearer"`。

---

## 8. 前端架构

### 8.1 入口与全局

- `main.tsx`：`ConfigProvider`（`locale=zhCN`，`theme.darkAlgorithm`）。
- `App.tsx`：路由 `/login`、`/`（Dashboard）、`*`（fallback）。
- `api/request.ts`：axios 实例 `baseURL="/api"`；请求拦截器从 `localStorage.token` 注入 `Authorization: Bearer`；响应 401 → 跳 `/login`。
- `vite.config.ts`：dev `server.port=9000`，`proxy /api → http://localhost:8000`，`build.outDir=../backend/static`。

### 8.2 `useFundData` Hook（状态中枢）

集中管理：filters、funds、total、pageSize、sorters（多列排序）、API 调用、预设 CRUD。**无外部状态库**。

`buildFilterParams`：把 filters 转成后端 query 参数；同字段多个 gte 取 `Math.max`，多个 lte 取 `Math.min`（多条件取交集语义）。

**三套独立轮询系统**（各 3s，`setTimeout` 递归而非 setInterval）：
- `pollRef` → `GET /api/fund_detail/task/running`
- `holdingsPollRef` → `GET /api/fund_holdings/task/running`
- `navPollRef` → `GET /api/fund_nav/task/running`

每套独立追踪对应模块的拉取任务进度，互不干扰。

### 8.3 组件

| 组件 | 职责 |
|---|---|
| `FundPage` | 页面容器 |
| `FundQueryCard` | 主表格（11 列）+ 多列排序 + 筛选区 |
| `FundDetailModal` | 单只详情弹窗 |
| `DataTaskCard` | 拉取任务进度卡（进度条 + 终止按钮），对接三套轮询 |
| `PresetBar` | 预设保存/加载/删除，可驱动批量拉取 |
| `MultiCompareFilter` | 多区间筛选（规模/夏普/回撤/仓位的 min-max） |
| `FundExcludeSelect` | 排除基金代码/名称选择器 |
| `TradeCalendar` | 交易日历页 |

`types.ts`：`FundItem, HoldingItem, RunningTask, FundTypeItem, RangeValue, QueryPreset, Filters, SortInfo`。

---

## 9. 配置与基础设施

### 9.1 环境变量（`backend/.env.example`）

```
DB_BACKEND=sqlite                 # sqlite（当前唯一实现） | mysql（规划中）
DB_PATH=                          # SQLite 文件路径（默认 backend/data.db）
SECRET_KEY=dev-secret             # JWT 密钥
# 以下为未来接入 MySQL 时使用（当前未实现，可忽略）
# MYSQL_HOST=
# MYSQL_PORT=3306
# MYSQL_USER=
# MYSQL_PASSWORD=
# MYSQL_DB=ifund
```

### 9.2 `start.sh`

创建 `backend/venv` → pip 装依赖（阿里云镜像）→ `npm install` → `npm run build`（输出 `backend/static`）→ `flask run --port 8000 --exclude-patterns "*.db"` + `vite` dev :9000；cleanup trap 退出时杀双进程。

> Flask debug reloader 用 `--exclude-patterns "*.db"` 排除 SQLite 文件，避免 WAL/SHM 变更触发无限重载。

### 9.3 `pyproject.toml`

`requires-python >=3.13`；`[tool.pylint.messages_control] disable = []`（**必须保持空**，Pylint 10/10 强制）。

### 9.4 建表方式

SQLite 启动时 `init_db()` 自动执行 `schema_sqlite.sql`（`CREATE TABLE IF NOT EXISTS`），重启幂等建表，无需手动操作。

> 未来接入 MySQL 时，`init_db()` 对 MySQL 后端的行为（自动建表 / 迁移脚本）另行约定；新增/变更字段须同时改 `schema_sqlite.sql` 与 `schema_mysql.sql`。

### 9.5 依赖（`backend/requirements.txt`）

`flask==3.1.0`、`flask-sqlalchemy==3.1.0`、`flask-jwt-extended==4.7.1`、`bcrypt==4.2.0`、`python-dotenv==1.0.1`、`akshare`、`requests`、`pandas`。

> 未来接入 MySQL 时新增驱动依赖（如 `PyMySQL` 或 `mysqlclient`）。

---

## 10. 业务规则汇总

| # | 规则 | 位置 |
|---|---|---|
| 1 | 基金名单同步是**全量替换**（DELETE all → batch_insert），非增量 | fund_crud.replace_all |
| 2 | fund_types 由 funds 的 type 派生，stock 类别优先（集合差集） | fund_crud._sync_fund_types |
| 3 | 偏股基金判定：type∈{股票型,混合型-偏股,混合型-灵活} 且 无指数/ETF 且 含C 不含A | fetcher._classify |
| 4 | 详情缓存 7 天，过期判断依据 `fetch_time`（非 trade_date） | detail_crud.is_expired |
| 5 | 详情 worker 缓存有效性另看 trade_date 是否等于最新 nav_date | fund_detail/worker |
| 6 | 持仓按基金**全量替换**（delete by fund_code + batch_insert），缓存 7 天 | holdings/worker._upsert |
| 7 | 持仓债券行 hold_amount 强制 None；报告期归一化 YYYYQN | holdings/worker |
| 8 | NAV/累计收益率**增量**同步，只插 trade_date > stored 的行 | nav/worker._process_fund |
| 9 | 交易日历**全量替换**，同步执行无 worker | trade_calendar |
| 10 | 多区间筛选：同字段多 gte 取 max、多 lte 取 min（交集语义） | 前端 buildFilterParams |
| 11 | 排序字段限白名单（全为 detail 列），按 detail 排序走 JOIN 路径 | fund/router |
| 12 | 异步任务防重：同 task_type 已有 running 则拒绝新任务 | 各 /sync |
| 13 | 终止支持跨机：executor_ip 非本机则 HTTP 转发到执行机 | terminate 流程 |

---

## 11. 关键约束与 Gotchas

1. **akshare 必须子进程**：与 Flask 线程 socket fd 冲突。
2. **Pylint 10/10**：`disable=[]` 保持空；只用行内 `# pylint: disable=xxx`（如 `broad-exception-caught`、`wrong-import-position`、`duplicate-code`、`import-outside-toplevel`、`protected-access`）。
3. **多后端契约一致性**：所有后端实现 §4.2 的 9 方法 + §4.3 的完整过滤语法（含 `neq/gt/lt/not.in/or`）；新增后端时业务代码零改动。
4. **唯一 DB 实现源**：业务代码与所有 worker 一律 `from app.db import ...`；**禁止**任何模块内联第二套 DB 实现（历史上 `fund_detail` worker 曾内联简化版 filter 解析，缺操作符，是 bug 来源——勿重蹈）。
5. **Flask reloader 排除 `*.db`**：否则 WAL/SHM 触发重载。
6. **worker 自带 sys.path 注入**：独立进程需手动把 backend 根加进 sys.path 才能 `import app.*`；打包时用 `IFUND_BACKEND_DIR` / `_MEIPASS`。
7. **未来 MySQL 接入清单**：新增 `app/db/mysql.py`（实现 `Database` 契约）+ `schema_mysql.sql`（字段与 SQLite 对齐）+ 驱动依赖 + `.env` 连接参数；`ilike`/大小写不敏感语义须对齐 SQLite 的 `COLLATE NOCASE`。
8. **README 过时**：写的是 FastAPI，实为 Flask。

---

## 12. 从零复原步骤

> 假设手上只有本文档，目标是重建可运行系统（当前阶段：**只做 SQLite 后端**）。

1. **建目录骨架**：按 §2 创建 backend/frontend 全部目录与空 `__init__.py`。
2. **写 schema**：照 §3.1 落 `schema_sqlite.sql`（字段务必与本文档一致）。
3. **DB 抽象层**：按 §4 落 `app/db/` 包：
   - `base.py`：`Database` ABC（9 方法契约 + `select_one` 基类默认实现）。
   - `sqlite.py`：`SqliteDatabase`，实现 §4.3 全部过滤操作符的解析（含 `neq/gt/lt/not.in/or`，参数化绑定）+ §4.4 的 `list_funds_with_details`（单 SQL JOIN）。
   - `__init__.py`：读 `DB_BACKEND`（默认 sqlite）+ `get_db()` 进程级单例 + 模块级函数委托（`select = _db.select` …）。
4. **task_runner**：照 §5.3 实现 launch_worker/terminate_task/terminate_by_pid/get_local_ip。
5. **业务模块**：按 §6 逐模块实现 api/crud/fetch(/worker)。worker 统一 `from app.db import ...`（不内联）。落实 §10 全部业务规则。
6. **认证**：照 §7 实现 auth 蓝图 + main.py 的 JWT 配置。
7. **应用工厂**：照 §6 注册 6 蓝图 + `/api/health` + 404→index.html SPA fallback；启动时执行 init_db。
8. **前端**：照 §8 实现 axios 拦截器、useFundData（三套轮询 + buildFilterParams 交集语义）、组件树、暗色主题。
9. **配置**：照 §9 写 `.env.example`、`start.sh`、`pyproject.toml`（disable 空）、requirements.txt。
10. **验收**：
    - `cd backend && ./venv/bin/pylint app/` → 10.00/10。
    - `./start.sh` → 访问 `http://localhost:9000`。
    - 跑通：注册登录 → fund/sync 同步名单 → 筛选/排序/分页 → fund_detail/holdings/nav 各起一次 worker → 前端进度条 → 终止任务。
11. **（后续）接入 MySQL**：SQLite 全链路稳定后，按 §11 第 7 条新增 MySQL 后端，切 `DB_BACKEND=mysql` 验证业务代码后端无关性（零改动）。

---

*文档完。技术细节以 `backend/app/` 源码为准；本文档与源码不一致时，以源码为事实，并据此更新本文档。*
