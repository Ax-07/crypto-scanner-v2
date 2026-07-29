import { useCallback, useEffect, useRef, useState } from "react"

import { marketApi } from "@/api/market"
import { useMarketStore } from "@/stores/market-store"
import type { Timeframe } from "@/types/scanner"
import type { MarketIndicatorConfig } from "@/types/market"

const INITIAL_LIMIT = positiveInteger(
  import.meta.env.VITE_MARKET_INITIAL_CANDLE_LIMIT,
  1_000,
)
const PAGE_LIMIT = positiveInteger(
  import.meta.env.VITE_MARKET_HISTORY_PAGE_LIMIT,
  1_000,
)
const WINDOW_BEFORE = positiveInteger(
  import.meta.env.VITE_MARKET_HISTORY_WINDOW_BEFORE,
  500,
)
const WINDOW_AFTER = positiveInteger(
  import.meta.env.VITE_MARKET_HISTORY_WINDOW_AFTER,
  500,
)
const MEMORY_LIMIT = Number(import.meta.env.VITE_MARKET_MAX_CANDLES_IN_MEMORY) > 0
  ? Math.floor(Number(import.meta.env.VITE_MARKET_MAX_CANDLES_IN_MEMORY))
  : 0

function positiveInteger(value: unknown, fallback: number) {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback
}

function boundedLimit(requested: number, loaded = 0) {
  return MEMORY_LIMIT > 0
    ? Math.max(1, Math.min(requested, MEMORY_LIMIT - loaded))
    : requested
}

function errorMessage(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Impossible de charger l'historique du marché"
}

export function useMarketHistory(
  symbol: string,
  timeframe: Timeframe,
  profile?: MarketIndicatorConfig,
) {
  const [loadingAll, setLoadingAll] = useState(false)
  const generationRef = useRef(0)
  const requestRef = useRef<AbortController | null>(null)
  const loadAllRef = useRef<AbortController | null>(null)
  const retryRef = useRef<
    | { kind: "initial" }
    | { kind: "before" }
    | { kind: "after" }
    | { kind: "jump"; anchorTime: number }
  >({ kind: "initial" })

  const loadLatest = useCallback(async (
    generation: number,
    controller: AbortController,
    syncMissing: boolean,
  ) => {
    const response = await marketApi.getCandles({
      symbol,
      timeframe,
      limit: boundedLimit(INITIAL_LIMIT),
      syncMissing,
      signal: controller.signal,
      profile,
    })
    useMarketStore.getState().initializeHistory(response, generation)
  }, [symbol, timeframe, profile])

  useEffect(() => {
    requestRef.current?.abort()
    loadAllRef.current?.abort()
    const generation = useMarketStore.getState().resetMarket(symbol, timeframe)
    generationRef.current = generation
    const controller = new AbortController()
    requestRef.current = controller
    const state = useMarketStore.getState()
    retryRef.current = { kind: "initial" }
    state.setHistoryActivity(generation, "initial", true)
    void loadLatest(generation, controller, false).catch((error: unknown) => {
      if (!controller.signal.aborted) {
        state.setHistoryError(generation, errorMessage(error))
        state.setHistoryActivity(generation, "initial", false)
      }
    })
    return () => {
      controller.abort()
      loadAllRef.current?.abort()
    }
  }, [loadLatest, symbol, timeframe])

  const loadMore = useCallback(async () => {
    const state = useMarketStore.getState()
    const generation = generationRef.current
    if (
      state.historyLoading
      || !state.historyInitialized
      || !state.hasMoreBefore
      || state.earliestLoadedTime === null
      || state.historyRequestGeneration !== generation
    ) return 0
    const controller = new AbortController()
    requestRef.current = controller
    retryRef.current = { kind: "before" }
    state.setHistoryActivity(generation, "before", true)
    try {
      const response = await marketApi.getCandles({
        symbol,
        timeframe,
        before: state.earliestLoadedTime,
        limit: boundedLimit(PAGE_LIMIT, state.loadedCandleCount),
        syncMissing: true,
        signal: controller.signal,
        profile,
      })
      return useMarketStore.getState().prependHistory(response, generation)
    } catch (error) {
      if (!controller.signal.aborted) {
        useMarketStore.getState().setHistoryError(generation, errorMessage(error))
        useMarketStore.getState().setHistoryActivity(generation, "before", false)
      }
      return 0
    }
  }, [symbol, timeframe, profile])

  const loadMoreAfter = useCallback(async () => {
    const state = useMarketStore.getState()
    const generation = generationRef.current
    if (
      state.mode !== "historical"
      || state.historyLoading
      || !state.hasMoreAfter
      || state.latestLoadedTime === null
      || state.historyRequestGeneration !== generation
    ) return 0
    const controller = new AbortController()
    requestRef.current = controller
    retryRef.current = { kind: "after" }
    state.setHistoryActivity(generation, "after", true)
    try {
      const response = await marketApi.getCandles({
        symbol,
        timeframe,
        after: state.latestLoadedTime,
        limit: boundedLimit(PAGE_LIMIT, state.loadedCandleCount),
        syncMissing: true,
        signal: controller.signal,
        profile,
      })
      return useMarketStore.getState().appendHistory(response, generation)
    } catch (error) {
      if (!controller.signal.aborted) {
        useMarketStore.getState().setHistoryError(generation, errorMessage(error))
        useMarketStore.getState().setHistoryActivity(generation, "after", false)
      }
      return 0
    }
  }, [symbol, timeframe, profile])

  const jumpToDate = useCallback(async (anchorTime: number) => {
    requestRef.current?.abort()
    const generation = generationRef.current
    const controller = new AbortController()
    requestRef.current = controller
    retryRef.current = { kind: "jump", anchorTime }
    const state = useMarketStore.getState()
    state.setHistoryActivity(generation, "jump", true)
    state.setHistoryError(generation, null)
    try {
      const response = await marketApi.getCandleWindow({
        symbol,
        timeframe,
        anchorTime,
        beforeCount: WINDOW_BEFORE,
        afterCount: WINDOW_AFTER,
        signal: controller.signal,
        profile,
      })
      useMarketStore.getState().replaceHistoricalWindow(
        response,
        generation,
        anchorTime,
      )
    } catch (error) {
      if (!controller.signal.aborted) {
        useMarketStore.getState().setHistoryError(generation, errorMessage(error))
        useMarketStore.getState().setHistoryActivity(generation, "jump", false)
      }
    }
  }, [symbol, timeframe, profile])

  const returnToLive = useCallback(async () => {
    requestRef.current?.abort()
    loadAllRef.current?.abort()
    const generation = generationRef.current
    const controller = new AbortController()
    requestRef.current = controller
    retryRef.current = { kind: "initial" }
    const state = useMarketStore.getState()
    state.setHistoryActivity(generation, "initial", true)
    state.setHistoryError(generation, null)
    try {
      await loadLatest(generation, controller, true)
      useMarketStore.getState().issueChartCommand("realtime")
    } catch (error) {
      if (!controller.signal.aborted) {
        useMarketStore.getState().setHistoryError(generation, errorMessage(error))
        useMarketStore.getState().setHistoryActivity(generation, "initial", false)
      }
    }
  }, [loadLatest])

  const goToBeginning = useCallback(async () => {
    if (loadAllRef.current) {
      loadAllRef.current.abort()
      return
    }
    const controller = new AbortController()
    loadAllRef.current = controller
    setLoadingAll(true)
    const generation = generationRef.current
    try {
      while (!controller.signal.aborted) {
        const state = useMarketStore.getState()
        if (
          state.historyRequestGeneration !== generation
          || !state.hasMoreBefore
          || state.earliestLoadedTime === null
          || state.historyLoading
        ) break
        state.setHistoryActivity(generation, "before", true)
        const response = await marketApi.getCandles({
          symbol,
          timeframe,
          before: state.earliestLoadedTime,
          limit: boundedLimit(PAGE_LIMIT, state.loadedCandleCount),
          syncMissing: true,
          signal: controller.signal,
          profile,
        })
        state.prependHistory(response, generation)
      }
      if (!controller.signal.aborted) {
        useMarketStore.getState().issueChartCommand("beginning")
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        useMarketStore.getState().setHistoryError(generation, errorMessage(error))
      }
    } finally {
      useMarketStore.getState().setHistoryActivity(generation, "before", false)
      if (loadAllRef.current === controller) loadAllRef.current = null
      setLoadingAll(false)
    }
  }, [symbol, timeframe, profile])

  const retry = useCallback(() => {
    const action = retryRef.current
    switch (action.kind) {
      case "jump":
        void jumpToDate(action.anchorTime)
        break
      case "before":
        void loadMore()
        break
      case "after":
        void loadMoreAfter()
        break
      default:
        void returnToLive()
    }
  }, [jumpToDate, loadMore, loadMoreAfter, returnToLive])

  return {
    loadMore,
    loadMoreAfter,
    jumpToDate,
    returnToLive,
    goToBeginning,
    retry,
    loadingAll,
  }
}
