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

  it("refuse une clé d'indicateur ou un champ de signal inconnu", () => {
    expect(() => indicatorSignalsSchema.parse({ ichimoku: completeSignal })).toThrow()
    expect(() => indicatorSignalSchema.parse({ ...completeSignal, confidence: 0.9 })).toThrow()
  })
})
