import { describe, expect, it } from "vitest"

import { structuredSignalFiltersSchema } from "@/schemas/structured-signal-filters"

const valid = {
  version: 1,
  indicators: {
    macd: {
      match: "all",
      conditions: [{ field: "direction", values: ["bullish", "neutral"] }],
    },
    bollinger: {
      match: "any",
      conditions: [
        { field: "state", values: ["oversold"] },
        { field: "signal", values: ["lower_band_reentry"] },
      ],
    },
  },
}

describe("structuredSignalFiltersSchema", () => {
  it("accepte les contrats complets, partiels et les groupes explicitement vides", () => {
    expect(structuredSignalFiltersSchema.parse(valid)).toEqual(valid)
    expect(structuredSignalFiltersSchema.safeParse({
      version: 1,
      indicators: { stochastic: { match: "any", conditions: [] } },
    }).success).toBe(true)
  })

  it.each([
    { ...valid, version: 2 },
    { version: 1, indicators: { rsi: { match: "all", conditions: [] } } },
    {
      version: 1,
      indicators: {
        macd: { match: "none", conditions: [] },
      },
    },
    {
      version: 1,
      indicators: {
        macd: { match: "all", conditions: [{ field: "strength", values: ["1"] }] },
      },
    },
    {
      version: 1,
      indicators: {
        macd: { match: "all", conditions: [{ field: "direction", values: [] }] },
      },
    },
    {
      version: 1,
      indicators: {
        macd: {
          match: "all",
          conditions: [{ field: "direction", values: ["bullish", "bullish"] }],
        },
      },
    },
    {
      version: 1,
      indicators: {
        macd: { match: "all", conditions: [{ field: "direction", values: ["up"] }] },
      },
    },
    {
      version: 1,
      indicators: {
        macd: { match: "all", conditions: [{ field: "status", values: ["unavailable"] }] },
      },
    },
  ])("rejette un contrat invalide", (payload) => {
    expect(structuredSignalFiltersSchema.safeParse(payload).success).toBe(false)
  })
})
