// fund 模块共享：比较字段定义、操作符映射、筛选条件摘要
import type { CompareOp, Filters } from './types'

export interface CompareFieldDef {
  key: string
  label: string
}

// 高级筛选可用的比较字段（对应后端 fund_details 列）
export const COMPARE_FIELDS: CompareFieldDef[] = [
  { key: 'scale', label: '规模(亿)' },
  { key: 'return_ytd', label: '今年收益%' },
  { key: 'max_drawdown_3y', label: '回撤3年%' },
  { key: 'max_drawdown_1y', label: '回撤1年%' },
  { key: 'sharpe_3y', label: '夏普3年' },
  { key: 'sharpe_1y', label: '夏普1年' },
  { key: 'position_stock', label: '股票仓位%' },
  { key: 'position_bond', label: '债券仓位%' },
  { key: 'position_other', label: '其他仓位%' },
]

export const COMPARE_OP_OPTIONS: { label: string; value: CompareOp }[] = [
  { label: '>', value: 'gt' },
  { label: '≥', value: 'gte' },
  { label: '<', value: 'lt' },
  { label: '≤', value: 'lte' },
  { label: '=', value: 'eq' },
]

export const OP_SYMBOL: Record<CompareOp, string> = {
  gt: '>',
  gte: '≥',
  lt: '<',
  lte: '≤',
  eq: '=',
}

const FIELD_LABEL: Record<string, string> = Object.fromEntries(
  COMPARE_FIELDS.map((f) => [f.key, f.label]),
)

/** 把一组筛选条件压成简短的可读摘要片段（用于预设卡片展示）。 */
export function summarizeFilters(f: Filters): string[] {
  const parts: string[] = []
  if (f.keyword) parts.push(`含"${f.keyword}"`)
  if (f.fund_types?.length) parts.push(`类型:${f.fund_types.join('/')}`)
  for (const c of f.conditions ?? []) {
    parts.push(`${FIELD_LABEL[c.field] ?? c.field}${OP_SYMBOL[c.op]}${c.value}`)
  }
  if (f.exclude_codes?.length) parts.push(`排除${f.exclude_codes.length}只`)
  if (f.name_excludes?.length) parts.push(`排名称${f.name_excludes.length}项`)
  return parts
}

// 拉取任务的模块定义（供预设卡片「拉取▾」下拉复用）
export const FETCH_MODULES: { key: string; label: string }[] = [
  { key: 'fund_detail', label: '拉取详情' },
  { key: 'fund_holdings', label: '拉取持仓' },
  { key: 'fund_nav', label: '拉取净值' },
]
