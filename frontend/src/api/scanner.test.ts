import { afterEach, describe, expect, it, vi } from "vitest"

import { parseScannerJob, scannerApi } from "@/api/scanner"
import { createScanConfig } from "@/test/scanner-fixtures"

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
  afterEach(() => vi.unstubAllGlobals())

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

  it("préserve une configuration structurée et rejette sa version inconnue", () => {
    const structured = {
      version: 1,
      indicators: {
        macd: {
          match: "all",
          conditions: [{ field: "direction", values: ["bullish"] }],
        },
      },
    } as const
    expect(parseScannerJob({
      ...job,
      config: { structured_signal_filters: structured },
    }).config.structured_signal_filters).toEqual(structured)
    expect(() => parseScannerJob({
      ...job,
      config: { structured_signal_filters: { version: 2, indicators: {} } },
    })).toThrow()
  })

  it("scannerApi.start sérialise le nouveau contrat et les champs legacy", async () => {
    const config = createScanConfig({
      filter_macd_signal: ["bearish"],
      structured_signal_filters: {
        version: 1,
        indicators: {
          macd: {
            match: "all",
            conditions: [{ field: "direction", values: ["bullish"] }],
          },
        },
      },
    })
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ...job,
      config,
    }), { status: 202, headers: { "Content-Type": "application/json" } }))
    vi.stubGlobal("fetch", fetchMock)

    await scannerApi.start(config)

    const request = fetchMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(String(request.body))).toMatchObject({
      filter_macd_signal: ["bearish"],
      structured_signal_filters: config.structured_signal_filters,
    })
  })
})
