import { renderHook, waitFor } from "@testing-library/react"
import { act } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { marketApi } from "@/api/market"
import { useMarketSocket } from "@/features/market/use-market-socket"
import { useMarketStore } from "@/stores/market-store"
import type { Timeframe } from "@/types/scanner"

class FakeSocket {
  static instances: FakeSocket[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  closed = false
  constructor(readonly url: string) { FakeSocket.instances.push(this) }
  close() { this.closed = true; this.onclose?.() }
  message(value: unknown) {
    this.onmessage?.({ data: JSON.stringify(value) } as MessageEvent)
  }
}

describe("useMarketSocket", () => {
  beforeEach(() => {
    FakeSocket.instances = []
    vi.stubGlobal("WebSocket", FakeSocket)
    vi.restoreAllMocks()
    useMarketStore.getState().resetStream()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("remplace le socket et ignore les messages de l'ancienne paire", () => {
    const { rerender, unmount } = renderHook(
      ({ symbol, timeframe }: { symbol: string; timeframe: Timeframe }) =>
        useMarketSocket(symbol, timeframe),
      { initialProps: { symbol: "BTC/USDC", timeframe: "1h" } },
    )
    const first = FakeSocket.instances[0]
    rerender({ symbol: "ETH/USDC", timeframe: "4h" })
    expect(first.closed).toBe(true)
    expect(FakeSocket.instances[1].url).toContain("symbol=ETH%2FUSDC")
    first.message({
      type: "history",
      symbol: "BTC/USDC",
      timeframe: "1h",
      candles: [{ time: 1 }],
      indicators: {},
      markers: [],
      snapshot: {},
    })
    expect(useMarketStore.getState().candles).toEqual([])
    unmount()
    expect(FakeSocket.instances[1].closed).toBe(true)
  })

  it("réamorce puis relit SQLite quand le premier historique est vide", async () => {
    useMarketStore.getState().resetMarket("BTC/USDC", "1h")
    const response = {
      exchange_id: "binance",
      market_type: "spot",
      symbol: "BTC/USDC",
      timeframe: "1h",
      candles: [{
        time: 1, open_time: 1_000, open: 1, high: 2, low: 0.5,
        close: 1.5, volume: 10, is_closed: true,
      }],
      indicators: {},
      markers: [],
      page: {
        limit: 2_000, count: 1, oldest_open_time: 1_000,
        newest_open_time: 1_000, next_before: 1_000, has_more_before: false,
        next_after: 1_000, has_more_after: false,
      },
      coverage: {
        earliest_open_time: 1_000, latest_open_time: 1_000,
        total_candles: 1, is_complete: false, gap_count: 0,
        available_from: 1_000, available_to: 1_000, local_candle_count: 1,
        local_earliest_time: 1_000, exchange_earliest_time: null,
        exchange_earliest_verified: false, history_last_error: null,
        is_earliest_known: false, is_recent_complete: true,
      },
      source: { read_from_sqlite: true, downloaded_from_exchange: 0 },
      anchor_time: null,
      anchor_before_available: false,
    }
    vi.spyOn(marketApi, "getCandles").mockResolvedValue(response)
    const { unmount } = renderHook(() =>
      useMarketSocket("BTC/USDC", "1h", true, true),
    )
    const socket = FakeSocket.instances[0]
    expect(socket.url).toContain("include_history=true")
    socket.message({
      type: "history",
      symbol: "BTC/USDC",
      timeframe: "1h",
      candles: response.candles,
      indicators: {},
      markers: [],
      snapshot: {},
    })
    await waitFor(() => expect(marketApi.getCandles).toHaveBeenCalled())
    await waitFor(() =>
      expect(useMarketStore.getState().coverage?.total_candles).toBe(1),
    )
    unmount()
  })

  it("rejects an invalid runtime message without mutating market data", () => {
    useMarketStore.getState().resetMarket("BTC/USDC", "1h")
    const { unmount } = renderHook(() => useMarketSocket("BTC/USDC", "1h"))
    FakeSocket.instances[0].message({ type: "update", candle: { time: "bad" } })
    expect(useMarketStore.getState().connectionError).toContain("contrat de marché")
    expect(useMarketStore.getState().candles).toEqual([])
    unmount()
  })

  it("reconnecte automatiquement en conservant le dernier snapshot", () => {
    vi.useFakeTimers()
    useMarketStore.getState().resetMarket("BTC/USDC", "1h")
    useMarketStore.setState({
      snapshot: { confirmed: { price: 42, indicator_signals: {} } },
    })
    const { unmount } = renderHook(() => useMarketSocket("BTC/USDC", "1h"))
    const first = FakeSocket.instances[0]

    act(() => first.onclose?.())
    expect(useMarketStore.getState().status).toBe("disconnected")
    expect(useMarketStore.getState().snapshot.confirmed?.price).toBe(42)

    act(() => vi.advanceTimersByTime(2_000))
    expect(FakeSocket.instances).toHaveLength(2)
    expect(useMarketStore.getState().status).toBe("connecting")
    expect(useMarketStore.getState().snapshot.confirmed?.price).toBe(42)
    unmount()
  })
})
