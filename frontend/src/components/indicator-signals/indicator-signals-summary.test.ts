import { describe, expect, it } from "vitest"

import {
  formatIndicatorDirectionCount,
  formatIndicatorSignalsCollectionMessage,
  getIndicatorSignalsCollectionState,
  summarizeIndicatorSignals,
} from "@/components/indicator-signals"
import type {
  IndicatorSignal,
  IndicatorSignals,
} from "@/types/indicator-signals"

const available: IndicatorSignal = {
  status: "available",
  direction: "bullish",
  signal: "bullish_cross",
  state: null,
  strength: 0.75,
  reason: null,
  raw_value: 42,
}

function unavailable(
  status: Exclude<IndicatorSignal["status"], "available">,
): IndicatorSignal {
  return {
    ...available,
    status,
    direction: "neutral",
    signal: null,
    strength: 0,
    raw_value: null,
  }
}

describe("summarizeIndicatorSignals", () => {
  it("compte tous les signaux disponibles et leurs directions", () => {
    expect(summarizeIndicatorSignals({
      rsi: available,
      macd: { ...available, direction: "bearish" },
      stochastic: { ...available, direction: "neutral" },
    })).toEqual({
      total: 3,
      available: 3,
      unavailable: 0,
      bullish: 1,
      bearish: 1,
      neutral: 1,
    })
  })

  it("compte les indisponibilités sans compter leur direction neutre contractuelle", () => {
    expect(summarizeIndicatorSignals({
      rsi: unavailable("insufficient_data"),
      macd: unavailable("invalid_data"),
      stochastic: unavailable("disabled"),
    })).toEqual({
      total: 3,
      available: 0,
      unavailable: 3,
      bullish: 0,
      bearish: 0,
      neutral: 0,
    })
  })

  it("gère un mélange et un dictionnaire partiel sans synthétiser les absents", () => {
    expect(summarizeIndicatorSignals({
      ema: available,
      bollinger: unavailable("invalid_data"),
    })).toMatchObject({
      total: 2,
      available: 1,
      unavailable: 1,
      bullish: 1,
    })
  })

  it("gère un objet vide sans muter la source", () => {
    const empty: IndicatorSignals = {}
    const before = JSON.stringify(empty)
    expect(summarizeIndicatorSignals(empty).total).toBe(0)
    expect(JSON.stringify(empty)).toBe(before)
  })

  it("ne mute pas un dictionnaire complet", () => {
    const signals: IndicatorSignals = {
      stochastic: unavailable("disabled"),
      rsi: available,
    }
    const before = structuredClone(signals)
    summarizeIndicatorSignals(signals)
    expect(signals).toEqual(before)
  })
})

describe("état et messages de la collection", () => {
  it("distingue payload historique, objet vide et dictionnaires disponibles", () => {
    expect(getIndicatorSignalsCollectionState(undefined)).toBe("legacy_absent")
    expect(getIndicatorSignalsCollectionState({})).toBe("empty")
    expect(getIndicatorSignalsCollectionState({ rsi: available })).toBe("available")
    expect(getIndicatorSignalsCollectionState({
      rsi: unavailable("insufficient_data"),
    })).toBe("available")
  })

  it.each([
    ["legacy_absent", "ce résultat", "Les signaux structurés ne sont pas disponibles pour ce résultat."],
    ["legacy_absent", "ce snapshot", "Les signaux structurés ne sont pas disponibles pour ce snapshot."],
    ["legacy_absent", "cette observation", "Les signaux structurés ne sont pas disponibles pour cette observation."],
    ["empty", "ce résultat", "Aucun signal structuré n’a été produit pour ce résultat."],
    ["empty", "ce snapshot", "Aucun signal structuré n’a été produit pour ce snapshot."],
    ["empty", "cette observation", "Aucun signal structuré n’a été produit pour cette observation."],
  ] as const)("formate %s pour %s", (state, context, expected) => {
    expect(formatIndicatorSignalsCollectionMessage({ state, context })).toBe(expected)
  })

  it("accorde les compteurs de direction", () => {
    expect(formatIndicatorDirectionCount("bullish", 1)).toBe("1 haussier")
    expect(formatIndicatorDirectionCount("bearish", 2)).toBe("2 baissiers")
    expect(formatIndicatorDirectionCount("neutral", 0)).toBe("0 neutres")
  })
})
