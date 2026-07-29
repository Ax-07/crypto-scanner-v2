import { describe, expect, it } from "vitest"

import { marketMessageSchema, markerSchema } from "@/api/market"

describe("market marker contract", () => {
  it("parses a crossover without divergence-only details", () => {
    const marker = {
      time: 1,
      position: "belowBar",
      shape: "arrowUp",
      color: "#22c55e",
      text: "BUY EMA 20/50",
      category: "signal",
    }
    expect(markerSchema.parse(marker)).toEqual(marker)
  })

  it("preserves every detailed divergence field", () => {
    const marker = {
      time: 8,
      position: "belowBar",
      shape: "arrowUp",
      color: "#a78bfa",
      text: "RSI divergence",
      category: "divergence",
      source: "RSI",
      divergence_type: "regular_bullish",
      first_time: 3,
      first_price: 10,
      second_price: 9,
      first_indicator: 40,
      second_indicator: 45,
    } as const
    expect(markerSchema.parse(marker)).toEqual(marker)
  })

  it("rejects unknown divergence values", () => {
    expect(() => markerSchema.parse({
      time: 1,
      position: "belowBar",
      shape: "arrowUp",
      color: "#fff",
      text: "unknown",
      category: "divergence",
      source: "PRICE",
      divergence_type: "invented",
    })).toThrow()
  })
})

describe("market structured signal compatibility", () => {
  const base = {
    type: "update",
    candle: { time: 1, open: 1, high: 2, low: 0, close: 1, volume: 1 },
    indicators: {},
    markers: [],
  } as const

  it("accepte les anciens messages history et update sans signaux", () => {
    const history = marketMessageSchema.parse({
      type: "history",
      symbol: "BTC/USDC",
      timeframe: "1h",
      candles: [],
      indicators: {},
      markers: [],
      snapshot: {},
    })
    const update = marketMessageSchema.parse({ ...base, snapshot: {} })
    expect(history.type === "history" && history.snapshot.indicator_signals).toBeUndefined()
    expect(update.type === "update" && update.snapshot.indicator_signals).toBeUndefined()
  })

  it.each([
    { strength: 1.01, raw_value: 1 },
    { strength: 0.5, raw_value: Number.POSITIVE_INFINITY },
  ])("rejette un signal marché invalide", ({ strength, raw_value }) => {
    expect(() => marketMessageSchema.parse({
      ...base,
      snapshot: {
        indicator_signals: {
          rsi: {
            status: "available",
            direction: "bullish",
            signal: "test",
            state: null,
            strength,
            reason: null,
            raw_value,
          },
        },
      },
    })).toThrow()
  })
})
