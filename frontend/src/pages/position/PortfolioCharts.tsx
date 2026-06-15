import { Card, Col, Row, Statistic } from 'antd'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

interface PortfolioChartsProps {
  portfolioNav: number[]
  maxDrawdown: number
}

export default function PortfolioCharts({ portfolioNav, maxDrawdown }: PortfolioChartsProps) {
  if (!portfolioNav || portfolioNav.length === 0) {
    return null
  }

  // 计算累计收益率
  const startNav = portfolioNav[0]
  const chartData = portfolioNav.map((nav, idx) => ({
    idx,
    nav: parseFloat(nav.toFixed(4)),
    return: parseFloat(((nav / startNav - 1) * 100).toFixed(2)),
  }))

  const latestNav = portfolioNav[portfolioNav.length - 1]
  const totalReturn = ((latestNav / startNav - 1) * 100).toFixed(2)

  return (
    <Row gutter={16}>
      <Col span={24}>
        <Card
          title="组合净值走势"
          size="small"
          extra={
            <span style={{ color: '#666', fontSize: 12 }}>
              起点: {startNav.toFixed(4)} | 当前: {latestNav.toFixed(4)} | 总收益: {totalReturn}%
            </span>
          }
        >
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="idx"
                stroke="#999"
                tick={{ fontSize: 12 }}
                interval={Math.floor(chartData.length / 8)}
              />
              <YAxis stroke="#999" tick={{ fontSize: 12 }} />
              <Tooltip
                contentStyle={{ backgroundColor: '#fff', border: '1px solid #ccc' }}
                formatter={(v: any) => [v.toFixed(4), '净值']}
                labelFormatter={(label) => `日期 ${label}`}
              />
              <Line
                type="monotone"
                dataKey="nav"
                stroke="#1890ff"
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      </Col>

      <Col span={24}>
        <Card title="组合风险指标" size="small">
          <Row gutter={16}>
            <Col span={12}>
              <Statistic
                title="最大回撤"
                value={maxDrawdown}
                precision={2}
                suffix="%"
                valueStyle={{ color: maxDrawdown > 20 ? '#ff7875' : '#52c41a' }}
              />
            </Col>
            <Col span={12}>
              <Statistic
                title="累计收益"
                value={totalReturn}
                precision={2}
                suffix="%"
                valueStyle={{ color: parseFloat(totalReturn) > 0 ? '#52c41a' : '#ff7875' }}
              />
            </Col>
          </Row>
        </Card>
      </Col>
    </Row>
  )
}
