import { describe, expect, it } from "vitest"

import { scanConfigSchema } from "@/features/scanner/scan-config-schema"
import { structuredSignalFiltersSchema } from "@/schemas/structured-signal-filters"
import { createScanConfig } from "@/test/scanner-fixtures"

function json(source: string): unknown {
  return JSON.parse(source)
}

describe("contrat JSON structured_signal_filters v1 figé", () => {
  it.each([
    '{"version":1,"indicators":{}}',
    `{
      "version": 1,
      "indicators": {
        "macd": {
          "match": "all",
          "conditions": [{"field": "direction", "values": ["bullish"]}]
        }
      }
    }`,
    `{
      "version": 1,
      "indicators": {
        "bollinger": {
          "match": "any",
          "conditions": [
            {"field": "state", "values": ["oversold"]},
            {"field": "signal", "values": ["lower_band_reentry"]}
          ]
        }
      }
    }`,
    `{
      "version": 1,
      "indicators": {
        "stochastic": {
          "match": "any",
          "conditions": [
            {"field": "signal", "values": ["bullish_cross", "oversold"]}
          ]
        }
      }
    }`,
    `{
      "version": 1,
      "indicators": {
        "macd": {
          "match": "all",
          "conditions": [
            {"field": "status", "values": ["available"]},
            {"field": "direction", "values": ["bullish"]}
          ]
        }
      }
    }`,
  ])("accepte sans transformation l'exemple officiel %#", (source) => {
    const payload = json(source)
    expect(structuredSignalFiltersSchema.parse(payload)).toEqual(payload)
  })

  it("accepte un contrat partiel et un groupe vide explicite", () => {
    const payload = json(`{
      "version": 1,
      "indicators": {
        "stochastic": {"match": "any", "conditions": []}
      }
    }`)
    expect(structuredSignalFiltersSchema.parse(payload)).toEqual(payload)
  })

  it.each([
    '{"version":2,"indicators":{}}',
    '{"version":1,"indicators":{"rsi":{"match":"all","conditions":[]}}}',
    '{"version":1,"indicators":{"macd":{"match":"none","conditions":[]}}}',
    `{
      "version": 1,
      "indicators": {
        "macd": {
          "match": "all",
          "conditions": [{"field": "strength", "values": ["1"]}]
        }
      }
    }`,
    `{
      "version": 1,
      "indicators": {
        "macd": {
          "match": "all",
          "conditions": [{"field": "direction", "values": []}]
        }
      }
    }`,
    `{
      "version": 1,
      "indicators": {
        "macd": {
          "match": "all",
          "conditions": [
            {"field": "direction", "values": ["bullish", "bullish"]}
          ]
        }
      }
    }`,
    `{
      "version": 1,
      "indicators": {
        "macd": {
          "match": "all",
          "conditions": [{"field": "signal", "values": ["  "]}]
        }
      }
    }`,
    `{
      "version": 1,
      "indicators": {
        "macd": {
          "match": "all",
          "conditions": [{"field": "status", "values": ["unavailable"]}]
        }
      }
    }`,
  ])("rejette le payload incompatible %#", (source) => {
    expect(structuredSignalFiltersSchema.safeParse(json(source)).success).toBe(false)
  })

  it("préserve une ancienne configuration sans champ structuré", () => {
    const legacy = createScanConfig({
      filter_macd_signal: ["bullish"],
      filter_bb_position: ["oversold"],
      filter_stoch_signal: ["bullish_cross", "oversold"],
    })
    const parsed = scanConfigSchema.parse(legacy)
    expect(parsed.structured_signal_filters).toBeUndefined()
    expect(parsed.filter_stoch_signal).toEqual(["bullish_cross", "oversold"])
  })

  it("accepte la coexistence legacy et structurée sans écraser aucun champ", () => {
    const config = createScanConfig({
      filter_macd_signal: ["bearish"],
      filter_bb_position: ["oversold"],
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
    const parsed = scanConfigSchema.parse(config)
    expect(parsed.filter_macd_signal).toEqual(["bearish"])
    expect(parsed.filter_bb_position).toEqual(["oversold"])
    expect(parsed.structured_signal_filters).toEqual(
      config.structured_signal_filters,
    )
  })
})
