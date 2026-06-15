import { useCallback, useEffect, useImperativeHandle, useState, forwardRef } from 'react'
import { Alert, Button, Card, Empty, Space, Spin, message } from 'antd'
import { FundOutlined } from '@ant-design/icons'
import request from '../../api/request'
import PositionRow from './PositionRow'
import PortfolioCharts from './PortfolioCharts'
import LookthroughCard from './LookthroughCard'
import type { PositionResult } from './types'

// ③ 簇级仓位建议视图：对共享预设镜像聚类后，按每簇 TOP1 基金景气度+乖离给出目标权重。
// presetId 由工作台容器下传；预设变化时自动生成仓位建议。
const PositionView = forwardRef<
  { run: () => Promise<void> },
  { presetId: number | null }
>(function PositionView({ presetId }, ref) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<PositionResult | null>(null)
  // 穿透联动：勾选的股票/行业，用于过滤+高亮下方代表基金
  const [selStocks, setSelStocks] = useState<string[]>([])
  const [selInds, setSelInds] = useState<string[]>([])

  const clearSel = useCallback(() => {
    setSelStocks([])
    setSelInds([])
  }, [])

  useEffect(() => {
    setResult(null)
    clearSel()
  }, [presetId, clearSel])

  const run = useCallback(async () => {
    if (!presetId) {
      message.warning('请先在上方选择一个预设')
      return
    }
    setLoading(true)
    setResult(null)
    clearSel()
    try {
      const { data } = await request.post<PositionResult>('/position/run', { preset_id: presetId })
      setResult(data)
    } catch {
      message.error('仓位计算失败')
    } finally {
      setLoading(false)
    }
  }, [presetId, clearSel])

  useImperativeHandle(ref, () => ({ run }), [run])

  const items = result?.items
  const meta = result?.meta
  const portfolio = result?.portfolio
  const lookthrough = result?.lookthrough
  const maxWeight = items && items.length ? Math.max(...items.map((i) => i.weight)) : 0

  // 联动过滤：勾选股票/行业后，仅保留「持有任一所选项」的代表基金（并集）
  const stockSet = new Set(selStocks)
  const indSet = new Set(selInds)
  const hasSel = selStocks.length > 0 || selInds.length > 0
  const shownItems = !items
    ? []
    : hasSel
      ? items.filter((it) => (it.holdings ?? []).some((h) => stockSet.has(h.code) || indSet.has(h.industry)))
      : items

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

      {!loading && portfolio && portfolio.curve.length > 0 && (
        <PortfolioCharts portfolio={portfolio} />
      )}

      {!loading && lookthrough && lookthrough.stocks.length > 0 && (
        <LookthroughCard
          data={lookthrough}
          selStocks={selStocks}
          selInds={selInds}
          onSelStocks={setSelStocks}
          onSelInds={setSelInds}
        />
      )}

      {!loading && hasSel && items && (
        <Alert
          type="warning"
          showIcon
          message={`已按 ${selStocks.length} 只股票 / ${selInds.length} 个行业筛选 · 命中 ${shownItems.length} / ${items.length} 只代表基金（并集，命中项已高亮）`}
          action={
            <Button size="small" type="link" onClick={clearSel}>
              清除筛选
            </Button>
          }
        />
      )}

      {!loading && items && items.length > 0 && (
        <Card title="各赛道仓位建议" size="small">
          {shownItems.length === 0 ? (
            <Empty description="所选股票/行业未命中任何代表基金" />
          ) : (
            shownItems.map((it) => (
              <PositionRow
                key={it.cluster_id}
                item={it}
                maxWeight={maxWeight}
                highlightStocks={stockSet}
                highlightInds={indSet}
              />
            ))
          )}
        </Card>
      )}

      {!loading && !result && <Empty description="点「生成仓位建议」分析该预设镜像" />}
    </div>
  )
})

export default PositionView
