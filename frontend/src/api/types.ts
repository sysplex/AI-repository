/**
 * 从 OpenAPI 自动生成的类型定义中导出的核心领域类型别名。
 * 保证类型零手写偏差，遵循 CONTRACTS.md。
 */

import type { components, paths } from './openapi';

export type { components, paths };

// 常用 Schema 别名
export type Schemas = components['schemas'];

// 1. 用户与认证
export type UserPublic = Schemas['UserPublic'];
export type TokenPair = Schemas['TokenPair'];
export type LoginRequest = Schemas['LoginRequest'];
export type LogoutRequest = Schemas['LogoutRequest'];
export type RegisterRequest = Schemas['RegisterRequest'];
export type PasswordResetRequest = Schemas['PasswordResetRequest'];
export type PasswordResetConfirm = Schemas['PasswordResetConfirm'];
export type UserSettings = Schemas['UserSettings'];
export type SettingsUpdate = Schemas['SettingsUpdate'];
export type UsageResponse = Schemas['UsageResponse'];
export type PaginatedUsers = Schemas['PaginatedUsers'];

// 2. 行情与市场数据
export type Bar = Schemas['Bar'];
export type Quote = Schemas['Quote'];
export type CompanyProfile = Schemas['CompanyProfile'];
export type Fundamentals = Schemas['Fundamentals'];
export type NewsItem = Schemas['NewsItem'];
export type FactsSnapshot = Schemas['FactsSnapshot'];

// 3. 技术指标与策略
export type Signal = Schemas['Signal'];
export type TechnicalSnapshot = Schemas['TechnicalSnapshot'];
export type StrategyMetadata = Schemas['StrategyMetadata'];
export type BacktestRequest = Schemas['BacktestRequest'];
export type BacktestResult = Schemas['BacktestResult'];

// 4. 模拟盘
export type AccountResponse = Schemas['AccountResponse'];
export type AccountOverview = Schemas['AccountOverview'];
export type AccountCreate = Schemas['AccountCreate'];
export type DepositRequest = Schemas['DepositRequest'];
export type OrderResponse = Schemas['OrderResponse'];
export type OrderCreate = Schemas['OrderCreate'];
export type PositionResponse = Schemas['PositionResponse'];
export type TradeResponse = Schemas['TradeResponse'];
export type EquitySnapshotResponse = Schemas['EquitySnapshotResponse'];
export type TradeJournalResponse = Schemas['TradeJournalResponse'];
export type TradeJournalUpdate = Schemas['TradeJournalUpdate'];
export type PerformanceMetrics = Schemas['PerformanceMetrics'];
export type RiskOverview = Schemas['RiskOverview'];

// 5. 投研与 AI 分析
export type ResearchEnvelope = Schemas['ResearchEnvelope'];
export type ResearchRequest = Schemas['ResearchRequest'];
export type BuyDecisionRequest = Schemas['BuyDecisionRequest'];
export type TechnicalAnalysisRequest = Schemas['TechnicalAnalysisRequest'];
export type EarningsAnalysisRequest = Schemas['EarningsAnalysisRequest'];
export type CompareRequest = Schemas['CompareRequest'];
export type LongTermRequest = Schemas['LongTermRequest'];
export type PortfolioRequest = Schemas['PortfolioRequest'];
export type AIPromptInfo = Schemas['AIPromptInfo'];
export type QuotaStatus = Schemas['QuotaStatus'];

// 6. 筛选器与自选清单
export type WatchlistRead = Schemas['WatchlistRead'];
export type WatchlistItemRead = Schemas['WatchlistItemRead'];
export type WatchlistCreate = Schemas['WatchlistCreate'];
export type WatchlistUpdate = Schemas['WatchlistUpdate'];
export type WatchlistItemCreate = Schemas['WatchlistItemCreate'];
export type WatchlistItemUpdate = Schemas['WatchlistItemUpdate'];
export type ScreenerRunRead = Schemas['ScreenerRunRead'];
export type ScreenerRunCreate = Schemas['ScreenerRunCreate'];
export type ScreenerResultItem = Schemas['ScreenerResultItem'];
export type UniverseInfo = Schemas['UniverseInfo'];
export type ThemeInfo = Schemas['ThemeInfo'];
export type ThemeStockItem = Schemas['ThemeStockItem'];
export type ThemeCardItem = Schemas['ThemeCardItem'];
export type ThemeCardsResponse = Schemas['ThemeCardsResponse'];
export type ExportToResearchRequest = Schemas['ExportToResearchRequest'];
