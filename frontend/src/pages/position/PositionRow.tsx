import { Tag, Tooltip } from 'antd'
import MiniNavChart from './MiniNavChart'
import ProsperityBars from './ProsperityBars'
import type { PositionItem } from './types'

const TAG_COLOR: Record<string, string> = { 加码: 'red', 标配: 'blue', 减码: 'default' }

// 形如 "1.78" / "-25.3%"；空值显示 -
function fmt(v: number | null | undefined, suffix = ''): string {
  return v === null || v === undefined ? '-' : `${Number(v).toFixed(2)}${suffix}`
}

// 单簇仓位建议行：左=目标权重 | 中=簇/基金/指标/走势图 + 前十大重仓股 | 右=动量四因子（收缩）
// highlightStocks/highlightInds：穿透联动选中的股票/行业，命中的重仓股会高亮。
export default function PositionRow({
  item,
  maxWeight,
  highlightStocks,
  highlightInds,
}: {
  item: PositionItem
  maxWeight: number
  highlightStocks?: Set<string>
  highlightInds?: Set<string>
}) {
  const { fund, prosperity: pros, deviation: dev, recommendation: rec } = item
  const pct = (item.weight * 100).toFixed(1)
  const basePct = (item.base_weight * 100).toFixed(1)
  const rel = item.weight - item.base_weight
  const noNav = item.nav_points < 60
  const holdings = item.holdings ?? []

  const metric = (label: string, value: string, color?: string) => (
    <span style={{ fontSize: 12, color: '#8c8c8c' }}>
      {label} <b style={{ color: color ?? 'inherit', fontWeight: 600 }}>{value}</b>
    </span>
  )

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',   // 窄屏时各栏自动换行，避免动量条与重仓股重叠
        gap: 16,
        padding: '14px 0',
        borderBottom: '1px solid rgba(140,140,140,0.15)',
        alignItems: 'flex-start',
      }}
    >
      {/* 左：目标权重 */}
      <div style={{ width: 140, flexShrink: 0 }}>
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

      {/* 中：簇 + 代表基金 + 指标 + 走势图 + 前十大重仓股 */}
      <div style={{ flex: '1 1 460px', minWidth: 320 }}>
        <div>
          <Tag color="geekblue">簇 {item.cluster_id}</Tag>
          <span style={{ fontWeight: 600 }}>
            {item.top_industries.length
              ? item.top_industries.map((ind, i) => (
                  <span key={`${ind.label}-${i}`}>
                    {i > 0 && <span style={{ color: '#8c8c8c', fontWeight: 400 }}> / </span>}
                    {ind.label}
                    <span style={{ color: '#8c8c8c', fontWeight: 400, fontSize: 12, marginLeft: 2 }}>
                      {ind.ratio.toFixed(1)}%
                    </span>
                  </span>
                ))
              : item.cluster_name}
          </span>
        </div>
        <div style={{ fontWeight: 600, marginTop: 6 }}>
          {fund.name}
          <span style={{ fontSize: 12, color: '#8c8c8c', fontWeight: 400, marginLeft: 8 }}>
            {fund.code} · 簇内综合分第 {fund.cluster_rank} · 共 {item.fund_count} 只
          </span>
          {fund.cluster_rank > 1 && (
            <Tooltip title="为降低与其它簇的底层相关性，组合优化选了该簇内综合分次优、但行业更分散的基金替代 TOP1">
              <Tag color="purple" style={{ marginLeft: 8 }}>降相关替代</Tag>
            </Tooltip>
          )}
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, marginTop: 6, alignItems: 'flex-start' }}>
          {/* 左块：指标 + 迷你走势图 */}
          <div style={{ flex: '1 1 320px', maxWidth: 430 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2px 14px' }}>
              {metric('Sharpe3y', fmt(fund.sharpe_3y), fund.sharpe_3y && fund.sharpe_3y >= 1 ? '#f5222d' : undefined)}
              {metric('Sharpe1y', fmt(fund.sharpe_1y))}
              {metric('回撤3y', fmt(fund.max_drawdown_3y, '%'), '#fa8c16')}
              {metric('今年', fmt(fund.return_ytd, '%'), (fund.return_ytd ?? 0) >= 0 ? '#f5222d' : '#52c41a')}
              {metric('股票仓位', fmt(fund.position_stock, '%'))}
              {fund.scale != null && metric('规模', `${fund.scale.toFixed(1)}亿`)}
            </div>
            <div style={{ marginTop: 6 }}>
              <MiniNavChart data={item.nav_curve} />
            </div>
          </div>

          {/* 右块：前十大重仓股（名称 · 行业 · 占净值比例） */}
          <div style={{ flex: 1, minWidth: 240 }}>
            <div style={{ fontSize: 12, color: '#8c8c8c', marginBottom: 4 }}>
              前十大重仓股{holdings.length ? `（合计 ${holdings.reduce((a, h) => a + h.ratio, 0).toFixed(1)}%）` : ''}
            </div>
            {holdings.length === 0 ? (
              <span style={{ fontSize: 12, color: '#8c8c8c' }}>暂无持仓数据</span>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', columnGap: 20, rowGap: 1 }}>
                {holdings.map((h, i) => {
                  const hitStock = highlightStocks?.has(h.code) ?? false
                  const hitInd = highlightInds?.has(h.industry) ?? false
                  const hit = hitStock || hitInd
                  return (
                    <div
                      key={`${h.code}-${i}`}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        fontSize: 12,
                        lineHeight: '20px',
                        background: hit ? 'rgba(250,173,20,0.18)' : undefined,
                        borderRadius: hit ? 3 : 0,
                      }}
                    >
                      <span style={{ color: '#8c8c8c', width: 14, textAlign: 'right', flexShrink: 0 }}>{i + 1}</span>
                      <span
                        style={{
                          flex: 1,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          color: hitStock ? '#fa8c16' : 'inherit',
                          fontWeight: hitStock ? 600 : 400,
                        }}
                      >
                        {h.name}
                      </span>
                      <Tooltip title={h.industry}>
                        <span
                          style={{
                            color: hitInd ? '#fa8c16' : '#8c8c8c',
                            fontWeight: hitInd ? 600 : 400,
                            flexShrink: 0,
                            maxWidth: 84,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {h.industry}
                        </span>
                      </Tooltip>
                      <span style={{ flexShrink: 0, width: 46, textAlign: 'right', fontWeight: 600 }}>
                        {h.ratio.toFixed(2)}%
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 右：动量强度（收缩为固定宽度）+ 乖离 + 理由 */}
      <div style={{ width: 280, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <span style={{ fontSize: 12, color: '#8c8c8c' }}>动量强度</span>
          <b style={{ fontSize: 16 }}>{pros.total.toFixed(0)}</b>
          <Tooltip title="当前净值相对 MA20/MA60 的乖离（0.6·d20+0.4·d60），择时参考">
            <span style={{ fontSize: 12, color: '#8c8c8c' }}>· 乖离 {dev.combined.toFixed(1)}%</span>
          </Tooltip>
          {noNav && <Tag color="warning">净值不足</Tag>}
        </div>
        <ProsperityBars pros={pros} />
        <div style={{ fontSize: 12, marginTop: 6, color: 'rgba(140,140,140,0.95)' }}>{rec.reason}</div>
      </div>
    </div>
  )
}
