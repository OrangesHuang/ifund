import { Tooltip } from 'antd'

interface Props {
  data: number[]
  width?: number
  height?: number
}

// 涨红跌绿（A 股习惯）：期末≥期初为红，否则为绿
const UP = '#ff4d4f'
const DOWN = '#52c41a'

/** 迷你净值走势图：基于累计净值序列绘制 SVG 折线，悬停展示区间涨跌幅。 */
export default function Sparkline({ data, width = 140, height = 36 }: Props) {
  const series = (data ?? []).filter((v) => Number.isFinite(v))
  if (series.length < 2) return <span className="text-gray-500">-</span>

  const first = series[0]
  const last = series[series.length - 1]
  const min = Math.min(...series)
  const max = Math.max(...series)
  const span = max - min || 1
  const pad = 2
  const innerW = width - pad * 2
  const innerH = height - pad * 2

  const points = series
    .map((v, i) => {
      const x = pad + (innerW * i) / (series.length - 1)
      const y = pad + innerH * (1 - (v - min) / span)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  const up = last >= first
  const color = up ? UP : DOWN
  const pct = first ? ((last - first) / first) * 100 : 0
  const sign = pct >= 0 ? '+' : ''

  return (
    <Tooltip
      title={`区间涨跌 ${sign}${pct.toFixed(2)}%（${series.length} 个交易日）`}
      getPopupContainer={() => document.body}
    >
      <svg width={width} height={height} className="cursor-default block">
        <polyline
          points={points}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
    </Tooltip>
  )
}
