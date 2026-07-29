import { describe, expect, it } from "vitest"

import { parseScannerJob } from "@/api/scanner"

const signal = {
  status: "available",
  direction: "bullish",
  signal: "exit_oversold",
  state: "near_oversold",
  strength: 0.75,
  reason: "Le RSI vient de sortir de la zone de survente",
  raw_value: 31.4,
} as const

const legacyResult = {
  symbol: "BTC/USDC",
  timeframe: "1h",
  rsi: 31.4,
  last_close_price: 100,
  last_close_time: "2026-07-29T00:00:00Z",
  trend_score: 1,
  trends: {},
  trend_states: {},
  trend_net_score: 1,
  moving_averages: {},
  macd: null,
  macd_signal: null,
  macd_histogram: null,
  macd_signal_type: null,
  bb_upper: null,
  bb_middle: null,
  bb_lower: null,
  bb_position: null,
  stoch_k: null,
  stoch_d: null,
  stoch_signal: null,
  confluence_score: null,
  confluence_grade: null,
  confluence_breakdown: {},
  confluence_effective_weights: {},
  confluence_details: {},
  indicator_availability: {},
}

const job = {
  id: "job-1",
  status: "completed",
  config: {},
  progress: {
    processed: 1,
    total: 1,
    successful: 1,
    filtered: 0,
    errors: 0,
    percent: 100,
  },
  results: [legacyResult],
}

describe("scanner structured signal boundary", () => {
  it("accepte un résultat historique sans fabriquer de signaux", () => {
    expect(parseScannerJob(job).results?.[0].indicator_signals).toBeUndefined()
  })

  it("préserve des signaux partiels et tous les anciens champs", () => {
    const parsed = parseScannerJob({
      ...job,
      results: [{ ...legacyResult, indicator_signals: { rsi: signal } }],
    })
    expect(parsed.results?.[0]).toMatchObject({
      symbol: "BTC/USDC",
      timeframe: "1h",
      last_close_price: 100,
      indicator_signals: { rsi: signal },
    })
    expect(parsed.results?.[0].indicator_signals?.macd).toBeUndefined()
  })

  it("rejette un signal invalide", () => {
    expect(() => parseScannerJob({
      ...job,
      results: [{
        ...legacyResult,
        indicator_signals: { rsi: { ...signal, strength: 1.1 } },
      }],
    })).toThrow()
  })
})
