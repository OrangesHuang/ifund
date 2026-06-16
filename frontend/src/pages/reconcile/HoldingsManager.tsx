import { useCallback, useEffect, useState } from 'react'
import { Button, Card, Empty, Table, Tag, Typography, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import request from '../../api/request'
import type { ComputedHolding } from './types'
import HoldingsEditor from './HoldingsEditor'
import TxnPanel from './TxnPanel'

const yuan = (v: number) => v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
const num = (v: number | null | undefined, d = 2) =>
  v == null ? '—' : v.toLocaleString('zh-CN', { maximumFractionDigits: d })

// 实际持仓管理：实际持仓（快照 + 交易合成，只读）+ 初始化快照（编辑）+ 交易记录。
// reloadSignal 由上层（如调仓建议批量落账）改动时触发整页重算。
export default function HoldingsManager({
  portfolioId, reloadSignal = 0,
}: { portfolioId: number | null; reloadSignal?: number }) {
  const [holdings, setHoldings] = useState<ComputedHolding[]>([])
  const [clusterMap, setClusterMap] = useState<Record<string, string>>({})
  const [hasPreset, setHasPreset] = useState(false)
  const [loading, setLoading] = useState(false)
  const [bump, setBump] = useState(0)   // 快照/交易改动 → 重算实际持仓

  const loadHoldings = useCallback(async () => {
    if (!portfolioId) { setHoldings([]); setClusterMap({}); setHasPreset(false); return }
    setLoading(true)
    try {
      const [hRes, cRes] = await Promise.all([
        request.get<{ items: ComputedHolding[] }>('/reconcile/holdings', {
          params: { portfolio_id: portfolioId },
        }),
        request.get<{ has_preset: boolean; map: Record<string, string> }>('/reconcile/holdings/clusters', {
          params: { portfolio_id: portfolioId },
        }).catch(() => ({ data: { has_preset: false, map: {} } })),
      ])
      setHoldings(hRes.data.items ?? [])
      setHasPreset(!!cRes.data.has_preset)
      setClusterMap(cRes.data.map ?? {})
    } catch {
      message.error('加载实际持仓失败')
    } finally {
      setLoading(false)
    }
  }, [portfolioId])

  useEffect(() => { loadHoldings() }, [loadHoldings, bump, reloadSignal])

  const onChanged = () => setBump((b) => b + 1)

  const total = holdings.reduce((s, h) => s + (h.market_value || 0), 0)
  const pnlTotal = holdings.reduce((s, h) => s + (h.pnl ?? 0), 0)
  const hasPnl = holdings.some((h) => h.pnl != null)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card
        size="small"
        title={
          <span>
            实际持仓
            <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal', marginLeft: 8 }}>
              共 {holdings.length} 只 · 市值 {yuan(total)} 元
              {hasPnl && <>· 浮盈 <span style={{ color: pnlTotal >= 0 ? '#f5222d' : '#52c41a' }}>{pnlTotal >= 0 ? '+' : ''}{yuan(pnlTotal)}</span> 元</>}
            </Typography.Text>
          </span>
        }
        extra={<Button size="small" icon={<ReloadOutlined />} onClick={loadHoldings}>刷新</Button>}
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: -4 }}>
          实际持仓 = 初始化快照 + 交易记录 综合算出（份额按交易当日单位净值折算，市值 = 份额 × 最新单位净值，
          成本按移动平均）。这里只读，改动请用下方「初始化快照」与「交易记录」。
        </Typography.Paragraph>
        {holdings.length === 0 ? (
          <Empty description="暂无持仓。先在下方「初始化快照」录入首次建仓金额。" />
        ) : (
          <Table<ComputedHolding>
            size="small"
            rowKey="fund_code"
            loading={loading}
            dataSource={holdings}
            pagination={false}
            columns={[
              {
                title: '基金', dataIndex: 'fund_name',
                render: (v: string, row) => (
                  <span>
                    {v || <Typography.Text type="secondary">—</Typography.Text>}
                    <Typography.Text type="secondary" style={{ fontFamily: 'monospace', marginLeft: 6, fontSize: 12 }}>
                      {row.fund_code}
                    </Typography.Text>
                    {row.valuation_ok === false && <Tag color="warning" style={{ marginLeft: 6 }}>估值不可用</Tag>}
                  </span>
                ),
              },
              ...(hasPreset ? [{
                title: '所属赛道（簇）', dataIndex: 'fund_code', key: 'cluster', width: 220,
                render: (code: string) => {
                  const name = clusterMap[code]
                  if (!name) return <Typography.Text type="secondary">—</Typography.Text>
                  return name === '赛道外'
                    ? <Tag>赛道外</Tag>
                    : <Tag color="blue">{name}</Tag>
                },
              }] : []),
              { title: '当前市值（元）', dataIndex: 'market_value', width: 140, align: 'right', render: (v: number) => yuan(v) },
              { title: '持有份额', dataIndex: 'shares', width: 130, align: 'right', render: (v: number | null) => num(v, 2) },
              {
                title: '最新净值', dataIndex: 'latest_nav', width: 130, align: 'right',
                render: (v: number | null, row) => v == null ? '—' : (
                  <span>{num(v, 4)}<Typography.Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>{row.nav_date}</Typography.Text></span>
                ),
              },
              { title: '成本（元）', dataIndex: 'cost', width: 120, align: 'right', render: (v: number | null) => v == null ? '—' : yuan(v) },
              {
                title: '浮动盈亏（元）', dataIndex: 'pnl', width: 130, align: 'right',
                render: (v: number | null) => {
                  if (v == null) return <Typography.Text type="secondary">—</Typography.Text>
                  const color = v > 0 ? '#f5222d' : v < 0 ? '#52c41a' : undefined
                  return <span style={{ color }}>{v > 0 ? '+' : ''}{yuan(v)}</span>
                },
              },
            ]}
          />
        )}
      </Card>

      <HoldingsEditor portfolioId={portfolioId} onChanged={onChanged} />

      <TxnPanel portfolioId={portfolioId} held={holdings} onChanged={onChanged} />
    </div>
  )
}
