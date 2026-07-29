import { describe, expect, it } from "vitest"

import {
  mergeCandles,
  mergeIndicatorHistory,
  mergeMarkers,
  upsertRealtimeCandle,
} from "@/features/market/market-history"
import type { Candle, MarketMarker } from "@/types/market"

const candle = (time: number, close = time): Candle => ({
  time,
  open_time: time * 1_000,
  open: close,
  high: close,
  low: close,
  close,
  volume: 1,
  is_closed: true,
})

describe("market history merge", () => {
  it("préfixe, remplace les doublons et conserve l'ordre strict", () => {
    const result = mergeCandles(
      [candle(3), candle(4)],
      [candle(1), candle(2), candle(3, 99)],
    )
    expect(result.prependedCount).toBe(2)
    expect(result.candles.map((item) => item.time)).toEqual([1, 2, 3, 4])
    expect(result.candles[2].close).toBe(99)
  })

  it("met à jour incrémentalement la dernière bougie et en ajoute une nouvelle", () => {
    const updated = upsertRealtimeCandle([candle(1), candle(2)], candle(2, 20))
    expect(updated.map((item) => item.close)).toEqual([1, 20])
    expect(upsertRealtimeCandle(updated, candle(3)).map((item) => item.time))
      .toEqual([1, 2, 3])
  })

  it("fusionne indicateurs et marqueurs anciens sans troncature", () => {
    const indicators = mergeIndicatorHistory(
      { rsi_14: [{ time: 2, value: 2 }] },
      { rsi_14: [{ time: 1, value: 1 }, { time: 2, value: 22 }] },
    )
    expect(indicators.rsi_14).toEqual([
      { time: 1, value: 1 },
      { time: 2, value: 22 },
    ])
    const marker = (time: number): MarketMarker => ({
      time,
      position: "aboveBar",
      shape: "circle",
      color: "red",
      text: `m${time}`,
    })
    const current = Array.from({ length: 500 }, (_, index) => marker(index + 1))
    expect(mergeMarkers(current, [marker(0), marker(500)])).toHaveLength(501)
  })
})
