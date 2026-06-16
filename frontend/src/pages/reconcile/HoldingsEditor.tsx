import { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Card, Empty, Input, InputNumber, Popconfirm, Space, Table, Typography, message,
} from 'antd'
import { DeleteOutlined, ImportOutlined, ReloadOutlined } from '@ant-design/icons'
import request from '../../api/request'
import type { UserHolding } from './types'

const { TextArea } = Input

// 千分位只加在整数部分（避免给小数位也插逗号，如 1,023.7,099,999）
const groupInt = (x: string | number | undefined) => {
  const [i, d] = `${x ?? ''}`.split('.')
  return i.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (d !== undefined ? `.${d}` : '')
}
const round2 = (n: number) => Math.round(n * 100) / 100

// 初始化快照：首次批量建仓的金额 + 盈亏（不含交易明细），后续加/减/转走「交易记录」。
// 快照行内改市值/删除 + 批量粘贴导入。按 portfolioId 隔离、持久化在 user_holdings 表；
// 改动后回调 onChanged（让上层重算实际持仓）。
export default function HoldingsEditor({
  portfolioId, onChanged,
}: { portfolioId: number | null; onChanged?: () => void }) {
  const [items, setItems] = useState<UserHolding[]>([])
  const [loading, setLoading] = useState(false)
  const [pasteText, setPasteText] = useState('')
  const [importing, setImporting] = useState(false)

  const load = useCallback(async () => {
    if (!portfolioId) {
      setItems([])
      return
    }
    setLoading(true)
    try {
      const { data } = await request.get<{ items: UserHolding[] }>('/reconcile/holdings/snapshot', {
        params: { portfolio_id: portfolioId },
      })
      setItems(data.items ?? [])
    } catch {
      message.error('加载快照失败')
    } finally {
      setLoading(false)
    }
  }, [portfolioId])

  useEffect(() => {
    load()
  }, [load])

  // 行内改市值：失焦即 upsert（保留原成本）
  const saveValue = async (code: string, name: string, mv: number, cost?: number | null) => {
    if (!portfolioId) return
    try {
      await request.post('/reconcile/holdings', {
        portfolio_id: portfolioId,
        fund_code: code, fund_name: name, market_value: round2(mv),
        cost: cost == null ? null : round2(cost),
      })
      onChanged?.()
    } catch {
      message.error('保存失败')
      load()
    }
  }

  const removeHolding = async (code: string) => {
    if (!portfolioId) return
    try {
      await request.delete(`/reconcile/holdings/${code}`, { params: { portfolio_id: portfolioId } })
      setItems((prev) => prev.filter((h) => h.fund_code !== code))
      onChanged?.()
    } catch {
      message.error('删除失败')
    }
  }

  // 粘贴导入：每行「名称/代码 市值 [持有收益]」，分隔符 tab/逗号/中文逗号/空白。全量替换。
  // 首段为 6 位数字按代码处理、否则按名称反查；其后所有数字中第 1 个为市值、最后 1 个为持有收益。
  const doImport = async () => {
    const rows = pasteText
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const parts = line.split(/[\t,，\s]+/).filter(Boolean)
        const first = parts[0] || ''
        const nums = parts
          .slice(1)
          .map((p) => Number(p.replace(/[+,，]/g, '')))
          .filter((n) => Number.isFinite(n))
        const mv = nums.length ? nums[0] : 0
        const pnl = nums.length >= 2 ? nums[nums.length - 1] : undefined   // 持有收益（可负）
        const cost = pnl !== undefined ? mv - pnl : undefined              // 成本=市值−持有收益
        const isCode = /^\d{6}$/.test(first)
        return {
          ...(isCode ? { fund_code: first } : { fund_name: first }),
          market_value: mv,
          ...(cost !== undefined ? { cost } : {}),
        }
      })
      .filter((r) => (r.fund_code || r.fund_name) && r.market_value > 0)
    if (rows.length === 0) {
      message.warning('未解析到有效行（格式：名称或代码 市值 [持有收益]，每行一只）')
      return
    }
    if (!portfolioId) {
      message.warning('请先选择一个实盘')
      return
    }
    setImporting(true)
    try {
      const { data } = await request.post<{ count: number }>('/reconcile/holdings/bulk', {
        portfolio_id: portfolioId, rows,
      })
      message.success(`已导入 ${data.count} 只（全量替换）`)
      setPasteText('')
      await load()
      onChanged?.()
    } catch {
      message.error('导入失败')
    } finally {
      setImporting(false)
    }
  }

  const total = items.reduce((s, h) => s + (h.market_value || 0), 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card
        size="small"
        title={`初始化快照（共 ${items.length} 只 · 合计 ${total.toLocaleString('zh-CN', { maximumFractionDigits: 0 })} 元）`}
        extra={
          <Button size="small" icon={<ReloadOutlined />} onClick={load}>
            刷新
          </Button>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="初始化快照只记录「金额 + 盈亏」、不含交易明细，用于首次大批量建仓的起点。建好快照后，后续的加仓 / 减仓 / 转仓请到下方「交易记录」录入——实际持仓由快照 + 交易记录综合算出。"
        />
        {items.length === 0 ? (
          <Empty description="暂无快照，请在下方粘贴导入首次建仓金额" />
        ) : (
          <Table
            size="small"
            rowKey="fund_code"
            loading={loading}
            dataSource={items}
            pagination={false}
            columns={[
              {
                title: '基金编码',
                dataIndex: 'fund_code',
                width: 120,
                render: (v: string) => <span style={{ fontFamily: 'monospace' }}>{v}</span>,
              },
              { title: '基金名称', dataIndex: 'fund_name', render: (v: string) => v || <Typography.Text type="secondary">—</Typography.Text> },
              {
                title: '快照市值（元）',
                dataIndex: 'market_value',
                width: 180,
                align: 'right',
                render: (v: number, row) => (
                  <InputNumber
                    value={v}
                    min={0}
                    precision={2}
                    style={{ width: 150 }}
                    formatter={groupInt}
                    parser={(x) => Number((x || '').replace(/,/g, ''))}
                    onBlur={(e) => {
                      const mv = Number((e.target.value || '').replace(/,/g, ''))
                      if (!Number.isFinite(mv) || mv === v) return
                      // 改市值时保持持有收益不变 → 成本随之调整
                      const oldPnl = row.cost == null ? null : (row.market_value || 0) - row.cost
                      const cost = oldPnl == null ? null : mv - oldPnl
                      saveValue(row.fund_code, row.fund_name, mv, cost)
                    }}
                  />
                ),
              },
              {
                title: '持有收益（元）',
                dataIndex: 'cost',
                width: 160,
                align: 'right',
                render: (_: unknown, row) => {
                  const pnl = row.cost == null ? null : round2((row.market_value || 0) - row.cost)
                  const color = pnl == null ? undefined : pnl > 0 ? '#f5222d' : pnl < 0 ? '#52c41a' : undefined
                  return (
                    <InputNumber
                      value={pnl}
                      precision={2}
                      style={{ width: 140, color }}
                      placeholder="未填"
                      formatter={groupInt}
                      parser={(x) => Number((x || '').replace(/[,+]/g, ''))}
                      onChange={(val) => {
                        // 清空 → 成本置空（未提供）
                        if (val === null || val === undefined) {
                          if (row.cost != null) saveValue(row.fund_code, row.fund_name, row.market_value, null)
                        }
                      }}
                      onBlur={(e) => {
                        const raw = (e.target.value || '').replace(/[,+]/g, '')
                        if (raw === '') return
                        const newPnl = Number(raw)
                        if (!Number.isFinite(newPnl) || newPnl === pnl) return
                        // 改持有收益时保持市值不变 → 成本 = 市值 − 持有收益
                        saveValue(row.fund_code, row.fund_name, row.market_value, (row.market_value || 0) - newPnl)
                      }}
                    />
                  )
                },
              },
              {
                title: '操作',
                width: 70,
                align: 'center',
                render: (_, row) => (
                  <Popconfirm title="删除该持仓？" onConfirm={() => removeHolding(row.fund_code)}>
                    <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                ),
              },
            ]}
          />
        )}
      </Card>

      <Card size="small" title="批量粘贴导入">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="每行一只基金，格式「名称或代码 市值 [持有收益]」，分隔符支持空格 / 逗号 / Tab。可直接从基金 App 复制（名称、市值、持有收益三列）粘贴；只看得到名称没有代码时按名称自动反查。持有收益可省略；成本=市值−持有收益，仅展示不参与调仓决策。导入为全量替换（覆盖现有持仓）。"
          />
          <TextArea
            rows={6}
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder={'示例（名称 市值 持有收益）：\n中欧红利优享 50467 +3200\n易方达蓝筹 15000 -800\n000001 30000'}
          />
          <Button type="primary" icon={<ImportOutlined />} loading={importing} onClick={doImport}>
            解析并导入
          </Button>
        </Space>
      </Card>
    </div>
  )
}
