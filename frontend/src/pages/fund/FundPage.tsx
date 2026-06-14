import { useState } from 'react'
import { Button, Col, Row, Space } from 'antd'
import { useFundData } from './hooks/useFundData'
import FundQueryCard from './FundQueryCard'
import PresetPanel from './components/PresetPanel'
import DataTaskCard from './components/DataTaskCard'
import FundDetailModal from './components/FundDetailModal'

export default function FundPage() {
  const data = useFundData()
  const [detailCode, setDetailCode] = useState<string | null>(null)

  return (
    <Space direction="vertical" className="w-full" style={{ width: '100%' }} size="middle">
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <DataTaskCard
            title="详情拉取"
            module="fund_detail"
            task={data.detailTask}
            onStart={data.startTask}
            onTerminate={data.terminateTask}
          />
        </Col>
        <Col xs={24} md={8}>
          <DataTaskCard
            title="持仓拉取"
            module="fund_holdings"
            task={data.holdingsTask}
            onStart={data.startTask}
            onTerminate={data.terminateTask}
          />
        </Col>
        <Col xs={24} md={8}>
          <DataTaskCard
            title="净值拉取"
            module="fund_nav"
            task={data.navTask}
            onStart={data.startTask}
            onTerminate={data.terminateTask}
          />
        </Col>
      </Row>

      <Space>
        <Button onClick={data.syncFundList} loading={data.loading}>
          同步基金名单
        </Button>
      </Space>

      <PresetPanel
        presets={data.presets}
        onSave={data.savePreset}
        onApply={data.applyPreset}
        onOverwrite={data.overwritePreset}
        onDelete={data.deletePreset}
        onFetch={(preset, module) => data.startTaskWith(module, preset.filters ?? {})}
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
        }}
        onOpenDetail={setDetailCode}
      />

      <FundDetailModal
        code={detailCode}
        open={detailCode !== null}
        onClose={() => setDetailCode(null)}
      />
    </Space>
  )
}
