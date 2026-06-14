import { useMemo, useState } from 'react'
import { Alert, Button, Card, Empty, Select, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import { useScreenData } from './hooks/useScreenData'
import { buildFundColumns } from '../fund/components/fundColumns'
import FundDetailModal from '../fund/components/FundDetailModal'
import type { FundItem } from '../fund/types'

export default function ScreenPage() {
  const { presets, presetId, latest, snapshot, loading, saving, selectPreset, refresh, saveMirror } =
    useScreenData()
  const [detailCode, setDetailCode] = useState<string | null>(null)

  const mirrorItems = snapshot?.items ?? []
  const latestCodes = useMemo(() => new Set(latest.map((f) => f.code)), [latest])
  const mirrorCodes = useMemo(() => new Set(mirrorItems.map((f) => f.code)), [mirrorItems])

  // 仅当已有镜像时才标注「新增」（无镜像不做对比）
  const newCount = snapshot ? latest.filter((f) => !mirrorCodes.has(f.code)).length : 0
  const droppedCount = mirrorItems.filter((f) => !latestCodes.has(f.code)).length

  const statusCol = (
    render: (code: string) => React.ReactNode,
  ): ColumnsType<FundItem>[number] => ({
    title: '状态',
    dataIndex: 'code',
    width: 76,
    fixed: 'left',
    render: (code: string) => render(code),
  })

  const latestColumns: ColumnsType<FundItem> = [
    statusCol((code) =>
      snapshot && !mirrorCodes.has(code) ? <Tag color="green">新增</Tag> : null,
    ),
    ...buildFundColumns({ onOpenDetail: setDetailCode, showNav: true }),
  ]
  const mirrorColumns: ColumnsType<FundItem> = [
    statusCol((code) => (!latestCodes.has(code) ? <Tag color="red">已剔除</Tag> : null)),
    ...buildFundColumns({ onOpenDetail: setDetailCode, showNav: false }),
  ]

  return (
    <Space direction="vertical" className="w-full" style={{ width: '100%' }} size="middle">
      <Card size="small">
        <Space wrap>
          <span className="text-gray-400">选择预设：</span>
          <Select
            placeholder="请选择基金预设条件"
            style={{ minWidth: 240 }}
            value={presetId ?? undefined}
            onChange={(v) => selectPreset(v)}
            options={presets.map((p) => ({ label: p.name, value: p.id }))}
          />
          <Button icon={<ReloadOutlined />} onClick={refresh} disabled={presetId == null} loading={loading}>
            重新筛选
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={saveMirror}
            disabled={presetId == null || !latest.length}
            loading={saving}
          >
            {snapshot ? '更新镜像' : '存为镜像'}
          </Button>
        </Space>
      </Card>

      {presetId == null ? (
        <Alert type="info" showIcon message="请选择一个基金预设，查看其镜像基金与最新筛选基金。" />
      ) : (
        <>
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
              scroll={{ x: 1500 }}
              pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 只` }}
            />
          </Card>

          <Card
            size="small"
            title={
              <Space>
                <span>镜像基金（{mirrorItems.length}）</span>
                {droppedCount > 0 && <Tag color="red">已剔除 {droppedCount}</Tag>}
                {snapshot && (
                  <span className="text-xs text-gray-400">镜像时间：{snapshot.created_at}</span>
                )}
              </Space>
            }
          >
            {snapshot ? (
              <Table<FundItem>
                rowKey="code"
                size="small"
                dataSource={mirrorItems}
                columns={mirrorColumns}
                scroll={{ x: 1340 }}
                pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 只` }}
              />
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无镜像，点上方「存为镜像」把当前筛选结果固化"
              />
            )}
          </Card>
        </>
      )}

      <FundDetailModal
        code={detailCode}
        open={detailCode !== null}
        onClose={() => setDetailCode(null)}
      />
    </Space>
  )
}
