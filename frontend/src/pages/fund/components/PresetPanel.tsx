import { useState } from 'react'
import { Button, Card, Empty, Popconfirm, Space, Tag, theme, Tooltip } from 'antd'
import { CheckCircleFilled, DeleteOutlined, EditOutlined } from '@ant-design/icons'
import { summarizeFilters } from '../constants'
import PresetNameModal from './PresetNameModal'
import type { QueryPreset } from '../types'

interface Props {
  presets: QueryPreset[]
  activeId: number | null
  onApply: (preset: QueryPreset) => void
  onRename: (id: number, name: string) => void
  onDelete: (id: number) => void
  onClear: () => void
}

export default function PresetPanel({
  presets,
  activeId,
  onApply,
  onRename,
  onDelete,
  onClear,
}: Props) {
  const { token } = theme.useToken()
  // 正在重命名的预设（null 表示模态关闭）
  const [renaming, setRenaming] = useState<QueryPreset | null>(null)

  return (
    <Card
      size="small"
      title="条件预设"
      extra={
        <Space size="small">
          <span className="text-xs text-gray-400">{presets.length} 个预设</span>
          {activeId != null && (
            <Button size="small" type="text" onClick={onClear}>
              清除选择
            </Button>
          )}
        </Space>
      }
    >
      {presets.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无预设，在下方筛选区设好条件后点「另存为预设」创建"
        />
      ) : (
        <div
          className="grid gap-3"
          style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(248px, 1fr))' }}
        >
          {presets.map((p) => {
            const summary = summarizeFilters(p.filters ?? {})
            const active = p.id === activeId
            return (
              <div
                key={p.id}
                onClick={() => onApply(p)}
                className="group relative flex h-full min-w-0 cursor-pointer flex-col overflow-hidden rounded-lg border p-3 transition-colors"
                style={{
                  borderColor: active ? token.colorPrimary : 'rgba(255,255,255,0.10)',
                  background: active ? token.colorPrimaryBg : 'rgba(255,255,255,0.02)',
                }}
                title="点击应用该预设"
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="flex min-w-0 flex-1 items-center gap-1 font-medium" title={p.name}>
                    {active && (
                      <CheckCircleFilled style={{ color: token.colorPrimary, fontSize: 13 }} />
                    )}
                    <span className="truncate">{p.name}</span>
                  </span>
                  <Space
                    size={0}
                    className={active ? '' : 'opacity-0 transition-opacity group-hover:opacity-100'}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Tooltip title="重命名">
                      <Button
                        size="small"
                        type="text"
                        icon={<EditOutlined />}
                        onClick={() => setRenaming(p)}
                      />
                    </Tooltip>
                    <Popconfirm
                      title="删除该预设？"
                      onConfirm={() => onDelete(p.id)}
                      onCancel={() => undefined}
                    >
                      <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  </Space>
                </div>

                <div className="min-h-[44px] flex-1">
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
              </div>
            )
          })}
        </div>
      )}

      <PresetNameModal
        open={renaming !== null}
        title="重命名预设"
        initialName={renaming?.name}
        onOk={(name) => {
          if (renaming) onRename(renaming.id, name)
          setRenaming(null)
        }}
        onCancel={() => setRenaming(null)}
      />
    </Card>
  )
}
