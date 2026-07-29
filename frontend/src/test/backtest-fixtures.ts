import type { IndicatorSignal } from "@/types/indicator-signals"
import type { BacktestConfig, BacktestJob, SignalObservation } from "@/types/backtest"

export const backtestSignal: IndicatorSignal = {
  status: "available",
  direction: "bullish",
  signal: "bullish_cross",
  state: "above_signal",
  strength: 0.75,
  reason: "Signal technique calculé à cet instant.",
  raw_value: 31.4,
}

export function createObservation(
  overrides: Partial<SignalObservation> = {},
): SignalObservation {
  return {
    id: 1,
    job_id: "job-1",
    symbol: "BTC/USDC",
    timeframe: "4h",
    decision_time: "2026-07-29T12:00:00Z",
    snapshot_status: "confirmed",
    accepted: true,
    rejection_stage: null,
    rejection_reason: null,
    close: 102.5,
    rsi: 31.4,
    trend_score: 2,
    trend_states: { "4h": "bullish" },
    macd_signal: "bullish",
    bollinger_position: "near_oversold",
    stochastic_signal: "bullish_cross",
    confluence_score: 74,
    confluence_grade: "B",
    confluence_factors: { rsi: 0.75 },
    confluence_breakdown: { rsi: 15 },
    availability: { rsi: "available" },
    indicator_signals: { rsi: backtestSignal },
    filter_trace: [],
    algorithm_version: "signal-evaluation-v2",
    profile_id: "inline",
    profile_fingerprint: "sha256:test",
    dataset_version: "dataset-test",
    calculation_mode: "canonical",
    schema_version: 2,
    source_ohlcv: { open: 100, high: 103, low: 99, close: 102.5, volume: 10 },
    raw_values: { rsi: 31.4 },
    classes: { macd: "bullish" },
    configured_weights: { rsi: 0.2 },
    effective_weights: { rsi: 20 },
    divergences: [],
    quality: { available_bars: 60 },
    ...overrides,
  }
}

export function createBacktestJob(
  overrides: Partial<BacktestJob> = {},
): BacktestJob {
  return {
    id: "job-1",
    status: "completed",
    config: {
      symbols: ["BTC/USDC"],
      start: "2026-07-01T00:00:00Z",
      end: "2026-07-29T00:00:00Z",
      signal_config: {} as BacktestConfig["signal_config"],
      horizons: [1, 3, 6],
      replay_mode: "every_bar",
      entry_policy: "signal_close",
      gap_policy: "reject_range",
      fee_bps: 10,
      slippage_bps: 5,
      snapshot_status: "confirmed",
    },
    progress: {
      processed: 100,
      total: 100,
      observations: 1,
      current_symbol: null,
      phase: "completed",
      percent: 100,
    },
    summary: null,
    correlations: null,
    ablations: null,
    warnings: [],
    error: null,
    created_at: "2026-07-29T00:00:00Z",
    started_at: "2026-07-29T00:00:01Z",
    completed_at: "2026-07-29T00:01:00Z",
    dataset_version: "dataset-test",
    algorithm_version: "signal-evaluation-v2",
    checkpoint: null,
    ...overrides,
  }
}
