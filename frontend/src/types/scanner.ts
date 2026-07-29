export type ScanStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"

export type MacdSignal = "bullish" | "bearish" | "neutral"
export type MarketType = "spot" | "swap" | "future"
export type Timeframe =
  | "1m" | "3m" | "5m" | "15m" | "30m" | "1h" | "2h"
  | "4h" | "6h" | "8h" | "12h" | "1d" | "3d" | "1w"
export type BollingerPosition =
  | "oversold"
  | "near_oversold"
  | "neutral"
  | "near_overbought"
  | "overbought"
export type StochasticSignal =
  | "oversold"
  | "overbought"
  | "bullish_cross"
  | "bearish_cross"
  | "neutral"
export type ConfluenceGrade = "F" | "D" | "C" | "B" | "A" | "A+"
export type TrendState = "bullish" | "bearish" | "neutral" | "unavailable"
export type Availability = IndicatorSignalStatus
export type ConfluenceIndicator =
  | "rsi"
  | "trend"
  | "macd"
  | "bollinger"
  | "stochastic"

/** Configuration complète envoyée à la création d'un job scanner. */
export type ScanConfig = {
  exchange_id: string
  market_type: MarketType
  quote: string
  exclude_stable_pairs: boolean
  max_pairs: number | null
  timeframe: Timeframe
  min_ohlcv_bars: number
  max_concurrency: number
  max_retries: number
  retry_delay_seconds: number
  use_rsi: boolean
  rsi_period: number
  rsi_threshold: number
  use_ma: boolean
  use_sma: boolean
  use_ema: boolean
  sma_periods: number[]
  ema_periods: number[]
  ma_timeframes: Timeframe[]
  min_trend_score: number
  use_macd: boolean
  macd_fast_period: number
  macd_slow_period: number
  macd_signal_period: number
  use_bollinger: boolean
  bollinger_period: number
  bollinger_std_dev: number
  use_stochastic: boolean
  stochastic_k_period: number
  stochastic_d_period: number
  stochastic_oversold: number
  stochastic_overbought: number
  use_confluence_score: boolean
  min_confluence_score: number
  confluence_weights: Record<ConfluenceIndicator, number>
  filter_macd_signal: MacdSignal[] | null
  filter_bb_position: BollingerPosition[] | null
  filter_stoch_signal: StochasticSignal[] | null
}

/** Analyse d'une paire renvoyée dans les résultats terminaux du job. */
export type ScanResult = {
  symbol: string
  timeframe: string
  rsi: number | null
  last_close_price: number | null
  last_close_time: string | null
  trend_score: number | null
  trends: Record<string, boolean | null>
  trend_states: Record<string, TrendState>
  trend_net_score: number | null
  moving_averages: Record<string, number>
  macd: number | null
  macd_signal: number | null
  macd_histogram: number | null
  macd_signal_type: MacdSignal | null
  bb_upper: number | null
  bb_middle: number | null
  bb_lower: number | null
  bb_position: BollingerPosition | null
  stoch_k: number | null
  stoch_d: number | null
  stoch_signal: StochasticSignal | null
  confluence_score: number | null
  confluence_grade: ConfluenceGrade | null
  confluence_breakdown: Record<string, number>
  confluence_effective_weights: Record<string, number>
  confluence_details: Record<string, ConfluenceFactorDetail>
  indicator_availability: Record<string, Availability>
  indicator_signals?: IndicatorSignals
}

export type ConfluenceFactorDetail = {
  status: Availability
  raw_value?: unknown
  signal?: unknown
  factor: number | null
  configured_weight: number
  effective_weight: number | null
  contribution: number | null
  reason: string | null
}

/** Snapshot public du job ; `results` n'est présent que sur l'endpoint de résultats. */
export type ScanJob = {
  id: string
  status: ScanStatus
  config: ScanConfig
  progress: {
    processed: number
    total: number
    successful: number
    filtered: number
    errors: number
    percent: number
  }
  result_count: number
  error: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  results?: ScanResult[]
}
import type { IndicatorSignals, IndicatorSignalStatus } from "@/types/indicator-signals"
