// 聚类分析页的数据结构（对应后端 /api/cluster/run 返回）

export interface ClusterIndustry {
  label: string
  ratio: number
}

export interface SignatureStock {
  code: string
  name: string
  industry: string
  overlap: number
  edge: number
}

export interface SecondaryStock {
  code: string
  name: string
  industry: string
  overlap: number
}

export interface Holding {
  code: string
  name: string
  ratio: number
  industry: string
}

export interface ClusterFund {
  code: string
  name: string
  score: number
  sharpe_3y: number | null
  scale: number | null
  holdings: Holding[]
}

export interface CapitalStock {
  code: string
  name: string
  industry: string
  overlap: number
  mv_yi: number
  mv_pct: number
}

export interface CapitalExposure {
  total_yi: number
  stocks: CapitalStock[]
}

export interface Cluster {
  cluster_id: number
  name: string
  top_industries: ClusterIndustry[]
  signature_stocks: SignatureStock[]
  secondary_stocks: SecondaryStock[]
  capital_exposure: CapitalExposure
  fund_count: number
  funds: ClusterFund[]
}

export interface ClusterMeta {
  n: number
  dropped: number
  total: number
  t: number
  target: number
  share_merged?: number   // 入口合并的 A/C/E 等同基金多份额数
}

export interface ClusterResult {
  clusters: Cluster[] | null
  meta?: ClusterMeta
  reason?: string
}
