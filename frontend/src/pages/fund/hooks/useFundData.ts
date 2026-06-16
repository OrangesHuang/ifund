import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { message } from 'antd'
import request from '../../../api/request'
import type {
  CompareCondition,
  Filters,
  FundItem,
  FundTypeItem,
  QueryPreset,
  RunningTask,
  SortInfo,
} from '../types'

const POLL_INTERVAL = 3000

/** 规范化筛选条件（去空字段 + 排序），用于稳定比较「当前条件」与「预设条件」是否一致。 */
function normalizeFilters(f: Filters): string {
  const out: Record<string, unknown> = {}
  if (f.keyword) out.keyword = f.keyword
  if (f.name_contains) out.name_contains = f.name_contains
  if (f.fund_types?.length) out.fund_types = [...f.fund_types].sort()
  if (f.exclude_codes?.length) out.exclude_codes = [...f.exclude_codes].sort()
  if (f.name_excludes?.length) out.name_excludes = [...f.name_excludes].sort()
  if (f.conditions?.length) {
    out.conditions = [...f.conditions].sort(
      (a: CompareCondition, b: CompareCondition) =>
        `${a.field}${a.op}${a.value}`.localeCompare(`${b.field}${b.op}${b.value}`),
    )
  }
  return JSON.stringify(out)
}

/**
 * buildFilterParams：filters → 后端 query 参数。
 * 比较条件序列化为 conds=field:op:value,...（同字段多条件即 AND 交集）。
 */
export function buildFilterParams(filters: Filters): Record<string, string> {
  const params: Record<string, string> = {}
  if (filters.keyword) params.keyword = filters.keyword
  if (filters.name_contains) params.name_contains = filters.name_contains
  if (filters.fund_types?.length) params.fund_types = filters.fund_types.join(',')
  if (filters.exclude_codes?.length) params.exclude_codes = filters.exclude_codes.join(',')
  if (filters.name_excludes?.length) {
    // 后端支持多个 name_excludes，逗号分隔传递
    params.name_excludes = filters.name_excludes.join(',')
  }
  if (filters.conditions?.length) {
    params.conds = filters.conditions
      .map((c) => `${c.field}:${c.op}:${c.value}`)
      .join(',')
  }
  return params
}

export function useFundData() {
  const [filters, setFilters] = useState<Filters>({})
  const [funds, setFunds] = useState<FundItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [sorters, setSorters] = useState<SortInfo[]>([])
  const [loading, setLoading] = useState(false)
  const [fundTypes, setFundTypes] = useState<FundTypeItem[]>([])
  const [presets, setPresets] = useState<QueryPreset[]>([])
  // 当前选中（应用）的预设 id；null 表示自由条件（全部基金）
  const [activePresetId, setActivePresetId] = useState<number | null>(null)

  // 三套独立轮询任务状态
  const [detailTask, setDetailTask] = useState<RunningTask | null>(null)
  const [holdingsTask, setHoldingsTask] = useState<RunningTask | null>(null)
  const [navTask, setNavTask] = useState<RunningTask | null>(null)

  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const holdingsPollRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const navPollRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // 各模块的「立即探测一次」函数，供发起/终止任务后重启轮询
  const tickRefs = useRef<Record<string, () => void>>({})

  const fetchFunds = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, string> = {
        ...buildFilterParams(filters),
        skip: String((page - 1) * pageSize),
        limit: String(pageSize),
        attach_holdings: '1',
        attach_nav: '1',
      }
      if (sorters.length) {
        const s = sorters[0]
        params.order_by = `${s.field}:${s.order}`
      }
      const { data } = await request.get('/fund/list', { params })
      setFunds(data.items ?? [])
      setTotal(data.total ?? 0)
    } catch {
      message.error('加载基金列表失败')
    } finally {
      setLoading(false)
    }
  }, [filters, page, pageSize, sorters])

  const loadFundTypes = useCallback(async () => {
    try {
      const { data } = await request.get('/fund/types')
      setFundTypes(data.items ?? data ?? [])
    } catch {
      /* 忽略 */
    }
  }, [])

  const loadPresets = useCallback(async () => {
    try {
      const { data } = await request.get('/fund/presets')
      setPresets(data.items ?? data ?? [])
    } catch {
      /* 忽略 */
    }
  }, [])

  // ---- 三套自适应轮询：仅当任务 running 时才继续，否则停止 ----
  const buildPoller = useCallback(
    (
      url: string,
      ref: React.MutableRefObject<ReturnType<typeof setTimeout> | null>,
      setter: (t: RunningTask | null) => void,
    ) => {
      const tick = async () => {
        // 先清掉待定计时器，避免重复触发导致轮询链叠加
        if (ref.current) {
          clearTimeout(ref.current)
          ref.current = null
        }
        let running = false
        try {
          const { data } = await request.get(url)
          const task = data && data.id ? (data as RunningTask) : null
          setter(task)
          running = !!task && task.status === 'running'
        } catch {
          setter(null)
        }
        // 仅在仍有运行中任务时排下一次轮询；null/已完成则停止
        if (running) ref.current = setTimeout(tick, POLL_INTERVAL)
      }
      return tick
    },
    [],
  )

  useEffect(() => {
    const detailTick = buildPoller('/fund_detail/task/running', pollRef, setDetailTask)
    const holdTick = buildPoller('/fund_holdings/task/running', holdingsPollRef, setHoldingsTask)
    const navTick = buildPoller('/fund_nav/task/running', navPollRef, setNavTask)
    tickRefs.current = {
      fund_detail: detailTick,
      fund_holdings: holdTick,
      fund_nav: navTick,
    }
    // 仅探测一次：若无运行中任务则不再轮询
    detailTick()
    holdTick()
    navTick()
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current)
      if (holdingsPollRef.current) clearTimeout(holdingsPollRef.current)
      if (navPollRef.current) clearTimeout(navPollRef.current)
    }
  }, [buildPoller])

  useEffect(() => {
    fetchFunds()
  }, [fetchFunds])

  useEffect(() => {
    loadFundTypes()
    loadPresets()
  }, [loadFundTypes, loadPresets])

  // ---- 拉取任务触发 ----
  // 按指定筛选条件发起拉取（预设拉取与当前条件拉取共用）
  const startTaskWith = useCallback(async (module: string, target: Filters) => {
    try {
      // 筛选条件作为 query 参数传给 /sync（后端 resolve_targets 读 request.args）
      const params = buildFilterParams(target)
      await request.post(`/${module}/sync`, null, { params })
      message.success('已发起拉取任务')
      // 发起后立即重启该模块轮询（运行中会持续刷新，完成后自动停止）
      tickRefs.current[module]?.()
    } catch (err) {
      // 409：同类任务已有一个在运行，透出后端原因；其余给通用提示
      const resp = (err as { response?: { status?: number; data?: { detail?: string } } }).response
      if (resp?.status === 409) {
        message.warning(resp.data?.detail || '已有运行中的任务，请等待完成')
      } else {
        message.error('发起任务失败')
      }
    }
  }, [])

  // 按当前查询条件发起拉取
  const startTask = useCallback(
    (module: string) => startTaskWith(module, filters),
    [filters, startTaskWith],
  )

  const terminateTask = useCallback(async (module: string, taskId: number) => {
    try {
      await request.post(`/${module}/task/${taskId}/terminate`)
      message.success('已请求终止')
      // 终止后刷新一次状态（变为非 running 时轮询会自动停止）
      tickRefs.current[module]?.()
    } catch {
      message.error('终止失败')
    }
  }, [])

  const syncFundList = useCallback(async () => {
    setLoading(true)
    try {
      await request.post('/fund/sync')
      message.success('基金名单已同步')
      await fetchFunds()
    } catch {
      message.error('同步失败')
    } finally {
      setLoading(false)
    }
  }, [fetchFunds])

  // ---- 预设选中态 ----
  // 当前选中的预设行；未选中为 null
  const activePreset = useMemo(
    () => presets.find((p) => p.id === activePresetId) ?? null,
    [presets, activePresetId],
  )
  // 当前筛选条件是否已偏离选中预设（用于显示「更新预设」）
  const dirty = useMemo(
    () =>
      activePreset
        ? normalizeFilters(filters) !== normalizeFilters(activePreset.filters ?? {})
        : false,
    [filters, activePreset],
  )

  // ---- 预设 CRUD ----
  // 另存为新预设：保存后自动选中新预设
  const savePreset = useCallback(
    async (name: string) => {
      try {
        const { data } = await request.post('/fund/presets', { name, filters })
        await loadPresets()
        if (data?.id) setActivePresetId(data.id)
        message.success('预设已保存')
      } catch {
        message.error('保存预设失败')
      }
    },
    [filters, loadPresets],
  )

  // 用当前查询条件覆盖指定预设（按 id，不改名）
  const overwritePreset = useCallback(
    async (id: number) => {
      try {
        await request.put(`/fund/presets/${id}`, { filters })
        await loadPresets()
        message.success('预设已更新')
      } catch {
        message.error('覆盖预设失败')
      }
    },
    [filters, loadPresets],
  )

  // 更新当前选中预设（= 用当前条件覆盖它）
  const updateActivePreset = useCallback(() => {
    if (activePresetId != null) overwritePreset(activePresetId)
  }, [activePresetId, overwritePreset])

  // 重命名预设（仅改名，不动条件）
  const renamePreset = useCallback(
    async (id: number, name: string) => {
      try {
        await request.put(`/fund/presets/${id}`, { name })
        await loadPresets()
        message.success('已重命名')
      } catch {
        message.error('重命名失败')
      }
    },
    [loadPresets],
  )

  const deletePreset = useCallback(
    async (id: number) => {
      await request.delete(`/fund/presets/${id}`)
      // 删的是当前选中预设则同时取消选中
      setActivePresetId((cur) => (cur === id ? null : cur))
      await loadPresets()
    },
    [loadPresets],
  )

  // 应用预设：选中高亮 + 载入条件
  const applyPreset = useCallback((preset: QueryPreset) => {
    setActivePresetId(preset.id)
    setFilters(preset.filters ?? {})
    setPage(1)
    message.success(`已应用预设「${preset.name}」`)
  }, [])

  // 取消选中（保留当前条件，仅去掉预设高亮）
  const clearPreset = useCallback(() => setActivePresetId(null), [])

  return {
    filters,
    setFilters,
    funds,
    total,
    page,
    setPage,
    pageSize,
    setPageSize,
    sorters,
    setSorters,
    loading,
    fundTypes,
    presets,
    activePresetId,
    activePreset,
    dirty,
    detailTask,
    holdingsTask,
    navTask,
    fetchFunds,
    syncFundList,
    startTask,
    startTaskWith,
    terminateTask,
    savePreset,
    overwritePreset,
    updateActivePreset,
    renamePreset,
    deletePreset,
    applyPreset,
    clearPreset,
  }
}
