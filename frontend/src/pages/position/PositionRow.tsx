import { Tag, Tooltip } from 'antd'
import ProsperityBars from './ProsperityBars'
import type { PositionItem } from './types'

const TAG_COLOR: Record<string, string> = { 加码: 'red', 标配: 'blue', 减码: 'default' }

// 单簇仓位建议行：左=目标权重+标签，中=簇/代表基金，右=景气四因子+乖离+理由
export default function PositionRow({ item, maxWeight }: { item: PositionItem; maxWeight: number }) {
  const { fund, prosperity: pros, deviation: dev, recommendation: rec } = item
  const pct = (item.weight * 100).toFixed(1)
  const basePct = (item.base_weight * 100).toFixed(1)
  const rel = item.weight - item.base_weight
  const industries = item.top_industries.map((i) => i.label).join(' / ') || item.cluster_name
  const noNav = item.nav_points < 60

  return (
    <div
      style={{
        display: 'flex',
        gap: 16,
        padding: '14px 0',
        borderBottom: '1px solid rgba(140,140,140,0.15)',
        alignItems: 'flex-start',
      }}
    >
      {/* 左：目标权重 */}
      <div style={{ width: 150, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
          <span style={{ fontSize: 26, fontWeight: 700, lineHeight: 1 }}>{pct}%</span>
          <Tag color={TAG_COLOR[rec.tag] ?? 'blue'} style={{ marginInlineEnd: 0 }}>
            {rec.tag}
          </Tag>
        </div>
        <div style={{ marginTop: 6, background: 'rgba(140,140,140,0.18)', borderRadius: 3, height: 8 }}>
          <div
            style={{
              width: `${maxWeight > 0 ? (item.weight / maxWeight) * 100 : 0}%`,
              background: rel > 0.005 ? '#fa541c' : rel < -0.005 ? '#8c8c8c' : '#1677ff',
              height: '100%',
              borderRadius: 3,
            }}
          />
        </div>
        <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 4 }}>
          基准 {basePct}% · {rel >= 0 ? '+' : ''}
          {(rel * 100).toFixed(1)}%
        </div>
      </div>

      {/* 中：簇 + 代表基金 */}
      <div style={{ width: 240, flexShrink: 0 }}>
        <Tag color="geekblue">簇 {item.cluster_id}</Tag>
        <span style={{ fontWeight: 600 }}>{industries}</span>
        <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 6 }}>
          代表基金（簇内综合分第一 · 共 {item.fund_count} 只）
        </div>
        <div style={{ fontWeight: 600, marginTop: 2 }}>{fund.name}</div>
        <div style={{ fontSize: 12, color: '#8c8c8c' }}>
          {fund.code} · 综合分 {fund.score.toFixed(3)} · Sharpe{' '}
          {fund.sharpe_3y == null ? '-' : fund.sharpe_3y.toFixed(2)}
          {fund.scale != null ? ` · ${fund.scale.toFixed(2)} 亿` : ''}
        </div>
      </div>

      {/* 右：景气度 + 乖离 + 理由 */}
      <div style={{ flex: 1, minWidth: 240 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <span style={{ fontSize: 12, color: '#8c8c8c' }}>景气度</span>
          <b style={{ fontSize: 16 }}>{pros.total.toFixed(0)}</b>
          <Tooltip title="当前净值相对 MA20/MA60 的乖离（0.6·d20+0.4·d60），择时参考">
            <span style={{ fontSize: 12, color: '#8c8c8c' }}>· 乖离 {dev.combined.toFixed(1)}%</span>
          </Tooltip>
          {noNav && <Tag color="warning">净值不足·中性估计</Tag>}
        </div>
        <ProsperityBars pros={pros} />
        <div style={{ fontSize: 12, marginTop: 6, color: 'rgba(140,140,140,0.95)' }}>{rec.reason}</div>
      </div>
    </div>
  )
}
