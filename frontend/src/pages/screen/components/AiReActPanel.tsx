import { useEffect, useRef, useState } from 'react'
import { Button, Tag, Tooltip, Typography } from 'antd'
import {
  CloseOutlined,
  ThunderboltOutlined,
  UpOutlined,
} from '@ant-design/icons'

const { Text } = Typography

/** 一轮 ReAct 的简称：思考 → 行动(工具调用) → 观察。 */
export interface ReActStep {
  round: number
  thought: string
  action: string
  args: Record<string, unknown>
  observation: string
}

interface Props {
  fundCode: string
  fundName?: string
  steps: ReActStep[]
  status: 'running' | 'done' | 'error'
  elapsed: number
  error?: string
  onClose: () => void
}

const DIM_LABEL: Record<string, string> = {
  profile: '档案/业绩',
  attribution: '经理归因',
  holdings: '持仓漂移',
  nav: '净值表现',
  caveats: '数据局限',
}

export default function AiReActPanel({
  fundCode,
  fundName,
  steps,
  status,
  elapsed,
  error,
  onClose,
}: Props) {
  const [minimized, setMinimized] = useState(false)
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  const dragRef = useRef<{ dx: number; dy: number; dragging: boolean }>({
    dx: 0,
    dy: 0,
    dragging: false,
  })
  const listRef = useRef<HTMLDivElement>(null)

  // 新步骤到达时自动滚到底部
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [steps.length, minimized])

  const onHeaderDown = (e: React.MouseEvent) => {
    dragRef.current.dragging = true
    dragRef.current.dx = e.clientX - (pos?.x ?? 0)
    dragRef.current.dy = e.clientY - (pos?.y ?? 0)
    const move = (ev: MouseEvent) => {
      if (!dragRef.current.dragging) return
      setPos({ x: ev.clientX - dragRef.current.dx, y: ev.clientY - dragRef.current.dy })
    }
    const up = () => {
      dragRef.current.dragging = false
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
    }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }

  const statusColor = status === 'running' ? 'processing' : status === 'done' ? 'green' : 'red'
  const statusLabel = status === 'running' ? '分析中' : status === 'done' ? '完成' : '出错'

  const header = (
    <div
      onMouseDown={onHeaderDown}
      style={{
        cursor: 'move',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 12px',
        background: 'linear-gradient(135deg,#1f3a5f,#2d5a8e)',
        color: '#fff',
        borderRadius: '8px 8px 0 0',
      }}
    >
      <ThunderboltOutlined />
      <span style={{ fontWeight: 600 }}>
        AI ReAct 分析 · {fundName ?? fundCode}
      </span>
      <Tag style={{ marginLeft: 'auto', marginRight: 0 }} color={statusColor}>
        {statusLabel}
      </Tag>
      <Tooltip title={minimized ? '展开' : '收起'}>
        <Button
          type="text"
          size="small"
          style={{ color: '#fff' }}
          icon={<UpOutlined rotate={minimized ? 180 : 0} />}
          onClick={() => setMinimized((m) => !m)}
        />
      </Tooltip>
      <Tooltip title="关闭">
        <Button type="text" size="small" style={{ color: '#fff' }} icon={<CloseOutlined />} onClick={onClose} />
      </Tooltip>
    </div>
  )

  return (
    <div
      style={{
        position: 'fixed',
        top: pos?.y ?? 88,
        left: pos?.x ?? undefined,
        right: pos ? undefined : 24,
        width: 420,
        maxWidth: 'calc(100vw - 48px)',
        zIndex: 2000,
        boxShadow: '0 6px 24px rgba(0,0,0,0.25)',
        borderRadius: 8,
        background: '#fff',
      }}
    >
      {header}
      {!minimized && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px', borderBottom: '1px solid #f0f0f0' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            已进行 {elapsed}s · {steps.length} 轮
          </Text>
          <span style={{ flex: 1 }} />
          {status === 'running' && (
            <Tag color="processing">Reason→Act→Observe</Tag>
          )}
        </div>
      )}
      {!minimized && (
        <div
          ref={listRef}
          style={{ maxHeight: 420, overflowY: 'auto', padding: 12, background: '#fafafa' }}
        >
          {steps.length === 0 && status === 'running' && (
            <div style={{ color: '#999', textAlign: 'center', padding: '24px 0' }}>
              正在启动 DeepSeek ReAct 分析…
            </div>
          )}
          {steps.map((s) => (
            <div key={s.round} style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Tag color="blue">第 {s.round} 轮</Tag>
                <Text type="secondary" style={{ fontSize: 12 }}>呼出 {s.action}</Text>
                <Tooltip title={JSON.stringify(s.args)}>
                  <Text style={{ fontSize: 12 }}>
                    {DIM_LABEL[String(s.args.dimension)] ?? String(s.args.dimension)}
                  </Text>
                </Tooltip>
              </div>
              {s.thought && (
                <div style={{ margin: '6px 0 4px', fontSize: 12, lineHeight: 1.5, color: '#333' }}>
                  <Text type="secondary">思考：</Text> {s.thought}
                </div>
              )}
              {s.observation && (
                <div style={{ fontSize: 12, lineHeight: 1.5, color: '#555', background: '#fff', borderRadius: 6, padding: '6px 8px', border: '1px solid #eaeaea' }}>
                  <Text type="secondary">观察：</Text> {s.observation}
                </div>
              )}
            </div>
          ))}
          {status === 'error' && (
            <div style={{ color: '#ff4d4f', fontSize: 12 }}>错误：{error}</div>
          )}
        </div>
      )}
    </div>
  )
}
