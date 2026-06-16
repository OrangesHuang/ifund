import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AutoComplete, Button, Card, DatePicker, Empty, InputNumber, Modal, Popconfirm,
  Segmented, Space, Table, Tag, Typography, message,
} from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import request from '../../api/request'
import type { ComputedHolding, Txn } from './types'

type Kind = 'buy' | 'sell' | 'transfer'

// 展示行：普通买/卖一行一只基金；转仓合并成一行（同 transfer_id 的卖出 + 买入）。
type Row =
  | { key: string; rowType: 'single'; txn: Txn }
  | { key: string; rowType: 'transfer'; transferId: string; sell?: Txn; buy?: Txn; trade_date: string; amount: number }

const yuan = (v: number) => v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
const num = (v: number | null | undefined, d = 2) =>
  v == null ? '—' : v.toLocaleString('zh-CN', { maximumFractionDigits: d })

const fundCell = (name: string | undefined, code: string | undefined) => (
  <span>
    {name || <Typography.Text type="secondary">—</Typography.Text>}
    <Typography.Text type="secondary" style={{ fontFamily: 'monospace', marginLeft: 6, fontSize: 12 }}>
      {code}
    </Typography.Text>
  </span>
)
const navCell = (v: number | null | undefined) =>
  v == null ? <Tag color="warning">估值不可用</Tag> : <span>{num(v, 4)}</span>

// 交易记录：初始化快照之后的加/减/转仓，按基金原则记账（金额 + 当日单位净值 → 份额）。
// 录入即落账锁定当日单位净值；实际持仓由快照 + 交易回放综合算出（见上方「实际持仓」）。
// 转仓底层存两条（卖出 + 买入，共享 transfer_id），此处合并为一行展示。
export default function TxnPanel({
  portfolioId, held, onChanged,
}: {
  portfolioId: number | null
  held: ComputedHolding[]   // 已持有基金（卖出/转出的候选）
  onChanged?: () => void
}) {
  const [items, setItems] = useState<Txn[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)               // 编辑单条买/卖
  const [editingTransfer, setEditingTransfer] = useState<{ sellId: number; buyId: number } | null>(null)  // 编辑转仓两条
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])               // 批量删除选中（展示行 key）
  // 表单
  const [kind, setKind] = useState<Kind>('buy')
  const [fund, setFund] = useState('')        // 买入/卖出 的基金（名称或代码）
  const [fromFund, setFromFund] = useState('') // 转出
  const [toFund, setToFund] = useState('')     // 转入
  const [date, setDate] = useState<Dayjs | null>(dayjs())
  const [amount, setAmount] = useState<number | null>(null)

  const load = useCallback(async () => {
    if (!portfolioId) { setItems([]); return }
    setLoading(true)
    try {
      const { data } = await request.get<{ items: Txn[] }>('/reconcile/txns', {
        params: { portfolio_id: portfolioId },
      })
      setItems(data.items ?? [])
    } catch {
      message.error('加载交易记录失败')
    } finally {
      setLoading(false)
    }
  }, [portfolioId])

  useEffect(() => { load() }, [load])

  // 把底层交易聚合成展示行：转仓的卖出 + 买入合并为一行。
  const rows = useMemo<Row[]>(() => {
    const out: Row[] = []
    const seen = new Map<string, Row & { rowType: 'transfer' }>()
    for (const t of items) {
      if (t.transfer_id) {
        let r = seen.get(t.transfer_id)
        if (!r) {
          r = { key: `tf-${t.transfer_id}`, rowType: 'transfer', transferId: t.transfer_id, trade_date: t.trade_date, amount: t.amount }
          seen.set(t.transfer_id, r)
          out.push(r)
        }
        if (t.txn_type === 'sell') r.sell = t
        else r.buy = t
      } else {
        out.push({ key: `s-${t.id}`, rowType: 'single', txn: t })
      }
    }
    return out
  }, [items])

  // 展示行 key → 底层交易 id 列表（批量删除用）
  const keyToTxnIds = useMemo(() => {
    const m = new Map<string, number[]>()
    for (const r of rows) {
      if (r.rowType === 'single') m.set(r.key, [r.txn.id])
      else m.set(r.key, [r.sell?.id, r.buy?.id].filter((x): x is number => x != null))
    }
    return m
  }, [rows])

  const heldOptions = held.map((h) => ({ value: h.fund_name || h.fund_code }))

  const resetForm = () => {
    setKind('buy'); setFund(''); setFromFund(''); setToFund('')
    setDate(dayjs()); setAmount(null)
  }
  const openModal = () => { setEditingId(null); setEditingTransfer(null); resetForm(); setOpen(true) }
  const openEdit = (t: Txn) => {
    setEditingId(t.id); setEditingTransfer(null)
    setKind(t.txn_type)
    setFund(t.fund_name || t.fund_code)
    setFromFund(''); setToFund('')
    setDate(dayjs(t.trade_date)); setAmount(t.amount)
    setOpen(true)
  }
  const openEditTransfer = (r: Row & { rowType: 'transfer' }) => {
    if (!r.sell || !r.buy) { message.warning('该转仓缺少配对条目，请逐条编辑'); return }
    setEditingId(null)
    setEditingTransfer({ sellId: r.sell.id, buyId: r.buy.id })
    setKind('transfer')
    setFromFund(r.sell.fund_name || r.sell.fund_code)
    setToFund(r.buy.fund_name || r.buy.fund_code)
    setFund('')
    setDate(dayjs(r.trade_date)); setAmount(r.amount)
    setOpen(true)
  }

  const submit = async () => {
    if (!portfolioId) { message.warning('请先选择一个实盘'); return }
    if (!date) { message.warning('请选择交易日'); return }
    if (!amount || amount <= 0) { message.warning('请输入正的交易金额'); return }
    const trade_date = date.format('YYYY-MM-DD')
    setSaving(true)
    try {
      if (editingTransfer) {
        if (!fromFund.trim() || !toFund.trim()) { message.warning('请填写转出与转入基金'); setSaving(false); return }
        await request.patch(`/reconcile/txns/${editingTransfer.sellId}`, {
          portfolio_id: portfolioId, kind: 'sell', trade_date, amount, fund_name: fromFund.trim(),
        })
        await request.patch(`/reconcile/txns/${editingTransfer.buyId}`, {
          portfolio_id: portfolioId, kind: 'buy', trade_date, amount, fund_name: toFund.trim(),
        })
        message.success('已修改转仓')
      } else if (editingId != null) {
        if (!fund.trim()) { message.warning('请填写基金'); setSaving(false); return }
        await request.patch(`/reconcile/txns/${editingId}`, {
          portfolio_id: portfolioId, kind, trade_date, amount, fund_name: fund.trim(),
        })
        message.success('已修改')
      } else if (kind === 'transfer') {
        if (!fromFund.trim() || !toFund.trim()) { message.warning('请填写转出与转入基金'); setSaving(false); return }
        await request.post('/reconcile/txns', {
          portfolio_id: portfolioId, kind, trade_date, amount,
          from_name: fromFund.trim(), to_name: toFund.trim(),
        })
        message.success('已记一笔')
      } else {
        if (!fund.trim()) { message.warning('请填写基金'); setSaving(false); return }
        await request.post('/reconcile/txns', {
          portfolio_id: portfolioId, kind, trade_date, amount, fund_name: fund.trim(),
        })
        message.success('已记一笔')
      }
      setOpen(false)
      await load()
      onChanged?.()
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.error(detail || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  // 删除一个展示行（转仓行连带两条一起删）
  const removeRow = async (key: string) => {
    if (!portfolioId) return
    const ids = keyToTxnIds.get(key) ?? []
    if (ids.length === 0) return
    try {
      if (ids.length === 1) {
        await request.delete(`/reconcile/txns/${ids[0]}`, { params: { portfolio_id: portfolioId } })
      } else {
        await request.post('/reconcile/txns/bulk-delete', { portfolio_id: portfolioId, ids })
      }
      setSelectedKeys((prev) => prev.filter((k) => k !== key))
      await load()
      onChanged?.()
    } catch {
      message.error('删除失败')
    }
  }

  const bulkDelete = async () => {
    if (!portfolioId || selectedKeys.length === 0) return
    const ids = selectedKeys.flatMap((k) => keyToTxnIds.get(k) ?? [])
    if (ids.length === 0) return
    try {
      const { data } = await request.post<{ count: number }>('/reconcile/txns/bulk-delete', {
        portfolio_id: portfolioId, ids,
      })
      message.success(`已删除 ${data.count} 条`)
      setSelectedKeys([])
      await load()
      onChanged?.()
    } catch {
      message.error('批量删除失败')
    }
  }

  const fundField = (() => {
    if (kind === 'transfer') {
      return (
        <>
          <div>
            <Typography.Text type="secondary">转出基金（从已持有里卖）</Typography.Text>
            <AutoComplete
              style={{ width: '100%', marginTop: 4 }}
              options={heldOptions}
              value={fromFund}
              onChange={setFromFund}
              filterOption={(i, o) => (o?.value ?? '').toLowerCase().includes(i.toLowerCase())}
              placeholder="转出基金名称或代码"
            />
          </div>
          <div>
            <Typography.Text type="secondary">转入基金（买入/加仓的目标）</Typography.Text>
            <AutoComplete
              style={{ width: '100%', marginTop: 4 }}
              options={heldOptions}
              value={toFund}
              onChange={setToFund}
              filterOption={(i, o) => (o?.value ?? '').toLowerCase().includes(i.toLowerCase())}
              placeholder="转入基金名称或代码（可填新基金）"
            />
          </div>
        </>
      )
    }
    return (
      <div>
        <Typography.Text type="secondary">{kind === 'buy' ? '买入/加仓基金' : '卖出/减仓基金'}</Typography.Text>
        <AutoComplete
          style={{ width: '100%', marginTop: 4 }}
          options={heldOptions}
          value={fund}
          onChange={setFund}
          filterOption={(i, o) => (o?.value ?? '').toLowerCase().includes(i.toLowerCase())}
          placeholder={kind === 'buy' ? '基金名称或代码（可填新基金）' : '从已持有里选要卖的基金'}
        />
      </div>
    )
  })()

  const editing = editingId != null || editingTransfer != null

  return (
    <Card
      size="small"
      title={`交易记录（${rows.length} 笔）`}
      extra={
        <Space>
          <Button size="small" type="primary" icon={<PlusOutlined />} onClick={openModal}>
            记一笔
          </Button>
          <Popconfirm
            title={`删除选中的 ${selectedKeys.length} 笔交易？`}
            description="转仓的卖出 + 买入两条会一并删除。"
            onConfirm={bulkDelete}
            disabled={selectedKeys.length === 0}
          >
            <Button size="small" danger icon={<DeleteOutlined />} disabled={selectedKeys.length === 0}>
              批量删除{selectedKeys.length > 0 ? `（${selectedKeys.length}）` : ''}
            </Button>
          </Popconfirm>
          <Button size="small" icon={<ReloadOutlined />} onClick={load}>
            刷新
          </Button>
        </Space>
      }
    >
      {rows.length === 0 ? (
        <Empty description="暂无交易记录。首次建仓用上方「初始化快照」；之后的加/减/转仓点「记一笔」。" />
      ) : (
        <Table<Row>
          size="small"
          rowKey="key"
          loading={loading}
          dataSource={rows}
          pagination={false}
          rowSelection={{
            selectedRowKeys: selectedKeys,
            onChange: (keys) => setSelectedKeys(keys as string[]),
          }}
          columns={[
            {
              title: '交易日', width: 110,
              render: (_, r) => r.rowType === 'single' ? r.txn.trade_date : r.trade_date,
            },
            {
              title: '类型', width: 110,
              render: (_, r) => r.rowType === 'transfer'
                ? <Tag color="purple">转仓</Tag>
                : <Tag color={r.txn.txn_type === 'buy' ? 'volcano' : 'green'}>{r.txn.txn_type === 'buy' ? '买入' : '卖出'}</Tag>,
            },
            {
              title: '基金',
              render: (_, r) => r.rowType === 'single'
                ? fundCell(r.txn.fund_name, r.txn.fund_code)
                : (
                  <Space direction="vertical" size={4}>
                    <span><Tag color="green">转出</Tag>{fundCell(r.sell?.fund_name, r.sell?.fund_code)}</span>
                    <span><Tag color="volcano">转入</Tag>{fundCell(r.buy?.fund_name, r.buy?.fund_code)}</span>
                  </Space>
                ),
            },
            {
              title: '金额（元）', width: 120, align: 'right',
              render: (_, r) => r.rowType === 'single' ? yuan(r.txn.amount) : yuan(r.amount),
            },
            {
              title: '单位净值', width: 110, align: 'right',
              render: (_, r) => r.rowType === 'single'
                ? navCell(r.txn.nav)
                : (
                  <Space direction="vertical" size={4} style={{ alignItems: 'flex-end' }}>
                    {navCell(r.sell?.nav)}
                    {navCell(r.buy?.nav)}
                  </Space>
                ),
            },
            {
              title: '份额', width: 130, align: 'right',
              render: (_, r) => r.rowType === 'single'
                ? num(r.txn.shares, 2)
                : (
                  <Space direction="vertical" size={4} style={{ alignItems: 'flex-end' }}>
                    <span>{num(r.sell?.shares, 2)}</span>
                    <span>{num(r.buy?.shares, 2)}</span>
                  </Space>
                ),
            },
            {
              title: '操作', width: 90, align: 'center',
              render: (_, r) => (
                <Space size={0}>
                  <Button
                    size="small" type="text" icon={<EditOutlined />}
                    onClick={() => r.rowType === 'single' ? openEdit(r.txn) : openEditTransfer(r)}
                  />
                  <Popconfirm
                    title={r.rowType === 'transfer' ? '删除该转仓（卖出 + 买入两条一并删除）？' : '删除该交易？'}
                    onConfirm={() => removeRow(r.key)}
                  >
                    <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      )}

      <Modal
        open={open}
        title={editingTransfer ? '修改转仓' : editingId != null ? '修改交易' : '记一笔交易'}
        onOk={submit}
        confirmLoading={saving}
        onCancel={() => setOpen(false)}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          {!editing && (
            <Segmented
              block
              value={kind}
              onChange={(v) => setKind(v as Kind)}
              options={[
                { label: '买入 / 加仓', value: 'buy' },
                { label: '卖出 / 减仓', value: 'sell' },
                { label: '转仓', value: 'transfer' },
              ]}
            />
          )}
          {editing && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {editingTransfer
                ? '修改转仓将同步更新「转出卖出」与「转入买入」两条，按新交易日的单位净值重新折算份额。'
                : '修改后将按新交易日的单位净值重新折算份额。'}
            </Typography.Text>
          )}
          {fundField}
          <div>
            <Typography.Text type="secondary">交易日（按当日单位净值折算份额）</Typography.Text>
            <DatePicker
              style={{ width: '100%', marginTop: 4 }}
              value={date}
              onChange={setDate}
              allowClear={false}
            />
          </div>
          <div>
            <Typography.Text type="secondary">金额（元）</Typography.Text>
            <InputNumber
              style={{ width: '100%', marginTop: 4 }}
              value={amount}
              min={0}
              precision={2}
              onChange={(v) => setAmount(v)}
              placeholder="申购 / 赎回金额"
              formatter={(x) => {
                const [i, d] = `${x ?? ''}`.split('.')
                return i.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (d !== undefined ? `.${d}` : '')
              }}
              parser={(x) => Number((x || '').replace(/,/g, ''))}
            />
          </div>
        </Space>
      </Modal>
    </Card>
  )
}
