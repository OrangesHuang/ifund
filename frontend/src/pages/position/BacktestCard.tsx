import { Alert, Card, Col, Row, Statistic, Table, theme } from 'antd'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { BacktestResult } from './types'

// 回测结果卡片：动量调权 vs 等权两条净值曲线 + 指标对比 + 结论。
// 验证「按动量/乖离调权」这一步相对等权是否产生净增量（追涨择时是否有效）。
export default function BacktestCard({ data }: { data: BacktestResult }) {
  const { token } = theme.useToken()
  const { strategy, equal, meta } = data

  // 两条曲线同日期同长度，按索引合并
  const merged = strategy.curve.map((p, i) => ({
    date: p.date,
    strat: +((p.nav - 1) * 100).toFixed(2),       // 累计收益率(%)
    equal: +((equal.curve[i].nav - 1) * 100).toFixed(2),
  }))

  const stratTotal = strategy.curve[strategy.curve.length - 1].nav - 1
  const equalTotal = equal.curve[equal.curve.length - 1].nav - 1
  const excessAnnual = strategy.annual_return - equal.annual_return

  // 结论：以年化超额为准，>0.5% 视为跑赢，<-0.5% 跑输，否则持平
  const verdict =
    excessAnnual > 0.005
      ? { type: 'success' as const, text: `动量调权跑赢等权：年化 +${(excessAnnual * 100).toFixed(2)}%。在这批代表基金、该区间内，按动量/乖离调权带来了正增量。` }
      : excessAnnual < -0.005
        ? { type: 'warning' as const, text: `动量调权跑输等权：年化 ${(excessAnnual * 100).toFixed(2)}%。在这批代表基金、该区间内，动量调权（追涨择时）未带来增益，简单等权更优——可考虑弱化动量倾斜或回归等权。` }
        : { type: 'info' as const, text: `动量调权与等权基本持平：年化差 ${(excessAnnual * 100).toFixed(2)}%。调权的额外复杂度在该区间未体现明显优势。` }

  const STRAT = token.colorPrimary
  const EQUAL = token.colorTextTertiary
  const fmtTick = (d: string) => `${d.slice(2, 4)}/${d.slice(5, 7)}`
  const tickGap = Math.max(1, Math.floor(merged.length / 8))
  const axisTick = { fontSize: 11, fill: token.colorTextTertiary }
  const tooltipStyle = {
    background: token.colorBgElevated,
    border: `1px solid ${token.colorBorderSecondary}`,
    borderRadius: token.borderRadius,
    fontSize: 12,
  }
  const pct = (v: number) => `${(v * 100).toFixed(2)}%`

  // 指标对比表
  const rows = [
    { key: 'total', metric: '累计收益', strat: pct(stratTotal), equal: pct(equalTotal) },
    { key: 'annual', metric: '年化收益', strat: pct(strategy.annual_return), equal: pct(equal.annual_return) },
    { key: 'vol', metric: '年化波动', strat: pct(strategy.annual_vol), equal: pct(equal.annual_vol) },
    { key: 'sharpe', metric: '夏普(rf=0)', strat: strategy.sharpe.toFixed(2), equal: equal.sharpe.toFixed(2) },
    { key: 'mdd', metric: '最大回撤', strat: pct(strategy.max_drawdown), equal: pct(equal.max_drawdown) },
  ]

  return (
    <Card size="small" title="回测验证：动量调权 vs 等权">
      <Alert type={verdict.type} showIcon message={verdict.text} style={{ marginBottom: 12 }} />

      <Row gutter={16} style={{ marginBottom: 8 }}>
        <Col span={8}>
          <Statistic
            title="动量调权 累计"
            value={stratTotal * 100}
            precision={2}
            suffix="%"
            valueStyle={{ color: stratTotal >= 0 ? '#f5222d' : '#52c41a', fontSize: 20 }}
          />
        </Col>
        <Col span={8}>
          <Statistic
            title="等权 累计"
            value={equalTotal * 100}
            precision={2}
            suffix="%"
            valueStyle={{ color: equalTotal >= 0 ? '#f5222d' : '#52c41a', fontSize: 20 }}
          />
        </Col>
        <Col span={8}>
          <Statistic
            title="年化超额"
            value={excessAnnual * 100}
            precision={2}
            suffix="%"
            valueStyle={{ color: excessAnnual >= 0 ? '#f5222d' : '#52c41a', fontSize: 20 }}
          />
        </Col>
      </Row>
      <div style={{ fontSize: 12, color: token.colorTextTertiary, marginBottom: 8 }}>
        {meta.start} ~ {meta.end} · {meta.n_funds} 只代表基金 · 每 {meta.step_days} 交易日再平衡 ·
        共 {meta.n_rebalances} 次调仓 · 每个调仓点用截至当时净值重算权重（无未来数据泄漏）
      </div>

      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={merged} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={token.colorBorderSecondary} />
          <XAxis dataKey="date" tickFormatter={fmtTick} interval={tickGap} tick={axisTick} minTickGap={16} />
          <YAxis domain={['auto', 'auto']} tickFormatter={(v) => `${v}%`} width={48} tick={axisTick} />
          <Tooltip
            labelFormatter={(d) => `日期 ${d}`}
            formatter={(v: number, name) => [`${v.toFixed(2)}%`, name === 'strat' ? '动量调权' : '等权']}
            contentStyle={tooltipStyle}
            labelStyle={{ color: token.colorTextSecondary }}
            itemStyle={{ color: token.colorText }}
          />
          <Line type="monotone" dataKey="strat" name="strat" stroke={STRAT} strokeWidth={1.8} dot={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="equal" name="equal" stroke={EQUAL} strokeWidth={1.4} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <div style={{ fontSize: 12, color: token.colorTextSecondary, margin: '4px 0 12px' }}>
        实线 = 动量调权累计收益率，虚线 = 等权对照
      </div>

      <Table
        size="small"
        rowKey="key"
        pagination={false}
        dataSource={rows}
        columns={[
          { title: '指标', dataIndex: 'metric', width: 120 },
          { title: '动量调权', dataIndex: 'strat', align: 'right' },
          { title: '等权', dataIndex: 'equal', align: 'right' },
        ]}
      />
      <div style={{ fontSize: 12, color: token.colorTextTertiary, marginTop: 8 }}>
        说明：固定当前代表基金集合，仅对比「权重怎么分」。回测口径不含行业感知再分配（依赖当下持仓、历史回测会泄漏未来数据），
        也暂无市场基准（库内指数基金缺净值）。单一区间结论仅供参考，非投资建议。
      </div>
    </Card>
  )
}
