import { Select } from 'antd'

interface Props {
  codes: string[]
  names: string[]
  onCodesChange: (v: string[]) => void
  onNamesChange: (v: string[]) => void
}

// 排除基金代码 / 名称关键字（tags 模式，自由输入）
export default function FundExcludeSelect({
  codes,
  names,
  onCodesChange,
  onNamesChange,
}: Props) {
  return (
    <div className="flex flex-col gap-2">
      <div>
        <div className="text-xs text-gray-400 mb-1">排除代码</div>
        <Select
          mode="tags"
          size="small"
          value={codes}
          onChange={onCodesChange}
          placeholder="输入基金代码后回车"
          style={{ width: '100%' }}
          tokenSeparators={[',', ' ']}
        />
      </div>
      <div>
        <div className="text-xs text-gray-400 mb-1">排除名称含</div>
        <Select
          mode="tags"
          size="small"
          value={names}
          onChange={onNamesChange}
          placeholder="输入名称关键字后回车"
          style={{ width: '100%' }}
          tokenSeparators={[',', ' ']}
        />
      </div>
    </div>
  )
}
