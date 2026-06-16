import { Button, Card, Table, Tag, Typography, message } from 'antd'
import { CopyOutlined, ArrowRightOutlined } from '@ant-design/icons'
import type { ReconTransfer } from './types'

const yuan = (v: number) => v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })

const FROM_META: Record<ReconTransfer['from_type'], { label: string; color: string }> = {
  cash: { label: '现金', color: 'blue' },
  outside: { label: '赛道外', color: 'purple' },
  trim: { label: '超配减仓', color: 'gold' },
}

// 换仓配对清单（swap 模式）：每行一笔「卖出来源 → 买入目标」资金流，按金额降序。
export default function TransfersTable({ transfers }: { transfers: ReconTransfer[] }) {
  const copyAll = () => {
    const text = transfers
      .map((t) => {
        const src = t.from_type === 'cash' ? '可投现金' : `${t.from_name}（${t.from_code}）`
        return `卖\t${src}\t→ 买\t${t.to_name}（${t.to_code}）\t${yuan(t.amount)} 元`
      })
      .join('\n')
    if (!text) {
      message.info('没有换仓动作')
      return
    }
    navigator.clipboard.writeText(text).then(
      () => message.success('已复制换仓清单'),
      () => message.error('复制失败'),
    )
  }

  return (
    <Card
      size="small"
      title={`换仓清单（${transfers.length} 笔：卖出来源 → 买入目标）`}
      extra={
        <Button size="small" icon={<CopyOutlined />} onClick={copyAll}>
          复制换仓清单
        </Button>
      }
    >
      <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginTop: -4 }}>
        资金来源优先级：现金 → 赛道外卖出（小额优先）→ 赛道内超配减仓。同一来源/目标可拆成多笔。
      </Typography.Paragraph>
      <Table<ReconTransfer>
        size="small"
        rowKey={(t, i) => `${t.from_code}-${t.to_code}-${i}`}
        dataSource={transfers}
        pagination={false}
        columns={[
          {
            title: '卖出（来源）',
            render: (_, t) => (
              <div style={{ lineHeight: 1.4 }}>
                <Tag color={FROM_META[t.from_type].color}>{FROM_META[t.from_type].label}</Tag>
                {t.from_type === 'cash' ? (
                  <span>可投现金</span>
                ) : (
                  <span>
                    {t.from_name}{' '}
                    <span style={{ fontFamily: 'monospace', color: '#999' }}>{t.from_code}</span>
                  </span>
                )}
              </div>
            ),
          },
          {
            title: '金额',
            dataIndex: 'amount',
            width: 120,
            align: 'right',
            render: (v: number) => <b style={{ color: '#fa541c' }}>{yuan(v)} 元</b>,
          },
          {
            title: '',
            width: 36,
            align: 'center',
            render: () => <ArrowRightOutlined style={{ color: '#bbb' }} />,
          },
          {
            title: '买入（目标）',
            render: (_, t) => (
              <div style={{ lineHeight: 1.4 }}>
                <Tag color={t.to_action === 'open' ? 'volcano' : 'orange'}>
                  {t.to_action === 'open' ? '建仓' : '加仓'}
                </Tag>
                {t.to_name}{' '}
                <span style={{ fontFamily: 'monospace', color: '#999' }}>{t.to_code}</span>
                <div style={{ fontSize: 12, color: '#999' }}>{t.to_cluster}</div>
              </div>
            ),
          },
        ]}
      />
    </Card>
  )
}
