import { useEffect, useRef, useState } from 'react'
import { Card, Select, Space, Tabs } from 'antd'
import request from '../../api/request'
import type { QueryPreset } from '../fund/types'
import MirrorView from '../screen/MirrorView'
import ClusterView from '../cluster/ClusterView'
import PositionView from '../position/PositionView'

// 组合分析工作台：三类分析（镜像基金 / 聚类 / 仓位）共享同一个预设镜像，
// 选择预设后自动运行聚类和仓位分析；用 Tab 切换不同视图。
export default function WorkbenchPage() {
  const [presets, setPresets] = useState<QueryPreset[]>([])
  const [presetId, setPresetId] = useState<number | null>(null)
  const [tab, setTab] = useState('mirror')
  const clusterRef = useRef<{ run: () => Promise<void> }>(null)
  const positionRef = useRef<{ run: () => Promise<void> }>(null)

  useEffect(() => {
    request
      .get('/fund/presets')
      .then(({ data }) => setPresets(data.items ?? data ?? []))
      .catch(() => undefined)
  }, [])

  // 预设变化时自动运行聚类和仓位分析
  useEffect(() => {
    if (!presetId) return
    setTimeout(() => {
      clusterRef.current?.run()
      positionRef.current?.run()
    }, 100)
  }, [presetId])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card size="small">
        <Space wrap>
          <span className="text-gray-400">选择预设：</span>
          <Select
            placeholder="请选择基金预设条件"
            style={{ minWidth: 260 }}
            value={presetId ?? undefined}
            onChange={setPresetId}
            options={presets.map((p) => ({ label: p.name, value: p.id }))}
          />
          <span style={{ color: '#999', fontSize: 12 }}>
            镜像基金 → 行业暴露聚类 → 簇级仓位建议，三步共用这一份预设镜像
          </span>
        </Space>
      </Card>

      <Tabs
        activeKey={tab}
        onChange={setTab}
        items={[
          {
            key: 'mirror',
            label: '镜像基金',
            children: <MirrorView presetId={presetId} presets={presets} />,
          },
          {
            key: 'cluster',
            label: '聚类分析',
            children: <ClusterView ref={clusterRef} presetId={presetId} />,
          },
          {
            key: 'position',
            label: '仓位建议',
            children: <PositionView ref={positionRef} presetId={presetId} />,
          },
        ]}
      />
    </div>
  )
}
