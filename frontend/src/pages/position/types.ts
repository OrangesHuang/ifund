// 仓位建议页的数据结构（对应后端 /api/position/run 返回）

export interface ProsperityBreakdown {
  total: number
  momentum: number
  risk_adj: number
  breadth: number
  consistency: number
}

export interface DeviationInfo {
  d20: number
  d60: number
  combined: number
}

export interface PositionFund {
  code: string
  name: string
  score: number
  sharpe_3y: number | null
  sharpe_1y: number | null
  max_drawdown_3y: number | null
  max_drawdown_1y: number | null
  return_ytd: number | null
  drawdown_ytd: number | null
  position_stock: number | null
  scale: number | null
}

export interface NavCurvePoint {
  date: string
  nav: number  // 相对窗口起点 rebase 到 1.0 的累计净值
}

// 代表基金的前十大重仓股（含行业、占净值比例）
export interface PositionHolding {
  code: string
  name: string
  ratio: number      // 占净值比例（%）
  industry: string   // 申万行业标签
}

// 底层持仓穿透：把各簇代表基金前十大股票按目标权重累加
export interface LookthroughFundRef {
  name: string
  ratio: number  // 该股在这只基金中的占净值比例（%）
}

export interface LookthroughStock {
  code: string
  name: string
  industry: string     // 申万行业标签
  exposure: number     // 组合穿透后该股票的实际仓位（%）
  fund_count: number   // 被几只代表基金持有（≥2 即重叠）
  funds: LookthroughFundRef[]
}

// 行业聚合：组合穿透后各行业的总仓位
export interface LookthroughIndustry {
  industry: string
  exposure: number     // 该行业累计穿透仓位（%）
  stock_count: number  // 该行业下的不同股票数
}

export interface Lookthrough {
  funds_covered: number    // 有前十大数据、参与穿透的代表基金数
  total_stocks: number     // 累计去重后的不同股票数
  overlap_stocks: number   // 被 ≥2 只基金同时持有的股票数
  visible_position: number // 前十大穿透后组合的股票总仓位（%）
  stocks: LookthroughStock[]
  industries: LookthroughIndustry[]
}

export interface PositionIndustry {
  label: string
  ratio: number
}

export interface Recommendation {
  tag: string
  reason: string
}

export interface PositionItem {
  cluster_id: number
  cluster_name: string
  top_industries: PositionIndustry[]
  fund_count: number
  fund: PositionFund
  nav_points: number
  prosperity: ProsperityBreakdown
  deviation: DeviationInfo
  nav_curve: NavCurvePoint[]
  holdings: PositionHolding[]
  base_weight: number
  weight: number
  recommendation: Recommendation
}

export interface PositionMeta {
  n_clusters: number
  base_weight: number
  nav_missing: string[]
}

export interface ClusterMetaBrief {
  n: number
  dropped: number
  total: number
  t: number
  target: number
}

export interface PortfolioPoint {
  date: string       // 交易日 YYYY-MM-DD
  nav: number        // 组合净值（共同起点 rebase 到 1.0）
  drawdown: number   // 相对历史峰值的回撤，负百分比（如 -5.2）
}

export interface Portfolio {
  curve: PortfolioPoint[]
  max_drawdown: number   // 最大回撤（正小数，如 0.23 表示 23%）
  annual_return: number  // 年化收益（小数）
  annual_vol: number     // 年化波动（小数）
  sharpe: number         // 夏普比率（rf=0）
}

export interface PositionResult {
  items: PositionItem[] | null
  portfolio?: Portfolio
  lookthrough?: Lookthrough
  meta?: PositionMeta
  cluster_meta?: ClusterMetaBrief
  reason?: string
}
