请对以下基金做历史穿透定性分析，回答三个核心问题：
① 靠运气还是硬实力（先做经理归因，再看业绩）
② 是否单押赛道（看持仓漂移趋势，不只看当下）
③ 有无可复用硬逻辑

可使用工具 `inspect_dimension` 按维度核验数据（attribution/holdings/nav/profile/caveats），
推理要充分、逐维确认后再输出最终 JSON 对象。

═══════════════════════════════════════
一、数据包字段速览
═══════════════════════════════════════

- meta：名称/类型/公司/成立日/规模(亿)/投资策略摘要
- metrics：return/sharpe/max_drawdown/volatility/rank 各周期(ytd/1y/3y/5y)，position_stock/bond
  ⚠️ 这些是全历史指标，不区分是谁做的——归因交给 manager 区块
- manager（归因核心）：
  - current/current_lead/is_comanaged：当前团队、主理人、是否共管
  - exact_team_since/exact_team_years：当前完全相同团队连续在任起始日与年限
  - lead_since/lead_years：主理人连续在任起始（容忍共管更替）
  - exact_team_covers/lead_covers：{1y,3y,5y} 各布尔——业绩窗口是否被当前团队/主理人任期覆盖
  - segment_count/distinct_team_count：任职段数/不同团队组合数（>1=历史换过团队）
  - recent_segments：最近若干段（起止/经理/任职天数/任职回报%）
- holdings（漂移+赛道判断核心，跨5季度）：
  - quarters[]：每季 top1/top3_ratio/top5_ratio/top10_ratio/hhi_top10/num_stock/report_type
    及行业结构：sw_l1_mix/top_l1/top_l1_share/distinct_l1_top10/theme_mix/top_theme/top_theme_share
  - consecutive_top10_overlap[]：相邻季前十大重合只数（低=高换手/交易型）
  - concentration_trend_top10：上升/平稳/下降
  - dominant_theme_by_quarter：逐季最大主题序列
  - distinct_dominant_theme/theme_concentration_trend(收敛/稳定/发散)
  - sector_focus：赛道定性线索（单一主题高度集中/单一主题主导/主题轮动/多行业分散）
  - latest_top10_detail：最新一季前十大明细 [{name,l1,theme,l3,ratio}]
  - latest_top10_ratio/latest_top1/latest_top_theme/latest_top_theme_share/latest_distinct_l1
- nav_regime：return_last_1y/3y、return_since_current_team（当前团队上任以来净收益）
- data_caveats：数据局限（必须纳入判断并降置信度）

═══════════════════════════════════════
二、判断规则
═══════════════════════════════════════

【问① 靠运气还是实力——先归因再打分】

归因优先级（判断 sharpe_3y/5y、return_3y/5y、rank 时先看落在谁的任期里）：
1. exact_team_covers[窗口]=true → 该窗口业绩完全归当前团队，可据此给实力分
2. exact_team_covers=false 但 lead_covers[窗口]=true → 主理人在但共管换过人：
   业绩部分归主理人，skill_reason 注明共管更替(distinct_team_count)，confidence 至多 medium
3. 两者皆 false（现任是接任）→ 长周期指标不算现任功劳：
   - 不得用 3y/5y 高 sharpe/排名抬 skill_score
   - 改用 return_since_current_team + 1y 指标评估现任
   - 现任 exact_team_years < 2 → style_stability=unproven、confidence=low

运气信号（压低 skill_score、luck_verdict 趋向 luck）：
- 业绩集中来自单一风口主题且该主题恰好近一两年爆发
- 长周期指标好但不归现任（接任者蹭前任余荫）
- distinct_team_count 大、团队频繁更替，业绩连续性存疑
- 最新季 top_theme_share ≥55% 且该主题恰好是近1-2年市场热点（如AI/新能源/周期资源）

实力信号（抬 skill_score、趋向 solid）：
- 有归属现任的够长(≥3y)任期，且该期内 sharpe/排名稳定靠前
- 超额不依赖单一主题（行业不单押、重仓有轮动但逻辑清晰）
- 跨不同市场环境仍兑现（看 recent_segments 各段任职回报稳健度）
- 持仓风格稳定（consecutive_top10_overlap 持续≥6/10）

【问② 是否单押赛道——看历史漂移不只看当下】

用 quarters[] 的 top10_ratio 序列 + concentration_trend_top10 + latest_top1 判断：
- single_bet：最新 top10_ratio ≳45% 或某主题连续多季霸榜且 trend=上升
  或 latest_top_theme_share ≥55%（即使历史分散，当前已漂移成单押）
- focused：适度集中（top10_ratio 约30-45%），行业不单押
- diversified：top10_ratio ≲30% 且分散

关键场景：同一经理但持仓从分散漂移成单押（top10_ratio 明显上行+单一主题霸榜）→
判 single_bet 或 focused，concentration_reason 写明「同一经理、风格漂移集中」，
若集中是无补偿押注（波动/回撤放大而超额不稳）则压低 rating。

consecutive_top10_overlap 辅判换手：重合持续偏低(≤4/10) → 交易型/高换手 →
style_stability=volatile、写 turnover_note。

【问②' fund_kind——一律以持仓行业结构判定，绝不看基金名/契约】

基金名与契约只是线索；与实际持仓冲突时以持仓为准。
例：某「消费优选」前十大横跨8个申万一级、最大主题占比仅46%
→ 不是消费赛道基而是选股型。

- sector：某大主题长期居首且当前仍集中——dominant_theme_by_quarter 基本同一主题，
  且最新 top_theme_share ≳55%、distinct_l1_top10 ≲4（sector_focus 多为赛道特征/赛道倾向）
- rotation：主导主题跨季切换（dominant_theme_by_quarter 有≥2个不同值，
  各季 top_theme_share 仍偏高）
- subjective：横跨多个申万一级、无单一主题过半——
  最新 distinct_l1_top10 ≥6~8、top_theme_share <50%。
  即便基金名含赛道词也判 subjective，
  在 concentration_reason/hard_thesis 点明「名不符实、实为选股型」

结合 theme_concentration_trend 看漂移：
- 名义赛道基但主题占比发散(更分散) → 正松绑为选股型，勿再判 sector
- 名义宽基/选股但主题占比收敛(更集中) → 正漂移成赛道单押，fund_kind 趋 sector

fund_kind 与 concentration 是两件事：fund_kind 看行业主题结构，concentration 看权重集中度。
「单一主题+高权重集中」= sector + single_bet；「多主题+权重分散」= subjective + diversified。

【问③ 有无可复用硬逻辑】

hard_thesis 写能力来源是否可解释、可复用：选股/行业轮动/风控/长期任职兑现。
若业绩主要靠单主题 β 或接任余荫，明说「硬逻辑不足/存疑」。

═══════════════════════════════════════
二'、硬性约束（必须遵守，覆盖主观判断）
═══════════════════════════════════════

以下规则优先级高于主观判断，违反时必须在 skill_reason 中说明理由：

1. **风格漂移硬约束**：
   - style_stability=volatile → rating ≤ 1（除非 skill_score ≥80 且 luck_verdict=solid）
   - consecutive_top10_overlap 连续多季 ≤3/10 → style_stability 必须为 volatile

2. **单一主题硬约束**：
   - latest_top_theme_share ≥65% → concentration 必须为 single_bet
   - latest_top_theme_share ≥55% 且 fund_kind=sector → skill_score ≤ 70（除非任期≥5y 且跨周期验证）

3. **运气归因硬约束**：
   - luck_verdict=luck → rating ≤ 1，recommend 必须为 0
   - luck_verdict=mixed → rating ≤ 2

4. **任期与样本硬约束**：
   - exact_team_years < 2 → confidence 必须为 low 或 medium，style_stability 必须为 unproven
   - exact_team_years < 1 → rating ≤ 1，recommend 必须为 0

5. **推荐硬约束**：
   - recommend=1 要求：rating ≥ 2 且 luck_verdict ∈ {solid, mixed} 且 style_stability ≠ volatile
   - 若 concentration=single_bet 且 fund_kind=sector → recommend 必须为 0（除非任期≥5y 且风格稳定）

6. **评级刻度硬锚定**：
   - rating=3：skill_score ≥80 且 style_stability=stable 且 luck_verdict=solid 且 recommend=1
   - rating=0：skill_score < 45 或 luck_verdict=luck 或 style_stability=unproven 且 confidence=low

═══════════════════════════════════════
三、打分刻度（skill_score 0-100，锚定归因）
═══════════════════════════════════════

- **85-100（卓越）**：任期≥5y 且跨越多轮牛熊；持仓风格稳定（overlap≥6/10）；
  超额不依赖单一主题（top_theme_share<50%）；sharpe_3y 同类前 20%
  例：张坤（易方达蓝筹）、朱少醒（富国天惠）级别
- **75-84（优秀）**：任期≥3y 且排名稳定靠前；持仓适度集中但不单押；
  超额部分可归因于选股或行业轮动能力
- **60-74（良好）**：数据不错但有以下之一：归属期偏短（2-3y）、超额部分来自风口/单押、
  主理在而共管频繁更替、风格有漂移迹象但业绩尚可
- **45-59（一般）**：任期<3y 或长周期指标不归现任；或靠单一热门主题且集中度上行；
  或风格漂移明显（overlap≤4/10 持续多季）
- **30-44（较差）**：接任者蹭前任余荫；或单押赛道且无补偿（回撤大、超额不稳）；
  或样本严重不足（<2y）
- **0-29（不推荐）**：任期<1y；或 luck_verdict=luck；或数据严重不足

**rating(0-3) 综合判定**（必须遵守硬性约束）：
- **rating=3（强烈推荐）**：skill_score≥80 + style_stability=stable + luck_verdict=solid + recommend=1
- **rating=2（推荐）**：skill_score≥60 + style_stability∈{stable,volatile但skill≥75} + luck_verdict∈{solid,mixed}
- **rating=1（观望）**：skill_score 45-74 但有明显瑕疵（风格漂移/单一主题/任期短）
- **rating=0（不推荐）**：skill_score<45 或 luck_verdict=luck 或 style_stability=unproven+confidence=low

**recommend(0/1) 判定**：
- recommend=1 必须同时满足：rating≥2 + luck_verdict≠luck + style_stability≠volatile（除非 skill≥80）
- 单押赛道（concentration=single_bet + fund_kind=sector）→ recommend=0（除非任期≥5y 且风格稳定）

═══════════════════════════════════════
四、输出字段（严格匹配，枚举只能取给定值）
═══════════════════════════════════════

| 字段 | 类型 | 说明 |
|------|------|------|
| verdict | string | 一句话总评，点明归因 |
| rating | int | 0-3 |
| recommend | int | 0或1 |
| skill_score | int | 0-100（按第三节刻度） |
| luck_verdict | string | solid/mixed/luck |
| skill_reason | string | 必须写归因：用了哪个窗口、归谁、覆盖与否 |
| concentration | string | single_bet/focused/diversified |
| concentration_reason | string | 引top10_ratio序列/趋势/第一大；同经理漂移集中务必点明 |
| fund_kind | string | subjective/rotation/sector（按持仓行业结构判，禁止看基金名） |
| hard_thesis | string | 能力来源是否可复用 |
| manager | string | 当前经理 = manager.current |
| tenure_years | float | 当前团队年限 = manager.exact_team_years |
| is_original | int | 0/1，当前团队是否自成立起就管 |
| is_comanaged | int | 0/1，是否共管 |
| scale_risk | string | tiny(<~1亿清盘险)/small/ok/large(过大恐平庸) |
| style_stability | string | stable/volatile(漂移/交易型)/unproven(样本不足) |
| turnover_note | string | 换手风格（引consecutive_top10_overlap） |
| tags | string[] | 如["接任","单主题","光模块"] |
| confidence | string | high/medium/low（归因不实/样本短→降） |
| model | string | 你的模型名 |
| data_basis | string | 用了哪些区块/区间（务必含归因窗口与持仓覆盖季度） |

═══════════════════════════════════════
五、填充准则
═══════════════════════════════════════

- 样本不足别硬下结论：任职<2年或净值历史短 → style_stability=unproven、
  confidence=low，skill_reason 注明样本短
- 区分经理与基金：同一经理在不同基金可能原装/接任/共管不同，锚点按这只基金填
- 接任要标注：现任非原装 → verdict/skill_reason 写明「接任」并谨慎给 skill_score
- 小规模警惕清盘：规模<~1亿 → scale_risk=tiny 并在 verdict 提示清盘风险
- 大规模警惕平庸：规模很大但任职回报平平 → scale_risk=large，
  hard_thesis 说明是否被规模拖累
- 务必填 data_basis 与 model：保证结论可追溯、可重跑
- data_caveats 若存在须纳入判断并降 confidence

═══════════════════════════════════════
六、数据包
═══════════════════════════════════════

__BUNDLE_JSON__

请分析并输出 JSON 对象。