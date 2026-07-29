import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { marketApi } from "@/api/market"
import { useMarketHistory } from "@/features/market/use-market-history"
import { useMarketStore } from "@/stores/market-store"
import type { CandlePageResponse } from "@/types/market"
import type { Timeframe } from "@/types/scanner"

vi.mock("@/api/market", () => ({
  marketApi: { getCandles: vi.fn(), getCandleWindow: vi.fn() },
}))

function payload(symbol: string, time: number, hasMoreBefore = false): CandlePageResponse {
  return {
    exchange_id: "binance",
    market_type: "spot",
    symbol,
    timeframe: "1h",
    candles: [{
      time,
      open_time: time * 1_000,
      open: 1,
      high: 1,
      low: 1,
      close: 1,
      volume: 1,
      is_closed: true,
    }],
    indicators: {},
    markers: [],
    page: {
      limit: 2_000,
      count: 1,
      oldest_open_time: time * 1_000,
      newest_open_time: time * 1_000,
      next_before: time * 1_000,
      next_after: time * 1_000,
      has_more_before: hasMoreBefore,
      has_more_after: false,
    },
    coverage: {
      earliest_open_time: time * 1_000,
      latest_open_time: time * 1_000,
      total_candles: 1,
      is_complete: true,
      gap_count: 0,
      available_from: time * 1_000,
      available_to: time * 1_000,
      local_earliest_time: time * 1_000,
      exchange_earliest_time: hasMoreBefore ? null : time * 1_000,
      exchange_earliest_verified: !hasMoreBefore,
      local_candle_count: 1,
      is_earliest_known: !hasMoreBefore,
      is_recent_complete: true,
      history_last_error: null,
    },
    source: { read_from_sqlite: true, downloaded_from_exchange: 0 },
    anchor_time: null,
    anchor_before_available: false,
  }
}

describe("useMarketHistory", () => {
  beforeEach(() => {
    vi.mocked(marketApi.getCandles).mockReset()
    vi.mocked(marketApi.getCandleWindow).mockReset()
    useMarketStore.getState().resetMarket("", "1h")
  })

  it("annule l'ancienne requête et ignore sa réponse tardive", async () => {
    let resolveBtc!: (value: CandlePageResponse) => void
    const btc = new Promise<CandlePageResponse>((resolve) => { resolveBtc = resolve })
    vi.mocked(marketApi.getCandles)
      .mockReturnValueOnce(btc)
      .mockResolvedValueOnce(payload("ETH/USDC", 2))

    const { rerender } = renderHook(
      ({ symbol, timeframe }: { symbol: string; timeframe: Timeframe }) =>
        useMarketHistory(symbol, timeframe),
      { initialProps: { symbol: "BTC/USDC", timeframe: "1h" } },
    )
    const firstSignal = vi.mocked(marketApi.getCandles).mock.calls[0][0].signal
    rerender({ symbol: "ETH/USDC", timeframe: "1h" })
    expect(firstSignal?.aborted).toBe(true)
    await waitFor(() => expect(useMarketStore.getState().candles[0]?.time).toBe(2))
    await act(async () => resolveBtc(payload("BTC/USDC", 1)))
    expect(useMarketStore.getState().selectionKey).toBe("ETH/USDC|1h")
    expect(useMarketStore.getState().candles.map((item) => item.time)).toEqual([2])
  })

  it("verrouille deux demandes de page simultanées", async () => {
    let resolvePage!: (value: CandlePageResponse) => void
    vi.mocked(marketApi.getCandles)
      .mockResolvedValueOnce(payload("BTC/USDC", 3, true))
      .mockReturnValueOnce(new Promise((resolve) => { resolvePage = resolve }))
    const { result } = renderHook(() => useMarketHistory("BTC/USDC", "1h"))
    await waitFor(() => expect(useMarketStore.getState().historyInitialized).toBe(true))
    await act(async () => {
      const first = result.current.loadMore()
      const second = result.current.loadMore()
      expect(await second).toBe(0)
      resolvePage(payload("BTC/USDC", 2))
      await first
    })
    expect(marketApi.getCandles).toHaveBeenCalledTimes(2)
    expect(vi.mocked(marketApi.getCandles).mock.calls[1][0].before).toBe(3_000)
  })

  it("charge directement une fenêtre historique autour d'une date", async () => {
    vi.mocked(marketApi.getCandles).mockResolvedValueOnce(
      payload("BTC/USDC", 3, true),
    )
    const historical = payload("BTC/USDC", 1, true)
    vi.mocked(marketApi.getCandleWindow).mockResolvedValueOnce({
      ...historical,
      anchor_time: 1_000,
      page: { ...historical.page, has_more_after: true },
    })
    const { result } = renderHook(() => useMarketHistory("BTC/USDC", "1h"))
    await waitFor(() => expect(useMarketStore.getState().historyInitialized).toBe(true))
    await act(async () => result.current.jumpToDate(1_000))
    expect(marketApi.getCandleWindow).toHaveBeenCalledWith(
      expect.objectContaining({ anchorTime: 1_000 }),
    )
    expect(useMarketStore.getState().mode).toBe("historical")
    expect(useMarketStore.getState().followRealtime).toBe(false)
  })
})
