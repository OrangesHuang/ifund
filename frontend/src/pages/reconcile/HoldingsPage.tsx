import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert, Button, Card, Divider, Input, Modal, Popconfirm, Segmented, Select, Space, Tabs, Tag, Typography, message,
} from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import request from '../../api/request'
import type { QueryPreset } from '../fund/types'
import type { Portfolio } from './types'
import HoldingsManager from './HoldingsManager'
import HoldingsPenetration from './HoldingsPenetration'
import ReconcileView from './ReconcileView'

// 实盘：一站式独立板块。选实盘 → 关联仓位建议（预设）→ 录入持仓 → 生成操作指南。
// 一个用户可有多个实盘（自己的 + 代管他人的），各自记住关联的预设。
export default function HoldingsPage() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [pid, setPid] = useState<number | null>(null)
  const [presets, setPresets] = useState<QueryPreset[]>([])
  // 新建 / 重命名弹窗
  const [editOpen, setEditOpen] = useState(false)
  const [editMode, setEditMode] = useState<'create' | 'rename'>('create')
  const [editName, setEditName] = useState('')
  // 调仓建议「批量保存为交易记录」后 +1，触发持仓管理页重算实际持仓
  const [reloadSignal, setReloadSignal] = useState(0)

  const current = useMemo(() => portfolios.find((p) => p.id === pid) ?? null, [portfolios, pid])

  const loadPortfolios = useCallback(async (selectId?: number) => {
    try {
      const { data } = await request.get<{ items: Portfolio[] }>('/reconcile/portfolios')
      const items = data.items ?? []
      setPortfolios(items)
      setPid((prev) => {
        if (selectId && items.some((p) => p.id === selectId)) return selectId
        if (prev && items.some((p) => p.id === prev)) return prev
        return items[0]?.id ?? null
      })
    } catch {
      message.error('加载实盘列表失败')
    }
  }, [])

  useEffect(() => {
    loadPortfolios()
    request
      .get('/fund/presets')
      .then(({ data }) => setPresets(data.items ?? data ?? []))
      .catch(() => undefined)
  }, [loadPortfolios])

  // 关联预设：PATCH 实盘（预设影响目标比例，需触发持仓重算）
  const linkPreset = async (presetId: number | null) => {
    if (!pid) return
    try {
      await request.patch(`/reconcile/portfolios/${pid}`, { preset_id: presetId })
      setPortfolios((prev) => prev.map((p) => (p.id === pid ? { ...p, preset_id: presetId } : p)))
      setReloadSignal((s) => s + 1)
    } catch {
      message.error('关联预设失败')
    }
  }

  // 均衡强度：PATCH 实盘（cap 影响目标基金筛选，需触发持仓重算）
  const linkCap = async (cap: number) => {
    if (!pid) return
    try {
      await request.patch(`/reconcile/portfolios/${pid}`, { cap })
      setPortfolios((prev) => prev.map((p) => (p.id === pid ? { ...p, cap } : p)))
      setReloadSignal((s) => s + 1)
    } catch {
      message.error('更新均衡强度失败')
    }
  }

  const openCreate = () => {
    setEditMode('create')
    setEditName('')
    setEditOpen(true)
  }
  const openRename = () => {
    if (!current) return
    setEditMode('rename')
    setEditName(current.name)
    setEditOpen(true)
  }
  const submitEdit = async () => {
    const name = editName.trim()
    if (!name) {
      message.warning('请输入实盘名称')
      return
    }
    try {
      if (editMode === 'create') {
        const { data } = await request.post<Portfolio>('/reconcile/portfolios', { name })
        await loadPortfolios(data.id)
        message.success('已新建实盘')
      } else if (current) {
        await request.patch(`/reconcile/portfolios/${current.id}`, { name })
        setPortfolios((prev) => prev.map((p) => (p.id === current.id ? { ...p, name } : p)))
        message.success('已重命名')
      }
      setEditOpen(false)
    } catch {
      message.error('操作失败')
    }
  }

  const removePortfolio = async () => {
    if (!current) return
    try {
      await request.delete(`/reconcile/portfolios/${current.id}`)
      message.success('已删除实盘')
      await loadPortfolios()
    } catch {
      message.error('删除失败')
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Alert
        type="info"
        showIcon
        message="实盘：选一个实盘（自己的或代管他人的资金）→ 关联一套②仓位建议（预设）→ 录入真实持仓 → 一键生成操作指南。持仓持久化、跨会话保留；盈亏仅展示不参与决策。各实盘各自记住关联的预设。"
      />

      <Card size="small" title="选择实盘">
        <Space wrap size="middle">
          <Select
            style={{ minWidth: 220 }}
            placeholder="选择实盘"
            value={pid ?? undefined}
            onChange={setPid}
            options={portfolios.map((p) => ({ label: p.name, value: p.id }))}
          />
          <Button icon={<PlusOutlined />} onClick={openCreate}>
            新建
          </Button>
          <Button icon={<EditOutlined />} onClick={openRename} disabled={!current}>
            重命名
          </Button>
          <Popconfirm
            title="删除该实盘？"
            description="该实盘下的持仓将一并删除，不可恢复。"
            onConfirm={removePortfolio}
            disabled={!current || portfolios.length <= 1}
          >
            <Button icon={<DeleteOutlined />} danger disabled={!current || portfolios.length <= 1}>
              删除
            </Button>
          </Popconfirm>

          <Divider type="vertical" />

          <span>关联仓位建议：</span>
          <Select
            style={{ minWidth: 260 }}
            placeholder="请选择预设（仓位建议来源）"
            allowClear
            value={current?.preset_id ?? undefined}
            onChange={(v) => linkPreset(v ?? null)}
            options={presets.map((p) => ({ label: p.name, value: p.id }))}
            disabled={!current}
          />
          {current && (current.preset_id ? (
            <Tag color="green">已关联</Tag>
          ) : (
            <Tag color="gold">未关联</Tag>
          ))}

          <Divider type="vertical" />

          <span>均衡强度：</span>
          <Segmented
            value={current?.cap ?? 0.18}
            onChange={(v) => linkCap(v as number)}
            options={[
              { label: '松', value: 0.22 },
              { label: '中', value: 0.18 },
              { label: '紧', value: 0.14 },
            ]}
            disabled={!current}
          />
        </Space>
        <div style={{ marginTop: 8 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            目标比例来自所关联预设的镜像 → 行业暴露聚类 → 簇级仓位建议。换实盘即切换其各自的持仓与关联预设。
          </Typography.Text>
        </div>
      </Card>

      <Tabs
        defaultActiveKey="holdings"
        items={[
          {
            key: 'holdings',
            label: '实际持仓管理',
            children: <HoldingsManager portfolioId={pid} reloadSignal={reloadSignal} />,
          },
          {
            key: 'penetration',
            label: '底层穿透',
            children: <HoldingsPenetration portfolioId={pid} reloadSignal={reloadSignal} />,
          },
          {
            key: 'reconcile',
            label: '调仓建议',
            children: (
              <ReconcileView
                portfolioId={pid}
                hasPreset={!!current?.preset_id}
                onSavedTxns={() => setReloadSignal((s) => s + 1)}
              />
            ),
          },
        ]}
      />

      <Modal
        open={editOpen}
        title={editMode === 'create' ? '新建实盘' : '重命名实盘'}
        onOk={submitEdit}
        onCancel={() => setEditOpen(false)}
        okText="确定"
        cancelText="取消"
        destroyOnClose
      >
        <Input
          autoFocus
          placeholder="实盘名称，如：我的实盘 / 老王的钱"
          value={editName}
          onChange={(e) => setEditName(e.target.value)}
          onPressEnter={submitEdit}
        />
      </Modal>
    </div>
  )
}
