// 实盘对账页的数据结构（对应后端 /api/reconcile/*）

// 用户实盘持仓（持久化在 user_holdings 表）
export interface UserHolding {
  id?: number
  fund_code: string
  fund_name: string
  market_value: number      // 当前市值（元）
  cost?: number | null      // 持仓成本（元）；null=未提供。盈亏=市值−成本
  updated_at?: string
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

// 一笔换仓配对（swap 模式）：卖出某来源 → 买入某目标基金
export interface ReconTransfer {
  from_type: 'cash' | 'outside' | 'trim'   // 资金来源：现金 / 赛道外卖出 / 超配减仓
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
  mode: 'sleeve' | 'whole' | 'swap'
  base_asset: number      // 目标分配基准（子仓位=匹配市值+现金）
  total_asset: number     // 总资产 = 全部持仓市值 + 可投现金
  held_total: number      // 当前持仓总市值（含赛道外）
  matched_total: number   // 对上赛道的持仓市值
  cash: number            // 可投现金
  outside_value: number   // 赛道外持仓市值
  buy_total: number       // 建议买入合计
  sell_total: number      // 建议卖出合计
  leftover_cash: number   // 配平后剩余现金
  from_cash?: number      // swap：来自现金的资金
  from_outside?: number   // swap：来自赛道外卖出的资金
  from_trim?: number      // swap：来自超配减仓的资金
  band: number            // 缓冲带（占基准比例）
  scaled: boolean         // 是否因资金不足等比缩减了买入
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
