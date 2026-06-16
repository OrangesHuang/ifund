// fund 模块共享类型

export interface HoldingItem {
  asset_code: string
  asset_name: string
  hold_ratio: number | null
  quarter: string
  holding_type: string
}

export interface FundItem {
  id: number
  code: string
  name: string
  type: string
  fund_type: string
  scale: number | null
  return_ytd: number | null
  drawdown_ytd: number | null
  sharpe_3y: number | null
  sharpe_1y: number | null
  max_drawdown_3y: number | null
  max_drawdown_1y: number | null
  position_stock: number | null
  position_bond: number | null
  holdings?: HoldingItem[]
  nav_series?: number[]
  [key: string]: unknown
}

export interface RunningTask {
  id: number
  task_type: string
  status: string
  target_count: number
  success_count: number
  fail_count: number
  current_count: number
  executor_ip: string
}

export interface FundTypeItem {
  type_name: string
  category: string
}

export type RangeValue = [number | null, number | null]

export type CompareOp = 'gt' | 'gte' | 'lt' | 'lte' | 'eq'

export interface CompareCondition {
  field: string
  op: CompareOp
  value: number
}

export interface QueryPreset {
  id: number
  name: string
  filters: Filters
  filters_json?: string
}

export interface Filters {
  keyword?: string
  name_contains?: string
  fund_types?: string[]
  exclude_codes?: string[]
  name_excludes?: string[]
  conditions?: CompareCondition[]
}

export interface SortInfo {
  field: string
  order: 'asc' | 'desc'
}
