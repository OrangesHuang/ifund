import { useState } from 'react'
import { Button, Card, Dropdown, Empty, Input, Popconfirm, Space, Tag, Tooltip } from 'antd'
import { DeleteOutlined, DownOutlined, SaveOutlined } from '@ant-design/icons'
import { FETCH_MODULES, summarizeFilters } from '../constants'
import type { QueryPreset } from '../types'

interface Props {
  presets: QueryPreset[]
  onSave: (name: string) => void
  onApply: (preset: QueryPreset) => void
  onOverwrite: (id: number) => void
  onDelete: (id: number) => void
  onFetch: (preset: QueryPreset, module: string) => void
}

export default function PresetPanel({
  presets,
  onSave,
  onApply,
  onOverwrite,
  onDelete,
  onFetch,
}: Props) {
  const [name, setName] = useState('')

  const handleSave = () => {
    if (!name.trim()) return
    onSave(name.trim())
    setName('')
  }

  return (
    <Card
      size="small"
      title="条件预设"
      extra={
        <Space.Compact>
          <Input
            size="small"
            placeholder="把当前筛选存为预设"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onPressEnter={handleSave}
            style={{ width: 180 }}
          />
          <Button size="small" type="primary" icon={<SaveOutlined />} onClick={handleSave}>
            保存
          </Button>
        </Space.Compact>
      }
    >
      {presets.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无预设，设置好筛选条件后点上方「保存」"
        />
      ) : (
        <div
          className="grid gap-3"
          style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(248px, 1fr))' }}
        >
          {presets.map((p) => {
            const summary = summarizeFilters(p.filters ?? {})
            return (
              <div
                key={p.id}
                className="flex h-full min-w-0 flex-col overflow-hidden rounded-lg border border-white/10 bg-white/[0.02] p-3"
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="min-w-0 flex-1 truncate font-medium" title={p.name}>
                    {p.name}
                  </span>
                  <Popconfirm title="删除该预设？" onConfirm={() => onDelete(p.id)}>
                    <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </div>

                <div className="mb-3 min-h-[44px] flex-1">
                  {summary.length ? (
                    <div className="flex flex-wrap content-start gap-1">
                      {summary.map((s, i) => (
                        <Tag key={i} className="m-0 max-w-full truncate" title={s}>
                          {s}
                        </Tag>
                      ))}
                    </div>
                  ) : (
                    <span className="text-xs text-gray-500">无条件（全部基金）</span>
                  )}
                </div>

                <Space.Compact block>
                  <Tooltip title="把该预设条件载入查询区">
                    <Button size="small" onClick={() => onApply(p)}>
                      应用
                    </Button>
                  </Tooltip>
                  <Popconfirm
                    title="覆盖该预设？"
                    description="用当前查询区的筛选条件覆盖此预设"
                    onConfirm={() => onOverwrite(p.id)}
                  >
                    <Tooltip title="用当前查询条件覆盖该预设（基于已有预设加条件后保存）">
                      <Button size="small">覆盖</Button>
                    </Tooltip>
                  </Popconfirm>
                  <Dropdown
                    menu={{
                      items: FETCH_MODULES.map((m) => ({ key: m.key, label: m.label })),
                      onClick: ({ key }) => onFetch(p, key),
                    }}
                  >
                    <Tooltip title="基于该预设条件发起数据拉取">
                      <Button size="small" type="primary">
                        拉取 <DownOutlined />
                      </Button>
                    </Tooltip>
                  </Dropdown>
                </Space.Compact>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
