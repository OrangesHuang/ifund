import { useCallback, useEffect, useState } from 'react'
import { message } from 'antd'
import request from '../../../api/request'
import { buildFilterParams } from '../../fund/hooks/useFundData'
import type { FundItem, QueryPreset } from '../../fund/types'

export interface Snapshot {
  id: number
  created_at: string
  fund_count: number
  items: FundItem[]
}

// 筛选页一次性展示全部命中（非分页），上限保护
const SCREEN_LIMIT = 500

// presetId / presets 由上层（工作台容器）统一管理并下传，本 hook 只负责
// 在 presetId 变化时拉取「最新筛选结果 + 镜像快照」，并提供刷新/存镜像。
export function useScreenData(presetId: number | null, presets: QueryPreset[]) {
  const [latest, setLatest] = useState<FundItem[]>([])
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  // 用预设条件实时筛选（复用 /fund/list）
  const runScreen = useCallback(async (preset: QueryPreset) => {
    const params: Record<string, string> = {
      ...buildFilterParams(preset.filters ?? {}),
      skip: '0',
      limit: String(SCREEN_LIMIT),
      attach_holdings: '1',
      attach_nav: '1',
    }
    const { data } = await request.get('/fund/list', { params })
    return (data.items ?? []) as FundItem[]
  }, [])

  const loadSnapshot = useCallback(async (id: number) => {
    const { data } = await request.get(`/fund/presets/${id}/snapshot`)
    setSnapshot(data.snapshot ?? null)
  }, [])

  const load = useCallback(async () => {
    if (presetId == null) {
      setLatest([])
      setSnapshot(null)
      return
    }
    const preset = presets.find((p) => p.id === presetId)
    if (!preset) return
    setLoading(true)
    try {
      const [items] = await Promise.all([runScreen(preset), loadSnapshot(presetId)])
      setLatest(items)
    } catch {
      message.error('筛选失败')
    } finally {
      setLoading(false)
    }
  }, [presetId, presets, runScreen, loadSnapshot])

  // 把当前最新筛选结果存为该预设的镜像
  const saveMirror = useCallback(async () => {
    if (presetId == null) return
    setSaving(true)
    try {
      // 镜像不存净值序列，减小体积
      const items = latest.map((it) => {
        const copy = { ...it }
        delete copy.nav_series
        return copy
      })
      await request.post(`/fund/presets/${presetId}/snapshot`, { items })
      await loadSnapshot(presetId)
      message.success('镜像已更新')
    } catch {
      message.error('保存镜像失败')
    } finally {
      setSaving(false)
    }
  }, [presetId, latest, loadSnapshot])

  useEffect(() => {
    load()
  }, [load])

  return { latest, snapshot, loading, saving, refresh: load, saveMirror }
}
