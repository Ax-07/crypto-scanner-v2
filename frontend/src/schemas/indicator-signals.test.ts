import { describe, expect, it } from "vitest"

import {
  indicatorSignalDirectionSchema,
  indicatorSignalSchema,
  indicatorSignalsSchema,
  indicatorSignalStatusSchema,
} from "@/schemas/indicator-signals"

const completeSignal = {
  status: "available",
  direction: "bullish",
  signal: "exit_oversold",
  state: "near_oversold",
  strength: 0.75,
  reason: "Le RSI vient de sortir de la zone de survente",
  raw_value: 31.4,
} as const

describe("indicator signal contract", () => {
  it("préserve un signal complet et accepte les champs métier nullables", () => {
    expect(indicatorSignalSchema.parse(completeSignal)).toEqual(completeSignal)
    expect(indicatorSignalSchema.parse({
      ...completeSignal,
      signal: null,
      state: null,
      reason: null,
      raw_value: null,
    })).toMatchObject({ signal: null, state: null, reason: null, raw_value: null })
  })

  it.each(["available", "insufficient_data", "invalid_data", "disabled"] as const)(
    "accepte le statut %s",
    (status) => expect(indicatorSignalStatusSchema.parse(status)).toBe(status),
  )

  it.each(["bullish", "bearish", "neutral"] as const)(
    "accepte la direction %s",
    (direction) => expect(indicatorSignalDirectionSchema.parse(direction)).toBe(direction),
  )

  it.each([0, 0.25, 0.5, 0.75, 1])(
    "accepte la force %s",
    (strength) => expect(indicatorSignalSchema.parse({ ...completeSignal, strength }).strength).toBe(strength),
  )

  it.each([-0.01, 1.01, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
    "refuse la force non conforme %s",
    (strength) => expect(() => indicatorSignalSchema.parse({ ...completeSignal, strength })).toThrow(),
  )

  it.each([Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
    "refuse la valeur brute non finie %s",
    (raw_value) => expect(() => indicatorSignalSchema.parse({ ...completeSignal, raw_value })).toThrow(),
  )

  it("accepte un dictionnaire partiel et un dictionnaire vide", () => {
    const partial = { rsi: completeSignal, macd: { ...completeSignal, signal: "bullish_cross" } }
    expect(indicatorSignalsSchema.parse(partial)).toEqual(partial)
    expect(indicatorSignalsSchema.parse({})).toEqual({})
  })

  it("valide strictement les composants ATR/ADX/Supertrend", () => {
    const component = { value: 2, normalized_value: null, unit: "price" } as const
    const atr = {
      ...completeSignal,
      direction: "neutral" as const,
      components: {
        true_range: component,
        atr: component,
        natr: { value: 2, normalized_value: 0.02, unit: "percent" as const },
        natr_change: { value: 0.1, normalized_value: null, unit: "percent" as const },
      },
    }
    expect(indicatorSignalsSchema.parse({ atr })).toEqual({ atr })
    expect(() => indicatorSignalsSchema.parse({
      atr: { ...atr, components: { ...atr.components, unexpected: component } },
    })).toThrow()
  })

  it("valide strictement Bollinger enrichi, Donchian et Keltner", () => {
    const price = { value: 100, normalized_value: null, unit: "price" } as const
    const percent = { value: 4, normalized_value: 0.04, unit: "percent" } as const
    const ratio = { value: 0.5, normalized_value: 0.5, unit: "ratio" } as const
    const bollinger = {
      ...completeSignal,
      components: {
        middle_band: price,
        upper_band: price,
        lower_band: price,
        band_width: price,
        band_width_percent: percent,
        band_position: ratio,
      },
    }
    const donchian = {
      ...completeSignal,
      signal: "breakout_up",
      state: "above_channel",
      components: {
        upper_channel: price,
        middle_channel: price,
        lower_channel: price,
        previous_upper_channel: price,
        previous_lower_channel: price,
        channel_width: price,
        channel_width_percent: percent,
        channel_position: ratio,
      },
    }
    const keltner = {
      ...completeSignal,
      components: {
        middle_line: price,
        upper_channel: price,
        lower_channel: price,
        atr: price,
        channel_width: price,
        channel_width_percent: percent,
        channel_position: ratio,
      },
    }
    expect(indicatorSignalsSchema.parse({ bollinger, donchian, keltner })).toEqual({
      bollinger,
      donchian,
      keltner,
    })
    expect(() =>
      indicatorSignalsSchema.parse({
        donchian: {
          ...donchian,
          components: { ...donchian.components, unknown: price },
        },
      }),
    ).toThrow()
  })

  it("refuse une clé d'indicateur ou un champ de signal inconnu", () => {
    expect(() => indicatorSignalsSchema.parse({ ichimoku: completeSignal })).toThrow()
    expect(() => indicatorSignalSchema.parse({ ...completeSignal, confidence: 0.9 })).toThrow()
  })
})
