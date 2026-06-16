import { useEffect, useState } from 'react'
import { Input, Modal } from 'antd'

interface Props {
  open: boolean
  title: string
  initialName?: string
  onOk: (name: string) => void
  onCancel: () => void
}

/** 预设命名模态：复用于「另存为预设」（initialName 空）与「重命名」（initialName=原名）。 */
export default function PresetNameModal({ open, title, initialName = '', onOk, onCancel }: Props) {
  const [name, setName] = useState(initialName)

  // 每次打开时回填初始名
  useEffect(() => {
    if (open) setName(initialName)
  }, [open, initialName])

  const submit = () => {
    const trimmed = name.trim()
    if (!trimmed) return
    onOk(trimmed)
  }

  return (
    <Modal
      open={open}
      title={title}
      onOk={submit}
      onCancel={onCancel}
      okButtonProps={{ disabled: !name.trim() }}
      destroyOnClose
      width={420}
    >
      <Input
        placeholder="请输入预设名称"
        value={name}
        onChange={(e) => setName(e.target.value)}
        onPressEnter={submit}
        maxLength={40}
        autoFocus
      />
    </Modal>
  )
}
