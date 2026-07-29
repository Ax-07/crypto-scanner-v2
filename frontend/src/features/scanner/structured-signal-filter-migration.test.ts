import { describe, expect, it } from "vitest"

import {
  migrateLegacySignalFilters,
  setStructuredFilterMatch,
  toggleStructuredFilterValue,
} from "@/features/scanner/structured-signal-filter-migration"
import { createScanConfig } from "@/test/scanner-fixtures"

describe("migration des filtres scanner", () => {
  it("convertit les trois champs legacy sans les supprimer", () => {
    const migrated = migrateLegacySignalFilters(createScanConfig({
      filter_macd_signal: ["bullish"],
      filter_bb_position: ["oversold", "neutral"],
      filter_stoch_signal: ["bullish_cross", "oversold"],
    }))
    expect(migrated).toMatchObject({
      filter_macd_signal: ["bullish"],
      filter_bb_position: ["oversold", "neutral"],
      filter_stoch_signal: ["bullish_cross", "oversold"],
      structured_signal_filters: {
        version: 1,
        indicators: {
          macd: {
            match: "any",
            conditions: [{ field: "direction", values: ["bullish"] }],
          },
          bollinger: {
            match: "any",
            conditions: [{ field: "state", values: ["oversold", "neutral"] }],
          },
          stochastic: {
            match: "any",
            conditions: [{ field: "signal", values: ["bullish_cross", "oversold"] }],
          },
        },
      },
    })
  })

  it("préserve un contrat déjà structuré", () => {
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
    expect(migrateLegacySignalFilters(config)).toBe(config)
  })

  it("matérialise le fallback legacy d'un autre indicateur pour l'édition", () => {
    const migrated = migrateLegacySignalFilters(createScanConfig({
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
    }))
    expect(migrated.structured_signal_filters?.indicators).toEqual({
      macd: {
        match: "all",
        conditions: [{ field: "direction", values: ["bullish"] }],
      },
      bollinger: {
        match: "any",
        conditions: [{ field: "state", values: ["oversold"] }],
      },
    })
  })

  it("gère ajout, suppression et stratégies all/any sans muter l'entrée", () => {
    const original = { version: 1, indicators: {} } as const
    const selected = toggleStructuredFilterValue(original, "stochastic", "state", "oversold")
    const all = setStructuredFilterMatch(selected, "stochastic", "all")
    const empty = toggleStructuredFilterValue(all, "stochastic", "state", "oversold")
    expect(original.indicators).toEqual({})
    expect(all.indicators.stochastic).toEqual({
      match: "all",
      conditions: [{ field: "state", values: ["oversold"] }],
    })
    expect(empty.indicators.stochastic?.conditions).toEqual([])
  })
})
