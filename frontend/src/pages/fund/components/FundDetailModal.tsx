import { useCallback, useEffect, useState } from 'react'
import { Descriptions, Empty, Modal, Select, Space, Spin, Table, Tabs, Tag, Typography } from 'antd'
import request from '../../../api/request'
import type { HoldingItem } from '../types'
import {
  CONC_META, CONFIDENCE_META, LUCK_META, SCALE_RISK_META, STYLE_META, metaOf, parseTags,
} from '../aiMeta'
import type { FundAi } from '../aiMeta'

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

function enumTag(map: Record<string, { label: string; color: string }>, v: string | null | undefined) {
  const m = metaOf(map, v)
  return m ? <Tag color={m.color}>{m.label}</Tag> : <span className="text-gray-400">-</span>
}

function boolTag(v: number | null | undefined, yes: string, no: string) {
  if (v === null || v === undefined) return <span className="text-gray-400">-</span>
  return <Tag color={v ? 'blue' : 'default'}>{v ? yes : no}</Tag>
}

/** AI 定性分析面板：未分析时给出 CLI 填充提示。 */
function renderAiPanel(ai: FundAi | null | undefined) {
  if (!ai) {
    return (
      <Empty description="暂无 AI 定性分析（可经 CLI 填充：preset ai-set --code <代码> --data '{...}'）" />
    )
  }
  const stars = ai.rating != null ? '★'.repeat(Math.max(0, Math.min(3, ai.rating))) || '·' : '-'
  const tags = parseTags(ai.tags)
  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Space wrap align="center">
        <span style={{ color: '#fadb14', fontSize: 16, letterSpacing: 2 }}>{stars}</span>
        {ai.recommend ? <Tag color="green">推荐</Tag> : null}
        {enumTag(CONFIDENCE_META, ai.confidence) /* 把握度 */}
        <Typography.Text strong>{fmt(ai.verdict)}</Typography.Text>
      </Space>

      <Descriptions size="small" column={2} bordered title="核心维度">
        <Descriptions.Item label="实力分">
          {ai.skill_score != null ? `${ai.skill_score} / 100` : '-'}
        </Descriptions.Item>
        <Descriptions.Item label="运气 vs 实力">{enumTag(LUCK_META, ai.luck_verdict)}</Descriptions.Item>
        <Descriptions.Item label="选股/择时理由" span={2}>{fmt(ai.skill_reason)}</Descriptions.Item>
        <Descriptions.Item label="集中度">{enumTag(CONC_META, ai.concentration)}</Descriptions.Item>
        <Descriptions.Item label="集中度理由">{fmt(ai.concentration_reason)}</Descriptions.Item>
        <Descriptions.Item label="硬实力逻辑" span={2}>{fmt(ai.hard_thesis)}</Descriptions.Item>
      </Descriptions>

      <Descriptions size="small" column={2} bordered title="经理 / 风险锚点">
        <Descriptions.Item label="基金经理">{fmt(ai.manager)}</Descriptions.Item>
        <Descriptions.Item label="任职年限">
          {ai.tenure_years != null ? `${ai.tenure_years} 年` : '-'}
        </Descriptions.Item>
        <Descriptions.Item label="是否原装">{boolTag(ai.is_original, '原装', '非原装')}</Descriptions.Item>
        <Descriptions.Item label="是否共管">{boolTag(ai.is_comanaged, '共管', '独管')}</Descriptions.Item>
        <Descriptions.Item label="规模风险">{enumTag(SCALE_RISK_META, ai.scale_risk)}</Descriptions.Item>
        <Descriptions.Item label="风格稳定性">{enumTag(STYLE_META, ai.style_stability)}</Descriptions.Item>
        <Descriptions.Item label="换手备注" span={2}>{fmt(ai.turnover_note)}</Descriptions.Item>
      </Descriptions>

      {tags.length > 0 && (
        <Space wrap>
          {tags.map((t) => (
            <Tag key={t}>{t}</Tag>
          ))}
        </Space>
      )}

      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        出处：{fmt(ai.model)} · 依据 {fmt(ai.data_basis)} · 分析 {fmt(ai.analyzed_at)} · 更新 {fmt(ai.updated_at)}
      </Typography.Text>
    </Space>
  )
}

export default function FundDetailModal({ code, open, onClose }: Props) {
  const [data, setData] = useState<DetailData | null>(null)
  const [loading, setLoading] = useState(false)
  // 持仓按季度独立加载，可切换历史报告期对比分析
  const [quarters, setQuarters] = useState<string[]>([])
  const [quarter, setQuarter] = useState<string | undefined>()
  const [holdings, setHoldings] = useState<HoldingItem[]>([])
  const [hLoading, setHLoading] = useState(false)

  const loadHoldings = useCallback((c: string, q?: string) => {
    setHLoading(true)
    request
      .get<{ quarters: string[]; quarter: string | null; holdings: HoldingItem[] }>(
        `/fund/${c}/holdings`, { params: q ? { quarter: q } : {} },
      )
      .then((resp) => {
        setQuarters(resp.data.quarters ?? [])
        setQuarter(resp.data.quarter ?? undefined)
        setHoldings(resp.data.holdings ?? [])
      })
      .catch(() => { setQuarters([]); setQuarter(undefined); setHoldings([]) })
      .finally(() => setHLoading(false))
  }, [])

  useEffect(() => {
    if (!open || !code) {
      setData(null); setQuarters([]); setQuarter(undefined); setHoldings([])
      return
    }
    setLoading(true)
    request
      .get(`/fund/${code}`)
      .then((resp) => setData(resp.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
    loadHoldings(code)
  }, [open, code, loadHoldings])

  const totalRatio = holdings.reduce((s, h) => s + (h.hold_ratio || 0), 0)

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
              key: 'ai',
              label: 'AI 定性分析',
              children: renderAiPanel(data?.ai as FundAi | null | undefined),
            },
            {
              key: 'holdings',
              label: `股票持仓(${holdings.length})`,
              children: (
                <Spin spinning={hLoading}>
                  <Space align="center" style={{ marginBottom: 12 }} wrap>
                    <Typography.Text type="secondary">报告期</Typography.Text>
                    <Select
                      size="small"
                      style={{ width: 130 }}
                      value={quarter}
                      onChange={(q) => { setQuarter(q); if (code) loadHoldings(code, q) }}
                      options={quarters.map((q) => ({ label: q, value: q }))}
                      placeholder="无持仓数据"
                      disabled={quarters.length === 0}
                    />
                    {holdings.length > 0 && (
                      <Typography.Text type="secondary">
                        前 {holdings.length} 大重仓 · 合计占净值 {totalRatio.toFixed(2)}%
                      </Typography.Text>
                    )}
                  </Space>
                  {holdings.length === 0 ? (
                    <Empty description="该报告期暂无股票持仓数据" />
                  ) : (
                    <Table<HoldingItem>
                      size="small"
                      rowKey={(r) => `${r.holding_type}-${r.asset_code}-${r.quarter}`}
                      dataSource={holdings}
                      pagination={false}
                      columns={[
                        { title: '排名', width: 56, align: 'center', render: (_, __, i) => i + 1 },
                        { title: '代码', dataIndex: 'asset_code', width: 100 },
                        { title: '名称', dataIndex: 'asset_name' },
                        { title: '占净值%', dataIndex: 'hold_ratio', width: 100, align: 'right', render: fmt },
                      ]}
                    />
                  )}
                </Spin>
              ),
            },
          ]}
        />
      </Spin>
    </Modal>
  )
}
