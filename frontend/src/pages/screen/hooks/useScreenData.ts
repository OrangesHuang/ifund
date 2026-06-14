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

export function useScreenData() {
  const [presets, setPresets] = useState<QueryPreset[]>([])
  const [presetId, setPresetId] = useState<number | null>(null)
  const [latest, setLatest] = useState<FundItem[]>([])
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const loadPresets = useCallback(async () => {
    try {
      const { data } = await request.get('/fund/presets')
      setPresets(data.items ?? data ?? [])
    } catch {
      /* 忽略 */
    }
  }, [])

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

  const selectPreset = useCallback(
    async (id: number) => {
      setPresetId(id)
      const preset = presets.find((p) => p.id === id)
      if (!preset) return
      setLoading(true)
      try {
        const [items] = await Promise.all([runScreen(preset), loadSnapshot(id)])
        setLatest(items)
      } catch {
        message.error('筛选失败')
      } finally {
        setLoading(false)
      }
    },
    [presets, runScreen, loadSnapshot],
  )

  const refresh = useCallback(() => {
    if (presetId != null) selectPreset(presetId)
  }, [presetId, selectPreset])

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
    loadPresets()
  }, [loadPresets])

  return { presets, presetId, latest, snapshot, loading, saving, selectPreset, refresh, saveMirror }
}
