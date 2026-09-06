import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Card, Input, Progress, Select, Space, Statistic, Table, Tag, message, Row, Col } from 'antd'
import { SyncOutlined } from '@ant-design/icons'
import request from '../../api/request'
import TenureHistory from './TenureHistory'
import type { CoverageStats, ManagerItem, RunningTask } from './types'

export default function ManagerPage() {
  const [items, setItems] = useState<ManagerItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [keyword, setKeyword] = useState('')
  const [coverage, setCoverage] = useState('all')
  const [sortField, setSortField] = useState('code')
  const [sortOrder, setSortOrder] = useState('asc')
  const [loading, setLoading] = useState(false)
  const [task, setTask] = useState<RunningTask | null>(null)
  const [stats, setStats] = useState<CoverageStats | null>(null)
  // 采集范围: presetId 为空 = 全量(2.7万只, 极慢, 不建议); 选镜像预设则只采集其基金
  const [presets, setPresets] = useState<{ id: number; name: string }[]>([])
  const [scopePreset, setScopePreset] = useState<number | undefined>()
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await request.get('/fund_manager/list', {
        params: { keyword, coverage, page, pageSize, sortField, sortOrder },
      })
      setItems(res.data.items)
      setTotal(res.data.total)
    } finally {
      setLoading(false)
    }
  }, [keyword, coverage, page, pageSize, sortField, sortOrder])

  const loadStats = useCallback(async () => {
    const res = await request.get('/fund_manager/stats')
    setStats(res.data)
  }, [])

  useEffect(() => { loadData() }, [loadData])
  useEffect(() => { loadStats() }, [loadStats])
  useEffect(() => {
    request.get('/fund/presets')
      .then((res) => setPresets((res.data || []).map((x: { id: number; name: string }) => ({ id: x.id, name: x.name }))))
      .catch(() => undefined)
  }, [])

  const pollTick = useCallback(async () => {
    try {
      const res = await request.get('/fund_manager/task/running')
      const data = res.data as RunningTask | null
      if (data && data.status === 'running') {
        setTask(data)
        pollRef.current = setTimeout(pollTick, 3000)
      } else {
        setTask(null)
        loadData()
        loadStats()
      }
    } catch {
      setTask(null)
    }
  }, [loadData, loadStats])

  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current) }, [])

  const startSync = async () => {
    try {
      await request.post('/fund_manager/sync', null, {
        params: scopePreset ? { presetId: scopePreset } : {},
      })
      message.info('采集任务已启动')
      pollTick()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      message.warning(msg || '启动失败')
    }
  }

  const columns = [
    { title: '代码', dataIndex: 'code', key: 'code', width: 70, sorter: true },
    { title: '名称', dataIndex: 'name', key: 'name', width: 160, ellipsis: true, sorter: true },
    { title: '类型', dataIndex: 'fund_type', key: 'fund_type', width: 100, ellipsis: true },
    { title: '公司', dataIndex: 'fund_company', key: 'fund_company', width: 100, ellipsis: true, sorter: true },
    {
      title: '规模(亿)', dataIndex: 'scale', key: 'scale', width: 80, sorter: true,
      render: (v: number | null) => v != null ? v.toFixed(1) : '-',
    },
    {
      title: '近1年', dataIndex: 'return_1y', key: 'return_1y', width: 70, sorter: true,
      render: (v: number | null) => v != null ? `${v.toFixed(1)}%` : '-',
    },
    {
      title: '近3年', dataIndex: 'return_3y', key: 'return_3y', width: 70, sorter: true,
      render: (v: number | null) => v != null ? `${v.toFixed(1)}%` : '-',
    },
    { title: '现任经理', dataIndex: 'fund_manager', key: 'fund_manager', width: 90, ellipsis: true },
    {
      title: '状态', key: 'status', width: 70,
      render: (_: unknown, r: ManagerItem) =>
        r.managers ? <Tag color="green">已采集</Tag> : <Tag>未采集</Tag>,
    },
    { title: '经理(tenure)', dataIndex: 'managers', key: 'managers', width: 100, ellipsis: true, sorter: true },
    { title: '任职起始', dataIndex: 'start_date', key: 'start_date', width: 100, sorter: true },
    {
      title: '任职天数', dataIndex: 'tenure_days', key: 'tenure_days', width: 80, sorter: true,
      render: (v: number | null) => v != null ? v : '-',
    },
    {
      title: '任期回报', dataIndex: 'tenure_return', key: 'tenure_return', width: 80, sorter: true,
      render: (v: number | null) => v != null ? `${v.toFixed(1)}%` : '-',
    },
    {
      title: '采集时间', dataIndex: 'fetch_time', key: 'fetch_time', width: 100,
      render: (v: string | null) => v ? v.slice(0, 10) : '-',
    },
  ]

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small">
        <Space wrap>
          <Button type="primary" icon={<SyncOutlined spin={!!task} />} onClick={startSync} disabled={!!task}>
            {task ? '采集中…' : '采集经理数据'}
          </Button>
          <Select
            value={scopePreset}
            onChange={(v) => setScopePreset(v)}
            placeholder="采集范围: 镜像预设"
            allowClear
            style={{ width: 200 }}
            options={presets.map((x) => ({ value: x.id, label: x.name }))}
          />
          <Input.Search
            placeholder="代码/名称/经理" allowClear style={{ width: 180 }}
            onSearch={(v) => { setKeyword(v); setPage(1) }}
          />
          <Select value={coverage} onChange={(v) => { setCoverage(v); setPage(1) }} style={{ width: 100 }}>
            <Select.Option value="all">全部</Select.Option>
            <Select.Option value="covered">已采集</Select.Option>
            <Select.Option value="uncovered">未采集</Select.Option>
          </Select>
        </Space>
        {task && (
          <Progress
            percent={task.total_count ? Math.round(task.current_count / task.total_count * 100) : 0}
            format={() => `${task.current_count}/${task.total_count} 成功${task.success_count} 失败${task.fail_count}`}
            style={{ marginTop: 8 }}
          />
        )}
      </Card>

      {stats && (
        <Row gutter={16}>
          <Col span={8}><Statistic title="基金总数" value={stats.total} /></Col>
          <Col span={8}><Statistic title="已采集" value={stats.covered} valueStyle={{ color: '#52c41a' }} /></Col>
          <Col span={8}><Statistic title="未采集" value={stats.uncovered} valueStyle={{ color: '#999' }} /></Col>
        </Row>
      )}

      <Table
        dataSource={items} columns={columns} rowKey="code" size="small" loading={loading}
        pagination={{
          current: page, pageSize, total, showSizeChanger: true,
          onChange: (p, ps) => { setPage(p); setPageSize(ps) },
        }}
        onChange={(_pag, _filters, sorter) => {
          const s = Array.isArray(sorter) ? sorter[0] : sorter
          if (s?.field) {
            setSortField(s.field as string)
            setSortOrder(s.order === 'descend' ? 'desc' : 'asc')
          }
        }}
        expandable={{
          expandedRowRender: (r) => <TenureHistory code={r.code} />,
          rowExpandable: (r) => !!r.managers,
        }}
        scroll={{ x: 1400 }}
      />
    </Space>
  )
}
