import { Alert, Button, Card, Col, Row, Space, Tag } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import DataTaskCard from './DataTaskCard'
import type { QueryPreset, RunningTask } from '../types'

interface Props {
  activePreset: QueryPreset | null
  // 当前筛选是否含高级筛选条件（拉取范围会受限于已有详情的基金）
  hasConditions: boolean
  detailTask: RunningTask | null
  holdingsTask: RunningTask | null
  navTask: RunningTask | null
  onStart: (module: string) => void
  onTerminate: (module: string, taskId: number) => void
  onSync: () => void
  syncing: boolean
}

/** 数据拉取区：统一一组拉取入口（详情/持仓/净值），范围跟随当前筛选/选中预设。 */
export default function DataFetchPanel({
  activePreset,
  hasConditions,
  detailTask,
  holdingsTask,
  navTask,
  onStart,
  onTerminate,
  onSync,
  syncing,
}: Props) {
  const scope = activePreset ? `按预设「${activePreset.name}」` : '按当前筛选条件'

  return (
    <Card
      size="small"
      title="数据拉取"
      extra={
        <Button size="small" icon={<ReloadOutlined />} onClick={onSync} loading={syncing}>
          同步基金名单
        </Button>
      }
    >
      <Space direction="vertical" className="w-full" style={{ width: '100%' }} size="middle">
        <Space size="small" wrap>
          <Tag color={activePreset ? 'blue' : 'default'} style={{ marginInlineEnd: 0 }}>
            拉取范围：{scope}
          </Tag>
          <span className="text-xs text-gray-400">
            下方三项均按此范围拉取；要按某预设拉取，请先在上方选中该预设。
          </span>
        </Space>

        {hasConditions && (
          <Alert
            type="warning"
            showIcon
            message="当前含高级筛选条件，拉取只会覆盖已有详情的基金，无法为新基金补详情/持仓/净值。如需覆盖新基金，请改用基础条件（类型/关键字）。"
          />
        )}

        <Row gutter={16}>
          <Col xs={24} md={8}>
            <DataTaskCard
              title="详情拉取"
              module="fund_detail"
              task={detailTask}
              onStart={onStart}
              onTerminate={onTerminate}
            />
          </Col>
          <Col xs={24} md={8}>
            <DataTaskCard
              title="持仓拉取"
              module="fund_holdings"
              task={holdingsTask}
              onStart={onStart}
              onTerminate={onTerminate}
            />
          </Col>
          <Col xs={24} md={8}>
            <DataTaskCard
              title="净值拉取"
              module="fund_nav"
              task={navTask}
              onStart={onStart}
              onTerminate={onTerminate}
            />
          </Col>
        </Row>
      </Space>
    </Card>
  )
}
