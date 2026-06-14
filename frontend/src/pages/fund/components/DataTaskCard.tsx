import { Button, Card, Progress, Space, Tag, Tooltip } from 'antd'
import type { RunningTask } from '../types'

interface Props {
  title: string
  module: string
  task: RunningTask | null
  onStart: (module: string) => void
  onTerminate: (module: string, taskId: number) => void
}

export default function DataTaskCard({ title, module, task, onStart, onTerminate }: Props) {
  const running = task && task.status === 'running'
  const percent =
    task && task.target_count > 0
      ? Math.round((task.current_count / task.target_count) * 100)
      : 0

  return (
    <Card size="small" title={title} className="mb-2">
      <Space direction="vertical" className="w-full" style={{ width: '100%' }}>
        {task ? (
          <>
            <Progress percent={percent} status={running ? 'active' : 'normal'} />
            <Space size="small" wrap>
              <Tag color={running ? 'processing' : 'default'}>{task.status}</Tag>
              <span>
                {task.current_count}/{task.target_count}
              </span>
              <Tag color="green">成功 {task.success_count}</Tag>
              <Tag color="red">失败 {task.fail_count}</Tag>
              {task.executor_ip && <Tag>{task.executor_ip}</Tag>}
            </Space>
          </>
        ) : (
          <span className="text-gray-400">无进行中的任务</span>
        )}
        <Space>
          <Tooltip title="按当前查询区的筛选条件拉取（预设拉取请用预设卡片）">
            <Button type="primary" size="small" onClick={() => onStart(module)} disabled={!!running}>
              按当前条件拉取
            </Button>
          </Tooltip>
          {running && (
            <Button danger size="small" onClick={() => onTerminate(module, task!.id)}>
              终止
            </Button>
          )}
        </Space>
      </Space>
    </Card>
  )
}
