import { create } from "zustand"

import {
  applyIndicatorUpdates,
  mergeCandles,
  mergeIndicatorHistory,
  mergeMarkers,
  normalizeMarker,
  upsertRealtimeCandle,
} from "@/features/market/market-history"
import type {
  Candle,
  CandleCoverage,
  CandlePageResponse,
  ChartCommand,
  ConnectionStatus,
  HistoryMessage,
  IndicatorHistory,
  IndicatorUpdates,
  IndicatorVisibility,
  MarketMarker,
  MarketMode,
  MarketSnapshot,
  UpdateMessage,
} from "@/types/market"

type HistoryActivity = "initial" | "before" | "after" | "jump"

interface MarketStore {
  memoryLimit: number
  selectionKey: string
  historyRequestGeneration: number
  mode: MarketMode
  status: ConnectionStatus
  connectionError: string | null
  candles: Candle[]
  indicators: IndicatorHistory
  markers: MarketMarker[]
  snapshot: MarketSnapshot
  latestCandle: Candle | null
  latestIndicators: IndicatorUpdates
  earliestLoadedTime: number | null
  latestLoadedTime: number | null
  coverage: CandleCoverage | null
  downloadedFromExchange: number
  hasMoreBefore: boolean
  hasMoreAfter: boolean
  historyLoading: boolean
  loadingInitial: boolean
  loadingBefore: boolean
  loadingAfter: boolean
  jumpingToDate: boolean
  historyInitialized: boolean
  historyError: string | null
  requestedAnchorTime: number | null
  followRealtime: boolean
  loadedCandleCount: number
  historyVersion: number
  historyPrependCount: number
  updateVersion: number
  chartCommand: ChartCommand | null
  chartCommandVersion: number
  visibility: IndicatorVisibility
  minimumSimultaneousMarkers: number
  resetMarket: (symbol: string, timeframe: string) => number
  setConnection: (status: ConnectionStatus, error?: string | null) => void
  setHistoryLoading: (generation: number, loading: boolean) => void
  setHistoryActivity: (
    generation: number,
    activity: HistoryActivity,
    loading: boolean,
  ) => void
  setHistoryError: (generation: number, error: string | null) => void
  initializeHistory: (response: CandlePageResponse, generation: number) => void
  prependHistory: (response: CandlePageResponse, generation: number) => number
  appendHistory: (response: CandlePageResponse, generation: number) => number
  replaceHistoricalWindow: (
    response: CandlePageResponse,
    generation: number,
    anchorTime: number,
  ) => void
  mergeRecentHistory: (response: CandlePageResponse, generation: number) => void
  applyHistory: (message: HistoryMessage, selectionKey?: string) => void
  applyUpdate: (message: UpdateMessage, selectionKey?: string) => void
  setFollowRealtime: (follow: boolean) => void
  issueChartCommand: (command: ChartCommand) => void
  toggleVisibility: (key: keyof IndicatorVisibility) => void
  setMinimumSimultaneousMarkers: (minimum: number) => void
  resetStream: () => void
}

const defaultVisibility: IndicatorVisibility = {
  ema: false,
  sma: false,
  bollinger: false,
  rsi: false,
  macd: false,
  stochastic: false,

  volatility: true,
  adx: true,
  supertrend: true,
  donchian: true,
  keltner: true,

  signals: true,
  divergences: false,
}

const MEMORY_LIMIT = (() => {
  const value = Number(import.meta.env.VITE_MARKET_MAX_CANDLES_IN_MEMORY)
  return Number.isInteger(value) && value > 0 ? value : 0
})()

function candleOpenTime(candle: Candle | undefined) {
  return candle ? (candle.open_time ?? candle.time * 1_000) : null
}

function sameSelection(state: MarketStore, response: CandlePageResponse, generation: number) {
  return generation === state.historyRequestGeneration
    && `${response.symbol}|${response.timeframe}` === state.selectionKey
}

function pageState(
  state: MarketStore,
  response: CandlePageResponse,
  candles: Candle[],
) {
  return {
    earliestLoadedTime: candleOpenTime(candles[0]),
    latestLoadedTime: candleOpenTime(candles[candles.length - 1]),
    coverage: response.coverage,
    downloadedFromExchange: response.source.downloaded_from_exchange,
    hasMoreBefore: response.page.has_more_before,
    hasMoreAfter: response.page.has_more_after,
    loadedCandleCount: candles.length,
  }
}

function mergeResponse(state: MarketStore, response: CandlePageResponse) {
  const currentCandles = state.mode === "live" && state.latestCandle
    ? upsertRealtimeCandle(state.candles, state.latestCandle)
    : state.candles
  const currentIndicators = state.mode === "live"
    ? applyIndicatorUpdates(state.indicators, state.latestIndicators)
    : state.indicators
  const merged = mergeCandles(currentCandles, response.candles)
  return {
    candles: merged.candles,
    indicators: mergeIndicatorHistory(currentIndicators, response.indicators),
    markers: mergeMarkers(state.markers, response.markers),
    ...pageState(state, response, merged.candles),
    historyVersion: state.historyVersion + 1,
    historyPrependCount: merged.prependedCount,
  }
}

function activityState(activity: HistoryActivity, loading: boolean) {
  return {
    historyLoading: loading,
    loadingInitial: activity === "initial" ? loading : false,
    loadingBefore: activity === "before" ? loading : false,
    loadingAfter: activity === "after" ? loading : false,
    jumpingToDate: activity === "jump" ? loading : false,
  }
}

export const useMarketStore = create<MarketStore>()((set) => ({
  memoryLimit: MEMORY_LIMIT,
  selectionKey: "",
  historyRequestGeneration: 0,
  mode: "live",
  status: "disconnected",
  connectionError: null,
  candles: [],
  indicators: {},
  markers: [],
  snapshot: {},
  latestCandle: null,
  latestIndicators: {},
  earliestLoadedTime: null,
  latestLoadedTime: null,
  coverage: null,
  downloadedFromExchange: 0,
  hasMoreBefore: false,
  hasMoreAfter: false,
  historyLoading: false,
  loadingInitial: false,
  loadingBefore: false,
  loadingAfter: false,
  jumpingToDate: false,
  historyInitialized: false,
  historyError: null,
  requestedAnchorTime: null,
  followRealtime: true,
  loadedCandleCount: 0,
  historyVersion: 0,
  historyPrependCount: 0,
  updateVersion: 0,
  chartCommand: null,
  chartCommandVersion: 0,
  visibility: defaultVisibility,
  minimumSimultaneousMarkers: 1,

  resetMarket: (symbol, timeframe) => {
    let generation = 0
    set((state) => {
      generation = state.historyRequestGeneration + 1
      return {
        selectionKey: `${symbol}|${timeframe}`,
        historyRequestGeneration: generation,
        mode: "live" as const,
        status: "disconnected" as const,
        connectionError: null,
        candles: [],
        indicators: {},
        markers: [],
        snapshot: {},
        latestCandle: null,
        latestIndicators: {},
        earliestLoadedTime: null,
        latestLoadedTime: null,
        coverage: null,
        downloadedFromExchange: 0,
        hasMoreBefore: false,
        hasMoreAfter: false,
        historyLoading: false,
        loadingInitial: false,
        loadingBefore: false,
        loadingAfter: false,
        jumpingToDate: false,
        historyInitialized: false,
        historyError: null,
        requestedAnchorTime: null,
        followRealtime: true,
        loadedCandleCount: 0,
        historyVersion: state.historyVersion + 1,
        historyPrependCount: 0,
      }
    })
    return generation
  },

  setConnection: (status, connectionError = null) => set({ status, connectionError }),
  setHistoryLoading: (generation, historyLoading) =>
    set((state) => generation === state.historyRequestGeneration
      ? { historyLoading }
      : {}),
  setHistoryActivity: (generation, activity, loading) =>
    set((state) => generation === state.historyRequestGeneration
      ? activityState(activity, loading)
      : {}),
  setHistoryError: (generation, historyError) =>
    set((state) => generation === state.historyRequestGeneration
      ? { historyError }
      : {}),

  initializeHistory: (response, generation) =>
    set((state) => {
      if (!sameSelection(state, response, generation)) return {}
      const liveData = state.mode === "historical"
        ? (() => {
            const candles = state.latestCandle
              ? upsertRealtimeCandle(response.candles, state.latestCandle)
              : response.candles
            return {
              candles,
              indicators: applyIndicatorUpdates(
                response.indicators,
                state.latestIndicators,
              ),
              markers: response.markers.map(normalizeMarker),
              ...pageState(state, response, candles),
              historyVersion: state.historyVersion + 1,
              historyPrependCount: 0,
            }
          })()
        : mergeResponse({ ...state, mode: "live" as const }, response)
      return {
        ...liveData,
        ...activityState("initial", false),
        mode: "live",
        followRealtime: true,
        requestedAnchorTime: null,
        historyInitialized: true,
        historyError: null,
        snapshot: response.snapshot ?? state.snapshot,
      }
    }),

  prependHistory: (response, generation) => {
    let count = 0
    set((state) => {
      if (!sameSelection(state, response, generation)) return {}
      const merged = mergeResponse(state, response)
      count = merged.historyPrependCount
      return { ...merged, ...activityState("before", false), historyError: null }
    })
    return count
  },

  appendHistory: (response, generation) => {
    let count = 0
    set((state) => {
      if (!sameSelection(state, response, generation)) return {}
      const known = new Set(state.candles.map((candle) => candle.time))
      count = response.candles.filter((candle) => !known.has(candle.time)).length
      return {
        ...mergeResponse(state, response),
        ...activityState("after", false),
        historyPrependCount: 0,
        historyError: null,
      }
    })
    return count
  },

  replaceHistoricalWindow: (response, generation, requestedAnchorTime) =>
    set((state) => {
      if (!sameSelection(state, response, generation)) return {}
      return {
        mode: "historical",
        candles: response.candles,
        indicators: response.indicators,
        markers: response.markers.map(normalizeMarker),
        ...pageState(state, response, response.candles),
        ...activityState("jump", false),
        requestedAnchorTime,
        followRealtime: false,
        historyInitialized: true,
        historyError: response.anchor_before_available
          ? "La date précède la première période disponible pour ce marché"
          : null,
        historyVersion: state.historyVersion + 1,
        historyPrependCount: 0,
        chartCommand: "historical",
        chartCommandVersion: state.chartCommandVersion + 1,
      }
    }),

  mergeRecentHistory: (response, generation) =>
    set((state) => {
      if (!sameSelection(state, response, generation)) return {}
      if (state.mode === "historical") {
        return {
          coverage: response.coverage,
          downloadedFromExchange: response.source.downloaded_from_exchange,
        }
      }
      return mergeResponse(state, response)
    }),

  applyHistory: (message, expectedSelectionKey) =>
    set((state) => {
      const key = `${message.symbol}|${message.timeframe}`
      if (key !== state.selectionKey || (expectedSelectionKey && key !== expectedSelectionKey)) {
        return {}
      }
      if (state.mode === "historical") {
        return { status: "connected", connectionError: null, snapshot: message.snapshot }
      }
      const merged = mergeCandles(state.candles, message.candles)
      return {
        status: "connected",
        connectionError: null,
        candles: merged.candles,
        indicators: mergeIndicatorHistory(state.indicators, message.indicators),
        markers: mergeMarkers(state.markers, message.markers),
        snapshot: message.snapshot,
        earliestLoadedTime: candleOpenTime(merged.candles[0]),
        latestLoadedTime: candleOpenTime(merged.candles.at(-1)),
        loadedCandleCount: merged.candles.length,
        historyVersion: state.historyVersion + 1,
        historyPrependCount: merged.prependedCount,
      }
    }),

  applyUpdate: (message, expectedSelectionKey) =>
    set((state) => {
      if (expectedSelectionKey && expectedSelectionKey !== state.selectionKey) return {}
      if (state.mode === "historical") {
        return {
          latestCandle: message.candle,
          latestIndicators: message.indicators,
          snapshot: message.snapshot,
        }
      }
      const advances = state.latestCandle !== null
        && message.candle.time > state.latestCandle.time
      let candles = advances
        ? upsertRealtimeCandle(
            upsertRealtimeCandle(state.candles, state.latestCandle as Candle),
            message.candle,
          )
        : state.latestCandle === null
          && state.candles.at(-1)?.time !== message.candle.time
          ? upsertRealtimeCandle(state.candles, message.candle)
          : state.candles
      const trimmedCount = MEMORY_LIMIT > 0
        ? Math.max(0, candles.length - MEMORY_LIMIT)
        : 0
      if (trimmedCount) candles = candles.slice(trimmedCount)
      const indicators = advances
        ? applyIndicatorUpdates(state.indicators, state.latestIndicators)
        : state.indicators
      const minimumTime = candles[0]?.time ?? Number.NEGATIVE_INFINITY
      return {
        latestCandle: message.candle,
        latestIndicators: message.indicators,
        candles,
        indicators: Object.fromEntries(
          Object.entries(indicators).map(([key, points]) => [
            key,
            points?.filter((point) => point.time >= minimumTime),
          ]),
        ) as IndicatorHistory,
        markers: mergeMarkers(state.markers, message.markers)
          .filter((marker) => marker.time >= minimumTime),
        snapshot: message.snapshot,
        earliestLoadedTime: candleOpenTime(candles[0]),
        latestLoadedTime: candleOpenTime(candles.at(-1)),
        loadedCandleCount: candles.length,
        historyVersion: state.historyVersion + Number(trimmedCount > 0),
        historyPrependCount: -trimmedCount,
        updateVersion: state.updateVersion + 1,
      }
    }),

  setFollowRealtime: (followRealtime) => set({ followRealtime }),
  issueChartCommand: (chartCommand) =>
    set((state) => ({
      chartCommand,
      chartCommandVersion: state.chartCommandVersion + 1,
      followRealtime: chartCommand === "realtime" ? true : state.followRealtime,
    })),
  toggleVisibility: (key) =>
    set((state) => ({
      visibility: { ...state.visibility, [key]: !state.visibility[key] },
    })),
  setMinimumSimultaneousMarkers: (minimum) =>
    set({ minimumSimultaneousMarkers: Math.min(5, Math.max(1, Math.trunc(minimum))) }),
  resetStream: () => {
    const state = useMarketStore.getState()
    const [symbol = "", timeframe = ""] = state.selectionKey.split("|")
    state.resetMarket(symbol, timeframe)
  },
}))
