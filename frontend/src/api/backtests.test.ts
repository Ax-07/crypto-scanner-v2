import { afterEach, describe, expect, it, vi } from "vitest"

import { backtestApi, backtestJobSchema, parseSignalObservationPage } from "@/api/backtests"
import {
  portfolioEquityPage,
  portfolioMetadata,
  portfolioTradePage,
} from "@/test/backtest-fixtures"

const payload = {
  id: "job-1",
  status: "running",
  config: {},
  progress: {
    processed: 2, total: 10, observations: 2, current_symbol: "BTC/USDC",
    phase: "replay", percent: 20,
  },
  summary: null,
  correlations: null,
  ablations: null,
  warnings: [],
  error: null,
  created_at: "2026-01-01T00:00:00Z",
  started_at: "2026-01-01T00:00:01Z",
  completed_at: null,
}

describe("backtestJobSchema", () => {
  it("accepte un message WebSocket complet", () => {
    expect(backtestJobSchema.parse(payload).progress.percent).toBe(20)
  })

  it("rejette un statut, un compteur ou un résumé mal formé", () => {
    expect(() => backtestJobSchema.parse({ ...payload, status: "unknown" })).toThrow()
    expect(() => backtestJobSchema.parse({
      ...payload, progress: { ...payload.progress, processed: "2" },
    })).toThrow()
    expect(() => backtestJobSchema.parse({ ...payload, summary: { observation_count: 1 } })).toThrow()
  })
})

describe("backtest structured signal boundary", () => {
  const observation = {
    id: 1,
    job_id: "job-1",
    symbol: "BTC/USDC",
    timeframe: "1h",
    decision_time: "2026-07-29T00:00:00Z",
    snapshot_status: "confirmed",
    accepted: true,
    rejection_stage: null,
    rejection_reason: null,
    close: 100,
    rsi: 31.4,
    trend_score: 1,
    trend_states: {},
    macd_signal: null,
    bollinger_position: null,
    stochastic_signal: null,
    confluence_score: null,
    confluence_grade: null,
    confluence_factors: {},
    availability: {},
    algorithm_version: "signal-evaluation-v2",
    profile_id: "inline",
    profile_fingerprint: null,
    dataset_version: "test",
    source_ohlcv: {},
    raw_values: {},
    classes: {},
    configured_weights: {},
    effective_weights: {},
    divergences: [],
    quality: {},
  }
  const signal = {
    status: "available",
    direction: "bullish",
    signal: "exit_oversold",
    state: "near_oversold",
    strength: 0.75,
    reason: "Sortie de survente",
    raw_value: 31.4,
  } as const

  it("accepte une observation historique sans signaux", () => {
    expect(parseSignalObservationPage({ items: [observation], total: 1 }).items[0]
      .indicator_signals).toBeUndefined()
  })

  it("préserve des signaux partiels sans modifier les autres données", () => {
    const parsed = parseSignalObservationPage({
      items: [{ ...observation, indicator_signals: { rsi: signal } }],
      total: 1,
    }).items[0]
    expect(parsed.indicator_signals).toEqual({ rsi: signal })
    expect(parsed.close).toBe(100)
    expect(parsed.accepted).toBe(true)
  })

  it("rejette un signal invalide", () => {
    expect(() => parseSignalObservationPage({
      items: [{
        ...observation,
        indicator_signals: { rsi: { ...signal, raw_value: Number.NEGATIVE_INFINITY } },
      }],
      total: 1,
    })).toThrow()
  })
})

describe("backtest observations pagination", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("transmet offset et limite sans modifier le payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      items: [],
      total: 125,
      offset: 50,
      limit: 25,
    }), { status: 200, headers: { "Content-Type": "application/json" } }))
    vi.stubGlobal("fetch", fetchMock)

    const page = await backtestApi.observations("job-1", 50, 25)

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/api/backtests/job-1/observations?offset=50&limit=25",
    )
    expect(page).toMatchObject({ items: [], total: 125, offset: 50, limit: 25 })
  })
})

describe("API portfolio", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("valide métadonnées, trades et equity et transmet leurs paramètres", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(portfolioMetadata), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(portfolioTradePage), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(portfolioEquityPage), { status: 200 }))
    vi.stubGlobal("fetch", fetchMock)

    await expect(backtestApi.portfolio("job-1")).resolves.toEqual(portfolioMetadata)
    await expect(backtestApi.trades("job-1", 50, 25)).resolves.toEqual(portfolioTradePage)
    await expect(backtestApi.equity("job-1", {
      mode: "sampled",
      maxPoints: 1000,
    })).resolves.toEqual(portfolioEquityPage)

    expect(String(fetchMock.mock.calls[1][0])).toContain("trades?offset=50&limit=25")
    expect(String(fetchMock.mock.calls[2][0])).toContain("equity?mode=sampled&max_points=1000")
  })

  it("rejette une réponse portfolio avec clé inconnue", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ...portfolioMetadata, unexpected: true }), { status: 200 }),
    ))
    await expect(backtestApi.portfolio("job-1")).rejects.toThrow()
  })

  it("télécharge le blob sans parser le CSV puis révoque son URL", async () => {
    const click = vi.fn()
    const anchor = document.createElement("a")
    vi.spyOn(document, "createElement").mockReturnValue(anchor)
    anchor.click = click
    const createObjectURL = vi.fn().mockReturnValue("blob:test")
    const revokeObjectURL = vi.fn()
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL })
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("a,b\r\n1,2", {
      status: 200,
      headers: { "Content-Disposition": 'attachment; filename="job-1-trades-v1.csv"' },
    })))

    await backtestApi.downloadPortfolioExport("job-1", "trades")

    expect(anchor.download).toBe("job-1-trades-v1.csv")
    expect(click).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:test")
  })
})
