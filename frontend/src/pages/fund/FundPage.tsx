import { useState } from 'react'
import { Space } from 'antd'
import { useFundData } from './hooks/useFundData'
import FundQueryCard from './FundQueryCard'
import PresetPanel from './components/PresetPanel'
import DataFetchPanel from './components/DataFetchPanel'
import FundDetailModal from './components/FundDetailModal'

export default function FundPage() {
  const data = useFundData()
  const [detailCode, setDetailCode] = useState<string | null>(null)

  return (
    <Space direction="vertical" className="w-full" style={{ width: '100%' }} size="middle">
      <PresetPanel
        presets={data.presets}
        activeId={data.activePresetId}
        onApply={data.applyPreset}
        onRename={data.renamePreset}
        onDelete={data.deletePreset}
        onClear={data.clearPreset}
      />

      <FundQueryCard
        funds={data.funds}
        total={data.total}
        loading={data.loading}
        page={data.page}
        pageSize={data.pageSize}
        filters={data.filters}
        fundTypes={data.fundTypes}
        onFiltersChange={data.setFilters}
        onPageChange={(p, ps) => {
          data.setPage(p)
          data.setPageSize(ps)
        }}
        onSortChange={data.setSorters}
        onSearch={() => {
          data.setPage(1)
          data.fetchFunds()
        }}
        onReset={() => {
          data.setFilters({})
          data.setSorters([])
          data.setPage(1)
          data.clearPreset()
        }}
        onOpenDetail={setDetailCode}
        activePreset={data.activePreset}
        dirty={data.dirty}
        onSavePreset={data.savePreset}
        onUpdatePreset={data.updateActivePreset}
      />

      <DataFetchPanel
        activePreset={data.activePreset}
        hasConditions={(data.filters.conditions?.length ?? 0) > 0}
        detailTask={data.detailTask}
        holdingsTask={data.holdingsTask}
        navTask={data.navTask}
        onStart={data.startTask}
        onTerminate={data.terminateTask}
        onSync={data.syncFundList}
        syncing={data.loading}
      />

      <FundDetailModal
        code={detailCode}
        open={detailCode !== null}
        onClose={() => setDetailCode(null)}
      />
    </Space>
  )
}
