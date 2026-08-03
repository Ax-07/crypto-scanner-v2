import { describe, expect, it } from "vitest"
import type { Logical } from "lightweight-charts"

import {
  filterMarkersBySimultaneousIndicators,
  shiftedLogicalRange,
  shouldPrefetchHistory,
} from "@/components/dashboard/trading-chart"
import type { IndicatorVisibility, MarketMarker, MarkerIndicator } from "@/types/market"

const visibility: IndicatorVisibility = {
  ema: true,
  sma: true,
  bollinger: true,
  rsi: true,
  macd: true,
  stochastic: true,
  volatility: true,
  adx: true,
  supertrend: true,
  donchian: true,
  keltner: true,
  signals: true,
  divergences: true,
}

function signal(
  time: number,
  indicator: MarkerIndicator,
  text: string = indicator,
): MarketMarker {
  return {
    time,
    position: "aboveBar",
    shape: "circle",
    color: "#fff",
    text,
    category: "signal",
    indicator,
  }
}

function divergence(time: number): MarketMarker {
  return {
    time,
    position: "belowBar",
    shape: "circle",
    color: "#fff",
    text: "Divergence RSI",
    category: "divergence",
    source: "RSI",
  }
}

describe("trading chart viewport", () => {
  it("compense la plage logique avec le nombre réellement préfixé", () => {
    expect(shiftedLogicalRange({ from: 20 as Logical, to: 120 as Logical }, 2_000))
      .toEqual({ from: 2_020, to: 2_120 })
    expect(shiftedLogicalRange({ from: 20 as Logical, to: 120 as Logical }, 0))
      .toEqual({ from: 20, to: 120 })
  })

  it("précharge au seuil uniquement quand une page peut partir", () => {
    const range = { from: 100 as Logical, to: 200 as Logical }
    expect(shouldPrefetchHistory(range, 100, true, true, false)).toBe(true)
    expect(shouldPrefetchHistory(range, 99, true, true, false)).toBe(false)
    expect(shouldPrefetchHistory(range, 100, true, true, true)).toBe(false)
    expect(shouldPrefetchHistory(range, 100, true, false, false)).toBe(false)
  })
})

describe("simultaneous marker filter", () => {
  it("conserve tous les signaux d'une bougie qui atteint le seuil", () => {
    const markers = [
      signal(10, "rsi"),
      signal(10, "macd"),
      signal(10, "supertrend"),
      signal(20, "rsi"),
      signal(20, "macd"),
    ]
    expect(filterMarkersBySimultaneousIndicators(markers, visibility, 3))
      .toEqual(markers.slice(0, 3))
  })

  it("recalcule le compteur avec les indicateurs visibles", () => {
    const markers = [signal(10, "rsi"), signal(10, "macd"), signal(10, "supertrend")]
    expect(filterMarkersBySimultaneousIndicators(
      markers,
      { ...visibility, rsi: false },
      3,
    )).toEqual([])
  })

  it("compte un indicateur une seule fois par bougie", () => {
    const markers = [
      signal(10, "rsi", "RSI A"),
      signal(10, "rsi", "RSI B"),
      signal(10, "macd"),
    ]
    expect(filterMarkersBySimultaneousIndicators(markers, visibility, 3))
      .toEqual([])
  })

  it("laisse les divergences indépendantes du seuil et des signaux", () => {
    const rsiDivergence = divergence(10)
    expect(filterMarkersBySimultaneousIndicators(
      [signal(10, "rsi"), rsiDivergence],
      { ...visibility, signals: false },
      5,
    )).toEqual([rsiDivergence])
  })
})
