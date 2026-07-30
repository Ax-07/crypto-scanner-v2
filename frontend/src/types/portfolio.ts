export type PortfolioSimulationVersion = 1
export type PortfolioPositionSizingMode = "percent_cash"
export type PortfolioExecutionPolicy = "next_open"
export type PortfolioEndOfTestPolicy = "force_close"

export interface PortfolioPositionSizingConfig {
  mode: PortfolioPositionSizingMode
  value: string
}

export interface PortfolioSimulationConfig {
  version: PortfolioSimulationVersion
  quote_asset: string
  initial_capital: string
  position_sizing: PortfolioPositionSizingConfig
  execution_policy: PortfolioExecutionPolicy
  fee_rate: string
  slippage_rate: string
  end_of_test_policy: PortfolioEndOfTestPolicy
}

export interface PortfolioSimulationSummary {
  version: 1
  quote_asset: string
  initial_capital: string
  final_cash: string
  final_equity: string
  net_profit: string
  total_return_ratio: string
  realized_pnl: string
  unrealized_pnl: string
  total_fees: string
  trade_count: number
  winning_trade_count: number
  losing_trade_count: number
  breakeven_trade_count: number
  win_rate: string | null
  average_trade_return: string | null
  max_drawdown_ratio: string
  exposure_ratio: string
  open_position_count: number
}

export interface PortfolioSimulationPublicResult {
  version: 1
  quote_asset: string
  summary: PortfolioSimulationSummary
  has_trades: boolean
  has_equity_curve: boolean
}

export type PortfolioDetailsStatus = "complete" | "unavailable_legacy"

export interface PortfolioRunMetadata {
  version: 1
  schema_version: 1
  engine_version: string
  quote_asset: string
  summary: PortfolioSimulationSummary
  details_status: PortfolioDetailsStatus
  order_count: number
  execution_count: number
  trade_count: number
  equity_point_count: number
  available_after_restart: boolean
}

export type PortfolioTradeExitReason = "validation_lost" | "end_of_test"

export interface PortfolioTrade {
  version: 1
  sequence: number
  trade_id: string
  position_id: string
  symbol: string
  quote_asset: string
  entry_observation_id: string
  exit_observation_id: string | null
  entry_time: string
  exit_time: string
  entry_price: string
  exit_price: string
  quantity: string
  entry_fee: string
  exit_fee: string
  gross_exit_proceeds: string
  net_exit_proceeds: string
  realized_pnl: string
  return_ratio: string
  duration_bars: number
  exit_reason: PortfolioTradeExitReason
}

export interface PortfolioEquityPoint {
  version: 1
  sequence: number
  timestamp: string
  cash: string
  position_value: string
  equity: string
  realized_pnl_cumulative: string
  unrealized_pnl: string
  fees_cumulative: string
  drawdown_ratio: string
}

export interface PortfolioTradePage {
  items: PortfolioTrade[]
  total: number
  offset: number
  limit: number
  has_more: boolean
}

export interface PortfolioEquityPage {
  items: PortfolioEquityPoint[]
  total: number
  offset: number
  limit: number
  has_more: boolean
  sampled: boolean
  source_point_count: number
}

export type PortfolioApiErrorCode =
  | "portfolio_not_requested"
  | "portfolio_job_not_completed"
  | "portfolio_details_unavailable"
  | "portfolio_details_legacy_unavailable"
  | "invalid_pagination"
