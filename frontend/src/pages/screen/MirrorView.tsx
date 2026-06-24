import { useMemo, useState } from 'react'
import { Alert, Button, Card, Empty, Popconfirm, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined, SaveOutlined, StopOutlined, UndoOutlined } from '@ant-design/icons'
import { useScreenData } from './hooks/useScreenData'
import { buildFundColumns } from '../fund/components/fundColumns'
import FundDetailModal from '../fund/components/FundDetailModal'
import NavTrendModal from '../fund/components/NavTrendModal'
import type { FundItem, QueryPreset } from '../fund/types'

// 镜像基金视图：对比「最新筛选结果」与「已存镜像」，并把当前结果存为镜像。
// 镜像区按「过滤名单」拆成「有效镜像 / 已过滤」两块——过滤名单复用预设 exclude_codes，
// 移入后下游聚类/仓位即时不含该基金（后端读快照时实时剔除）。
// presetId / presets 由工作台容器统一下传（共享一个预设下拉）。
export default function MirrorView({
  presetId,
  presets,
  onMirrorSaved,
}: {
  presetId: number | null
  presets: QueryPreset[]
  onMirrorSaved?: () => void   // 镜像更新 / 过滤名单变化后联动（重跑聚类/仓位）
}) {
  const {
    latest, snapshot, loading, saving, refresh, saveMirror,
    excluded, addExcluded, removeExcluded,
  } = useScreenData(presetId, presets)
  const [detailCode, setDetailCode] = useState<string | null>(null)
  const [trend, setTrend] = useState<{ code: string; name: string } | null>(null)
  // 受控分页：移入/移回过滤名单使行数变化时，把当前页 clamp 回有效范围，避免停在空白页
  const [latestPag, setLatestPag] = useState({ current: 1, pageSize: 20 })
  const [mirrorPag, setMirrorPag] = useState({ current: 1, pageSize: 20 })

  const mirrorItems = snapshot?.items ?? []
  const excludedSet = useMemo(() => new Set(excluded), [excluded])
  const latestCodes = useMemo(() => new Set(latest.map((f) => f.code)), [latest])
  const mirrorCodes = useMemo(() => new Set(mirrorItems.map((f) => f.code)), [mirrorItems])

  // 镜像拆两区：有效（未过滤）/ 已过滤
  const effectiveItems = useMemo(
    () => mirrorItems.filter((f) => !excludedSet.has(f.code)),
    [mirrorItems, excludedSet],
  )
  const filteredItems = useMemo(
    () => mirrorItems.filter((f) => excludedSet.has(f.code)),
    [mirrorItems, excludedSet],
  )

  // 仅当已有镜像时才标注「新增」（无镜像不做对比）；剔除/新增只看「有效镜像」
  const newCount = snapshot ? latest.filter((f) => !mirrorCodes.has(f.code)).length : 0
  const droppedCount = effectiveItems.filter((f) => !latestCodes.has(f.code)).length

  // 数据条数变化后，当前页可能越界 → clamp 到末页（dataSource 变短时不显示空白页）
  const latestCurrent = Math.min(latestPag.current, Math.max(1, Math.ceil(latest.length / latestPag.pageSize)))
  const mirrorCurrent = Math.min(mirrorPag.current, Math.max(1, Math.ceil(effectiveItems.length / mirrorPag.pageSize)))

  // 移入/移回过滤名单后联动重跑聚类/仓位
  const handleExclude = async (code: string) => {
    if (await addExcluded(code)) onMirrorSaved?.()
  }
  const handleRestore = async (code: string) => {
    if (await removeExcluded(code)) onMirrorSaved?.()
  }

  const statusCol = (
    render: (code: string) => React.ReactNode,
  ): ColumnsType<FundItem>[number] => ({
    title: '状态',
    dataIndex: 'code',
    width: 76,
    fixed: 'left',
    render: (code: string) => render(code),
  })

  // 行内「移入过滤」操作列（有效镜像用）
  const excludeActionCol: ColumnsType<FundItem>[number] = {
    title: '过滤',
    key: 'op_exclude',
    width: 92,
    fixed: 'right',
    render: (_: unknown, row: FundItem) => (
      <Popconfirm
        title="移入过滤名单？"
        description="该基金将从镜像剔除，聚类/仓位不再纳入"
        okText="移入"
        cancelText="取消"
        onConfirm={() => handleExclude(row.code)}
      >
        <Button size="small" type="link" danger icon={<StopOutlined />}>
          移入过滤
        </Button>
      </Popconfirm>
    ),
  }
  // 行内「移回」操作列（过滤名单用）
  const restoreActionCol: ColumnsType<FundItem>[number] = {
    title: '操作',
    key: 'op_restore',
    width: 88,
    fixed: 'right',
    render: (_: unknown, row: FundItem) => (
      <Button size="small" type="link" icon={<UndoOutlined />} onClick={() => handleRestore(row.code)}>
        移回
      </Button>
    ),
  }

  const latestColumns: ColumnsType<FundItem> = [
    statusCol((code) =>
      snapshot && !mirrorCodes.has(code) ? <Tag color="green">新增</Tag> : null,
    ),
    ...buildFundColumns({
      onOpenDetail: setDetailCode,
      onOpenTrend: (code, name) => setTrend({ code, name }),
      showNav: true,
      showAi: true,
    }),
  ]
  const effectiveColumns: ColumnsType<FundItem> = [
    statusCol((code) => (!latestCodes.has(code) ? <Tag color="red">已剔除</Tag> : null)),
    ...buildFundColumns({ onOpenDetail: setDetailCode, showNav: false, showAi: true }),
    excludeActionCol,
  ]
  const filteredColumns: ColumnsType<FundItem> = [
    ...buildFundColumns({ onOpenDetail: setDetailCode, showNav: false, showAi: true }),
    restoreActionCol,
  ]

  if (presetId == null) {
    return <Alert type="info" showIcon message="请在上方选择一个基金预设，查看其镜像基金与最新筛选基金。" />
  }

  return (
    <Space direction="vertical" className="w-full" style={{ width: '100%' }} size="middle">
      <Space wrap>
        <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
          重新筛选
        </Button>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          onClick={async () => {
            if (await saveMirror()) onMirrorSaved?.()
          }}
          disabled={!latest.length}
          loading={saving}
        >
          {snapshot ? '更新镜像' : '存为镜像'}
        </Button>
      </Space>

      <Card
        size="small"
        title={
          <Space>
            <span>最新筛选基金（{latest.length}）</span>
            {newCount > 0 && <Tag color="green">新增 {newCount}</Tag>}
          </Space>
        }
      >
        <Table<FundItem>
          rowKey="code"
          size="small"
          loading={loading}
          dataSource={latest}
          columns={latestColumns}
          scroll={{ x: 2320 }}
          pagination={{
            current: latestCurrent,
            pageSize: latestPag.pageSize,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 只`,
            onChange: (current, pageSize) => setLatestPag({ current, pageSize }),
          }}
        />
      </Card>

      <Card
        size="small"
        title={
          <Space>
            <span>镜像基金（{effectiveItems.length}）</span>
            {droppedCount > 0 && <Tag color="red">已剔除 {droppedCount}</Tag>}
            {snapshot && <span className="text-xs text-gray-400">镜像时间：{snapshot.created_at}</span>}
          </Space>
        }
      >
        {snapshot ? (
          <Table<FundItem>
            rowKey="code"
            size="small"
            dataSource={effectiveItems}
            columns={effectiveColumns}
            scroll={{ x: 2200 }}
            pagination={{
              current: mirrorCurrent,
              pageSize: mirrorPag.pageSize,
              showSizeChanger: true,
              showTotal: (t) => `共 ${t} 只`,
              onChange: (current, pageSize) => setMirrorPag({ current, pageSize }),
            }}
          />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无镜像，点上方「存为镜像」把当前筛选结果固化"
          />
        )}
      </Card>

      {snapshot && (
        <Card
          size="small"
          title={
            <Space>
              <StopOutlined style={{ color: '#ff4d4f' }} />
              <span>过滤名单（{filteredItems.length}）</span>
              <span className="text-xs text-gray-400">
                这些基金已从镜像剔除，聚类/仓位不纳入；可「移回」撤销
              </span>
            </Space>
          }
        >
          {filteredItems.length ? (
            <Table<FundItem>
              rowKey="code"
              size="small"
              dataSource={filteredItems}
              columns={filteredColumns}
              scroll={{ x: 2120 }}
              pagination={false}
            />
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无过滤基金，可在上方镜像列表对 AI 评价较差的基金点「移入过滤」"
            />
          )}
        </Card>
      )}

      <FundDetailModal code={detailCode} open={detailCode !== null} onClose={() => setDetailCode(null)} />
      <NavTrendModal
        code={trend?.code ?? null}
        name={trend?.name}
        open={!!trend}
        onClose={() => setTrend(null)}
      />
    </Space>
  )
}
