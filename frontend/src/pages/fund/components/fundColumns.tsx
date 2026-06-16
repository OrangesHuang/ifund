import { Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import Sparkline from './Sparkline'
import type { FundItem, HoldingItem } from '../types'

export function num(v: unknown): string {
  if (v === null || v === undefined) return '-'
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(2) : String(v)
}

export function ratio(v: number | null | undefined): string {
  return v === null || v === undefined ? '' : `${Number(v).toFixed(2)}%`
}

/** 前十大持仓列：按类型（股票/债券）过滤，默认显示第一大，悬停 Tooltip 展示完整前十。 */
export function renderHoldings(
  holdings: HoldingItem[] | undefined,
  type: 'stock' | 'bond' = 'stock',
) {
  const label = type === 'stock' ? '重仓股' : '重仓债'
  const list = (holdings ?? []).filter((h) => h.holding_type === type)
  if (!list.length) return <span className="text-gray-500">-</span>
  const top = list[0]
  const content = (
    <div style={{ maxWidth: 240 }}>
      <div className="mb-1 text-xs text-gray-400">前十大{label} · {top.quarter}</div>
      {list.map((h, i) => (
        <div key={`${h.asset_code}-${i}`} className="flex justify-between gap-4 text-xs leading-5">
          <span className="truncate">
            {i + 1}. {h.asset_name || h.asset_code}
          </span>
          <span className="shrink-0 tabular-nums">{ratio(h.hold_ratio)}</span>
        </div>
      ))}
    </div>
  )
  return (
    <Tooltip title={content} placement="left" autoAdjustOverflow getPopupContainer={() => document.body}>
      <span className="cursor-default">
        {top.asset_name || top.asset_code}
        {top.hold_ratio != null && <span className="ml-1 text-gray-400">{ratio(top.hold_ratio)}</span>}
      </span>
    </Tooltip>
  )
}

interface ColumnOptions {
  // 返回 true 表示该列可排序（由调用方根据后端白名单决定）
  sortable?: (field: string) => true | undefined
  onOpenDetail?: (code: string) => void
  // 点击净值走势迷你图：打开交互式大图（带十字准星）
  onOpenTrend?: (code: string, name: string) => void
  // 是否展示净值走势迷你图（镜像快照无净值序列时可关闭）
  showNav?: boolean
}

/** 基金详情结果列：基金筛选页与基金管理页共用，保证列与渲染一致。 */
export function buildFundColumns(opts: ColumnOptions = {}): ColumnsType<FundItem> {
  const { sortable, onOpenDetail, onOpenTrend, showNav = true } = opts
  const sorter = (field: string) => (sortable ? sortable(field) : undefined)
  const columns: ColumnsType<FundItem> = [
    { title: '代码', dataIndex: 'code', width: 90 },
    {
      title: '名称',
      dataIndex: 'name',
      width: 200,
      render: (v: string, row) =>
        onOpenDetail ? <a onClick={() => onOpenDetail(row.code)}>{v}</a> : v,
    },
    { title: '类型', dataIndex: 'type', width: 120 },
    { title: '规模', dataIndex: 'scale', width: 100, sorter: sorter('scale'), render: num },
    { title: '今年收益', dataIndex: 'return_ytd', width: 100, sorter: sorter('return_ytd'), render: num },
    { title: '今年回撤', dataIndex: 'drawdown_ytd', width: 100, sorter: sorter('drawdown_ytd'), render: num },
    { title: '夏普3年', dataIndex: 'sharpe_3y', width: 100, sorter: sorter('sharpe_3y'), render: num },
    { title: '夏普1年', dataIndex: 'sharpe_1y', width: 100, sorter: sorter('sharpe_1y'), render: num },
    { title: '回撤3年', dataIndex: 'max_drawdown_3y', width: 100, sorter: sorter('max_drawdown_3y'), render: num },
    { title: '回撤1年', dataIndex: 'max_drawdown_1y', width: 100, render: num },
    { title: '股票仓位', dataIndex: 'position_stock', width: 100, sorter: sorter('position_stock'), render: num },
    { title: '债券仓位', dataIndex: 'position_bond', width: 100, render: num },
    {
      title: '前十大股票持仓',
      key: 'holdings_stock',
      dataIndex: 'holdings',
      width: 160,
      ellipsis: true,
      render: (holdings: HoldingItem[] | undefined) => renderHoldings(holdings, 'stock'),
    },
    {
      title: '前十大债券持仓',
      key: 'holdings_bond',
      dataIndex: 'holdings',
      width: 160,
      ellipsis: true,
      render: (holdings: HoldingItem[] | undefined) => renderHoldings(holdings, 'bond'),
    },
  ]
  if (showNav) {
    columns.push({
      title: '净值走势',
      dataIndex: 'nav_series',
      width: 120,
      fixed: 'right',
      render: (series: number[] | undefined, row) =>
        onOpenTrend ? (
          <span
            onClick={() => onOpenTrend(row.code, row.name)}
            style={{ cursor: 'pointer' }}
            title="点击查看交互式净值走势"
          >
            <Sparkline data={series ?? []} width={104} height={30} />
          </span>
        ) : (
          <Sparkline data={series ?? []} width={104} height={30} />
        ),
    })
  }
  return columns
}
