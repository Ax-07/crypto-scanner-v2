import type { Availability, ConfluenceGrade, ScanConfig, TrendState } from "@/types/scanner"
import type { IndicatorSignals } from "@/types/indicator-signals"

export type BacktestStatus = "pending" | "running" | "completed" | "failed" | "cancelled" | "interrupted"
export type BacktestConfig = {
  symbols: string[]
  start: string
  end: string
  signal_config: ScanConfig
  horizons: number[]
  replay_mode: "every_bar" | "state_changes" | "filtered_signals"
  entry_policy: "signal_close" | "next_open"
  gap_policy: "reject_range" | "skip_affected" | "allow_with_warning"
  fee_bps: number
  slippage_bps: number
  snapshot_status: "confirmed" | "provisional"
}

export type BacktestSummary = {
  observation_count: number
  accepted_count: number
  rejected_count: number
  censored_count: number
  warnings: string[]
  horizons: Record<string, Record<string, unknown>>
  segments: Record<string, unknown>
  filter_funnel: Array<{ stage: string; input: number; passed: number; rejected: number }>
  provisional_supported: boolean
  trade_simulation_included: boolean
}

export type BacktestJob = {
  id: string
  status: BacktestStatus
  config: BacktestConfig
  progress: {
    processed: number
    total: number
    observations: number
    current_symbol: string | null
    phase: string
    percent: number
  }
  summary: BacktestSummary | null
  correlations: Record<string, unknown> | null
  ablations: Record<string, unknown> | null
  warnings: string[]
  error: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  dataset_version: string
  algorithm_version: string
  checkpoint: Record<string, unknown> | null
}

export type SignalObservation = {
  id: number
  job_id: string
  symbol: string
  timeframe: string
  decision_time: string
  snapshot_status: "confirmed" | "provisional"
  accepted: boolean
  rejection_stage: string | null
  rejection_reason: string | null
  close: number
  rsi: number | null
  trend_score: number | null
  trend_states: Record<string, TrendState>
  macd_signal: string | null
  bollinger_position: string | null
  stochastic_signal: string | null
  confluence_score: number | null
  confluence_grade: ConfluenceGrade | null
  confluence_factors: Record<string, number | null>
  availability: Record<string, Availability>
  indicator_signals?: IndicatorSignals
  algorithm_version: string
  profile_id: string
  profile_fingerprint: string | null
  dataset_version: string
  source_ohlcv: Record<string, number>
  raw_values: Record<string, unknown>
  classes: Record<string, string | null>
  configured_weights: Record<string, number>
  effective_weights: Record<string, number>
  divergences: Array<Record<string, unknown>>
  quality: Record<string, unknown>
}
