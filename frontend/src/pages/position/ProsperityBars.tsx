import { Tooltip } from 'antd'
import type { ProsperityBreakdown } from './types'

const FACTORS: { key: keyof ProsperityBreakdown; label: string; hint: string }[] = [
  { key: 'momentum', label: '动量', hint: '1m/3m/6m 收益加权（跨簇 min-max 归一）' },
  { key: 'risk_adj', label: '风险调整', hint: '近 60 日 Sharpe-like（跨簇 rank 归一）' },
  { key: 'breadth', label: '广度', hint: '净值站上 MA20/MA60 的程度 + 乖离深度' },
  { key: 'consistency', label: '一致性', hint: '最近连续正收益月数 / 总月数' },
]

// 动量强度四因子迷你条（0–100），颜色随分值由灰转暖
function barColor(v: number): string {
  if (v >= 66) return '#fa541c'
  if (v >= 40) return '#1677ff'
  return '#8c8c8c'
}

export default function ProsperityBars({ pros }: { pros: ProsperityBreakdown }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 200 }}>
      {FACTORS.map((f) => {
        const v = pros[f.key]
        return (
          <div key={f.key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 52, fontSize: 11, color: '#8c8c8c', textAlign: 'right' }}>
              {f.label}
            </span>
            <div style={{ flex: 1, background: 'rgba(140,140,140,0.18)', borderRadius: 3, height: 10 }}>
              <Tooltip title={`${f.hint}：${v.toFixed(0)}`}>
                <div
                  style={{
                    width: `${Math.max(0, Math.min(100, v))}%`,
                    background: barColor(v),
                    height: '100%',
                    borderRadius: 3,
                  }}
                />
              </Tooltip>
            </div>
            <span style={{ width: 28, fontSize: 11, textAlign: 'right' }}>{v.toFixed(0)}</span>
          </div>
        )
      })}
    </div>
  )
}
