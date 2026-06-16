import { useEffect, useMemo, useState } from 'react'
import { Empty, Modal, Segmented, Spin, Statistic, theme } from 'antd'
import dayjs from 'dayjs'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import request from '../../../api/request'

interface NavPoint {
  date: string
  nav: number
}

interface Props {
  code: string | null
  name?: string
  open: boolean
  onClose: () => void
}

const RANGES = [
  { label: '近3月', value: 3 },
  { label: '近6月', value: 6 },
  { label: '近1年', value: 12 },
  { label: '近3年', value: 36 },
  { label: '全部', value: 0 },
]

const UP = '#f5222d'   // 涨红
const DOWN = '#52c41a' // 跌绿

/** 交互式净值走势：累计净值折线 + 十字准星（横竖虚线），hover 看每日日期/净值/较首日涨跌。 */
export default function NavTrendModal({ code, name, open, onClose }: Props) {
  const { token } = theme.useToken()
  const [data, setData] = useState<NavPoint[]>([])
  const [loading, setLoading] = useState(false)
  const [range, setRange] = useState(12)
  // 当前鼠标命中的点（驱动十字准星 + 顶部数值）
  const [active, setActive] = useState<NavPoint | null>(null)

  useEffect(() => {
    if (!open || !code) return
    setLoading(true)
    setActive(null)
    request
      .get<{ items: NavPoint[] }>(`/fund/${code}/nav`, { params: { limit: 800 } })
      .then(({ data: d }) => setData(d.items ?? []))
      .catch(() => setData([]))
      .finally(() => setLoading(false))
  }, [open, code])

  // 按区间切片（不足两点则回退全量）
  const sliced = useMemo(() => {
    const series = data.filter((p) => Number.isFinite(p.nav))
    if (!range || series.length === 0) return series
    const cutoff = dayjs(series[series.length - 1].date).subtract(range, 'month')
    const win = series.filter((p) => !dayjs(p.date).isBefore(cutoff))
    return win.length >= 2 ? win : series
  }, [data, range])

  const first = sliced[0]?.nav ?? 0
  const last = sliced[sliced.length - 1]?.nav ?? 0
  const pct = first ? ((last - first) / first) * 100 : 0
  const lineColor = last >= first ? UP : DOWN

  // 顶部展示：默认末点，hover 时跟随准星
  const shown = active ?? sliced[sliced.length - 1] ?? null
  const shownPct = shown && first ? ((shown.nav - first) / first) * 100 : 0

  const fmtTick = (d: string) => `${d.slice(2, 4)}/${d.slice(5, 7)}`
  const tickGap = Math.max(1, Math.floor(sliced.length / 8))
  const axisTick = { fontSize: 11, fill: token.colorTextTertiary }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={720}
      title={`${name ?? ''} 净值走势`}
      destroyOnClose
    >
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12, marginBottom: 8 }}>
        <div style={{ display: 'flex', gap: 24 }}>
          <Statistic
            title={shown ? `净值 · ${shown.date}` : '净值'}
            value={shown ? shown.nav : 0}
            precision={4}
            valueStyle={{ fontSize: 22 }}
          />
          <Statistic
            title="较区间首日"
            value={shownPct}
            precision={2}
            suffix="%"
            prefix={shownPct >= 0 ? '+' : ''}
            valueStyle={{ fontSize: 22, color: shownPct >= 0 ? UP : DOWN }}
          />
        </div>
        <Segmented size="small" options={RANGES} value={range} onChange={(v) => setRange(v as number)} />
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 80 }}>
          <Spin tip="加载净值中…" />
        </div>
      ) : sliced.length < 2 ? (
        <Empty description="暂无净值数据（可能尚未采集）" style={{ padding: 60 }} />
      ) : (
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart
            data={sliced}
            margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
            onMouseMove={(s) => {
              const p = s?.activePayload?.[0]?.payload as NavPoint | undefined
              if (p) setActive(p)
            }}
            onMouseLeave={() => setActive(null)}
          >
            <defs>
              <linearGradient id="navFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={lineColor} stopOpacity={0.22} />
                <stop offset="100%" stopColor={lineColor} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={token.colorBorderSecondary} />
            <XAxis dataKey="date" tickFormatter={fmtTick} interval={tickGap} tick={axisTick} minTickGap={16} />
            <YAxis domain={['auto', 'auto']} tickFormatter={(v) => v.toFixed(2)} width={52} tick={axisTick} />
            <Tooltip
              cursor={{ stroke: token.colorTextTertiary, strokeDasharray: '3 3' }}
              content={({ active: a, payload }) => {
                if (!a || !payload?.length) return null
                const p = payload[0].payload as NavPoint
                const pp = first ? ((p.nav - first) / first) * 100 : 0
                return (
                  <div
                    style={{
                      background: token.colorBgElevated,
                      border: `1px solid ${token.colorBorderSecondary}`,
                      borderRadius: token.borderRadius,
                      padding: '6px 10px',
                      fontSize: 12,
                    }}
                  >
                    <div style={{ color: token.colorTextSecondary }}>{p.date}</div>
                    <div style={{ color: token.colorText }}>净值 {p.nav.toFixed(4)}</div>
                    <div style={{ color: pp >= 0 ? UP : DOWN }}>
                      较首日 {pp >= 0 ? '+' : ''}{pp.toFixed(2)}%
                    </div>
                  </div>
                )
              }}
            />
            {/* 十字准星：竖线由 Tooltip cursor 提供，横线用 ReferenceLine 跟随当前点 */}
            {active && (
              <ReferenceLine y={active.nav} stroke={token.colorTextTertiary} strokeDasharray="3 3" ifOverflow="extendDomain" />
            )}
            <Area type="monotone" dataKey="nav" stroke={lineColor} strokeWidth={1.6} fill="url(#navFill)" isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </Modal>
  )
}
