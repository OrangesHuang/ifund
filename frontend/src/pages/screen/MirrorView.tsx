import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Card, Descriptions, Divider, Drawer, Empty, Input, message, Modal, Popconfirm, Progress, Radio, Rate, Select, Space, Spin, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { EditOutlined, ReloadOutlined, SaveOutlined, StopOutlined, ThunderboltOutlined, UndoOutlined } from '@ant-design/icons'
import request from '../../api/request'
import { useScreenData } from './hooks/useScreenData'
import { buildFundColumns } from '../fund/components/fundColumns'
import FundDetailModal from '../fund/components/FundDetailModal'
import NavTrendModal from '../fund/components/NavTrendModal'
import AiReActPanel, { type ReActStep } from './components/AiReActPanel'
import type { FundItem, QueryPreset } from '../fund/types'
import { CONC_META, KIND_META, LUCK_META } from '../fund/aiMeta'

const { TextArea } = Input
const { Text } = Typography

export default function MirrorView({
  presetId,
  presets,
  onMirrorSaved,
}: {
  presetId: number | null
  presets: QueryPreset[]
  onMirrorSaved?: () => void
}) {
  const {
    latest, snapshot, loading, saving, refresh, saveMirror,
    excluded, addExcluded, removeExcluded,
  } = useScreenData(presetId, presets)
  const [detailCode, setDetailCode] = useState<string | null>(null)
  const [trend, setTrend] = useState<{ code: string; name: string } | null>(null)
  const [latestPag, setLatestPag] = useState({ current: 1, pageSize: 20 })
  const [mirrorPag, setMirrorPag] = useState({ current: 1, pageSize: 20 })

  const mirrorItems = snapshot?.items ?? []
  const excludedSet = useMemo(() => new Set(excluded), [excluded])
  const latestCodes = useMemo(() => new Set(latest.map((f) => f.code)), [latest])
  const mirrorCodes = useMemo(() => new Set(mirrorItems.map((f) => f.code)), [mirrorItems])

  const effectiveItems = useMemo(
    () => mirrorItems.filter((f) => !excludedSet.has(f.code)),
    [mirrorItems, excludedSet],
  )
  const filteredItems = useMemo(
    () => mirrorItems.filter((f) => excludedSet.has(f.code)),
    [mirrorItems, excludedSet],
  )

  // --- AI 维度筛选状态 ---
  const [aiFilterRating, setAiFilterRating] = useState<number | null>(null)
  const [aiFilterLuck, setAiFilterLuck] = useState<string[]>([])
  const [aiFilterConc, setAiFilterConc] = useState<string[]>([])
  const [aiFilterKind, setAiFilterKind] = useState<string[]>([])

  const applyAiFilter = useCallback((items: FundItem[]) => {
    let arr = items
    if (aiFilterRating !== null) {
      arr = arr.filter((f) => (f.ai?.rating ?? null) === aiFilterRating)
    }
    if (aiFilterLuck.length) {
      arr = arr.filter((f) => f.ai?.luck_verdict && aiFilterLuck.includes(f.ai.luck_verdict))
    }
    if (aiFilterConc.length) {
      arr = arr.filter((f) => f.ai?.concentration && aiFilterConc.includes(f.ai.concentration))
    }
    if (aiFilterKind.length) {
      arr = arr.filter((f) => f.ai?.fund_kind && aiFilterKind.includes(f.ai.fund_kind))
    }
    return arr
  }, [aiFilterRating, aiFilterLuck, aiFilterConc, aiFilterKind])

  const filteredEffectiveItems = useMemo(() => applyAiFilter(effectiveItems), [effectiveItems, applyAiFilter])
  const filteredExcludedItems = useMemo(() => applyAiFilter(filteredItems), [filteredItems, applyAiFilter])

  const resetAiFilter = useCallback(() => {
    setAiFilterRating(null)
    setAiFilterLuck([])
    setAiFilterConc([])
    setAiFilterKind([])
  }, [])

  const hasAiFilter = aiFilterRating !== null || aiFilterLuck.length > 0 || aiFilterConc.length > 0 || aiFilterKind.length > 0

  const newCount = snapshot ? latest.filter((f) => !mirrorCodes.has(f.code)).length : 0
  const droppedCount = effectiveItems.filter((f) => !latestCodes.has(f.code)).length

  const latestCurrent = Math.min(latestPag.current, Math.max(1, Math.ceil(latest.length / latestPag.pageSize)))
  const mirrorCurrent = Math.min(mirrorPag.current, Math.max(1, Math.ceil(filteredEffectiveItems.length / mirrorPag.pageSize)))

  const handleExclude = async (code: string) => {
    if (await addExcluded(code)) onMirrorSaved?.()
  }
  const handleRestore = async (code: string) => {
    if (await removeExcluded(code)) onMirrorSaved?.()
  }

  // --- AI 分析流式状态 ---
  const [analyzingCode, setAnalyzingCode] = useState<string | null>(null)
  const [streamText, setStreamText] = useState('')
  const [streamDone, setStreamDone] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [aiResult, setAiResult] = useState<Record<string, unknown> | null>(null)
  const [parseError, setParseError] = useState('')
  // --- ReAct 浮窗（记录分析过程多轮进展）---
  const [reactSteps, setReactSteps] = useState<ReActStep[]>([])
  const [reactStatus, setReactStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle')
  const [reactError, setReactError] = useState('')
  const [reactName, setReactName] = useState('')
  const [promptDrawerOpen, setPromptDrawerOpen] = useState(false)
  const [promptSystem, setPromptSystem] = useState('')
  const [promptUser, setPromptUser] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const streamTextRef = useRef('')

  const loadPrompt = useCallback(async () => {
    try {
      const { data } = await request.get('/fund/ai-prompt')
      setPromptSystem(data.system ?? '')
      setPromptUser(data.user ?? '')
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    if (promptDrawerOpen) loadPrompt()
  }, [promptDrawerOpen, loadPrompt])

  useEffect(() => {
    if (analyzingCode && !streamDone) {
      setElapsed(0)
      const id = setInterval(() => setElapsed((s) => s + 1), 1000)
      return () => clearInterval(id)
    }
  }, [analyzingCode, streamDone])

  const handleSavePrompt = async () => {
    try {
      await request.put('/fund/ai-prompt', { system: promptSystem, user: promptUser })
      message.success('提示词已保存')
      setPromptDrawerOpen(false)
    } catch {
      message.error('保存失败')
    }
  }

  const handleResetPrompt = async () => {
    try {
      const { data } = await request.delete('/fund/ai-prompt')
      setPromptSystem(data.system ?? '')
      setPromptUser(data.user ?? '')
      message.success('已恢复为仓库默认提示词')
    } catch {
      message.error('恢复失败')
    }
  }

  const handleAnalyze = async (code: string, name?: string) => {
    setAnalyzingCode(code)
    setStreamText('')
    setStreamDone(false)
    setElapsed(0)
    setAiResult(null)
    setParseError('')
    setReactSteps([])
    setReactStatus('running')
    setReactError('')
    setReactName(name ?? '')
    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      const token = localStorage.getItem('token')
      const resp = await fetch(`/api/fund/${code}/ai-analyze`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: 'text/event-stream',
        },
        signal: ctrl.signal,
      })

      const reader = resp.body?.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      if (!reader) throw new Error('No reader')

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.type === 'chunk') {
              setStreamText((prev) => {
                streamTextRef.current = prev + evt.text
                return streamTextRef.current
              })
            } else if (evt.type === 'round') {
              setReactSteps((prev) => [
                ...prev,
                {
                  round: evt.round,
                  thought: evt.thought,
                  action: evt.action,
                  args: evt.args ?? {},
                  observation: evt.observation,
                },
              ])
            } else if (evt.type === 'done') {
              setReactStatus('done')
              setStreamDone(true)
              // 从流式文本中提取 JSON 并解析
              const raw = streamTextRef.current
              let jsonStr = raw
              const m = raw.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/)
              if (m) jsonStr = m[1].trim()
              const m2 = jsonStr.match(/\{[\s\S]*\}/)
              if (m2) jsonStr = m2[0]
              try {
                setAiResult(JSON.parse(jsonStr))
              } catch {
                setParseError('JSON 解析失败，显示原始文本')
              }
              message.success(`${code} AI 分析完成`)
              refresh()
              onMirrorSaved?.()
            } else if (evt.type === 'error') {
              setStreamDone(true)
              setReactStatus('error')
              setReactError(evt.detail ?? '')
              message.error(`分析失败: ${evt.detail}`)
            }
          } catch { /* skip malformed */ }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        message.info('已取消分析')
      } else {
        message.error(`${code} AI 分析失败`)
      }
    } finally {
      setStreamDone(true)
      abortRef.current = null
    }
  }

  const handleCancelAnalyze = () => {
    abortRef.current?.abort()
    setAnalyzingCode(null)
    setReactStatus('idle')
    setReactSteps([])
  }

  const handleCloseStreamModal = () => {
    if (!streamDone) {
      abortRef.current?.abort()
    }
    setAnalyzingCode(null)
    setReactStatus('idle')
    setReactSteps([])
  }

  // --- AI 结果格式化辅助 ---
  const luckLabel: Record<string, string> = { solid: '实力', mixed: '中性', luck: '运气' }
  const luckColor: Record<string, string> = { solid: 'green', mixed: 'orange', luck: 'red' }
  const concLabel: Record<string, string> = { single_bet: '单押', focused: '集中', diversified: '分散' }
  const concColor: Record<string, string> = { single_bet: 'red', focused: 'orange', diversified: 'green' }
  const kindLabel: Record<string, string> = { subjective: '主观选股', rotation: '行业轮动', sector: '赛道主题' }
  const kindColor: Record<string, string> = { subjective: 'blue', rotation: 'purple', sector: 'red' }
  const scaleLabel: Record<string, string> = { tiny: '极小(清盘风险)', small: '偏小', ok: '适中', large: '过大(恐平庸)' }
  const scaleColor: Record<string, string> = { tiny: 'red', small: 'orange', ok: 'green', large: 'warning' }
  const styleLabel: Record<string, string> = { stable: '稳定', volatile: '漂移/交易型', unproven: '样本不足' }
  const styleColor: Record<string, string> = { stable: 'green', volatile: 'orange', unproven: 'default' }

  const r = aiResult ?? {}
  const tags = Array.isArray(r.tags) ? r.tags as string[] : []
  const ratingVal = Number(r.rating ?? 0)
  const skillScore = Number(r.skill_score ?? 0)
  const recommend = Number(r.recommend ?? 0)

  const statusCol = (
    render: (code: string) => React.ReactNode,
  ): ColumnsType<FundItem>[number] => ({
    title: '状态',
    dataIndex: 'code',
    width: 76,
    fixed: 'left',
    render: (code: string) => render(code),
  })

  const aiAnalyzeCol: ColumnsType<FundItem>[number] = {
    title: 'AI',
    key: 'ai_analyze',
    width: 80,
    fixed: 'right',
    render: (_: unknown, row: FundItem) => {
      const isLoading = analyzingCode === row.code
      return (
        <Popconfirm
          title="AI 定性分析"
          description="将调用 AI 流式分析该基金，约需 30-60 秒"
          okText="开始分析"
          cancelText="取消"
          onConfirm={() => handleAnalyze(row.code, row.name)}
        >
          <Button size="small" type="link" icon={<ThunderboltOutlined />} loading={isLoading}>
            AI分析
          </Button>
        </Popconfirm>
      )
    },
  }

  const excludeActionCol: ColumnsType<FundItem>[number] = {
    title: '过滤',
    key: 'op_exclude',
    width: 92,
    fixed: 'right',
    render: (_: unknown, row: FundItem) => (
      <Popconfirm
        title="移入过滤名单？"
        description="该基金将从镜像剔除，聚类/仓位不再纳入"
        okText="移入"
        cancelText="取消"
        onConfirm={() => handleExclude(row.code)}
      >
        <Button size="small" type="link" danger icon={<StopOutlined />}>
          移入过滤
        </Button>
      </Popconfirm>
    ),
  }

  const restoreActionCol: ColumnsType<FundItem>[number] = {
    title: '操作',
    key: 'op_restore',
    width: 88,
    fixed: 'right',
    render: (_: unknown, row: FundItem) => (
      <Button size="small" type="link" icon={<UndoOutlined />} onClick={() => handleRestore(row.code)}>
        移回
      </Button>
    ),
  }

  const latestColumns: ColumnsType<FundItem> = [
    statusCol((code) =>
      snapshot && !mirrorCodes.has(code) ? <Tag color="green">新增</Tag> : null,
    ),
    ...buildFundColumns({
      onOpenDetail: setDetailCode,
      onOpenTrend: (code, name) => setTrend({ code, name }),
      showNav: true,
      showAi: true,
    }),
    aiAnalyzeCol,
  ]
  const effectiveColumns: ColumnsType<FundItem> = [
    statusCol((code) => (!latestCodes.has(code) ? <Tag color="red">已剔除</Tag> : null)),
    ...buildFundColumns({ onOpenDetail: setDetailCode, showNav: false, showAi: true }),
    aiAnalyzeCol,
    excludeActionCol,
  ]
  const filteredColumns: ColumnsType<FundItem> = [
    ...buildFundColumns({ onOpenDetail: setDetailCode, showNav: false, showAi: true }),
    aiAnalyzeCol,
    restoreActionCol,
  ]

  const aiFilterBar = (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12, marginBottom: 12 }}>
      <span style={{ fontSize: 13, opacity: 0.65 }}>AI筛选：</span>
      <Radio.Group
        size="small"
        value={aiFilterRating ?? ''}
        onChange={(e) => setAiFilterRating(e.target.value === '' ? null : Number(e.target.value))}
        optionType="button"
        buttonStyle="solid"
      >
        <Radio.Button value="">全部★</Radio.Button>
        {[0, 1, 2, 3].map((v) => <Radio.Button key={v} value={v}>{v}★</Radio.Button>)}
      </Radio.Group>
      <Select
        mode="multiple"
        size="small"
        allowClear
        placeholder="运气"
        style={{ minWidth: 120 }}
        value={aiFilterLuck}
        onChange={setAiFilterLuck}
        options={Object.entries(LUCK_META).map(([k, v]) => ({ value: k, label: v.label }))}
      />
      <Select
        mode="multiple"
        size="small"
        allowClear
        placeholder="集中度"
        style={{ minWidth: 120 }}
        value={aiFilterConc}
        onChange={setAiFilterConc}
        options={Object.entries(CONC_META).map(([k, v]) => ({ value: k, label: v.label }))}
      />
      <Select
        mode="multiple"
        size="small"
        allowClear
        placeholder="属性"
        style={{ minWidth: 120 }}
        value={aiFilterKind}
        onChange={setAiFilterKind}
        options={Object.entries(KIND_META).map(([k, v]) => ({ value: k, label: v.label }))}
      />
      {hasAiFilter && (
        <Button size="small" onClick={resetAiFilter}>重置</Button>
      )}
    </div>
  )

  if (presetId == null) {
    return <Alert type="info" showIcon message="请在上方选择一个基金预设，查看其镜像基金与最新筛选基金。" />
  }

  return (
    <Space direction="vertical" className="w-full" style={{ width: '100%' }} size="middle">
      <Space wrap>
        <Button icon={<ReloadOutlined />} onClick={refresh} loading={loading}>
          重新筛选
        </Button>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          onClick={async () => {
            if (await saveMirror()) onMirrorSaved?.()
          }}
          disabled={!latest.length}
          loading={saving}
        >
          {snapshot ? '更新镜像' : '存为镜像'}
        </Button>
        <Button icon={<EditOutlined />} onClick={() => setPromptDrawerOpen(true)}>
          AI提示词
        </Button>
      </Space>

      {/* 流式分析弹窗 */}
      <Modal
        title={
          <Space>
            <ThunderboltOutlined style={{ color: '#1890ff' }} />
            <span>{streamDone ? `分析完成：${analyzingCode}` : `正在分析：${analyzingCode}`}</span>
          </Space>
        }
        open={analyzingCode !== null}
        onCancel={handleCloseStreamModal}
        width={720}
        footer={streamDone ? (
          <Button onClick={handleCloseStreamModal}>关闭</Button>
        ) : (
          <Button danger onClick={handleCancelAnalyze}>取消分析</Button>
        )}
      >
        {!streamDone ? (
          <div style={{ textAlign: 'center', padding: '48px 0' }}>
            <Spin size="large" />
            <div style={{ marginTop: 16, opacity: 0.65 }}>
              AI 正在分析中，已等待 {elapsed} 秒…
            </div>
            <div style={{ marginTop: 8, fontSize: 12, opacity: 0.45 }}>
              首次分析需调用 AI Agent（含工具调用），通常 30-60 秒
            </div>
          </div>
        ) : aiResult ? (
          <div style={{ maxHeight: 520, overflow: 'auto' }}>
            {/* 一句话总评 */}
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 12 }}>
              {String(r.verdict ?? '无结论')}
            </div>

            {/* 评分行 */}
            <Space direction="vertical" style={{ width: '100%' }} size={8}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 13, opacity: 0.65, minWidth: 56 }}>综合评级</span>
                <Rate disabled allowHalf value={ratingVal} style={{ fontSize: 16 }} />
                {recommend === 1 && <Tag color="green" style={{ margin: 0 }}>推荐</Tag>}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 13, opacity: 0.65, minWidth: 56 }}>实力分</span>
                <Progress
                  percent={skillScore}
                  size="small"
                  style={{ flex: 1, maxWidth: 300 }}
                  strokeColor={skillScore >= 75 ? '#52c41a' : skillScore >= 45 ? '#faad14' : '#ff4d4f'}
                />
                <span style={{ fontSize: 13, fontWeight: 600 }}>{skillScore}</span>
              </div>
            </Space>

            <Divider style={{ margin: '12px 0' }} />

            {/* 核心标签 */}
            <Space wrap size={[8, 8]}>
              {r.luck_verdict && (
                <Tag color={luckColor[String(r.luck_verdict)] ?? 'default'}>
                  运气判断：{luckLabel[String(r.luck_verdict)] ?? r.luck_verdict}
                </Tag>
              )}
              {r.concentration && (
                <Tag color={concColor[String(r.concentration)] ?? 'default'}>
                  集中度：{concLabel[String(r.concentration)] ?? r.concentration}
                </Tag>
              )}
              {r.fund_kind && (
                <Tag color={kindColor[String(r.fund_kind)] ?? 'default'}>
                  基金属性：{kindLabel[String(r.fund_kind)] ?? r.fund_kind}
                </Tag>
              )}
              {r.confidence && <Tag>置信度：{r.confidence}</Tag>}
              {r.scale_risk && (
                <Tag color={scaleColor[String(r.scale_risk)] ?? 'default'}>
                  规模：{scaleLabel[String(r.scale_risk)] ?? r.scale_risk}
                </Tag>
              )}
              {r.style_stability && (
                <Tag color={styleColor[String(r.style_stability)] ?? 'default'}>
                  风格：{styleLabel[String(r.style_stability)] ?? r.style_stability}
                </Tag>
              )}
            </Space>

            {tags.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <Space wrap size={[6, 6]}>
                  {tags.map((t) => <Tag key={t} style={{ margin: 0 }}>{t}</Tag>)}
                </Space>
              </div>
            )}

            <Divider style={{ margin: '12px 0' }} />

            {/* 经理信息 */}
            <Descriptions column={2} size="small" style={{ fontSize: 13 }} labelStyle={{ opacity: 0.65 }}>
              {r.manager && <Descriptions.Item label="经理">{String(r.manager)}</Descriptions.Item>}
              {r.tenure_years != null && <Descriptions.Item label="任职年限">{Number(r.tenure_years).toFixed(1)} 年</Descriptions.Item>}
              {r.is_original != null && <Descriptions.Item label="是否原装">{Number(r.is_original) ? '是' : '否'}</Descriptions.Item>}
              {r.is_comanaged != null && <Descriptions.Item label="是否共管">{Number(r.is_comanaged) ? '是' : '否'}</Descriptions.Item>}
            </Descriptions>

            <Divider style={{ margin: '12px 0' }} />

            {/* 详细理由 */}
            <Space direction="vertical" style={{ width: '100%' }} size={10}>
              {r.skill_reason && (
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, opacity: 0.85 }}>归因理由</div>
                  <div style={{ fontSize: 13, lineHeight: 1.6, opacity: 0.8 }}>{String(r.skill_reason)}</div>
                </div>
              )}
              {r.concentration_reason && (
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, opacity: 0.85 }}>集中度分析</div>
                  <div style={{ fontSize: 13, lineHeight: 1.6, opacity: 0.8 }}>{String(r.concentration_reason)}</div>
                </div>
              )}
              {r.hard_thesis && (
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, opacity: 0.85 }}>硬实力逻辑</div>
                  <div style={{ fontSize: 13, lineHeight: 1.6, opacity: 0.8 }}>{String(r.hard_thesis)}</div>
                </div>
              )}
              {r.turnover_note && (
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, opacity: 0.85 }}>换手备注</div>
                  <div style={{ fontSize: 13, lineHeight: 1.6, opacity: 0.8 }}>{String(r.turnover_note)}</div>
                </div>
              )}
            </Space>

            {r.data_basis && (
              <>
                <Divider style={{ margin: '12px 0' }} />
                <div style={{ fontSize: 11, opacity: 0.45 }}>
                  数据依据：{String(r.data_basis)}
                  {r.model ? ` | 模型：${r.model}` : ''}
                </div>
              </>
            )}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '32px 0' }}>
            {parseError ? (
              <>
                <div style={{ color: '#ff4d4f', marginBottom: 12 }}>{parseError}</div>
                <pre style={{
                  maxHeight: 400, overflow: 'auto', margin: 0, padding: 12,
                  borderRadius: 6, fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                  background: 'var(--ant-color-bg-container)', color: 'var(--ant-color-text)',
                }}>
                  {streamText}
                </pre>
              </>
            ) : (
              <Spin />
            )}
          </div>
        )}
      </Modal>

      <Card
        size="small"
        title={
          <Space>
            <span>最新筛选基金（{latest.length}）</span>
            {newCount > 0 && <Tag color="green">新增 {newCount}</Tag>}
          </Space>
        }
      >
        <Table<FundItem>
          rowKey="code"
          size="small"
          loading={loading}
          dataSource={latest}
          columns={latestColumns}
          scroll={{ x: 2520 }}
          pagination={{
            current: latestCurrent,
            pageSize: latestPag.pageSize,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 只`,
            onChange: (current, pageSize) => setLatestPag({ current, pageSize }),
          }}
        />
      </Card>

      <Card
        size="small"
        title={
          <Space>
            <span>镜像基金（{filteredEffectiveItems.length}/{effectiveItems.length}）</span>
            {droppedCount > 0 && <Tag color="red">已剔除 {droppedCount}</Tag>}
            {snapshot && <span className="text-xs text-gray-400">镜像时间：{snapshot.created_at}</span>}
          </Space>
        }
      >
        {snapshot ? (
          <>
            {aiFilterBar}
            <Table<FundItem>
              rowKey="code"
              size="small"
              dataSource={filteredEffectiveItems}
              columns={effectiveColumns}
              scroll={{ x: 2400 }}
              pagination={{
                current: mirrorCurrent,
                pageSize: mirrorPag.pageSize,
                showSizeChanger: true,
                showTotal: (t) => `共 ${t} 只`,
                onChange: (current, pageSize) => setMirrorPag({ current, pageSize }),
              }}
            />
          </>
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无镜像，点上方「存为镜像」把当前筛选结果固化"
          />
        )}
      </Card>

      {snapshot && (
        <Card
          size="small"
          title={
            <Space>
              <StopOutlined style={{ color: '#ff4d4f' }} />
              <span>过滤名单（{filteredExcludedItems.length}/{filteredItems.length}）</span>
              <span className="text-xs text-gray-400">
                这些基金已从镜像剔除，聚类/仓位不纳入；可「移回」撤销
              </span>
            </Space>
          }
        >
          {filteredExcludedItems.length ? (
            <>
              {aiFilterBar}
              <Table<FundItem>
                rowKey="code"
                size="small"
                dataSource={filteredExcludedItems}
                columns={filteredColumns}
                scroll={{ x: 2320 }}
                pagination={false}
              />
            </>
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无过滤基金，可在上方镜像列表对 AI 评价较差的基金点「移入过滤」"
            />
          )}
        </Card>
      )}

      <FundDetailModal code={detailCode} open={detailCode !== null} onClose={() => setDetailCode(null)} />
      <NavTrendModal
        code={trend?.code ?? null}
        name={trend?.name}
        open={!!trend}
        onClose={() => setTrend(null)}
      />

      {/* 浮窗：记录 AI ReAct 分析过程与多轮进展 */}
      {(reactStatus === 'running' || reactStatus === 'done' || reactStatus === 'error') && (
        <AiReActPanel
          fundCode={analyzingCode ?? ''}
          fundName={reactName}
          steps={reactSteps}
          status={reactStatus}
          elapsed={elapsed}
          error={reactError}
          onClose={() => {
            setReactStatus('idle')
            setReactSteps([])
            setReactError('')
          }}
        />
      )}

      {/* 提示词编辑抽屉 */}
      <Drawer
        title="AI 分析提示词"
        open={promptDrawerOpen}
        onClose={() => setPromptDrawerOpen(false)}
        width={640}
        extra={
          <Space>
            <Popconfirm
              title="恢复为仓库默认提示词？"
              description="将删除数据库里的覆盖，回落到 prompts/*.md 文件默认值。"
              onConfirm={handleResetPrompt}
              okText="恢复"
              cancelText="取消"
            >
              <Button>恢复默认</Button>
            </Popconfirm>
            <Button type="primary" onClick={handleSavePrompt}>
              保存
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Text strong style={{ display: 'block', marginBottom: 8 }}>System Prompt（系统指令）</Text>
            <TextArea
              rows={4}
              value={promptSystem}
              onChange={(e) => setPromptSystem(e.target.value)}
              placeholder="系统级指令，如：只输出 JSON..."
            />
          </div>
          <div>
            <Text strong style={{ display: 'block', marginBottom: 8 }}>
              User Prompt Template（分析指令模板，__BUNDLE_JSON__ 会被替换为数据包）
            </Text>
            <TextArea
              rows={20}
              value={promptUser}
              onChange={(e) => setPromptUser(e.target.value)}
              placeholder="分析指令 + 字段定义..."
              style={{ fontFamily: 'monospace', fontSize: 12 }}
            />
          </div>
        </Space>
      </Drawer>
    </Space>
  )
}
