import { forwardRef, useCallback, useEffect, useImperativeHandle, useState } from 'react'
import { Alert, Button, Card, Empty, InputNumber, Segmented, Space, Spin, Tag, Tooltip, message } from 'antd'
import { ClockCircleOutlined, ReconciliationOutlined } from '@ant-design/icons'
import request from '../../api/request'
import HoldingsEditor from './HoldingsEditor'
import SummaryCard from './SummaryCard'
import ReconcileTable from './ReconcileTable'
import type { ReconResult } from './types'

// 实盘对账视图：导入持仓 + 可投现金，复用③仓位的目标权重，按赛道对齐算加/减/建/清金额。
// presetId 由工作台下传；与仓位建议共用同一预设镜像、同一 cap（均衡强度）。
const ReconcileView = forwardRef<
  { run: () => Promise<void> },
  { presetId: number | null }
>(function ReconcileView({ presetId }, ref) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ReconResult | null>(null)
  const [cash, setCash] = useState(0)
  // 缓冲带：偏离在总资产的此比例内则保持不动（抗短期噪音、保调仓连贯）。默认标准 3%。
  const [band, setBand] = useState(0.03)
  // 均衡强度 cap：与仓位建议一致，默认「紧」0.14。
  const [cap, setCap] = useState(0.14)
  // 模式：子仓位（默认，赛道外保留不动）/ 整盘（赛道外清仓、按全账户迁移）。
  const [mode, setMode] = useState<'sleeve' | 'whole'>('sleeve')

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
      const { data } = await request.post<ReconResult>('/reconcile/run', {
        preset_id: presetId,
        cash,
        band,
        cap,
        mode,
      })
      setResult(data)
    } catch {
      message.error('对账失败')
    } finally {
      setLoading(false)
    }
  }, [presetId, cash, band, cap, mode])

  // 工作台预设变化时不自动对账（持仓/现金是用户输入，需手动触发）；仅暴露给父组件备用。
  useImperativeHandle(ref, () => ({ run }), [run])

  const rows = result?.rows
  const summary = result?.summary
  const meta = result?.meta

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Alert
        type="info"
        showIcon
        message="实盘对账：把③仓位建议的目标权重落到你的真实持仓上。按「赛道（聚类簇）」对齐，不强制你换成系统选的代表基金——只看每个赛道总仓位够不够。默认「子仓位」模式：把所选预设当成账户里的一个子仓位，只调能对上赛道的基金，赛道外的保留不动（不建议清仓）。先在下方导入持仓（可含持有收益，盈亏仅展示不参与决策）、填可投现金，再点「开始对账」。仅供参考、非投资建议。"
      />

      <HoldingsEditor onChanged={() => setResult(null)} />

      <Card size="small" title="对账参数">
        <Space wrap size="large">
          <span>
            可投现金：
            <InputNumber
              value={cash}
              min={0}
              precision={2}
              style={{ width: 160, marginLeft: 8 }}
              formatter={(x) => `${x}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
              parser={(x) => Number((x || '').replace(/,/g, ''))}
              addonAfter="元"
            />
          </span>
          <Tooltip title="子仓位：把预设当成账户里的一个子仓位，只调能对上赛道的基金，赛道外保留不动、目标按「匹配市值+现金」分配。整盘：把整个账户向目标迁移，赛道外建议清仓、目标按「全账户+现金」分配。">
            <span>
              模式：
              <Segmented
                style={{ marginLeft: 8 }}
                value={mode}
                onChange={(v) => setMode(v as 'sleeve' | 'whole')}
                options={[
                  { label: '子仓位', value: 'sleeve' },
                  { label: '整盘', value: 'whole' },
                ]}
              />
            </span>
          </Tooltip>
          <Tooltip title="缓冲带：目标与实际的偏离在「基准资产 × 此比例」以内就保持不动，抑制短期噪音、保持调仓连贯。宽松=更少折腾，灵敏=更贴目标。">
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
          <Tooltip title="均衡强度（单一行业穿透占比上限），与仓位建议一致。紧=更分散。改这里会用新 cap 重算目标权重。">
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
            开始对账
          </Button>
        </Space>
        {meta && (meta.nav_as_of || meta.holdings_quarter) && (
          <div style={{ marginTop: 10 }}>
            <Tooltip title="目标权重基于库内已采集数据现场计算，非实时行情。要反映最新市况请先跑数据采集。">
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
          <Spin tip="对账计算中…" />
        </div>
      )}

      {!loading && result && rows === null && (
        <Alert type="info" showIcon message={result.reason ?? '无法对账'} />
      )}

      {!loading && summary && <SummaryCard summary={summary} />}
      {!loading && rows && rows.length > 0 && <ReconcileTable rows={rows} />}

      {!loading && !result && <Empty description="导入持仓并填写可投现金后，点「开始对账」" />}
    </div>
  )
})

export default ReconcileView
