import { Button, Card, Space, Table, Tag, Tooltip, Typography, message } from 'antd'
import { CopyOutlined } from '@ant-design/icons'
import type { ReconAction, ReconMatch, ReconRow, ReconUserFund } from './types'

const BUY = '#fa541c'   // 建仓/加仓（补）
const SELL = '#8c8c8c'  // 减仓/清仓（减）

const ACTION_META: Record<ReconAction, { label: string; color: string }> = {
  open: { label: '建仓', color: 'volcano' },
  add: { label: '加仓', color: 'orange' },
  trim: { label: '减仓', color: 'default' },
  exit: { label: '清仓', color: 'default' },
  hold: { label: '不动', color: 'default' },
  keep: { label: '保留', color: 'blue' },
}

// 无需执行的动作：复制时跳过
const PASSIVE: ReconAction[] = ['hold', 'keep']

const MATCH_LABEL: Record<Exclude<ReconMatch, null>, string> = {
  exact: '代码命中',
  name: '名称命中',
  similar: '行业相似',
  outside: '赛道外',
  no_data: '无持仓数据',
}

const yuan = (v: number) => Math.abs(v).toLocaleString('zh-CN', { maximumFractionDigits: 0 })

const MATCH_COLOR = (m: Exclude<ReconMatch, null>) =>
  m === 'exact' || m === 'name' ? 'green' : m === 'similar' ? 'gold' : 'default'

// 展开行：该赛道归类到的全部持仓明细（当前市值=这些之和），解释聚合口径。
function ClusterFunds({ row }: { row: ReconRow }) {
  const funds = row.user_funds
  return (
    <div style={{ padding: '4px 0 4px 24px' }}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        本赛道归类到 {funds.length} 只持仓，合计 {yuan(row.actual)} 元（即左侧「当前市值」）：
      </Typography.Text>
      <Table<ReconUserFund>
        size="small"
        style={{ marginTop: 6 }}
        rowKey={(f) => f.code}
        dataSource={funds}
        pagination={false}
        columns={[
          {
            title: '基金',
            render: (_, f) => (
              <span>
                {f.name}{' '}
                <span style={{ fontFamily: 'monospace', color: '#999' }}>{f.code}</span>
              </span>
            ),
          },
          {
            title: '市值',
            dataIndex: 'market_value',
            width: 120,
            align: 'right',
            render: (v: number) => `${yuan(v)} 元`,
          },
          {
            title: '占本赛道',
            width: 90,
            align: 'right',
            render: (_, f) =>
              row.actual > 0 ? `${((f.market_value / row.actual) * 100).toFixed(0)}%` : '—',
          },
          {
            title: '盈亏',
            dataIndex: 'pnl',
            width: 110,
            align: 'right',
            render: (v: number | null | undefined) => {
              if (v === null || v === undefined) return <Typography.Text type="secondary">—</Typography.Text>
              const color = v > 0 ? '#f5222d' : v < 0 ? '#52c41a' : undefined
              return <span style={{ color }}>{v > 0 ? '+' : ''}{yuan(v)}</span>
            },
          },
          {
            title: '匹配',
            dataIndex: 'match',
            width: 100,
            align: 'center',
            render: (m: Exclude<ReconMatch, null>, f) => {
              const tag = <Tag color={MATCH_COLOR(m)}>{MATCH_LABEL[m]}</Tag>
              return m === 'similar'
                ? <Tooltip title={`行业相似度 ${f.sim ?? '—'}（勉强归类，请核对）`}>{tag}</Tooltip>
                : tag
            },
          },
        ]}
      />
    </div>
  )
}

// 对账结果表：每行一个目标赛道（或一只赛道外基金），给出加/减/建/清的金额与操作标的。
export default function ReconcileTable({ rows }: { rows: ReconRow[] }) {
  // 复制：赛道\t动作\t金额\t操作基金，方便粘贴到 Excel 执行
  const copyAll = () => {
    const text = rows
      .filter((r) => !PASSIVE.includes(r.action))
      .map((r) => {
        const verb = r.amount >= 0 ? '补' : '减'
        return `${r.cluster_name}\t${ACTION_META[r.action].label}\t${verb}${yuan(r.amount)}\t${r.target_fund.name}（${r.target_fund.code}）`
      })
      .join('\n')
    if (!text) {
      message.info('没有需要执行的动作（全部保持不动）')
      return
    }
    navigator.clipboard.writeText(text).then(
      () => message.success('已复制可执行动作'),
      () => message.error('复制失败'),
    )
  }

  return (
    <Card
      title="对账建议"
      size="small"
      extra={
        <Button size="small" icon={<CopyOutlined />} onClick={copyAll}>
          复制可执行动作
        </Button>
      }
    >
      <Table<ReconRow>
        size="small"
        rowKey={(r) => `${r.cluster_id ?? 'out'}-${r.target_fund.code}`}
        dataSource={rows}
        pagination={false}
        expandable={{
          rowExpandable: (r) => r.user_funds.length > 0,
          expandedRowRender: (r) => <ClusterFunds row={r} />,
        }}
        columns={[
          {
            title: '赛道',
            dataIndex: 'cluster_name',
            render: (v: string, r) =>
              r.cluster_id === null ? <Tag color="default">赛道外</Tag> : <span>{v}</span>,
          },
          {
            title: (
              <Tooltip title="按赛道（聚类簇）汇总：归到同一赛道的多只持仓市值之和。点行首 ▸ 展开看构成。">
                <span>当前市值 ⓘ</span>
              </Tooltip>
            ),
            dataIndex: 'actual',
            width: 130,
            align: 'right',
            render: (v: number, r) => (
              <Space size={4} direction="vertical" style={{ lineHeight: 1.2 }}>
                <span>{yuan(v)} 元</span>
                {r.user_funds.length > 1 && (
                  <span style={{ fontSize: 11, color: '#999' }}>{r.user_funds.length} 只合计</span>
                )}
              </Space>
            ),
          },
          {
            title: '目标市值',
            dataIndex: 'target',
            width: 120,
            align: 'right',
            render: (v: number, r) =>
              r.cluster_id === null ? <Typography.Text type="secondary">0</Typography.Text> : `${yuan(v)} 元`,
          },
          {
            title: '目标占比',
            dataIndex: 'weight',
            width: 90,
            align: 'right',
            render: (v: number, r) =>
              r.cluster_id === null ? '—' : `${(v * 100).toFixed(1)}%`,
          },
          {
            title: (
              <Tooltip title="该赛道当前市值占总持仓市值（含赛道外）的比例，与目标占比对照看偏离。">
                <span>实际占比 ⓘ</span>
              </Tooltip>
            ),
            dataIndex: 'actual_ratio',
            width: 90,
            align: 'right',
            render: (v: number | null | undefined) =>
              v === null || v === undefined ? '—' : `${(v * 100).toFixed(1)}%`,
          },
          {
            title: '盈亏',
            dataIndex: 'pnl',
            width: 110,
            align: 'right',
            render: (v: number | null | undefined) => {
              if (v === null || v === undefined) return <Typography.Text type="secondary">—</Typography.Text>
              const color = v > 0 ? '#f5222d' : v < 0 ? '#52c41a' : undefined
              return (
                <span style={{ color }}>
                  {v > 0 ? '+' : ''}
                  {yuan(v)}
                </span>
              )
            },
          },
          {
            title: '动作',
            dataIndex: 'action',
            width: 80,
            align: 'center',
            render: (a: ReconAction) => <Tag color={ACTION_META[a].color}>{ACTION_META[a].label}</Tag>,
          },
          {
            title: '建议金额',
            dataIndex: 'amount',
            width: 130,
            align: 'right',
            render: (v: number, r) => {
              if (r.action === 'hold' || r.action === 'keep') return <Typography.Text type="secondary">—</Typography.Text>
              const buy = v >= 0
              return (
                <b style={{ color: buy ? BUY : SELL }}>
                  {buy ? '补 ' : '减 '}
                  {yuan(v)} 元
                </b>
              )
            },
          },
          {
            title: '操作基金',
            dataIndex: 'target_fund',
            render: (_, r) => (
              <Space size={4} direction="vertical" style={{ lineHeight: 1.3 }}>
                <span>
                  {r.action === 'open' ? '买入代表基金：' : ''}
                  {r.target_fund.name}{' '}
                  <span style={{ fontFamily: 'monospace', color: '#999' }}>{r.target_fund.code}</span>
                </span>
                {r.note && <span style={{ fontSize: 12, color: '#999' }}>{r.note}</span>}
              </Space>
            ),
          },
          {
            title: '匹配',
            dataIndex: 'match',
            width: 100,
            align: 'center',
            render: (m: ReconMatch, r) => {
              if (!m) return <Typography.Text type="secondary">—</Typography.Text>
              const tip =
                m === 'similar' ? `行业相似度 ${r.sim ?? '—'}（勉强归类，请核对）` :
                m === 'no_data' ? '库中无该基金持仓数据，无法准确归类' :
                m === 'outside' ? `与各赛道最高相似度 ${r.sim ?? '—'}` : ''
              const color = m === 'exact' || m === 'name' ? 'green' : m === 'similar' ? 'gold' : 'default'
              const label = MATCH_LABEL[m]
              return tip ? (
                <Tooltip title={tip}>
                  <Tag color={color}>{label}</Tag>
                </Tooltip>
              ) : (
                <Tag color={color}>{label}</Tag>
              )
            },
          },
        ]}
      />
    </Card>
  )
}
