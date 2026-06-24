import { useCallback, useEffect, useRef, useState } from 'react'
import { message } from 'antd'
import request from '../../../api/request'
import { buildFilterParams } from '../../fund/hooks/useFundData'
import type { FundItem, QueryPreset } from '../../fund/types'

export interface Snapshot {
  id: number
  created_at: string
  fund_count: number
  items: FundItem[]
  excluded_codes?: string[]
}

// 筛选页一次性展示全部命中（非分页），上限保护
const SCREEN_LIMIT = 500

// presetId / presets 由上层（工作台容器）统一管理并下传，本 hook 只负责
// 在 presetId 变化时拉取「最新筛选结果 + 镜像快照」，并提供刷新/存镜像/过滤名单维护。
export function useScreenData(presetId: number | null, presets: QueryPreset[]) {
  const [latest, setLatest] = useState<FundItem[]>([])
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  // 过滤名单（= 预设 filters.exclude_codes，与查询页排除复用）；权威值来自后端快照返回
  const [excluded, setExcluded] = useState<string[]>([])
  // 连点「移入过滤」时，闭包里的 excluded 会陈旧 → 用 ref 始终持有最新名单，供即时累加
  const excludedRef = useRef<string[]>([])
  useEffect(() => { excludedRef.current = excluded }, [excluded])
  // 写预设的串行队列 + 在途计数：保证多次写按序落库互不覆盖，且全部完成后只刷新/联动一次
  const queueRef = useRef<Promise<void>>(Promise.resolve())
  const pendingRef = useRef(0)

  // 镜像基金 = 预设「全集」：实时筛选一律不套用人工过滤名单(exclude_codes)。
  // 过滤名单只是事后标记——由 MirrorView 据此把全集拆「有效镜像/已过滤」两块，
  // 并由 downstream 聚类/仓位用 snapshot_items(with_exclude) 排除。故重新拉取镜像不会清空/削减过滤名单。
  const runScreen = useCallback(async (preset: QueryPreset) => {
    const params: Record<string, string> = {
      ...buildFilterParams({ ...(preset.filters ?? {}), exclude_codes: [] }),
      skip: '0',
      limit: String(SCREEN_LIMIT),
      attach_holdings: '1',
      attach_nav: '1',
      attach_ai: '1',
    }
    const { data } = await request.get('/fund/list', { params })
    return (data.items ?? []) as FundItem[]
  }, [])

  const loadSnapshot = useCallback(async (id: number): Promise<Snapshot | null> => {
    const { data } = await request.get(`/fund/presets/${id}/snapshot`)
    const snap = (data.snapshot ?? null) as Snapshot | null
    setSnapshot(snap)
    return snap
  }, [])

  const load = useCallback(async () => {
    if (presetId == null) {
      setLatest([])
      setSnapshot(null)
      setExcluded([])
      return
    }
    const preset = presets.find((p) => p.id === presetId)
    if (!preset) return
    setLoading(true)
    try {
      // 先取快照（含权威过滤名单），再据此实时筛选 latest，保证两者排除口径一致
      const snap = await loadSnapshot(presetId)
      const exCodes = snap?.excluded_codes ?? preset.filters?.exclude_codes ?? []
      setExcluded(exCodes)
      setLatest(await runScreen(preset))
    } catch {
      message.error('筛选失败')
    } finally {
      setLoading(false)
    }
  }, [presetId, presets, runScreen, loadSnapshot])

  // 过滤名单变更统一入口：compute 基于「最新名单」(ref) 算出新名单（add=并入 / remove=移除）。
  // ① 立即乐观更新 UI（基金即时在镜像/过滤名单间移动，不加 loading 遮罩，连点不被挡）；
  // ② PUT 串到队列尾按序落库，杜绝「后点的用旧名单覆盖前一次」的竞态；
  // ③ 仅当队列全部清空（队尾）时刷新快照并返回 true，触发上层联动一次；非队尾返回 false（不重复联动，非报错）。
  const mutateExcluded = useCallback(
    (compute: (cur: string[]) => string[]): Promise<boolean> => {
      if (presetId == null) return Promise.resolve(false)
      const preset = presets.find((p) => p.id === presetId)
      if (!preset) return Promise.resolve(false)
      const nextCodes = compute(excludedRef.current)
      excludedRef.current = nextCodes            // 立即记录最新意图，供下一次连点累加
      setExcluded(nextCodes)                      // 乐观更新，无需等后端
      if (preset.filters) preset.filters.exclude_codes = nextCodes
      pendingRef.current += 1
      const nextFilters = { ...(preset.filters ?? {}), exclude_codes: nextCodes }
      queueRef.current = queueRef.current
        .then(() => request.put(`/fund/presets/${presetId}`, { filters: nextFilters }))
        .then(() => undefined)
      return queueRef.current
        .then(async () => {
          pendingRef.current -= 1
          if (pendingRef.current !== 0) return false  // 非队尾：等最后一次统一刷新/联动
          await loadSnapshot(presetId)
          setLatest(await runScreen(preset))
          return true
        })
        .catch(async () => {
          pendingRef.current -= 1
          if (pendingRef.current === 0) {
            const snap = await loadSnapshot(presetId)   // 失败后回拉后端真实名单纠正乐观 UI
            const real = snap?.excluded_codes ?? []
            setExcluded(real)
            if (preset.filters) preset.filters.exclude_codes = real
            setLatest(await runScreen(preset))
          }
          message.error('更新过滤名单失败')
          return false
        })
    },
    [presetId, presets, runScreen, loadSnapshot],
  )

  // 移入过滤名单（基于最新名单去重并入）
  const addExcluded = useCallback(
    (code: string) => mutateExcluded((cur) => Array.from(new Set([...cur, code]))),
    [mutateExcluded],
  )
  // 移回（基于最新名单移除）
  const removeExcluded = useCallback(
    (code: string) => mutateExcluded((cur) => cur.filter((c) => c !== code)),
    [mutateExcluded],
  )

  // 把当前最新筛选结果存为该预设的镜像；成功返回 true（供上层联动重跑聚类/仓位）
  const saveMirror = useCallback(async (): Promise<boolean> => {
    if (presetId == null) return false
    setSaving(true)
    try {
      // 镜像不存净值序列 / AI（AI 由读取时动态挂载），减小体积
      const items = latest.map((it) => {
        const copy = { ...it }
        delete copy.nav_series
        delete copy.ai
        return copy
      })
      await request.post(`/fund/presets/${presetId}/snapshot`, { items })
      await loadSnapshot(presetId)
      message.success('镜像已更新')
      return true
    } catch {
      message.error('保存镜像失败')
      return false
    } finally {
      setSaving(false)
    }
  }, [presetId, latest, loadSnapshot])

  useEffect(() => {
    load()
  }, [load])

  return {
    latest, snapshot, loading, saving, refresh: load, saveMirror,
    excluded, addExcluded, removeExcluded,
  }
}
