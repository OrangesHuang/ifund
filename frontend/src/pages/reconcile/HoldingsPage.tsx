import { Alert } from 'antd'
import HoldingsEditor from './HoldingsEditor'

// 实盘持仓：独立顶层板块（不隶属组合分析）。录入/维护你的真实持仓，
// 供「组合分析 → 操作指南」按赛道对齐推导加/减/建/清。
export default function HoldingsPage() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Alert
        type="info"
        showIcon
        message="实盘持仓：录入并维护你的真实持仓（基金 + 当前市值，可含持有收益）。这里是独立的台账，持仓持久化、跨会话保留；盈亏仅展示不参与决策。录好后到「组合分析 → 操作指南」即可把仓位建议落到这些持仓上。"
      />
      <HoldingsEditor />
    </div>
  )
}
