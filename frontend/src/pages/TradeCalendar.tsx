import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Card, Empty, InputNumber, Space, Spin, Tooltip, message } from 'antd'
import request from '../api/request'

interface LatestTask {
  id?: number
  status?: string
  target_count?: number
  updated_at?: string
}

const WEEK_LABELS = ['日', '一', '二', '三', '四', '五', '六']
const MONTH_LABELS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

const pad = (n: number) => String(n).padStart(2, '0')
const toKey = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`

/** 生成某月的格子：前置 null 占位对齐星期，再排 1..daysInMonth。 */
function buildMonthCells(year: number, month: number): (number | null)[] {
  const startWeekday = new Date(year, month, 1).getDay()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const cells: (number | null)[] = Array(startWeekday).fill(null)
  for (let d = 1; d <= daysInMonth; d += 1) cells.push(d)
  return cells
}

interface MiniMonthProps {
  year: number
  month: number
  tradeSet: Set<string>
  todayKey: string
}

function MiniMonth({ year, month, tradeSet, todayKey }: MiniMonthProps) {
  const cells = buildMonthCells(year, month)
  const tradeCount = cells.filter((d) => d !== null && tradeSet.has(toKey(year, month, d))).length

  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="font-medium">{MONTH_LABELS[month]}</span>
        <span className="text-xs text-gray-500">{tradeCount} 天</span>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-[11px]">
        {WEEK_LABELS.map((w, i) => (
          <div key={w} className={i === 0 || i === 6 ? 'text-gray-600' : 'text-gray-500'}>
            {w}
          </div>
        ))}
        {cells.map((d, idx) => {
          if (d === null) return <div key={`e-${idx}`} />
          const key = toKey(year, month, d)
          const isTrade = tradeSet.has(key)
          const isToday = key === todayKey
          const base = 'flex h-6 items-center justify-center rounded'
          const tone = isTrade
            ? 'bg-green-600/90 text-white font-medium'
            : 'text-gray-600'
          const ring = isToday ? ' ring-1 ring-amber-400' : ''
          const cell = (
            <div key={d} className={`${base} ${tone}${ring}`}>
              {d}
            </div>
          )
          return isTrade ? (
            <Tooltip key={d} title={`${key} · 交易日`}>
              {cell}
            </Tooltip>
          ) : (
            cell
          )
        })}
      </div>
    </div>
  )
}

export default function TradeCalendar() {
  const [year, setYear] = useState<number>(new Date().getFullYear())
  const [dates, setDates] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [latest, setLatest] = useState<LatestTask>({})

  const tradeSet = useMemo(() => new Set(dates), [dates])
  const todayKey = useMemo(() => {
    const now = new Date()
    return toKey(now.getFullYear(), now.getMonth(), now.getDate())
  }, [])

  const loadDates = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await request.get('/trade_calendar/dates', {
        params: { year: String(year) },
      })
      setDates(data.dates ?? [])
    } catch {
      message.error('加载交易日失败')
    } finally {
      setLoading(false)
    }
  }, [year])

  const loadLatest = useCallback(async () => {
    try {
      const { data } = await request.get('/trade_calendar/task/latest')
      setLatest(data ?? {})
    } catch {
      /* 忽略 */
    }
  }, [])

  useEffect(() => {
    loadDates()
  }, [loadDates])

  useEffect(() => {
    loadLatest()
  }, [loadLatest])

  const sync = async () => {
    setSyncing(true)
    try {
      const { data } = await request.post('/trade_calendar/sync')
      message.success(`同步完成，共 ${data.count} 个交易日`)
      await loadDates()
      await loadLatest()
    } catch {
      message.error('同步失败')
    } finally {
      setSyncing(false)
    }
  }

  return (
    <Card
      title={
        <Space>
          <span>交易日历</span>
          <span className="text-sm font-normal text-gray-500">
            {year} 年 · {dates.length} 个交易日
          </span>
        </Space>
      }
      extra={
        <Space>
          <InputNumber
            value={year}
            min={2000}
            max={2100}
            onChange={(v) => v && setYear(v)}
            style={{ width: 100 }}
          />
          <Button onClick={loadDates}>查询</Button>
          <Button type="primary" onClick={sync} loading={syncing}>
            同步交易日历
          </Button>
        </Space>
      }
    >
      <div className="mb-4 flex items-center justify-between text-gray-400">
        <span>
          最近同步：{latest.status ?? '无'}（{latest.target_count ?? 0} 个日期）
        </span>
        <Space size={16} className="text-xs">
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded bg-green-600/90" /> 交易日
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded ring-1 ring-amber-400" /> 今天
          </span>
        </Space>
      </div>

      <Spin spinning={loading}>
        {dates.length === 0 && !loading ? (
          <Empty description={`${year} 年暂无交易日数据，请先同步`} />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {MONTH_LABELS.map((_, m) => (
              <MiniMonth key={m} year={year} month={m} tradeSet={tradeSet} todayKey={todayKey} />
            ))}
          </div>
        )}
      </Spin>
    </Card>
  )
}
