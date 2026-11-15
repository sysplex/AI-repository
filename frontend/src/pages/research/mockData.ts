import type { ResearchEnvelope } from '../../api/types';

export const MOCK_RESEARCH_DATA: Record<string, ResearchEnvelope> = {
  NVDA: {
    schema_version: '1.0',
    use_case: 'research',
    symbol: 'NVDA',
    as_of: new Date().toISOString().split('T')[0],
    summary:
      '英伟达（NVDA）是全球加速计算与生成式 AI 算力无可争议的领导者，凭借 CUDA 软件生态壁垒形成极高转换成本，短期受数据中心 Capex 驱动景气高涨，中长期需关注下游客户自研 ASIC 与供应链多元化风险。',
    payload: {
      business_model:
        '以 GPU 加速芯片、网络交换互联（Infiniband/Spectrum-X）及 CUDA 全栈软件库构成的完整 AI 工厂基础设施提供商。收入核心来自 Compute & Networking（占比 >85%）。',
      moat: '生态级网络效应与极高开发者转换成本。全球数百万 AI/CUDA 开发者与底层框架深度绑定，CUDA 库经过 18 年沉淀形成软硬件协同的深厚护城河。',
      risks: [
        '超大规模云厂商（CSP）自研加速芯片（TPU, Trainium, Maia）在中长期的替代压力',
        '地缘政治出口管制限制带来的特定市场收入份额波动',
        '高基数下半导体周期性 Capex 资本开支放缓的潜在估值回调',
      ],
      bull_case:
        '下一代 Blackwell 架构架构算力集群放量超预期，企业级 AI 软件生态变现提速，毛利率维持在 75% 以上，市值持续领跑全球。',
      bear_case:
        '云厂商 AI 投资回报率（ROI）不及预期导致算力采购缩水，竞争对手推出高性价比替代方案，毛利率承压回落至 65% 以下。',
      neutral_case:
        '未来 2–3 年数据中心收入保持 20%–30% 稳健复合增速，成为全球数字化 AI 算力公用事业底座，估值维持在合理分位数区间。',
      valuation: {
        pe_ttm: 54.2,
        forward_pe: 36.8,
        ps_ratio: 28.5,
        dcf_fair_value: 155.0,
        margin_of_safety_pct: 6.2,
      },
    },
    evidence: [
      {
        claim: 'Data Center Revenue reached record high',
        source_field: 'facts.segments.datacenter.revenue',
      },
      {
        claim: 'Gross Margin remained above 75%',
        source_field: 'facts.financials.gross_margin',
      },
    ],
    data_gaps: ['下游终端应用客户的真实算力利用率数据缺失'],
    disclaimer: '本内容仅供研究与模拟学习，不构成任何投资建议。市场有风险，投资需谨慎。',
  },
};

export const MOCK_BUY_DECISION_DATA: Record<string, ResearchEnvelope> = {
  NVDA: {
    schema_version: '1.0',
    use_case: 'buy_decision',
    symbol: 'NVDA',
    as_of: new Date().toISOString().split('T')[0],
    summary:
      '当前价格接近公允价值区间上限，建议采取定投或回调买入策略（BUY ON PULLBACK），设定目标入场区间并在 $135 附近建立核心底仓。',
    payload: {
      verdict: 'BUY',
      confidence_score: 86,
      current_price: 145.89,
      target_price: 140.0,
      margin_of_safety: 9.8,
      suggested_entry_range: [136.0, 142.0],
      max_downside_risk: '-16.5% (支撑位参考 $122.00)',
      key_catalysts: [
        'Blackwell B200 全球算力集群第四季度交付进度公告',
        '主要云厂商（微软、Meta、亚马逊）最新季度 AI 资本开支指引上修',
        '自研企业级端侧 AI 模型与工业数字化订单落地',
      ],
      actionable_plan:
        '首批仓位（30%）可于现价小额建仓，第二批加仓（40%）挂单于 $138.00 支撑位，若跌破 $128.00 触发防御性观望。',
    },
    evidence: [
      {
        claim: 'Current Price is $145.89',
        source_field: 'facts.market.price',
      },
    ],
    data_gaps: [],
    disclaimer: '本内容仅供研究与模拟学习，不构成任何投资建议。市场有风险，投资需谨慎。',
  },
};

export const MOCK_EARNINGS_DATA: Record<string, ResearchEnvelope> = {
  NVDA: {
    schema_version: '1.0',
    use_case: 'earnings',
    symbol: 'NVDA',
    as_of: new Date().toISOString().split('T')[0],
    summary:
      '最新季度财报全面超市场预期（Double Beat），数据中心业务单季营收创新高，未来季度业绩指引维持强劲增长动能。',
    payload: {
      quarter: 'FY2026 Q3',
      report_date: '2026-11-12',
      eps: {
        actual: 0.81,
        estimate: 0.75,
        surprise_percent: 8.0,
        beat: true,
      },
      revenue: {
        actual: 35.08, // in Billions
        estimate: 33.16,
        surprise_percent: 5.79,
        beat: true,
      },
      guidance: {
        status: 'raised',
        details:
          '预计下一季度营收达 $37.5B（±2%），超出华尔街共识预期的 $37.0B，毛利率预计维持在 73.5%–74.5% 高位区间。',
      },
      key_takeaways: [
        '数据中心单季营收同比增长 112%，AI 基础设施需求持续供不应求',
        '网络业务营收达 $3.12B，Spectrum-X 以太网交换机渗透率大幅提升',
        '现金及有价证券储备达 $38.5B，当季向股东回购股票 $11.0B',
      ],
      historical_trend: [
        { quarter: 'Q4 25', eps: 0.52, rev: 22.1 },
        { quarter: 'Q1 26', eps: 0.61, rev: 26.04 },
        { quarter: 'Q2 26', eps: 0.68, rev: 30.04 },
        { quarter: 'Q3 26', eps: 0.81, rev: 35.08 },
      ],
    },
    evidence: [],
    data_gaps: [],
    disclaimer: '本内容仅供研究与模拟学习，不构成任何投资建议。市场有风险，投资需谨慎。',
  },
};

export const MOCK_LONG_TERM_DATA: Record<string, ResearchEnvelope> = {
  NVDA: {
    schema_version: '1.0',
    use_case: 'long_term',
    symbol: 'NVDA',
    as_of: new Date().toISOString().split('T')[0],
    summary:
      '5–10 年长期持有评级为 Tier 1 核心压舱石标的，在护城河与行业跑道维度获得全满分评价，唯一需要防范的论文破裂条件为外部生态框架彻底颠覆 CUDA 垄断。',
    payload: {
      rating: 'Tier 1 核心压舱石',
      score: 93,
      years: 5,
      pillars: [
        {
          name: '商业模式与可持续性',
          score: 95,
          tier: 'A+',
          rationale: '全栈软硬件一体化，算力芯片+网络互联+CUDA生态三位一体变现闭环。',
        },
        {
          name: '经济护城河深度',
          score: 98,
          tier: 'A+',
          rationale: 'CUDA 18 年累积全球开发者粘性，跨架构移植成本极高，软硬护城河极深。',
        },
        {
          name: '行业发展跑道 (TAM)',
          score: 96,
          tier: 'A+',
          rationale: '全球数据中心数万亿美元存量硬件替换与主权 AI、具身智能驱动长期跑道。',
        },
        {
          name: '资本配置与管理层',
          score: 92,
          tier: 'A',
          rationale: '创始人 Jensen Huang 战略前瞻极强，研发投入占收比高，大规模回购回报股东。',
        },
        {
          name: '资产负债表与财务堡垒',
          score: 90,
          tier: 'A',
          rationale: '净现金储备充裕，零流动性危机风险，经营现金流充沛。',
        },
        {
          name: '估值合理性与安全边际',
          score: 82,
          tier: 'B+',
          rationale: '市盈率处于近三年中位数附近，需靠持续高增长消化估值倍数。',
        },
        {
          name: '反脆弱性与适应力',
          score: 94,
          tier: 'A+',
          rationale: '即使宏观经济放缓，AI 降本增效刚性需求依然支撑算力底座升级。',
        },
      ],
      thesis_breakers: [
        {
          condition: '主流大模型框架（如 PyTorch / JAX）实现真正跨芯片无缝热迁移，CUDA 转换成本降为零',
          severity: 'CRITICAL',
          monitoring_metric: '非 CUDA 加速芯片在大模型训练集群中的部署比例（警戒阈值 >25%）',
        },
        {
          condition: 'CSP 自研定制专用 ASIC（TPU / Trainium）成本性能比大幅压倒通用 GPU 算力集群',
          severity: 'HIGH',
          monitoring_metric: '三大云厂商自研芯片在内部算力开支的占比（警戒阈值 >40%）',
        },
        {
          condition: '数据中心毛利率连续两季度失守 60% 红线',
          severity: 'WARNING',
          monitoring_metric: '公司官方季报 GAAP 毛利率变化曲线',
        },
      ],
      recommendation:
        '建议作为成长型/科技主题投资组合的压舱石核心配置，持有周期建议 5 年以上，定期每季度核对 3 条论文破裂条件。',
    },
    evidence: [],
    data_gaps: [],
    disclaimer: '本内容仅供研究与模拟学习，不构成任何投资建议。市场有风险，投资需谨慎。',
  },
};

export const MOCK_COMPARE_DATA: ResearchEnvelope = {
  schema_version: '1.0',
  use_case: 'compare',
  symbol: 'NVDA,MSFT,AAPL',
  as_of: new Date().toISOString().split('T')[0],
  summary:
    '横向对比显示：NVDA 在算力增长与护城河爆发力最强；MSFT 在商业化软件生态与综合抗风险能力最均衡；AAPL 在现金流稳健度与股东回报最为深厚。',
  payload: {
    symbols: ['NVDA', 'MSFT', 'AAPL'],
    winner: {
      overall: 'MSFT',
      growth: 'NVDA',
      value: 'AAPL',
      profitability: 'NVDA',
      safety: 'MSFT',
    },
    rankings: [
      {
        symbol: 'MSFT',
        rank: 1,
        score: 92,
        suitable_for: '平衡型与长期稳健复合收益投资者',
        rationale: '企业云（Azure）+ Office 365 具备全行业最高商业定价权，AI 变现闭环最明确。',
      },
      {
        symbol: 'NVDA',
        rank: 2,
        score: 90,
        suitable_for: '进取型超额 alpha 追求者',
        rationale: 'AI 军备竞赛首要受益者，短期利润弹性最高，但波动率相对较大。',
      },
      {
        symbol: 'AAPL',
        rank: 3,
        score: 87,
        suitable_for: '价值防守型与高确定性分红回购爱好者',
        rationale: '20 亿活跃设备生态底座，极高自由现金流与巨额回购，Apple Intelligence 构筑渐进换机潮。',
      },
    ],
    dimension_matrix: [
      { dimension: '商业模式壁垒', scores: { NVDA: 95, MSFT: 94, AAPL: 93 } },
      { dimension: '未来三年复合增速', scores: { NVDA: 96, MSFT: 85, AAPL: 75 } },
      { dimension: '自由现金流质量', scores: { NVDA: 88, MSFT: 92, AAPL: 98 } },
      { dimension: '估值性价比', scores: { NVDA: 78, MSFT: 82, AAPL: 80 } },
      { dimension: '宏观抗周期韧性', scores: { NVDA: 80, MSFT: 95, AAPL: 92 } },
      { dimension: '股东回报与回购', scores: { NVDA: 82, MSFT: 88, AAPL: 97 } },
    ],
  },
  evidence: [],
  data_gaps: [],
  disclaimer: '本内容仅供研究与模拟学习，不构成任何投资建议。市场有风险，投资需谨慎。',
};

export const MOCK_PORTFOLIO_DATA: ResearchEnvelope = {
  schema_version: '1.0',
  use_case: 'portfolio',
  symbol: 'PORTFOLIO',
  as_of: new Date().toISOString().split('T')[0],
  summary:
    '为 $100,000 本金构建的进取成长型组合配置已优化完成。100% 满足金额与权重绝对守恒定律，预留 8% 战术现金应对市场回撤。',
  payload: {
    total_amount: 100000,
    cash_amount: 8000,
    cash_percent: 8.0,
    expected_return: '15.5%–18.0% 年化复合收益',
    portfolio_risk: '中等偏高（Beta 1.15）',
    allocations: [
      {
        symbol: 'NVDA',
        weight_percent: 28.0,
        amount_allocated: 28000,
        shares_to_buy: 191,
        current_price: 145.89,
        role: 'AI 算力爆发驱动核心',
      },
      {
        symbol: 'MSFT',
        weight_percent: 24.0,
        amount_allocated: 24000,
        shares_to_buy: 56,
        current_price: 422.5,
        role: '企业云底座与稳定器',
      },
      {
        symbol: 'AMZN',
        weight_percent: 20.0,
        amount_allocated: 20000,
        shares_to_buy: 96,
        current_price: 208.18,
        role: '电商与 AWS 云计算双轮驱动',
      },
      {
        symbol: 'AAPL',
        weight_percent: 20.0,
        amount_allocated: 20000,
        shares_to_buy: 87,
        current_price: 228.25,
        role: '全球消费电子压舱石与现金流堡垒',
      },
    ],
    rebalance_rules: [
      '单一标的权重浮动超过 ±5%（如 NVDA 突破 33% 或跌破 23%）触发再平衡',
      '每半年度按最新基本面评分校准权重',
      '现金储备用于突发系统性回撤时分批低吸',
    ],
  },
  evidence: [],
  data_gaps: [],
  disclaimer: '本内容仅供研究与模拟学习，不构成任何投资建议。市场有风险，投资需谨慎。',
};
