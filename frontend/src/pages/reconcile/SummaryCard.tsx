import { Card, Col, Row, Statistic, Tag, Tooltip } from 'antd'
import type { ReconSummary } from './types'

const yuan = (v: number) => v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })

// 对账汇总卡：模式 + 总资产构成 + 盈亏（仅展示）+ 买卖合计 + 动作计数 + 资金约束提示
const MODE_META: Record<ReconSummary['mode'], { label: string; color: string; tip: string }> = {
  sleeve: {
    label: '子仓位', color: 'blue',
    tip: '把所选预设当成账户里的一个子仓位，只调能对上赛道的基金，赛道外保留不动。目标按「匹配市值 + 可投现金」分配。',
  },
  swap: {
    label: '智能换仓', color: 'gold',
    tip: '在子仓位目标下，按「现金→赛道外→超配减仓」优先级把低配缺口配对到资金来源，生成「卖A→买B」换仓清单。赛道外够补即止、不强制全清，尽量不动赛道内已有持仓。',
  },
  whole: {
    label: '整盘', color: 'volcano',
    tip: '把整个账户向目标迁移，赛道外基金建议清仓。目标按「全账户市值 + 可投现金」分配。',
  },
}

export default function SummaryCard({ summary }: { summary: ReconSummary }) {
  const c = summary.counts
  const sleeve = summary.mode === 'sleeve'
  const swap = summary.mode === 'swap'
  const m = MODE_META[summary.mode]
  const pnl = summary.pnl_total
  const pnlColor = pnl == null ? undefined : pnl > 0 ? '#f5222d' : pnl < 0 ? '#52c41a' : undefined
  return (
    <Card
      size="small"
      title={
        <span>
          对账汇总{' '}
          <Tooltip title={m.tip}>
            <Tag color={m.color}>{m.label}</Tag>
          </Tooltip>
        </span>
      }
    >
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={8} md={6}>
          <Statistic title="总资产" value={yuan(summary.total_asset)} suffix="元" />
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Tooltip title="对上赛道、参与本次调仓的持仓市值">
            <Statistic title="匹配市值" value={yuan(summary.matched_total)} suffix="元" />
          </Tooltip>
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Statistic title="可投现金" value={yuan(summary.cash)} suffix="元" />
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Tooltip title="不属于本组合任一赛道的持仓市值">
            <Statistic
              title={sleeve ? '赛道外（保留）' : swap ? '赛道外（按需卖出）' : '赛道外（清仓）'}
              value={yuan(summary.outside_value)}
              suffix="元"
              valueStyle={{ color: summary.outside_value > 0 ? '#8c8c8c' : undefined }}
            />
          </Tooltip>
        </Col>
        {swap && (
          <Col xs={24} sm={16} md={18}>
            <Tooltip title="本次换仓的买入资金来源构成，按优先级：现金 → 赛道外卖出 → 赛道内超配减仓">
              <Statistic
                title="换仓资金来源"
                valueRender={() => (
                  <span style={{ fontSize: 16 }}>
                    现金 <b style={{ color: '#1677ff' }}>{yuan(summary.from_cash ?? 0)}</b>
                    {' + '}赛道外卖出 <b style={{ color: '#722ed1' }}>{yuan(summary.from_outside ?? 0)}</b>
                    {' + '}超配减仓 <b style={{ color: '#d48806' }}>{yuan(summary.from_trim ?? 0)}</b>
                    {' = 买入 '}<b style={{ color: '#fa541c' }}>{yuan(summary.buy_total)}</b> 元
                  </span>
                )}
              />
            </Tooltip>
          </Col>
        )}
        {summary.has_cost && (
          <>
            <Col xs={12} sm={8} md={6}>
              <Tooltip
                title={`基于有成本的持仓（${yuan(summary.cost_covered_mv)} 元）；仅展示，不参与调仓决策`}
              >
                <Statistic
                  title="未实现盈亏"
                  value={pnl == null ? '—' : `${pnl > 0 ? '+' : ''}${yuan(pnl)}`}
                  suffix={pnl == null ? '' : '元'}
                  valueStyle={{ color: pnlColor }}
                />
              </Tooltip>
            </Col>
            <Col xs={12} sm={8} md={6}>
              <Statistic
                title="收益率"
                value={summary.return_pct == null ? '—' : summary.return_pct}
                suffix={summary.return_pct == null ? '' : '%'}
                precision={summary.return_pct == null ? undefined : 2}
                valueStyle={{ color: pnlColor }}
              />
            </Col>
          </>
        )}
        <Col xs={12} sm={8} md={6}>
          <Statistic title="建议买入合计" value={yuan(summary.buy_total)} suffix="元" valueStyle={{ color: '#fa541c' }} />
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Statistic title="建议卖出合计" value={yuan(summary.sell_total)} suffix="元" valueStyle={{ color: '#8c8c8c' }} />
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Statistic title="配平后剩余现金" value={yuan(summary.leftover_cash)} suffix="元" />
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Statistic title="缓冲带" value={(summary.band * 100).toFixed(1)} suffix="%" />
        </Col>
      </Row>
      <div style={{ marginTop: 12 }}>
        {c.open > 0 && <Tag color="volcano">建仓 {c.open}</Tag>}
        {c.add > 0 && <Tag color="orange">加仓 {c.add}</Tag>}
        {c.trim > 0 && <Tag color="default">减仓 {c.trim}</Tag>}
        {c.exit > 0 && <Tag color="default">清仓 {c.exit}</Tag>}
        {c.keep > 0 && <Tag color="blue">保留 {c.keep}</Tag>}
        {c.hold > 0 && <Tag>不动 {c.hold}</Tag>}
        {summary.scaled && (
          <Tag color="gold" style={{ marginLeft: 8 }}>
            本轮受可投资金约束，买入已等比缩减，未完全到位
          </Tag>
        )}
      </div>
    </Card>
  )
}
