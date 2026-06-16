// 实盘对账页的数据结构（对应后端 /api/reconcile/*）

// 实盘账户：一个用户可有多个实盘（自己的 + 代管他人的），各自关联一套仓位建议（预设）
export interface Portfolio {
  id: number
  name: string
  preset_id: number | null   // 关联的仓位建议（预设）id；null=未关联
  created_at?: string
}

// 用户实盘持仓快照（持久化在 user_holdings 表；初始化金额 + 盈亏）
export interface UserHolding {
  id?: number
  fund_code: string
  fund_name: string
  market_value: number      // 快照市值（元）
  cost?: number | null      // 快照成本（元）= 市值−盈亏；null=未提供
  base_shares?: number | null
  base_date?: string | null
  updated_at?: string
}

// 实际持仓（快照 + 交易回放合成；后端 holdings_compute）
export interface ComputedHolding {
  fund_code: string
  fund_name: string
  market_value: number          // 当前市值 = 份额 × 最新单位净值
  cost?: number | null          // 合成成本（移动平均）
  shares?: number | null        // 合成份额
  latest_nav?: number | null    // 最新单位净值
  nav_date?: string | null      // 最新净值日
  pnl?: number | null           // 未实现盈亏 = 市值 − 成本
  valuation_ok?: boolean        // false=无净值，按金额累计的退化估值
}

// 实盘交易记录（holding_txns 表）：买入/卖出，转仓拆成共享 transfer_id 的一买一卖
export interface Txn {
  id: number
  fund_code: string
  fund_name: string
  txn_type: 'buy' | 'sell'
  trade_date: string
  amount: number                // 申购/赎回金额（元）
  nav?: number | null           // 落账锁定的当日单位净值
  shares?: number | null        // 折算份额 = amount ÷ nav
  transfer_id?: string | null   // 非空=属于一次转仓
  note?: string
}

// 簇（赛道）展示元信息：序号 + 名称 + 带占比的申万三级行业 top3
export interface ClusterMeta {
  seq: number
  label: string
  industries: { label: string; ratio: number }[]
}

// 对账动作：建仓 / 加仓 / 减仓 / 不动 / 清仓 / 保留（子仓位模式下的赛道外）
export type ReconAction = 'open' | 'add' | 'trim' | 'hold' | 'exit' | 'keep'

// 赛道归类方式：代码命中 / 主体名命中 / 行业相似 / 赛道外 / 无持仓数据
export type ReconMatch = 'exact' | 'name' | 'similar' | 'outside' | 'no_data' | null

// 落在某赛道下的用户持仓基金
export interface ReconUserFund {
  code: string
  name: string
  market_value: number
  cost?: number | null
  pnl?: number | null      // 未实现盈亏（市值−成本）
  match: Exclude<ReconMatch, null>
  sim: number
}

export interface ReconFundRef {
  code: string
  name: string
}

// 一行对账建议（一个目标赛道，或一只赛道外基金）
export interface ReconRow {
  cluster_id: number | null
  cluster_name: string
  weight: number          // 目标占比（小数）
  target: number          // 目标市值（元）
  actual: number          // 当前市值（元）
  pnl?: number | null     // 该赛道未实现盈亏（仅展示）
  target_fund: ReconFundRef   // 建议操作/买入的基金
  user_funds: ReconUserFund[] // 该赛道下已持有的基金
  match: ReconMatch
  sim: number | null
  action: ReconAction
  amount: number          // 建议金额：正=买入，负=卖出
  note: string
}

export interface ReconCounts {
  open: number
  add: number
  trim: number
  hold: number
  exit: number
  keep: number
}

// 一笔换仓配对：卖出某来源 → 买入某目标基金
export interface ReconTransfer {
  from_type: 'trim' | 'outside' | 'add_cash'  // 资金来源：超配减仓 / 赛道外卖出 / 追加现金
  from_code: string
  from_name: string
  from_cluster: string
  to_code: string
  to_name: string
  to_cluster: string
  to_action: 'open' | 'add'
  amount: number
}

export interface ReconSummary {
  sell_outside: boolean   // 开关：赛道外是否可卖
  trim_overflow: boolean  // 开关：赛道内超配是否可减
  base_asset: number      // 目标分配盘子
  total_asset: number     // 加满后总资产 = 当前持仓 + 追加现金
  held_total: number      // 当前持仓总市值（含赛道外）
  matched_total: number   // 对上赛道的持仓市值
  outside_value: number   // 赛道外持仓市值
  buy_total: number       // 建议买入合计
  sell_total: number      // 建议卖出合计（超配减 + 赛道外卖）
  from_trim: number       // 来自超配减仓的资金
  from_outside: number    // 来自赛道外卖出的资金
  cash_needed: number     // 系统反推「加满还差多少现金」
  band: number            // 缓冲带（占盘子比例）
  scaled: boolean         // 是否有赛道因可动用资金不足而未完全到位
  has_cost: boolean       // 是否有成本数据
  pnl_total: number | null    // 有成本部分的未实现盈亏（仅展示）
  return_pct: number | null   // 有成本部分的收益率%（仅展示）
  cost_covered_mv: number     // 有成本的持仓市值
  counts: ReconCounts
}

export interface ReconMatchCounts {
  exact: number
  name: number
  similar: number
  outside: number
  no_data: number
}

export interface ReconMeta {
  n_target_clusters: number
  match_counts: ReconMatchCounts
  outside_count: number
  transfer_count?: number
  cap?: number
  nav_as_of?: string | null
  holdings_quarter?: string | null
}

export interface ReconResult {
  rows: ReconRow[] | null
  summary?: ReconSummary
  meta?: ReconMeta
  transfers?: ReconTransfer[]
  reason?: string
}
