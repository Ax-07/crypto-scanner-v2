import type {
  AdxIndicatorConfig,
  AtrIndicatorConfig,
  Availability,
  ConfluenceFactorDetail,
  ConfluenceGrade,
  TrendState,
  SupertrendIndicatorConfig,
  DonchianIndicatorConfig,
  KeltnerIndicatorConfig,
} from "@/types/scanner"
import type { IndicatorSignals } from "@/types/indicator-signals"

export type ConnectionStatus = "connecting" | "connected" | "disconnected" | "error"

export interface Candle {
  time: number
  open_time?: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  is_closed?: boolean
}

export interface IndicatorPoint {
  time: number
  value: number
  color?: string
}

export type IndicatorKey =
  | `ema_${number}`
  | `sma_${number}`
  | `rsi_${number}`
  | "bollinger_upper"
  | "bollinger_middle"
  | "bollinger_lower"
  | "macd"
  | "macd_signal"
  | "macd_histogram"
  | "stochastic_k"
  | "stochastic_d"

  // Volatilité
  | "atr"
  | "natr"

  // ADX / DMI
  | "adx"
  | "adx_dx"
  | "adx_plus_di"
  | "adx_minus_di"
  | "adx_true_range"

  // Supertrend
  | "supertrend"
  | "supertrend_atr"
  | "supertrend_input_valid"
  | "supertrend_lower_band"
  | "supertrend_trend"
  | "supertrend_upper_band"

  // Donchian
  | "donchian_upper_channel"
  | "donchian_middle_channel"
  | "donchian_lower_channel"
  | "donchian_previous_upper_channel"
  | "donchian_previous_lower_channel"
  | "donchian_channel_position"
  | "donchian_channel_width"
  | "donchian_channel_width_percent"

  // Keltner
  | "keltner_upper_channel"
  | "keltner_middle_line"
  | "keltner_lower_channel"
  | "keltner_atr"
  | "keltner_channel_position"
  | "keltner_channel_width"
  | "keltner_channel_width_percent"

  // Données internes supplémentaires
  | "atr_true_range"

export type IndicatorHistory = Partial<Record<IndicatorKey, IndicatorPoint[]>>
export type IndicatorUpdates = Partial<Record<IndicatorKey, IndicatorPoint>>

export type MarkerCategory = "signal" | "divergence"
export type DivergenceSource = "RSI" | "MACD"
export type DivergenceType =
  | "regular_bullish"
  | "regular_bearish"
  | "hidden_bullish"
  | "hidden_bearish"

export interface MarketMarker {
  time: number
  position: "aboveBar" | "belowBar" | "inBar"
  shape: "circle" | "square" | "arrowUp" | "arrowDown"
  color: string
  text: string
  category?: MarkerCategory
  indicator?: MarkerIndicator
  source?: DivergenceSource
  divergence_type?: DivergenceType
  first_time?: number
  first_price?: number
  second_price?: number
  first_indicator?: number
  second_indicator?: number
  first_indicator_name?: number
  second_indicator_name?: number
}

export interface Confluence {
  score: number
  grade: ConfluenceGrade
  breakdown?: Record<string, number>
  effective_weights?: Record<string, number>
  details?: Record<string, ConfluenceFactorDetail>
}

export interface MarketIndicatorConfig {
  rsi_period: number
  rsi_threshold: number
  use_rsi: boolean
  use_ma: boolean
  use_sma: boolean
  use_ema: boolean
  sma_periods: number[]
  ema_periods: number[]
  macd_fast_period: number
  macd_slow_period: number
  macd_signal_period: number
  use_macd: boolean
  bollinger_period: number
  bollinger_std_dev: number
  use_bollinger: boolean
  stochastic_k_period: number
  stochastic_d_period: number
  stochastic_oversold: number
  stochastic_overbought: number
  use_stochastic: boolean
  atr?: AtrIndicatorConfig | null
  adx?: AdxIndicatorConfig | null
  supertrend?: SupertrendIndicatorConfig | null
  donchian?: DonchianIndicatorConfig | null
  keltner?: KeltnerIndicatorConfig | null
  use_confluence_score: boolean
  confluence_weights: Record<string, number>
  origin: "default" | "scan" | "custom"
}

export interface SignalView {
  price?: number | null
  timestamp?: number | null
  rsi?: number | null
  trend?: TrendState
  macd?: string | null
  bollinger?: string | null
  stochastic?: string | null
  confluence?: Confluence | null
  availability?: Record<string, Availability>
  indicator_signals?: IndicatorSignals
  is_forming?: boolean
}

export interface MarketSnapshot extends SignalView {
  confirmed?: SignalView
  provisional?: SignalView | null
  profile?: MarketIndicatorConfig
}

/** Message initial qui remplace toutes les séries du marché courant. */
export interface HistoryMessage {
  type: "history"
  symbol: string
  timeframe: string
  candles: Candle[]
  indicators: IndicatorHistory
  markers: MarketMarker[]
  snapshot: MarketSnapshot
}

/** Message incrémental qui met à jour la bougie et les derniers indicateurs. */
export interface UpdateMessage {
  type: "update"
  candle: Candle
  indicators: IndicatorUpdates
  markers: MarketMarker[]
  snapshot: MarketSnapshot
}

export interface ErrorMessage {
  type: "error"
  message: string
}

/** Union discriminée de tous les messages acceptés par le flux marché. */
export type MarketMessage = HistoryMessage | UpdateMessage | ErrorMessage

export interface IndicatorVisibility {
  ema: boolean
  sma: boolean
  bollinger: boolean
  rsi: boolean
  macd: boolean
  stochastic: boolean

  volatility: boolean
  adx: boolean
  supertrend: boolean
  donchian: boolean
  keltner: boolean

  signals: boolean
  divergences: boolean
}

export interface CandlePage {
  limit: number
  count: number
  oldest_open_time: number | null
  newest_open_time: number | null
  next_before: number | null
  next_after: number | null
  has_more_before: boolean
  has_more_after: boolean
}

export interface CandleCoverage {
  earliest_open_time: number | null
  latest_open_time: number | null
  total_candles: number
  is_complete: boolean
  gap_count: number
  available_from: number | null
  available_to: number | null
  local_earliest_time: number | null
  exchange_earliest_time: number | null
  exchange_earliest_verified: boolean
  local_candle_count: number
  is_earliest_known: boolean
  is_recent_complete: boolean
  history_last_error: string | null
}

export interface CandleSource {
  read_from_sqlite: boolean
  downloaded_from_exchange: number
}

export interface CandlePageResponse {
  exchange_id: string
  market_type: string
  symbol: string
  timeframe: string
  candles: Candle[]
  indicators: IndicatorHistory
  markers: MarketMarker[]
  page: CandlePage
  coverage: CandleCoverage
  source: CandleSource
  anchor_time: number | null
  anchor_before_available: boolean
  snapshot?: MarketSnapshot
  profile?: MarketIndicatorConfig
}

export type MarkerIndicator =
  | "ema"
  | "macd"
  | "supertrend"
  | "rsi"
  | "stochastic"
  | "bollinger"
  | "adx"
  | "atr"
  | "donchian"
  | "keltner"

export type StackedMarker = MarketMarker & {
  stackLevel: number
  verticalOffset: number
}

export type MarketMode = "live" | "historical"
export type ChartCommand = "realtime" | "fit" | "beginning" | "latest" | "historical"
