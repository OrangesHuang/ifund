import { useEffect, useState } from 'react'
import { Descriptions, Modal, Spin, Table, Tabs } from 'antd'
import request from '../../../api/request'
import type { HoldingItem } from '../types'

interface Props {
  code: string | null
  open: boolean
  onClose: () => void
}

interface DetailData {
  [key: string]: unknown
  holdings?: HoldingItem[]
}

const BASIC_FIELDS: [string, string][] = [
  ['fund_name', '基金简称'],
  ['fund_full_name', '基金全称'],
  ['fund_company', '基金公司'],
  ['fund_manager', '基金经理'],
  ['establish_date', '成立日期'],
  ['scale', '规模'],
  ['fund_type', '类型'],
  ['fund_rating', '评级'],
]

const PERF_FIELDS: [string, string][] = [
  ['return_ytd', '今年以来'],
  ['return_1y', '近一年'],
  ['return_3y', '近三年'],
  ['return_5y', '近五年'],
  ['sharpe_3y', '夏普3年'],
  ['max_drawdown_3y', '最大回撤3年'],
  ['position_stock', '股票仓位'],
  ['position_bond', '债券仓位'],
]

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === '') return '-'
  return String(v)
}

export default function FundDetailModal({ code, open, onClose }: Props) {
  const [data, setData] = useState<DetailData | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || !code) return
    setLoading(true)
    request
      .get(`/fund/${code}`)
      .then((resp) => setData(resp.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [open, code])

  const holdings = data?.holdings ?? []

  return (
    <Modal open={open} onCancel={onClose} footer={null} width={760} title={`基金详情 · ${code ?? ''}`}>
      <Spin spinning={loading}>
        <Tabs
          items={[
            {
              key: 'basic',
              label: '基础信息',
              children: (
                <Descriptions size="small" column={2} bordered>
                  {BASIC_FIELDS.map(([k, label]) => (
                    <Descriptions.Item key={k} label={label}>
                      {fmt(data?.[k])}
                    </Descriptions.Item>
                  ))}
                </Descriptions>
              ),
            },
            {
              key: 'perf',
              label: '业绩与风险',
              children: (
                <Descriptions size="small" column={2} bordered>
                  {PERF_FIELDS.map(([k, label]) => (
                    <Descriptions.Item key={k} label={label}>
                      {fmt(data?.[k])}
                    </Descriptions.Item>
                  ))}
                </Descriptions>
              ),
            },
            {
              key: 'holdings',
              label: `持仓(${holdings.length})`,
              children: (
                <Table<HoldingItem>
                  size="small"
                  rowKey={(r) => `${r.holding_type}-${r.asset_code}-${r.quarter}`}
                  dataSource={holdings}
                  pagination={false}
                  columns={[
                    { title: '代码', dataIndex: 'asset_code' },
                    { title: '名称', dataIndex: 'asset_name' },
                    { title: '占比%', dataIndex: 'hold_ratio', render: fmt },
                    { title: '季度', dataIndex: 'quarter' },
                    { title: '类型', dataIndex: 'holding_type' },
                  ]}
                />
              ),
            },
          ]}
        />
      </Spin>
    </Modal>
  )
}
