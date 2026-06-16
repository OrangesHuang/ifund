import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Empty, Segmented, Space, Spin, Tag, Tooltip, message } from 'antd'
import { ClockCircleOutlined, ReconciliationOutlined } from '@ant-design/icons'
import request from '../../api/request'
import SummaryCard from './SummaryCard'
import ReconcileTable from './ReconcileTable'
import TransfersTable from './TransfersTable'
import type { ReconResult } from './types'

// 操作指南：把所选实盘关联的②仓位建议目标比例落到实盘持仓上，按赛道对齐推导操作。
// 两个正交开关覆盖四类意图；现金由系统反推（"加满还差多少"），无需预填。
export default function ReconcileView({
  portfolioId, hasPreset, onSavedTxns,
}: { portfolioId: number | null; hasPreset: boolean; onSavedTxns?: () => void }) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ReconResult | null>(null)
  // 缓冲带：偏离在盘子的此比例内则保持不动（抗短期噪音、保调仓连贯）。默认标准 3%。
  const [band, setBand] = useState(0.03)
  // 均衡强度 cap：与仓位建议一致，默认「紧」0.14。
  const [cap, setCap] = useState(0.14)
  // 开关一：赛道外是否可卖去补缺口（false=保留不动）。默认保留。
  const [sellOutside, setSellOutside] = useState(false)
  // 开关二：赛道内超配是否可减（true=削峰填谷 / false=不减只往上加）。默认可减（最省）。
  const [trimOverflow, setTrimOverflow] = useState(true)

  // 切换实盘后清空旧结果
  useEffect(() => {
    setResult(null)
  }, [portfolioId])

  const run = useCallback(async () => {
    if (!portfolioId) {
      message.warning('请先选择一个实盘')
      return
    }
    if (!hasPreset) {
      message.warning('请先为该实盘关联一个仓位建议（预设）')
      return
    }
    setLoading(true)
    setResult(null)
    try {
      const { data } = await request.post<ReconResult>('/reconcile/run', {
        portfolio_id: portfolioId,
        band,
        cap,
        sell_outside: sellOutside,
        trim_overflow: trimOverflow,
      })
      setResult(data)
    } catch {
      message.error('生成操作指南失败')
    } finally {
      setLoading(false)
    }
  }, [portfolioId, hasPreset, band, cap, sellOutside, trimOverflow])

  const rows = result?.rows
  const summary = result?.summary
  const meta = result?.meta

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card size="small" title="调仓方式">
        <Space wrap size="large">
          <Tooltip title="保留不动：赛道外基金不卖（最小干预）。可卖补仓：把赛道外基金卖出，优先用于补低配赛道。">
            <span>
              赛道外基金：
              <Segmented
                style={{ marginLeft: 8 }}
                value={sellOutside ? 'sell' : 'keep'}
                onChange={(v) => setSellOutside(v === 'sell')}
                options={[
                  { label: '保留不动', value: 'keep' },
                  { label: '可卖补仓', value: 'sell' },
                ]}
              />
            </span>
          </Tooltip>
          <Tooltip title="可减（削峰填谷）：卖出超配赛道补低配赛道，盘子=赛道内现额，理论零追加。不减（只往上加）：超配赛道不碰，只买入，盘子放大到最超配赛道达标——严重超配时追加现金需求会很高。">
            <span>
              赛道内超配：
              <Segmented
                style={{ marginLeft: 8 }}
                value={trimOverflow ? 'cut' : 'nocut'}
                onChange={(v) => setTrimOverflow(v === 'cut')}
                options={[
                  { label: '可减（削峰填谷）', value: 'cut' },
                  { label: '不减（只往上加）', value: 'nocut' },
                ]}
              />
            </span>
          </Tooltip>
          <Tooltip title="缓冲带：目标与实际的偏离在「盘子 × 此比例」以内就保持不动，抑制短期噪音、保持调仓连贯。宽松=更少折腾，灵敏=更贴目标。">
            <span>
              缓冲带：
              <Segmented
                style={{ marginLeft: 8 }}
                value={band}
                onChange={(v) => setBand(v as number)}
                options={[
                  { label: '宽松 5%', value: 0.05 },
                  { label: '标准 3%', value: 0.03 },
                  { label: '灵敏 1.5%', value: 0.015 },
                ]}
              />
            </span>
          </Tooltip>
          <Tooltip title="均衡强度（单一行业穿透占比上限），与仓位建议一致。紧=更分散。改这里会用新 cap 重算目标比例。">
            <span>
              均衡强度：
              <Segmented
                style={{ marginLeft: 8 }}
                value={cap}
                onChange={(v) => setCap(v as number)}
                options={[
                  { label: '松', value: 0.22 },
                  { label: '中', value: 0.18 },
                  { label: '紧', value: 0.14 },
                ]}
              />
            </span>
          </Tooltip>
          <Button type="primary" icon={<ReconciliationOutlined />} loading={loading} onClick={run}>
            生成操作指南
          </Button>
        </Space>
        {meta && (meta.nav_as_of || meta.holdings_quarter) && (
          <div style={{ marginTop: 10 }}>
            <Tooltip title="目标比例基于库内已采集数据现场计算，非实时行情。要反映最新市况请先跑数据采集。">
              <Tag icon={<ClockCircleOutlined />} color="default">
                数据截止：净值 {meta.nav_as_of ?? '—'}
                {meta.holdings_quarter ? ` · 持仓 ${meta.holdings_quarter}` : ''}
              </Tag>
            </Tooltip>
            {meta.match_counts && (meta.match_counts.similar > 0 || meta.match_counts.no_data > 0) && (
              <Tag color="gold">
                {meta.match_counts.similar > 0 ? `${meta.match_counts.similar} 只按行业相似归类` : ''}
                {meta.match_counts.similar > 0 && meta.match_counts.no_data > 0 ? ' · ' : ''}
                {meta.match_counts.no_data > 0 ? `${meta.match_counts.no_data} 只无持仓数据无法归类` : ''}
              </Tag>
            )}
          </div>
        )}
      </Card>

      {loading && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin tip="计算操作指南中…" />
        </div>
      )}

      {!loading && result && rows === null && (
        <Alert type="info" showIcon message={result.reason ?? '无法生成操作指南'} />
      )}

      {!loading && summary && <SummaryCard summary={summary} />}
      {!loading && result?.transfers && result.transfers.length > 0 && (
        <TransfersTable
          transfers={result.transfers}
          portfolioId={portfolioId}
          onSaved={onSavedTxns}
        />
      )}
      {!loading && rows && rows.length > 0 && <ReconcileTable rows={rows} />}

      {!loading && !result && (
        <Empty description="录入持仓、关联仓位建议后，选好调仓方式点「生成操作指南」" />
      )}
    </div>
  )
}
