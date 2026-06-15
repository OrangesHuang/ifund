import { useCallback, useEffect, useImperativeHandle, useState, forwardRef } from 'react'
import { Alert, Button, Card, Empty, Segmented, Space, Spin, Tooltip, message } from 'antd'
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
  // 均衡强度：单一行业穿透占比上限 cap，越小越分散（牺牲更多景气权重），越大越接近纯景气
  const [cap, setCap] = useState(0.18)
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

  // capArg 用于切换均衡强度时立即用新值重算（避免 setCap 异步导致闭包读到旧值）
  const run = useCallback(async (capArg?: number) => {
    if (!presetId) {
      message.warning('请先在上方选择一个预设')
      return
    }
    setLoading(true)
    setResult(null)
    clearSel()
    try {
      const { data } = await request.post<PositionResult>('/position/run', {
        preset_id: presetId,
        cap: capArg ?? cap,
      })
      setResult(data)
    } catch {
      message.error('仓位计算失败')
    } finally {
      setLoading(false)
    }
  }, [presetId, clearSel, cap])

  // 工作台容器在预设变化时通过 ref 触发，用当前均衡强度
  useImperativeHandle(ref, () => ({ run: () => run() }), [run])

  const onCapChange = (v: number) => {
    setCap(v)
    if (result) run(v)   // 已有结果才即时重算，避免空选预设时误触
  }

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
        <Button type="primary" icon={<FundOutlined />} loading={loading} onClick={() => run()}>
          生成仓位建议
        </Button>
        <Tooltip title="单一行业穿透占比上限：松=22%（更接近纯景气，行业更集中），中=18%，紧=14%（更分散，牺牲更多景气权重）。切换会立即重算。">
          <Segmented
            value={cap}
            disabled={loading}
            onChange={(v) => onCapChange(v as number)}
            options={[
              { label: '均衡·松', value: 0.22 },
              { label: '均衡·中', value: 0.18 },
              { label: '均衡·紧', value: 0.14 },
            ]}
          />
        </Tooltip>
        {meta && (
          <span style={{ color: '#888', fontSize: 12 }}>
            {meta.n_clusters} 个赛道 · 等权基准 {(meta.base_weight * 100).toFixed(1)}% · 单行业上限 {(meta.cap * 100).toFixed(0)}%
            {meta.funds_swapped ? ` · ${meta.funds_swapped} 簇为降相关选了次优基金` : ''}
            {meta.nav_missing.length ? ` · ${meta.nav_missing.length} 只缺净值按中性估计` : ''}
          </span>
        )}
      </Space>

      {!loading && result && items && items.length > 0 && (
        <Alert
          type="info"
          showIcon
          message="每簇从综合分前 5 候选里选 1 只「代表基金」：在保证质量前提下尽量降低底层行业相关性（必要时用次优基金替代 TOP1）。权重 = 景气因子 × 乖离因子的基准，再做行业感知再分配（单一行业穿透占比 ≤ 上限），截断到 [3%, 25%] 后归一到 100%。景气度由代表基金净值四因子估计（top10 持仓口径，单基金代理），仅供参考、非投资建议。"
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
