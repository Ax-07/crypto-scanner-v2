import { beforeEach, describe, expect, it } from "vitest"

import { marketMessageSchema } from "@/api/market"
import { useMarketStore } from "@/stores/market-store"
import type { CandlePageResponse } from "@/types/market"

function response(symbol: string, times: number[]): CandlePageResponse {
  return {
    exchange_id: "binance",
    market_type: "spot",
    symbol,
    timeframe: "1h",
    candles: times.map((time) => ({
      time,
      open_time: time * 1_000,
      open: 1,
      high: 2,
      low: 0,
      close: 1,
      volume: 1,
      is_closed: true,
    })),
    indicators: {},
    markers: [],
    page: {
      limit: 2,
      count: times.length,
      oldest_open_time: times[0] ? times[0] * 1_000 : null,
      newest_open_time: times.at(-1) ? times.at(-1)! * 1_000 : null,
      next_before: times[0] ? times[0] * 1_000 : null,
      next_after: times.at(-1) ? times.at(-1)! * 1_000 : null,
      has_more_before: times[0] !== 1,
      has_more_after: false,
    },
    coverage: {
      earliest_open_time: 1_000,
      latest_open_time: 4_000,
      total_candles: 4,
      is_complete: true,
      gap_count: 0,
      available_from: 1_000,
      available_to: 4_000,
      local_earliest_time: 1_000,
      exchange_earliest_time: 1_000,
      exchange_earliest_verified: true,
      local_candle_count: 4,
      is_earliest_known: true,
      is_recent_complete: true,
      history_last_error: null,
    },
    source: { read_from_sqlite: true, downloaded_from_exchange: 0 },
    anchor_time: null,
    anchor_before_available: false,
  }
}

describe("market store history generations", () => {
  beforeEach(() => useMarketStore.getState().resetMarket("BTC/USDC", "1h"))

  it("ignore une réponse tardive de l'ancienne sélection", () => {
    const oldGeneration = useMarketStore.getState().historyRequestGeneration
    const generation = useMarketStore.getState().resetMarket("ETH/USDC", "1h")
    useMarketStore.getState().initializeHistory(response("BTC/USDC", [1, 2]), oldGeneration)
    expect(useMarketStore.getState().candles).toEqual([])
    useMarketStore.getState().initializeHistory(response("ETH/USDC", [3, 4]), generation)
    expect(useMarketStore.getState().candles.map((item) => item.time)).toEqual([3, 4])
  })

  it("expose le nombre réellement préfixé après déduplication", () => {
    const generation = useMarketStore.getState().historyRequestGeneration
    useMarketStore.getState().initializeHistory(response("BTC/USDC", [3, 4]), generation)
    const added = useMarketStore.getState().prependHistory(
      response("BTC/USDC", [1, 2, 3]),
      generation,
    )
    expect(added).toBe(2)
    expect(useMarketStore.getState().historyPrependCount).toBe(2)
    expect(useMarketStore.getState().loadedCandleCount).toBe(4)
  })

  it("ne recopie pas tout l'historique à chaque variation de la bougie ouverte", () => {
    const generation = useMarketStore.getState().historyRequestGeneration
    useMarketStore.getState().initializeHistory(response("BTC/USDC", [3, 4]), generation)
    const reference = useMarketStore.getState().candles
    useMarketStore.getState().applyUpdate({
      type: "update",
      candle: { ...reference[1], close: 99 },
      indicators: { rsi_14: { time: 4, value: 50 } },
      markers: [],
      snapshot: {},
    }, "BTC/USDC|1h")
    expect(useMarketStore.getState().candles).toBe(reference)
    expect(useMarketStore.getState().latestCandle?.close).toBe(99)
  })

  it("isole les updates live pendant la consultation historique", () => {
    const generation = useMarketStore.getState().historyRequestGeneration
    useMarketStore.getState().initializeHistory(response("BTC/USDC", [3, 4]), generation)
    useMarketStore.getState().replaceHistoricalWindow(
      response("BTC/USDC", [1, 2]),
      generation,
      2_000,
    )
    const historical = useMarketStore.getState().candles
    useMarketStore.getState().applyUpdate({
      type: "update",
      candle: { ...historical[1], time: 5, open_time: 5_000, close: 99 },
      indicators: {},
      markers: [],
      snapshot: {},
    }, "BTC/USDC|1h")
    expect(useMarketStore.getState().candles).toBe(historical)
    expect(useMarketStore.getState().candles.map((item) => item.time)).toEqual([1, 2])
    expect(useMarketStore.getState().latestCandle?.time).toBe(5)
  })

  it("revient au live sans fusionner deux plages disjointes", () => {
    const generation = useMarketStore.getState().historyRequestGeneration
    useMarketStore.getState().replaceHistoricalWindow(
      response("BTC/USDC", [1, 2]),
      generation,
      2_000,
    )
    useMarketStore.getState().initializeHistory(
      response("BTC/USDC", [100, 101]),
      generation,
    )
    expect(useMarketStore.getState().mode).toBe("live")
    expect(useMarketStore.getState().candles.map((item) => item.time)).toEqual([100, 101])
    expect(useMarketStore.getState().followRealtime).toBe(true)
  })

  it("un message WebSocket history ne supprime pas les pages anciennes", () => {
    const generation = useMarketStore.getState().historyRequestGeneration
    useMarketStore.getState().initializeHistory(response("BTC/USDC", [3, 4]), generation)
    useMarketStore.getState().prependHistory(
      response("BTC/USDC", [1, 2]),
      generation,
    )
    useMarketStore.getState().applyHistory({
      type: "history",
      symbol: "BTC/USDC",
      timeframe: "1h",
      candles: response("BTC/USDC", [4]).candles,
      indicators: {},
      markers: [],
      snapshot: {},
    }, "BTC/USDC|1h")
    expect(useMarketStore.getState().candles.map((item) => item.time)).toEqual([
      1, 2, 3, 4,
    ])
  })

  it.each(["history", "update"] as const)(
    "préserve indicator_signals après parsing puis stockage d'un message %s",
    (type) => {
      const signal = {
        status: "available",
        direction: "bullish",
        signal: "exit_oversold",
        state: "near_oversold",
        strength: 0.75,
        reason: "Sortie de survente",
        raw_value: null,
      } as const
      const snapshot = {
        price: 100,
        indicator_signals: {
          rsi: signal,
          macd: {
            ...signal,
            status: "invalid_data" as const,
            direction: "neutral" as const,
            signal: null,
          },
          stochastic: {
            ...signal,
            status: "disabled" as const,
            direction: "neutral" as const,
            signal: null,
          },
        },
      }
      const raw = type === "history"
        ? {
            type,
            symbol: "BTC/USDC",
            timeframe: "1h",
            candles: [],
            indicators: {},
            markers: [],
            snapshot,
          }
        : {
            type,
            candle: { time: 5, open: 1, high: 2, low: 0, close: 1, volume: 1 },
            indicators: {},
            markers: [],
            snapshot,
          }
      const parsed = marketMessageSchema.parse(raw)
      if (parsed.type === "history") {
        useMarketStore.getState().applyHistory(parsed, "BTC/USDC|1h")
      } else if (parsed.type === "update") {
        useMarketStore.getState().applyUpdate(parsed, "BTC/USDC|1h")
      }
      expect(useMarketStore.getState().snapshot.indicator_signals).toEqual(
        snapshot.indicator_signals,
      )
    },
  )
})
