import { useCallback, useEffect, useImperativeHandle, useState, forwardRef } from 'react'
import { Alert, Button, Collapse, Empty, Space, Spin, Tag, message } from 'antd'
import { ClusterOutlined } from '@ant-design/icons'
import request from '../../api/request'
import ClusterCard from './ClusterCard'
import type { ClusterResult } from './types'

// ② 行业暴露聚类视图：对共享预设的镜像快照做聚类分析。
// presetId 由工作台容器下传；预设变化时自动运行聚类。
const ClusterView = forwardRef<
  { run: () => Promise<void> },
  { presetId: number | null }
>(function ClusterView({ presetId }, ref) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ClusterResult | null>(null)

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
      const { data } = await request.post<ClusterResult>('/cluster/run', { preset_id: presetId })
      setResult(data)
    } catch {
      message.error('聚类失败')
    } finally {
      setLoading(false)
    }
  }, [presetId])

  useImperativeHandle(ref, () => ({ run }), [run])

  const clusters = result?.clusters
  const meta = result?.meta

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Space wrap>
        <Button type="primary" icon={<ClusterOutlined />} loading={loading} onClick={run}>
          运行聚类
        </Button>
        {meta && (
          <span style={{ color: '#888', fontSize: 12 }}>
            共 {meta.total ?? meta.n} 只基金 · {meta.t} 簇
            {meta.share_merged ? ` · 已合并 ${meta.share_merged} 只 A/C 同基金份额` : ''}
            {meta.dropped ? ` · 其中 ${meta.dropped} 只无股票持仓归「其他」` : ''}
          </span>
        )}
      </Space>

      {loading && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin tip="聚类计算中…" />
        </div>
      )}

      {!loading && result && clusters === null && (
        <Alert type="info" showIcon message={result.reason ?? '无法聚类'} />
      )}

      {!loading && clusters && clusters.length > 0 && (
        <Collapse
          defaultActiveKey={clusters.slice(0, 1).map((c) => String(c.cluster_id))}
          items={clusters.map((c) => ({
            key: String(c.cluster_id),
            label: (
              <Space wrap size={[6, 4]}>
                <Tag color="geekblue">簇 {c.cluster_id}</Tag>
                <span style={{ fontWeight: 600 }}>
                  {c.top_industries.length
                    ? c.top_industries.map((i) => `${i.label} ${i.ratio.toFixed(1)}%`).join(' / ')
                    : c.name}
                </span>
                <span style={{ color: '#888' }}>· {c.fund_count} 只 ·</span>
                {c.signature_stocks.slice(0, 3).map((s) => (
                  <Tag key={s.code} color="blue">
                    {s.name}
                  </Tag>
                ))}
              </Space>
            ),
            children: <ClusterCard cluster={c} />,
          }))}
        />
      )}

      {!loading && !result && <Empty description="点「运行聚类」分析该预设镜像" />}
    </div>
  )
})

export default ClusterView
