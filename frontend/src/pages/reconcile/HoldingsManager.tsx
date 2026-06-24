import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Card, Empty, Table, Tag, Typography, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import request from '../../api/request'
import type { ClusterMeta, ComputedHolding } from './types'
import HoldingsEditor from './HoldingsEditor'
import TxnPanel from './TxnPanel'

const yuan = (v: number) => v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
const num = (v: number | null | undefined, d = 2) =>
  v == null ? '—' : v.toLocaleString('zh-CN', { maximumFractionDigits: d })

const ZERO_EPS = 0.5   // 市值 ≤ 此值视为「已清零」，仍展示在表格但标记「已清仓」，不计入统计

// 实际持仓管理：实际持仓（快照 + 交易合成，只读）+ 初始化快照（编辑）+ 交易记录。
// reloadSignal 由上层（如调仓建议批量落账）改动时触发整页重算。
export default function HoldingsManager({
  portfolioId, reloadSignal = 0,
}: { portfolioId: number | null; reloadSignal?: number }) {
  const [holdings, setHoldings] = useState<ComputedHolding[]>([])
  const [clusterMap, setClusterMap] = useState<Record<string, number | null>>({})
  const [clusterMeta, setClusterMeta] = useState<Record<string, ClusterMeta>>({})
  const [hasPreset, setHasPreset] = useState(false)
  const [loading, setLoading] = useState(false)
  const [bump, setBump] = useState(0)   // 快照/交易改动 → 重算实际持仓

  const loadHoldings = useCallback(async () => {
    if (!portfolioId) {
      setHoldings([]); setClusterMap({}); setClusterMeta({}); setHasPreset(false); return
    }
    setLoading(true)
    try {
      const [hRes, cRes] = await Promise.all([
        request.get<{ items: ComputedHolding[] }>('/reconcile/holdings', {
          params: { portfolio_id: portfolioId },
        }),
        request.get<{ has_preset: boolean; map: Record<string, number | null>; clusters: Record<string, ClusterMeta> }>(
          '/reconcile/holdings/clusters', { params: { portfolio_id: portfolioId } },
        ).catch(() => ({ data: { has_preset: false, map: {}, clusters: {} } })),
      ])
      setHoldings(hRes.data.items ?? [])
      setHasPreset(!!cRes.data.has_preset)
      setClusterMap(cRes.data.map ?? {})
      setClusterMeta(cRes.data.clusters ?? {})
    } catch {
      message.error('加载实际持仓失败')
    } finally {
      setLoading(false)
    }
  }, [portfolioId])

  useEffect(() => { loadHoldings() }, [loadHoldings, bump, reloadSignal])

  const onChanged = () => setBump((b) => b + 1)

  // 1) 已清零（市值≈0）的仍展示在表格并计入累计盈亏/投入（已实现盈亏是真实回报），但不计入市值/占比统计
  const zeroCount = holdings.filter((h) => (h.market_value || 0) <= ZERO_EPS).length
  const active = useMemo(() => holdings.filter((h) => (h.market_value || 0) > ZERO_EPS), [holdings])

  // 扩展 clusterMap：把目标基金代码也映射到对应簇，确保待建仓虚拟行归入正确赛道
  const extendedClusterMap = useMemo(() => {
    const m: Record<string, number | null> = { ...clusterMap }
    for (const [cid, meta] of Object.entries(clusterMeta)) {
      const code = meta.target_fund?.code
      if (code && m[code] === undefined) m[code] = Number(cid)
    }
    return m
  }, [clusterMap, clusterMeta])

  // 2) 按赛道分组排序：簇序号升序、赛道外最后、组内市值降序；已清零基金沉底
  const groupKey = useCallback((code: string) => {
    const cid = extendedClusterMap[code]
    if (cid != null && clusterMeta[String(cid)]) return String(cid)
    // 兜底：检查是否是某个簇的目标基金（防止 extendedClusterMap 未生效）
    for (const [k, meta] of Object.entries(clusterMeta)) {
      if (meta.target_fund?.code === code) return k
    }
    return '__outside__'
  }, [extendedClusterMap, clusterMeta])

  const sorted = useMemo(() => {
    const seqOf = (code: string) => {
      const k = groupKey(code)
      if (k === '__outside__') return Number.MAX_SAFE_INTEGER
      const s = clusterMeta[k]?.seq
      return s != null ? s : Number.MAX_SAFE_INTEGER - 1
    }
    return [...holdings].sort((a, b) => {
      const aClr = (a.market_value || 0) <= ZERO_EPS ? 1 : 0
      const bClr = (b.market_value || 0) <= ZERO_EPS ? 1 : 0
      if (aClr !== bClr) return aClr - bClr
      const sa = seqOf(a.fund_code), sb = seqOf(b.fund_code)
      if (sa !== sb) return sa - sb
      return (b.market_value || 0) - (a.market_value || 0)
    })
  }, [holdings, clusterMeta, groupKey])

  // 目标基金补全：不在实盘中的簇目标基金补一行虚拟行（0 值），方便用户看到该买什么
  const displayList = useMemo(() => {
    if (!hasPreset) return sorted
    const heldCodes = new Set(holdings.map((h) => h.fund_code))
    const phantoms: ComputedHolding[] = []
    for (const meta of Object.values(clusterMeta)) {
      const code = meta.target_fund?.code
      if (code && !heldCodes.has(code)) {
        phantoms.push({
          fund_code: code, fund_name: meta.target_fund?.name || '',
          market_value: 0, pnl: null, cost: null, shares: null,
          latest_nav: null, nav_date: null, valuation_ok: true, _phantom: true,
        })
      }
    }
    if (phantoms.length === 0) return sorted
    const out = [...sorted]
    const seqOfGroup = (k: string) => {
      if (k === '__outside__') return Number.MAX_SAFE_INTEGER
      const s = clusterMeta[k]?.seq
      return s != null ? s : Number.MAX_SAFE_INTEGER - 1
    }
    for (const ph of phantoms) {
      const pk = groupKey(ph.fund_code)
      const pSeq = seqOfGroup(pk)
      let insertIdx = out.length
      for (let i = 0; i < out.length; i++) {
        const ik = groupKey(out[i].fund_code)
        if (ik === pk) {
          let j = i
          while (j < out.length && groupKey(out[j].fund_code) === pk) j++
          insertIdx = j
          break
        }
        if (seqOfGroup(ik) > pSeq) {
          insertIdx = i
          break
        }
      }
      out.splice(insertIdx, 0, ph)
    }
    return out
  }, [sorted, holdings, clusterMeta, hasPreset, groupKey])

  // 目标基金代码集合（用于标记）
  const targetFundCodes = useMemo(() => {
    const s = new Set<string>()
    for (const meta of Object.values(clusterMeta)) {
      if (meta.target_fund?.code) s.add(meta.target_fund.code)
    }
    return s
  }, [clusterMeta])

  // 合并单元格：每个赛道分组的首行 rowSpan = 组大小，其余为 0
  const rowSpanByCode = useMemo(() => {
    const m: Record<string, number> = {}
    let i = 0
    while (i < displayList.length) {
      const k = groupKey(displayList[i].fund_code)
      let j = i
      while (j < displayList.length && groupKey(displayList[j].fund_code) === k) j++
      m[displayList[i].fund_code] = j - i
      for (let t = i + 1; t < j; t++) m[displayList[t].fund_code] = 0
      i = j
    }
    return m
  }, [displayList, groupKey])

  // 按赛道聚合：总市值、累计盈亏、总成本、累计投入（用于赛道合并单元格展示）
  const clusterAgg = useMemo(() => {
    const agg: Record<string, { mv: number; pnl: number; cost: number; invested: number }> = {}
    for (const h of displayList) {
      const k = groupKey(h.fund_code)
      if (!agg[k]) agg[k] = { mv: 0, pnl: 0, cost: 0, invested: 0 }
      agg[k].mv += h.market_value || 0
      agg[k].pnl += h.pnl ?? 0
      agg[k].cost += h.cost ?? 0
      agg[k].invested += h.total_invested ?? 0
    }
    return agg
  }, [displayList, groupKey])

  // 市值/占比只算在持（active）；累计盈亏/投入纳入已清仓（其已实现盈亏是真实回报），
  // 与簇汇总（基于含已清仓的 displayList）口径一致。phantom 仅在 displayList，不在 holdings。
  const total = active.reduce((s, h) => s + (h.market_value || 0), 0)
  const pnlTotal = holdings.reduce((s, h) => s + (h.pnl ?? 0), 0)
  const investedTotal = holdings.reduce((s, h) => s + (h.total_invested ?? 0), 0)
  const hasPnl = holdings.some((h) => h.pnl != null)

  const renderCluster = (code: string) => {
    const k = groupKey(code)
    const agg = clusterAgg[k] || { mv: 0, pnl: 0, cost: 0, invested: 0 }
    const cid = extendedClusterMap[code]
    const meta = cid != null ? clusterMeta[String(cid)] : undefined
    const pct = total > 0 ? (agg.mv / total * 100).toFixed(1) : '0.0'
    const pnlPct = agg.invested > 0 ? (agg.pnl / agg.invested * 100).toFixed(2) : null
    const pnlColor = agg.pnl > 0 ? '#f5222d' : agg.pnl < 0 ? '#52c41a' : undefined

    const summary = (
      <div style={{ marginTop: 6, fontSize: 12, lineHeight: '18px' }}>
        <span>市值 {yuan(agg.mv)} 元</span>
        <span style={{ marginLeft: 8, fontWeight: 600 }}>{pct}%</span>
        <span style={{ marginLeft: 8, color: pnlColor }}>
          {agg.pnl > 0 ? '+' : ''}{yuan(agg.pnl)}
        </span>
        {pnlPct != null && (
          <span style={{ marginLeft: 4, color: pnlColor, fontSize: 11 }}>
            ({agg.pnl > 0 ? '+' : ''}{pnlPct}%)
          </span>
        )}
      </div>
    )

    if (!meta) return (
      <div>
        <Tag>赛道外</Tag>
        {summary}
      </div>
    )
    const isOptimized = meta.seq != null
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <Tag
          color={isOptimized ? 'blue' : 'default'}
          style={{ alignSelf: 'flex-start', fontWeight: isOptimized ? 600 : 400 }}
        >
          {isOptimized ? `簇${meta.seq}` : (meta.label || '未入选簇')}
        </Tag>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {meta.industries.map((ind) => (
            <span key={ind.label} style={{ fontSize: 12 }}>
              <Typography.Text>{ind.label}</Typography.Text>
              <Typography.Text type="secondary" style={{ marginLeft: 2 }}>{Math.round(ind.ratio)}%</Typography.Text>
            </span>
          ))}
        </div>
        {!isOptimized && (
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            该赛道因均衡强度限制未入选仓位建议
          </Typography.Text>
        )}
        {summary}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card
        size="small"
        title={
          <span>
            实际持仓
            <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal', marginLeft: 8 }}>
              共 {holdings.length} 只 · 市值 {yuan(total)} 元
              {hasPnl && <>· 累计盈亏 <span style={{ color: pnlTotal >= 0 ? '#f5222d' : '#52c41a' }}>{pnlTotal >= 0 ? '+' : ''}{yuan(pnlTotal)}</span> 元</>}
              {hasPnl && investedTotal > 0 && (
                <>· 收益率 <span style={{ color: pnlTotal >= 0 ? '#f5222d' : '#52c41a' }}>
                  {pnlTotal >= 0 ? '+' : ''}{(pnlTotal / investedTotal * 100).toFixed(2)}%
                </span></>
              )}
              {zeroCount > 0 && <>· 其中 {zeroCount} 只已清仓</>}
            </Typography.Text>
          </span>
        }
        extra={<Button size="small" icon={<ReloadOutlined />} onClick={loadHoldings}>刷新</Button>}
      >
        <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: -4 }}>
          实际持仓 = 初始化快照 + 交易记录 综合算出（份额按交易当日单位净值折算，市值 = 份额 × 最新单位净值，
          成本按移动平均）。这里只读，改动请用下方「初始化快照」与「交易记录」。
          {hasPreset && '「所属赛道」按关联预设的聚类簇归类，相同赛道已合并展示。'}
        </Typography.Paragraph>
        {displayList.length === 0 ? (
          <Empty description="暂无持仓。先在下方「初始化快照」录入首次建仓金额。" />
        ) : (
          <Table<ComputedHolding>
            size="small"
            rowKey="fund_code"
            loading={loading}
            dataSource={displayList}
            pagination={false}
            columns={[
              ...(hasPreset ? [{
                title: '所属赛道（簇）', dataIndex: 'fund_code', key: 'cluster', width: 340,
                onCell: (row: ComputedHolding) => ({ rowSpan: rowSpanByCode[row.fund_code] ?? 1 }),
                render: (code: string) => renderCluster(code),
              }] : []),
              {
                title: '基金', dataIndex: 'fund_name',
                render: (v: string, row: ComputedHolding) => {
                  const isPhantom = row._phantom === true
                  const isTarget = targetFundCodes.has(row.fund_code)
                  return (
                    <span style={isPhantom ? { opacity: 0.6 } : undefined}>
                      {v || <Typography.Text type="secondary">—</Typography.Text>}
                      <Typography.Text type="secondary" style={{ fontFamily: 'monospace', marginLeft: 6, fontSize: 12 }}>
                        {row.fund_code}
                      </Typography.Text>
                      {isTarget && <Tag color="gold" style={{ marginLeft: 6 }}>目标</Tag>}
                      {!isPhantom && (row.market_value || 0) <= ZERO_EPS && <Tag style={{ marginLeft: 6 }}>已清仓</Tag>}
                      {isPhantom && <Tag color="default" style={{ marginLeft: 6 }}>待建仓</Tag>}
                      {row.valuation_ok === false && <Tag color="warning" style={{ marginLeft: 6 }}>估值不可用</Tag>}
                    </span>
                  )
                },
              },
              { title: '当前市值（元）', dataIndex: 'market_value', width: 140, align: 'right', render: (v: number) => yuan(v) },
              { title: '持有份额', dataIndex: 'shares', width: 130, align: 'right', render: (v: number | null) => num(v, 2) },
              {
                title: '最新净值', dataIndex: 'latest_nav', width: 130, align: 'right',
                render: (v: number | null, row) => v == null ? '—' : (
                  <span>{num(v, 4)}<Typography.Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>{row.nav_date}</Typography.Text></span>
                ),
              },
              { title: '成本（元）', dataIndex: 'cost', width: 120, align: 'right', render: (v: number | null) => v == null ? '—' : yuan(v) },
              {
                title: '累计盈亏（元）', dataIndex: 'pnl', width: 130, align: 'right',
                render: (v: number | null) => {
                  if (v == null) return <Typography.Text type="secondary">—</Typography.Text>
                  const color = v > 0 ? '#f5222d' : v < 0 ? '#52c41a' : undefined
                  return <span style={{ color }}>{v > 0 ? '+' : ''}{yuan(v)}</span>
                },
              },
              {
                title: '实际占比', dataIndex: 'market_value', key: 'ratio', width: 90, align: 'right',
                render: (v: number) => total > 0 ? `${(v / total * 100).toFixed(1)}%` : '—',
              },
              {
                title: '收益率', dataIndex: 'pnl', key: 'return_pct', width: 100, align: 'right',
                render: (v: number | null, row: ComputedHolding) => {
                  if (v == null || !row.total_invested) return <Typography.Text type="secondary">—</Typography.Text>
                  const pct = v / row.total_invested * 100
                  const color = pct > 0 ? '#f5222d' : pct < 0 ? '#52c41a' : undefined
                  return <span style={{ color }}>{pct > 0 ? '+' : ''}{pct.toFixed(2)}%</span>
                },
              },
            ]}
          />
        )}
      </Card>

      <HoldingsEditor portfolioId={portfolioId} onChanged={onChanged} />

      <TxnPanel portfolioId={portfolioId} held={holdings} onChanged={onChanged} />
    </div>
  )
}
