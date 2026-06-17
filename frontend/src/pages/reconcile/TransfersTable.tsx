import { useState } from 'react'
import { Button, Card, Popconfirm, Space, Table, Tag, Typography, message } from 'antd'
import { CopyOutlined, SaveOutlined } from '@ant-design/icons'
import request from '../../api/request'
import type { ReconTransfer } from './types'

const yuan = (v: number) => v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
const share = (v: number) => v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })

const BUY = '#fa541c'   // 建仓/加仓/转入：橙
const SRC = '#722ed1'   // 资金来源基金：紫
const CASH = '#d4380d'  // 追加现金：火山红

const fundLabel = (name: string, code: string) => `${name}（${code}）`

// 一笔操作的纯文本句子（用于复制）。
function sentence(t: ReconTransfer): string {
  const act = t.to_action === 'open' ? '建仓' : '加仓'
  const to = fundLabel(t.to_name, t.to_code)
  if (t.from_type === 'add_cash') {
    return `${to} ${act} ${yuan(t.amount)} 元（现金）`
  }
  // 赛道内超配减仓 / 赛道外卖出 → 转仓到目标基金
  const sh = t.from_shares ? `（约 ${share(t.from_shares)} 份）` : ''
  return `${fundLabel(t.from_name, t.from_code)} 转仓 ${yuan(t.amount)} 元${sh} 至 ${to}（${act}）`
}

// 操作指南：每行一句调仓者习惯的「A 转仓 X元 至 B / C 建仓 X元」。
export default function TransfersTable({
  transfers, portfolioId, onSaved,
}: { transfers: ReconTransfer[]; portfolioId?: number | null; onSaved?: () => void }) {
  const [saving, setSaving] = useState(false)

  // 批量落账：把对账建议的每笔转仓写成真实交易记录（追加现金的只记买入，不带来源）。
  const saveAll = async () => {
    if (!portfolioId) { message.warning('请先选择一个实盘'); return }
    const rows = transfers.map((t) => t.from_type === 'add_cash'
      ? { to_code: t.to_code, to_name: t.to_name, amount: t.amount }
      : { from_code: t.from_code, from_name: t.from_name, to_code: t.to_code, to_name: t.to_name, amount: t.amount })
    setSaving(true)
    try {
      const { data } = await request.post<{ count: number; trade_date: string }>(
        '/reconcile/txns/from-rebalance', { portfolio_id: portfolioId, transfers: rows })
      message.success(`已落账 ${data.count} 笔交易记录（交易日 ${data.trade_date}）`)
      onSaved?.()
    } catch {
      message.error('批量落账失败')
    } finally {
      setSaving(false)
    }
  }

  const copyAll = () => {
    const text = transfers.map(sentence).join('\n')
    if (!text) {
      message.info('没有调仓动作')
      return
    }
    navigator.clipboard.writeText(text).then(
      () => message.success('已复制操作指南'),
      () => message.error('复制失败'),
    )
  }

  // 富文本渲染：来源紫 / 现金红 → 金额橙 → 目标橙；末尾标建仓/加仓。
  const render = (t: ReconTransfer) => {
    const act = t.to_action === 'open' ? '建仓' : '加仓'
    const to = (
      <b style={{ color: BUY }}>{fundLabel(t.to_name, t.to_code)}</b>
    )
    if (t.from_type === 'add_cash') {
      return (
        <span style={{ lineHeight: 1.6 }}>
          <Tag color="volcano">现金</Tag>
          {to} <b style={{ color: BUY }}>{act}</b>{' '}
          <b style={{ color: CASH }}>{yuan(t.amount)} 元</b>
          <span style={{ color: '#999' }}>（追加现金）</span>
        </span>
      )
    }
    const fromTag = t.from_type === 'outside'
      ? <Tag color="purple">赛道外</Tag>
      : <Tag color="gold">超配减仓</Tag>
    return (
      <span style={{ lineHeight: 1.6 }}>
        {fromTag}
        <b style={{ color: SRC }}>{fundLabel(t.from_name, t.from_code)}</b>{' '}
        转仓 <b style={{ color: BUY }}>{yuan(t.amount)} 元</b>
        {t.from_shares != null && (
          <span style={{ color: '#999', marginLeft: 4 }}>≈ {share(t.from_shares)} 份</span>
        )}{' '}
        至 {to}{' '}
        <Tag color={t.to_action === 'open' ? 'volcano' : 'orange'} style={{ marginLeft: 4 }}>
          {act}
        </Tag>
      </span>
    )
  }

  return (
    <Card
      size="small"
      title={`操作指南（${transfers.length} 笔调仓动作）`}
      extra={
        <Space>
          <Popconfirm
            title="批量保存为交易记录？"
            description="把以上每笔转仓按最近交易日的单位净值落成真实交易记录（转仓=一卖一买）。会追加到「实际持仓管理」的交易记录中。"
            onConfirm={saveAll}
            okText="保存"
            cancelText="取消"
          >
            <Button size="small" type="primary" icon={<SaveOutlined />} loading={saving}>
              批量保存为交易记录
            </Button>
          </Popconfirm>
          <Button size="small" icon={<CopyOutlined />} onClick={copyAll}>
            复制操作指南
          </Button>
        </Space>
      }
    >
      <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: -4 }}>
        按调仓顺序执行：「来源基金 转仓 金额 至 目标基金」表示把来源基金赎回同等金额、申购到目标基金；
        「目标基金 建仓/加仓 金额（现金）」表示用追加现金买入。资金来源优先级（尽量不用现金）：
        赛道内超配减仓 → 赛道外卖出 → 追加现金兜底。
        券商「基金转换」按份额操作，故附「≈ 份额」= 转仓金额 ÷ 转出基金最新单位净值（估算，实际以确认日净值为准）。
      </Typography.Paragraph>
      <Table<ReconTransfer>
        size="small"
        showHeader={false}
        rowKey={(t, i) => `${t.from_code}-${t.to_code}-${i}`}
        dataSource={transfers}
        pagination={false}
        columns={[
          { title: '操作', render: (_, t) => render(t) },
        ]}
      />
    </Card>
  )
}
