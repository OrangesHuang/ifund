import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Empty, Space, Spin, message } from 'antd'
import { FundOutlined } from '@ant-design/icons'
import request from '../../api/request'
import PositionRow from './PositionRow'
import type { PositionResult } from './types'

// ③ 簇级仓位建议视图：对共享预设镜像聚类后，按每簇 TOP1 基金景气度+乖离给出目标权重。
// presetId 由工作台容器下传；预设变化时清空旧结果，需手动点「生成仓位建议」。
export default function PositionView({ presetId }: { presetId: number | null }) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<PositionResult | null>(null)

  useEffect(() => {
    setResult(null)
  }, [presetId])

  const run = useCallback(async () => {
    if (!presetId) {
      message.warning('请先在上方选择一个预设')
      return
    }
    setLoading(true)
    setResult(null)
    try {
      const { data } = await request.post<PositionResult>('/position/run', { preset_id: presetId })
      setResult(data)
    } catch {
      message.error('仓位计算失败')
    } finally {
      setLoading(false)
    }
  }, [presetId])

  const items = result?.items
  const meta = result?.meta
  const maxWeight = items && items.length ? Math.max(...items.map((i) => i.weight)) : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Space wrap>
        <Button type="primary" icon={<FundOutlined />} loading={loading} onClick={run}>
          生成仓位建议
        </Button>
        {meta && (
          <span style={{ color: '#888', fontSize: 12 }}>
            {meta.n_clusters} 个赛道 · 等权基准 {(meta.base_weight * 100).toFixed(1)}%
            {meta.nav_missing.length ? ` · ${meta.nav_missing.length} 只缺净值按中性估计` : ''}
          </span>
        )}
      </Space>

      {!loading && result && items && items.length > 0 && (
        <Alert
          type="info"
          showIcon
          message="每簇只配综合分第一的「代表基金」；权重 = 等权基准 × 景气因子 × 乖离因子，截断到 [3%, 25%] 后归一到 100%。景气度由代表基金净值四因子估计（top10 持仓口径，单基金代理），仅供参考、非投资建议。"
        />
      )}

      {loading && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin tip="景气度与仓位计算中…" />
        </div>
      )}

      {!loading && result && items === null && (
        <Alert type="info" showIcon message={result.reason ?? '无法计算'} />
      )}

      {!loading && items && items.length > 0 && (
        <Card>
          {items.map((it) => (
            <PositionRow key={it.cluster_id} item={it} maxWeight={maxWeight} />
          ))}
        </Card>
      )}

      {!loading && !result && <Empty description="点「生成仓位建议」分析该预设镜像" />}
    </div>
  )
}
