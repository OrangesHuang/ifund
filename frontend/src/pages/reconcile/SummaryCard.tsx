import { Card, Col, Row, Statistic, Tag, Tooltip } from 'antd'
import type { ReconSummary } from './types'

const yuan = (v: number) => v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })

// 对账汇总卡：模式 + 总资产构成 + 盈亏（仅展示）+ 买卖合计 + 动作计数 + 资金约束提示
export default function SummaryCard({ summary }: { summary: ReconSummary }) {
  const c = summary.counts
  const sleeve = summary.mode === 'sleeve'
  const pnl = summary.pnl_total
  const pnlColor = pnl == null ? undefined : pnl > 0 ? '#f5222d' : pnl < 0 ? '#52c41a' : undefined
  return (
    <Card
      size="small"
      title={
        <span>
          对账汇总{' '}
          <Tooltip
            title={
              sleeve
                ? '子仓位模式：把所选预设当成账户里的一个子仓位，只调能对上赛道的基金，赛道外基金保留不动。目标按「匹配市值 + 可投现金」分配。'
                : '整盘模式：把整个账户向目标迁移，赛道外基金建议清仓。目标按「全账户市值 + 可投现金」分配。'
            }
          >
            <Tag color={sleeve ? 'blue' : 'volcano'}>{sleeve ? '子仓位' : '整盘'}</Tag>
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
          <Tooltip title={sleeve ? '不属于本组合任一赛道、本次保留不动的持仓市值' : '不属于本组合任一赛道、建议清仓的持仓市值'}>
            <Statistic
              title={sleeve ? '赛道外（保留）' : '赛道外（清仓）'}
              value={yuan(summary.outside_value)}
              suffix="元"
              valueStyle={{ color: summary.outside_value > 0 ? '#8c8c8c' : undefined }}
            />
          </Tooltip>
        </Col>
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
