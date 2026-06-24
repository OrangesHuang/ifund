// 基金 AI 定性分析：类型 + 枚举中文/配色词表（列表列与详情弹窗共用）
// 与后端 fund_ai_analysis 表、CLI cli/preset.py 的枚举保持一致。

export interface FundAi {
  verdict?: string | null
  rating?: number | null
  recommend?: number | null
  skill_score?: number | null
  luck_verdict?: string | null
  skill_reason?: string | null
  concentration?: string | null
  concentration_reason?: string | null
  fund_kind?: string | null // subjective(主观选股) | rotation(景气轮动) | sector(赛道押注)
  hard_thesis?: string | null
  manager?: string | null
  tenure_years?: number | null
  is_original?: number | null
  is_comanaged?: number | null
  scale_risk?: string | null
  style_stability?: string | null
  turnover_note?: string | null
  tags?: string | null // JSON 字符串数组
  confidence?: string | null
  model?: string | null
  data_basis?: string | null
  analyzed_at?: string | null
  updated_at?: string | null
}

interface EnumMeta {
  label: string
  color: string // antd Tag color
}

export const LUCK_META: Record<string, EnumMeta> = {
  solid: { label: '实力', color: 'green' },
  mixed: { label: '中性', color: 'default' },
  luck: { label: '运气', color: 'red' },
}

export const CONC_META: Record<string, EnumMeta> = {
  single_bet: { label: '单押', color: 'red' },
  focused: { label: '集中', color: 'orange' },
  diversified: { label: '分散', color: 'green' },
}

// 基金属性：主观选股 / 景气轮动 / 赛道押注。赛道=押注固定单一赛道的 beta 工具（倾向过滤），
// 轮动=靠自上而下景气比较主动切赛道（主观能力，需自行判断），主观=主动跨行业选股配置。
export const KIND_META: Record<string, EnumMeta> = {
  subjective: { label: '主观', color: 'green' },
  rotation: { label: '轮动', color: 'blue' },
  sector: { label: '赛道', color: 'red' },
}

export const SCALE_RISK_META: Record<string, EnumMeta> = {
  tiny: { label: '极小·清盘风险', color: 'red' },
  small: { label: '偏小', color: 'orange' },
  ok: { label: '适中', color: 'green' },
  large: { label: '过大', color: 'orange' },
}

export const STYLE_META: Record<string, EnumMeta> = {
  stable: { label: '稳定', color: 'green' },
  volatile: { label: '漂移', color: 'orange' },
  unproven: { label: '未证明', color: 'default' },
}

export const CONFIDENCE_META: Record<string, EnumMeta> = {
  high: { label: '高', color: 'green' },
  medium: { label: '中', color: 'blue' },
  low: { label: '低', color: 'default' },
}

/** 取枚举展示信息；未知值原样回显（灰色）。 */
export function metaOf(map: Record<string, EnumMeta>, v: string | null | undefined): EnumMeta | null {
  if (!v) return null
  return map[v] ?? { label: v, color: 'default' }
}

/** tags 字段是 JSON 字符串数组，安全解析成 string[]。 */
export function parseTags(raw: string | null | undefined): string[] {
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr.map(String) : []
  } catch {
    return []
  }
}
