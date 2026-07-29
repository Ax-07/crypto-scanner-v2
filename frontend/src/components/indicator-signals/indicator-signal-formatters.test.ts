import { describe, expect, it } from "vitest"

import {
  INDICATOR_CONFIG,
  INDICATOR_DIRECTION_LABELS,
  INDICATOR_LABELS,
  INDICATOR_ORDER,
  INDICATOR_STATUS_LABELS,
  formatIndicatorRawValue,
  formatTechnicalLabel,
} from "@/components/indicator-signals"

describe("indicator signal display configuration", () => {
  it("exposes every indicator label in canonical order", () => {
    expect(INDICATOR_ORDER).toEqual(["rsi", "sma", "ema", "macd", "bollinger", "stochastic"])
    expect(INDICATOR_ORDER.map((name) => INDICATOR_LABELS[name])).toEqual([
      "RSI",
      "SMA",
      "EMA",
      "MACD",
      "Bollinger",
      "Stochastique",
    ])
    expect(INDICATOR_CONFIG.rsi.description).toBe("Indice de force relative")
  })

  it("centralizes status and direction labels", () => {
    expect(INDICATOR_STATUS_LABELS).toEqual({
      available: "Disponible",
      insufficient_data: "Données insuffisantes",
      invalid_data: "Données invalides",
      disabled: "Désactivé",
    })
    expect(INDICATOR_DIRECTION_LABELS).toEqual({
      bullish: "Haussier",
      bearish: "Baissier",
      neutral: "Neutre",
    })
  })
})

describe("formatTechnicalLabel", () => {
  it.each([
    ["exit_oversold", "Sortie de survente"],
    ["bullish_cross", "Croisement haussier"],
    ["lower_band_reentry", "Réintégration de la bande basse"],
    ["near_overbought", "Proche du surachat"],
    ["neutral", "Neutre"],
  ])("formats %s", (value, expected) => {
    expect(formatTechnicalLabel(value)).toBe(expected)
  })

  it("humanizes an unknown snake_case value without throwing", () => {
    expect(formatTechnicalLabel("custom_signal")).toBe("Custom signal")
    expect(formatTechnicalLabel("")).toBe("Valeur inconnue")
  })

  it("formats slash-separated technical states", () => {
    expect(formatTechnicalLabel("above_signal/above_zero")).toBe(
      "Au-dessus du signal / Au-dessus de zéro",
    )
  })
})

describe("formatIndicatorRawValue", () => {
  it("formats RSI and Stochastic with a deterministic French decimal separator", () => {
    expect(formatIndicatorRawValue("rsi", 31.456)).toBe("31,46")
    expect(formatIndicatorRawValue("stochastic", 18.235)).toBe("18,24")
  })

  it("uses dynamic precision for MACD and price-like indicators", () => {
    expect(formatIndicatorRawValue("macd", 0.0000123456)).toBe("0,00001235")
    expect(formatIndicatorRawValue("macd", 1.23456)).toBe("1,2346")
    expect(formatIndicatorRawValue("sma", 1234.567)).toBe("1 234,57")
    expect(formatIndicatorRawValue("ema", 0.0000123456)).toBe("0,00001235")
    expect(formatIndicatorRawValue("bollinger", 102.12345)).toBe("102,1235")
  })

  it.each([null, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
    "renders %s as unavailable",
    (value) => {
      expect(formatIndicatorRawValue("rsi", value)).toBe("—")
    },
  )
})
