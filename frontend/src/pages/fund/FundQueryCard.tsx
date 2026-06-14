import { Button, Card, Collapse, Input, Select, Space, Table } from 'antd'
import type { SorterResult } from 'antd/es/table/interface'
import MultiCompareFilter from './components/MultiCompareFilter'
import FundExcludeSelect from './components/FundExcludeSelect'
import { buildFundColumns } from './components/fundColumns'
import type {
  CompareCondition,
  Filters,
  FundItem,
  FundTypeItem,
  SortInfo,
} from './types'

interface Props {
  funds: FundItem[]
  total: number
  loading: boolean
  page: number
  pageSize: number
  filters: Filters
  fundTypes: FundTypeItem[]
  onFiltersChange: (f: Filters) => void
  onPageChange: (page: number, pageSize: number) => void
  onSortChange: (sorters: SortInfo[]) => void
  onSearch: () => void
  onReset: () => void
  onOpenDetail: (code: string) => void
}

// 后端 allowed_sort_fields 对应的可排序列
const SORTABLE = new Set([
  'scale',
  'return_ytd',
  'drawdown_ytd',
  'sharpe_3y',
  'sharpe_1y',
  'max_drawdown_3y',
  'position_stock',
])

export default function FundQueryCard({
  funds,
  total,
  loading,
  page,
  pageSize,
  filters,
  fundTypes,
  onFiltersChange,
  onPageChange,
  onSortChange,
  onSearch,
  onReset,
  onOpenDetail,
}: Props) {
  const sortable = (field: string) => (SORTABLE.has(field) ? true : undefined)

  const columns = buildFundColumns({ sortable, onOpenDetail, showNav: true })

  const handleTableChange = (
    _pagination: unknown,
    _filters: unknown,
    sorter: SorterResult<FundItem> | SorterResult<FundItem>[],
  ) => {
    const arr = Array.isArray(sorter) ? sorter : [sorter]
    const sorters: SortInfo[] = arr
      .filter((s) => s.field && s.order)
      .map((s) => ({
        field: String(s.field),
        order: s.order === 'ascend' ? 'asc' : 'desc',
      }))
    onSortChange(sorters)
  }

  const setConditions = (conditions: CompareCondition[]) =>
    onFiltersChange({ ...filters, conditions })

  return (
    <Card title="基金筛选" size="small">
      <Space direction="vertical" className="w-full" style={{ width: '100%' }} size="middle">
        <Space wrap>
          <Input
            placeholder="代码/名称关键字"
            value={filters.keyword}
            onChange={(e) => onFiltersChange({ ...filters, keyword: e.target.value })}
            onPressEnter={onSearch}
            style={{ width: 200 }}
            allowClear
          />
          <Select
            mode="multiple"
            placeholder="基金类型"
            value={filters.fund_types}
            onChange={(v) => onFiltersChange({ ...filters, fund_types: v })}
            options={fundTypes.map((t) => ({ label: t.type_name, value: t.type_name }))}
            style={{ minWidth: 200 }}
            allowClear
          />
          <Button type="primary" onClick={onSearch} loading={loading}>
            查询
          </Button>
          <Button onClick={onReset}>清空</Button>
        </Space>

        <Collapse
          size="small"
          items={[
            {
              key: 'adv',
              label: '高级筛选（条件 / 排除）',
              children: (
                <Space direction="vertical" className="w-full" style={{ width: '100%' }}>
                  <MultiCompareFilter value={filters.conditions ?? []} onChange={setConditions} />
                  <FundExcludeSelect
                    codes={filters.exclude_codes ?? []}
                    names={filters.name_excludes ?? []}
                    onCodesChange={(v) => onFiltersChange({ ...filters, exclude_codes: v })}
                    onNamesChange={(v) => onFiltersChange({ ...filters, name_excludes: v })}
                  />
                </Space>
              ),
            },
          ]}
        />

        <Table<FundItem>
          rowKey="code"
          size="small"
          loading={loading}
          dataSource={funds}
          columns={columns}
          onChange={handleTableChange}
          scroll={{ x: 1340 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 只`,
            onChange: onPageChange,
          }}
        />
      </Space>
    </Card>
  )
}
