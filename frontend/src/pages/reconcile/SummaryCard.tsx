import { Card, Col, Row, Statistic, Tag, Tooltip } from 'antd'
import type { ReconSummary } from './types'

const yuan = (v: number) => v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })

// 对账汇总卡：策略（两开关）+ 总资产构成 + 加满还差多少现金 + 资金来源 + 盈亏（仅展示）+ 动作计数
export default function SummaryCard({ summary }: { summary: ReconSummary }) {
  const c = summary.counts
  const { sell_outside, trim_overflow } = summary
  const pnl = summary.pnl_total
  const pnlColor = pnl == null ? undefined : pnl > 0 ? '#f5222d' : pnl < 0 ? '#52c41a' : undefined
  const needCash = summary.cash_needed > 0

  return (
    <Card
      size="small"
      title={
        <span>
          操作指南{' '}
          <Tag color={sell_outside ? 'purple' : 'blue'}>
            赛道外{sell_outside ? '可卖' : '保留'}
          </Tag>
          <Tag color={trim_overflow ? 'gold' : 'default'}>
            超配{trim_overflow ? '可减' : '不减'}
          </Tag>
        </span>
      }
    >
      <Row gutter={[16, 16]}>
        <Col xs={12} sm={8} md={6}>
          <Tooltip title="按目标比例分配的总盘子。超配可减时=赛道内现额(+赛道外可卖)；超配不减时=放大到最超配赛道达标。">
            <Statistic title="目标盘子" value={yuan(summary.base_asset)} suffix="元" />
          </Tooltip>
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Tooltip title="对上赛道、参与本次调仓的持仓市值">
            <Statistic title="赛道内市值" value={yuan(summary.matched_total)} suffix="元" />
          </Tooltip>
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Tooltip title="不属于本组合任一赛道的持仓市值">
            <Statistic
              title={sell_outside ? '赛道外（按需卖出）' : '赛道外（保留不动）'}
              value={yuan(summary.outside_value)}
              suffix="元"
              valueStyle={{ color: summary.outside_value > 0 ? '#8c8c8c' : undefined }}
            />
          </Tooltip>
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Tooltip title="系统反推「把各赛道加满到目标比例还差多少现金」。0 表示靠卖出腾挪即可、无需追加投入。">
            <Statistic
              title="还需追加现金"
              value={needCash ? yuan(summary.cash_needed) : '0'}
              suffix="元"
              valueStyle={{ color: needCash ? '#fa541c' : '#52c41a', fontWeight: 600 }}
            />
          </Tooltip>
        </Col>

        <Col xs={24} md={18}>
          <Tooltip title="本次买入的资金来源构成，优先级：超配减仓 → 赛道外卖出 → 追加现金兜底">
            <Statistic
              title="买入资金来源"
              valueRender={() => (
                <span style={{ fontSize: 16 }}>
                  超配减仓 <b style={{ color: '#d48806' }}>{yuan(summary.from_trim)}</b>
                  {' + '}赛道外卖出 <b style={{ color: '#722ed1' }}>{yuan(summary.from_outside)}</b>
                  {' + '}追加现金 <b style={{ color: '#fa541c' }}>{yuan(summary.cash_needed)}</b>
                  {' = 买入 '}<b style={{ color: '#fa541c' }}>{yuan(summary.buy_total)}</b> 元
                </span>
              )}
            />
          </Tooltip>
        </Col>
        <Col xs={24} md={6}>
          <Statistic title="当前持仓合计" value={yuan(summary.held_total)} suffix="元" />
        </Col>

        {summary.replace_total > 0 && (
          <Col xs={24} md={18}>
            <Tooltip title="把簇内「非目标基金」换成本簇目标基金的等额换手总额——即便它收益更高也按目标标的归一；不改变赛道仓位，仅为精确还原目标标的">
              <Statistic
                title="标的替换（等额换仓，不改仓位）"
                valueRender={() => (
                  <span style={{ fontSize: 16 }}>
                    共 <b style={{ color: '#13c2c2' }}>{yuan(summary.replace_total)}</b> 元 ·
                    簇内非目标基金 → 目标基金
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
            有赛道因可动用资金不足而未完全到位
          </Tag>
        )}
      </div>
    </Card>
  )
}
