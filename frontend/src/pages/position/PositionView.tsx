import { useCallback, useEffect, useImperativeHandle, useState, forwardRef } from 'react'
import { Alert, Button, Card, Empty, Segmented, Space, Spin, Table, Tag, Tooltip, message } from 'antd'
import { ClockCircleOutlined, CopyOutlined, ExperimentOutlined, FundOutlined } from '@ant-design/icons'
import request from '../../api/request'
import PositionRow from './PositionRow'
import PortfolioCharts from './PortfolioCharts'
import LookthroughCard from './LookthroughCard'
import BacktestCard from './BacktestCard'
import type { BacktestResponse, BacktestResult, PositionResult } from './types'

// ③ 簇级仓位建议视图：对共享预设镜像聚类后，按每簇代表基金动量强度+乖离给出目标权重。
// presetId 由工作台容器下传；预设变化时自动生成仓位建议。
const PositionView = forwardRef<
  { run: () => Promise<void> },
  { presetId: number | null }
>(function PositionView({ presetId }, ref) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<PositionResult | null>(null)
  // 均衡强度：单一行业穿透占比上限 cap，越小越分散（牺牲更多动量权重），越大越接近纯动量
  const [cap, setCap] = useState(0.18)
  // 仓位建议展示模式：detail=完整（指标/走势/持仓），simple=简洁（名称/编码/比例，便于复制）
  const [viewMode, setViewMode] = useState<'detail' | 'simple'>('detail')
  // 穿透联动：勾选的股票/行业，用于过滤+高亮下方代表基金
  const [selStocks, setSelStocks] = useState<string[]>([])
  const [selInds, setSelInds] = useState<string[]>([])
  // 回测验证：动量调权 vs 等权（按需触发，较重）
  const [backtest, setBacktest] = useState<BacktestResult | null>(null)
  const [btLoading, setBtLoading] = useState(false)

  const clearSel = useCallback(() => {
    setSelStocks([])
    setSelInds([])
  }, [])

  useEffect(() => {
    setResult(null)
    setBacktest(null)
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
    setBacktest(null)   // 重新生成建议后，旧回测失效
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

  // 回测验证：固定当前代表基金集合，walk-forward 比较动量调权 vs 等权
  const runBacktest = useCallback(async () => {
    if (!presetId) {
      message.warning('请先在上方选择一个预设')
      return
    }
    setBtLoading(true)
    setBacktest(null)
    try {
      const { data } = await request.post<BacktestResponse>('/position/backtest', {
        preset_id: presetId,
        cap,
      })
      if (data.result) setBacktest(data.result)
      else message.info(data.reason ?? '无法回测')
    } catch {
      message.error('回测失败')
    } finally {
      setBtLoading(false)
    }
  }, [presetId, cap])

  // 工作台容器在预设变化时通过 ref 触发，用当前均衡强度
  useImperativeHandle(ref, () => ({ run: () => run() }), [run])

  const onCapChange = (v: number) => {
    setCap(v)
    setBacktest(null)    // 均衡强度变了→代表基金可能变，旧回测失效
    if (result) run(v)   // 已有结果才即时重算，避免空选预设时误触
  }

  const items = result?.items
  const meta = result?.meta
  const clusterMeta = result?.cluster_meta
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

  // 简洁模式：把「名称\t编码\t建议仓位」整体复制，方便粘贴到 Excel
  const copyAll = () => {
    const text = shownItems
      .map((it) => `${it.fund.name}\t${it.fund.code}\t${(it.weight * 100).toFixed(1)}%`)
      .join('\n')
    navigator.clipboard.writeText(text).then(
      () => message.success(`已复制 ${shownItems.length} 行`),
      () => message.error('复制失败'),
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Space wrap>
        <Button type="primary" icon={<FundOutlined />} loading={loading} onClick={() => run()}>
          生成仓位建议
        </Button>
        <Tooltip title="固定当前代表基金集合，按月度再平衡做 walk-forward 回测，比较「动量调权 vs 等权」，验证调权这一步是否真的有用。较重，按需运行。">
          <Button icon={<ExperimentOutlined />} loading={btLoading} onClick={runBacktest}>
            回测验证
          </Button>
        </Tooltip>
        <Tooltip title="单一行业穿透占比上限：松=22%（更接近纯动量，行业更集中），中=18%，紧=14%（更分散，牺牲更多动量权重）。切换会立即重算。">
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
            {clusterMeta?.share_merged ? ` · 已合并 ${clusterMeta.share_merged} 只 A/C 份额` : ''}
            {meta.nav_missing.length ? ` · ${meta.nav_missing.length} 只缺净值按中性估计` : ''}
          </span>
        )}
        {meta && (meta.nav_as_of || meta.holdings_quarter) && (
          <Tooltip title="本建议基于库内已采集数据现场计算，非实时行情。净值随下次采集前移、持仓季度级更新；要反映最新市况请先跑数据采集再重新生成。">
            <Tag icon={<ClockCircleOutlined />} color="default" style={{ marginInlineEnd: 0 }}>
              数据截止：净值 {meta.nav_as_of ?? '—'}
              {meta.holdings_quarter ? ` · 持仓 ${meta.holdings_quarter}` : ''}
            </Tag>
          </Tooltip>
        )}
      </Space>

      {!loading && result && items && items.length > 0 && (
        <Alert
          type="info"
          showIcon
          message="每簇从综合分前 5 候选里选 1 只「代表基金」：在保证质量前提下尽量降低底层行业相关性（必要时用次优基金替代 TOP1）。权重 = 动量因子 × 乖离因子的基准，再做行业感知再分配（单一行业穿透占比 ≤ 上限），截断到 [3%, 25%] 后归一到 100%。动量强度（近期净值趋势强度，非基本面景气）由代表基金净值四因子估计（top10 持仓口径、单基金代理），属追涨择时、仅供参考、非投资建议。"
        />
      )}

      {loading && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin tip="动量与仓位计算中…" />
        </div>
      )}

      {!loading && result && items === null && (
        <Alert type="info" showIcon message={result.reason ?? '无法计算'} />
      )}

      {!loading && portfolio && portfolio.curve.length > 0 && (
        <PortfolioCharts portfolio={portfolio} />
      )}

      {btLoading && (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <Spin tip="回测计算中（逐调仓点重算权重）…" />
        </div>
      )}

      {!btLoading && backtest && <BacktestCard data={backtest} />}

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
        <Card
          title="各赛道仓位建议"
          size="small"
          extra={
            <Space>
              {viewMode === 'simple' && shownItems.length > 0 && (
                <Button size="small" icon={<CopyOutlined />} onClick={copyAll}>
                  复制全部
                </Button>
              )}
              <Segmented
                size="small"
                value={viewMode}
                onChange={(v) => setViewMode(v as 'detail' | 'simple')}
                options={[
                  { label: '简洁', value: 'simple' },
                  { label: '详细', value: 'detail' },
                ]}
              />
            </Space>
          }
        >
          {shownItems.length === 0 ? (
            <Empty description="所选股票/行业未命中任何代表基金" />
          ) : viewMode === 'simple' ? (
            <Table
              size="small"
              rowKey="cluster_id"
              dataSource={shownItems}
              pagination={false}
              columns={[
                { title: '基金名称', dataIndex: ['fund', 'name'] },
                {
                  title: '基金编码',
                  dataIndex: ['fund', 'code'],
                  width: 120,
                  render: (v: string) => <span style={{ fontFamily: 'monospace' }}>{v}</span>,
                },
                {
                  title: '建议仓位',
                  dataIndex: 'weight',
                  width: 110,
                  align: 'right',
                  render: (w: number) => <b>{(w * 100).toFixed(1)}%</b>,
                },
              ]}
            />
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
