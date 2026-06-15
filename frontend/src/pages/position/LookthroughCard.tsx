import { useState } from 'react'
import { Card, Col, Row, Segmented, Statistic, Table, Tag, Tooltip, theme } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { Lookthrough, LookthroughIndustry, LookthroughStock } from './types'

interface Props {
  data: Lookthrough
  selStocks: string[]       // 勾选的股票代码（联动过滤下方基金）
  selInds: string[]         // 勾选的行业
  onSelStocks: (keys: string[]) => void
  onSelInds: (keys: string[]) => void
}

// 底层持仓穿透：把各簇代表基金的前十大股票按目标权重累加，
// 可切「按股票 / 按行业」——股票看集中度与重叠，行业看组合整体配置。
// 勾选股票/行业即联动下方仅显示持有它们的代表基金（并集）。
export default function LookthroughCard({ data, selStocks, selInds, onSelStocks, onSelInds }: Props) {
  const { token } = theme.useToken()
  const [mode, setMode] = useState<'stock' | 'industry'>('stock')

  const fundList = (s: LookthroughStock) => (
    <div style={{ maxWidth: 240 }}>
      {s.funds.map((f, i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 12, lineHeight: '18px' }}>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
          <span style={{ flexShrink: 0 }}>{f.ratio}%</span>
        </div>
      ))}
    </div>
  )

  // 仓位列：数值 + 相对最大值的横条，直观看占比
  const expoCell = (v: number, max: number) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-end' }}>
      <div style={{ flex: 1, maxWidth: 90, height: 6, background: 'rgba(140,140,140,0.18)', borderRadius: 3 }}>
        <div
          style={{
            width: `${max > 0 ? (v / max) * 100 : 0}%`,
            height: '100%',
            borderRadius: 3,
            background: token.colorPrimary,
          }}
        />
      </div>
      <b style={{ width: 56, textAlign: 'right', color: v >= 3 ? '#f5222d' : token.colorText }}>{v.toFixed(2)}%</b>
    </div>
  )

  const maxStock = data.stocks[0]?.exposure ?? 0
  const stockColumns: ColumnsType<LookthroughStock> = [
    {
      title: '股票',
      dataIndex: 'name',
      render: (v: string, r) => (
        <span>
          {v} <span style={{ color: token.colorTextTertiary, fontSize: 12 }}>{r.code}</span>
        </span>
      ),
    },
    { title: '行业', dataIndex: 'industry', width: 150, ellipsis: true, render: (v: string) => v || '其他' },
    {
      title: '组合穿透仓位',
      dataIndex: 'exposure',
      align: 'right',
      width: 180,
      defaultSortOrder: 'descend',
      sorter: (a, b) => a.exposure - b.exposure,
      render: (v: number) => expoCell(v, maxStock),
    },
    {
      title: '持有基金',
      dataIndex: 'fund_count',
      align: 'center',
      width: 120,
      sorter: (a, b) => a.fund_count - b.fund_count,
      render: (v: number, r) => (
        <Tooltip title={fundList(r)} placement="left">
          {v >= 2 ? <Tag color="orange">{v} 只重叠</Tag> : <span>{v} 只</span>}
        </Tooltip>
      ),
    },
  ]

  const maxInd = data.industries[0]?.exposure ?? 0
  const total = data.visible_position || 1
  const industryColumns: ColumnsType<LookthroughIndustry> = [
    { title: '行业', dataIndex: 'industry', render: (v: string) => v || '其他' },
    { title: '含股票', dataIndex: 'stock_count', align: 'center', width: 90, render: (v: number) => `${v} 只` },
    {
      title: '组合穿透仓位',
      dataIndex: 'exposure',
      align: 'right',
      width: 180,
      defaultSortOrder: 'descend',
      sorter: (a, b) => a.exposure - b.exposure,
      render: (v: number) => expoCell(v, maxInd),
    },
    {
      title: '占可见仓位',
      dataIndex: 'exposure',
      align: 'right',
      width: 110,
      render: (v: number) => <span style={{ color: token.colorTextSecondary }}>{((v / total) * 100).toFixed(1)}%</span>,
    },
  ]

  return (
    <Card
      size="small"
      title="底层持仓穿透"
      extra={
        <Segmented
          size="small"
          value={mode}
          onChange={(v) => setMode(v as 'stock' | 'industry')}
          options={[
            { label: '按股票', value: 'stock' },
            { label: '按行业', value: 'industry' },
          ]}
        />
      }
    >
      <Row gutter={16} style={{ marginBottom: 8 }}>
        <Col span={6}>
          <Statistic title="覆盖代表基金" value={data.funds_covered} suffix="只" valueStyle={{ fontSize: 20 }} />
        </Col>
        {mode === 'stock' ? (
          <>
            <Col span={6}>
              <Statistic title="累计不同股票" value={data.total_stocks} suffix="只" valueStyle={{ fontSize: 20 }} />
            </Col>
            <Col span={6}>
              <Statistic
                title="重叠股票"
                value={data.overlap_stocks}
                suffix="只"
                valueStyle={{ fontSize: 20, color: data.overlap_stocks ? '#fa8c16' : token.colorText }}
              />
            </Col>
          </>
        ) : (
          <>
            <Col span={6}>
              <Statistic title="覆盖行业" value={data.industries.length} suffix="个" valueStyle={{ fontSize: 20 }} />
            </Col>
            <Col span={6}>
              <Statistic
                title="最大单一行业"
                value={data.industries[0]?.exposure ?? 0}
                precision={2}
                suffix="%"
                valueStyle={{ fontSize: 20, color: '#fa8c16' }}
              />
            </Col>
          </>
        )}
        <Col span={6}>
          <Statistic title="前十大穿透总仓位" value={data.visible_position} precision={2} suffix="%" valueStyle={{ fontSize: 20 }} />
        </Col>
      </Row>
      <div style={{ fontSize: 12, color: token.colorTextTertiary, marginBottom: 8 }}>
        {mode === 'stock'
          ? '穿透仓位 = ∑（基金目标权重 × 该基金中此股占净值比例）。重叠越多 → 底层实际越集中、代表基金相关性越高。仅含可见前十大持仓，非完整持仓。'
          : '把股票穿透仓位按申万行业聚合，看组合整体行业配置。行业越集中说明组合实际押注越窄。仅含可见前十大持仓，非完整持仓。'}
      </div>

      {mode === 'stock' ? (
        <Table<LookthroughStock>
          size="small"
          rowKey="code"
          columns={stockColumns}
          dataSource={data.stocks}
          rowSelection={{
            selectedRowKeys: selStocks,
            onChange: (keys) => onSelStocks(keys as string[]),
            columnWidth: 40,
          }}
          pagination={{ pageSize: 10, size: 'small', showSizeChanger: false }}
        />
      ) : (
        <Table<LookthroughIndustry>
          size="small"
          rowKey="industry"
          columns={industryColumns}
          dataSource={data.industries}
          rowSelection={{
            selectedRowKeys: selInds,
            onChange: (keys) => onSelInds(keys as string[]),
            columnWidth: 40,
          }}
          pagination={data.industries.length > 10 ? { pageSize: 10, size: 'small', showSizeChanger: false } : false}
        />
      )}
    </Card>
  )
}
