import { useCallback, useEffect, useState } from 'react'
import { Button, Card, Empty, Segmented, Table, Typography, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import request from '../../api/request'
import type { HoldingsPenetration as Penetration, PenetrationIndustry, PenetrationStock } from './types'

const pct = (v: number, d = 2) => `${v.toLocaleString('zh-CN', { maximumFractionDigits: d })}%`

// 实际持仓底层穿透：把各基金前十大持仓按市值权重穿透累加，聚合到申万三级行业/个股。
// 数据源同 CLI `holdings penetration`（后端 holdings_compute.penetrate_holdings）。
export default function HoldingsPenetration({
  portfolioId, reloadSignal = 0,
}: { portfolioId: number | null; reloadSignal?: number }) {
  const [data, setData] = useState<Penetration | null>(null)
  const [by, setBy] = useState<'industry' | 'stock'>('industry')
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (!portfolioId) { setData(null); return }
    setLoading(true)
    try {
      const { data: d } = await request.get<Penetration>('/reconcile/holdings/penetration', {
        params: { portfolio_id: portfolioId },
      })
      setData(d)
    } catch {
      message.error('加载底层穿透失败')
    } finally {
      setLoading(false)
    }
  }, [portfolioId])

  useEffect(() => { load() }, [load, reloadSignal])

  const empty = !data || (data.industries.length === 0 && data.stocks.length === 0)

  return (
    <Card
      size="small"
      title={
        <span>
          底层穿透
          {data && (
            <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal', marginLeft: 8 }}>
              市值 {data.total_market_value.toLocaleString('zh-CN', { maximumFractionDigits: 0 })} 元 ·
              前十大可见仓位 {pct(data.visible_position_pct)}
            </Typography.Text>
          )}
        </span>
      }
      extra={
        <span>
          <Segmented
            size="small"
            value={by}
            onChange={(v) => setBy(v as 'industry' | 'stock')}
            options={[{ label: '按行业', value: 'industry' }, { label: '按个股', value: 'stock' }]}
            style={{ marginRight: 8 }}
          />
          <Button size="small" icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </span>
      }
    >
      <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: -4 }}>
        每只股票占整个组合的比例 = Σ（基金市值权重 × 该股占该基金净值%），仅统计各基金已披露的前十大持仓，
        故合计 = 前十大可见仓位（{data ? pct(data.visible_position_pct) : '—'}），其余为未披露部分。
      </Typography.Paragraph>

      {empty ? (
        <Empty description="暂无可穿透的持仓（需有市值且基金已披露前十大持仓数据）。" />
      ) : by === 'industry' ? (
        <Table<PenetrationIndustry>
          size="small"
          rowKey="industry"
          loading={loading}
          dataSource={data!.industries}
          pagination={false}
          columns={[
            { title: '申万三级行业', dataIndex: 'industry' },
            {
              title: '穿透占比', dataIndex: 'ratio', width: 160, align: 'right',
              render: (v: number) => pct(v, 3),
            },
            { title: '股票数', dataIndex: 'stock_count', width: 100, align: 'right' },
          ]}
        />
      ) : (
        <Table<PenetrationStock>
          size="small"
          rowKey="code"
          loading={loading}
          dataSource={data!.stocks}
          pagination={{ pageSize: 20, size: 'small' }}
          expandable={{
            expandedRowRender: (row) => (
              <Table
                size="small"
                rowKey={(f) => f.fund}
                dataSource={row.funds}
                pagination={false}
                columns={[
                  { title: '来源基金', dataIndex: 'fund' },
                  {
                    title: '基金权重', dataIndex: 'fund_weight', width: 140, align: 'right',
                    render: (v: number) => pct(v),
                  },
                  {
                    title: '占该基金净值', dataIndex: 'stock_ratio', width: 140, align: 'right',
                    render: (v: number) => pct(v),
                  },
                ]}
              />
            ),
          }}
          columns={[
            {
              title: '股票', dataIndex: 'name',
              render: (v: string, row) => (
                <span>
                  {v}
                  <Typography.Text type="secondary" style={{ fontFamily: 'monospace', marginLeft: 6, fontSize: 12 }}>
                    {row.code}
                  </Typography.Text>
                </span>
              ),
            },
            { title: '申万三级行业', dataIndex: 'industry', width: 200 },
            {
              title: '穿透占比', dataIndex: 'ratio', width: 140, align: 'right',
              render: (v: number) => pct(v, 3),
            },
            { title: '基金数', dataIndex: 'fund_count', width: 90, align: 'right' },
          ]}
        />
      )}
    </Card>
  )
}
