import { useEffect, useRef, useState } from 'react'
import { Button, InputNumber, Select, Space } from 'antd'
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons'
import { COMPARE_FIELDS as FIELDS, COMPARE_OP_OPTIONS as OP_OPTIONS } from '../constants'
import type { CompareCondition, CompareOp } from '../types'

interface Row {
  op: CompareOp
  value: number | null
}

type RowMap = Record<string, Row[]>

/** 由外部 conditions 重建「每字段至少一行」的内部行模型。 */
function buildRows(conditions: CompareCondition[]): RowMap {
  const map: RowMap = {}
  for (const f of FIELDS) map[f.key] = []
  for (const c of conditions) {
    if (!map[c.field]) map[c.field] = []
    map[c.field].push({ op: c.op, value: c.value })
  }
  for (const f of FIELDS) if (map[f.key].length === 0) map[f.key] = [{ op: 'gt', value: null }]
  return map
}

/** 把行模型压成 conditions（丢弃未填值的行）。 */
function flatten(rows: RowMap): CompareCondition[] {
  const out: CompareCondition[] = []
  for (const f of FIELDS) {
    for (const r of rows[f.key] ?? []) {
      if (r.value !== null && r.value !== undefined) {
        out.push({ field: f.key, op: r.op, value: r.value })
      }
    }
  }
  return out
}

interface Props {
  value: CompareCondition[]
  onChange: (next: CompareCondition[]) => void
}

export default function MultiCompareFilter({ value, onChange }: Props) {
  const [rows, setRows] = useState<RowMap>(() => buildRows(value))
  // 记录自身最近一次 emit 的签名，用于区分「外部预设变更」与「自身编辑」
  const lastEmit = useRef<string>(JSON.stringify(value))

  useEffect(() => {
    const sig = JSON.stringify(value)
    if (sig === lastEmit.current) return // 自身触发，保留空行不重建
    lastEmit.current = sig
    setRows(buildRows(value))
  }, [value])

  const emit = (next: RowMap) => {
    setRows(next)
    const conds = flatten(next)
    lastEmit.current = JSON.stringify(conds)
    onChange(conds)
  }

  const setRow = (key: string, idx: number, patch: Partial<Row>) => {
    const list = (rows[key] ?? []).map((r, i) => (i === idx ? { ...r, ...patch } : r))
    emit({ ...rows, [key]: list })
  }

  const addRow = (key: string) => {
    emit({ ...rows, [key]: [...(rows[key] ?? []), { op: 'gt', value: null }] })
  }

  const removeRow = (key: string, idx: number) => {
    const list = (rows[key] ?? []).filter((_, i) => i !== idx)
    emit({ ...rows, [key]: list.length ? list : [{ op: 'gt', value: null }] })
  }

  return (
    <div className="grid grid-cols-1 gap-x-6 gap-y-2 md:grid-cols-2">
      {FIELDS.map((f) => (
        <div key={f.key} className="flex items-start gap-2">
          <div className="w-20 shrink-0 pt-1 text-xs text-gray-400">{f.label}</div>
          <div className="flex flex-1 flex-col gap-1">
            {(rows[f.key] ?? []).map((r, idx) => (
              <Space key={idx} size={4}>
                <Select<CompareOp>
                  size="small"
                  value={r.op}
                  options={OP_OPTIONS}
                  onChange={(op) => setRow(f.key, idx, { op })}
                  style={{ width: 64 }}
                />
                <InputNumber
                  size="small"
                  placeholder="值"
                  value={r.value}
                  onChange={(v) => setRow(f.key, idx, { value: v as number | null })}
                  style={{ width: 110 }}
                />
                {idx === 0 ? (
                  <Button
                    size="small"
                    type="text"
                    icon={<PlusOutlined />}
                    onClick={() => addRow(f.key)}
                  />
                ) : (
                  <Button
                    size="small"
                    type="text"
                    danger
                    icon={<MinusCircleOutlined />}
                    onClick={() => removeRow(f.key, idx)}
                  />
                )}
              </Space>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
