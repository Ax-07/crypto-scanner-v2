/**
 * Adaptateur impératif entre le store marché et Lightweight Charts.
 * Il distingue le remplacement d'un historique des mises à jour incrémentales.
 */
import { useEffect, useRef } from "react"
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type LogicalRange,
  type Logical,
  type LineData,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts"

import { useMarketStore } from "@/stores/market-store"
import type { Candle, IndicatorPoint, MarketMarker } from "@/types/market"

type CandleApi = ISeriesApi<"Candlestick">
type LineApi = ISeriesApi<"Line">
type HistogramApi = ISeriesApi<"Histogram">

interface SeriesRefs {
  candle: CandleApi
  ema20: LineApi
  ema50: LineApi
  sma20: LineApi
  sma50: LineApi
  bollingerUpper: LineApi
  bollingerMiddle: LineApi
  bollingerLower: LineApi
  rsi: LineApi
  macd: LineApi
  macdSignal: LineApi
  macdHistogram: HistogramApi
  stochasticK: LineApi
  stochasticD: LineApi
  markerPlugin: ISeriesMarkersPluginApi<Time>
}

type Props = { onLoadMore: () => void | Promise<number> }

const PREFETCH_THRESHOLD = (() => {
  const value = Number(import.meta.env.VITE_MARKET_PREFETCH_THRESHOLD_BARS)
  return Number.isInteger(value) && value >= 0 ? value : 100
})()

const periodOrder = (left: string, right: string) =>
  Number(left.split("_")[1]) - Number(right.split("_")[1])

/** Convertit les secondes Unix du backend vers le type nominal de Lightweight Charts. */
function chartTime(time: number): UTCTimestamp {
  return time as UTCTimestamp
}

function candleData(candle: Candle): CandlestickData<Time> {
  return { ...candle, time: chartTime(candle.time) }
}

function lineData(point: IndicatorPoint): LineData<Time> {
  return { time: chartTime(point.time), value: point.value }
}

function histogramData(point: IndicatorPoint): HistogramData<Time> {
  return {
    time: chartTime(point.time),
    value: point.value,
    color: point.value >= 0 ? "#22c55e" : "#ef4444",
  }
}

function chartMarker(marker: MarketMarker): SeriesMarker<Time> {
  return {
    time: chartTime(marker.time),
    position: marker.position,
    shape: marker.shape,
    color: marker.color,
    text: marker.text,
  }
}

export function shiftedLogicalRange(range: LogicalRange, prependedCount: number): LogicalRange {
  return {
    from: (Number(range.from) + prependedCount) as Logical,
    to: (Number(range.to) + prependedCount) as Logical,
  }
}

export function shouldPrefetchHistory(
  range: LogicalRange | null,
  threshold: number,
  initialized: boolean,
  hasMoreBefore: boolean,
  loading: boolean,
) {
  return Boolean(
    range
    && Number(range.from) <= threshold
    && initialized
    && hasMoreBefore
    && !loading,
  )
}

/**
 * Synchronise un graphique multi-panneaux avec l'historique et les updates du store.
 * L'instance impérative est créée une fois puis détruite explicitement au démontage.
 */
export function TradingChart({ onLoadMore }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<SeriesRefs | null>(null)
  const onLoadMoreRef = useRef(onLoadMore)
  const candleCountRef = useRef(0)
  const followingRealtimeRef = useRef(true)
  const initializedRef = useRef(false)

  const candles = useMarketStore((state) => state.candles)
  const indicators = useMarketStore((state) => state.indicators)
  const markers = useMarketStore((state) => state.markers)
  const latestCandle = useMarketStore((state) => state.latestCandle)
  const latestIndicators = useMarketStore((state) => state.latestIndicators)
  const historyVersion = useMarketStore((state) => state.historyVersion)
  const historyPrependCount = useMarketStore((state) => state.historyPrependCount)
  const updateVersion = useMarketStore((state) => state.updateVersion)
  const visibility = useMarketStore((state) => state.visibility)
  const chartCommand = useMarketStore((state) => state.chartCommand)
  const chartCommandVersion = useMarketStore((state) => state.chartCommandVersion)
  const mode = useMarketStore((state) => state.mode)
  const followRealtime = useMarketStore((state) => state.followRealtime)

  useEffect(() => {
    onLoadMoreRef.current = onLoadMore
  }, [onLoadMore])

  useEffect(() => {
    candleCountRef.current = candles.length
  }, [candles.length])

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#111827" },
        textColor: "#9ca3af",
        panes: {
          separatorColor: "#273244",
          separatorHoverColor: "#3b4b62",
          enableResize: true,
        },
      },
      grid: {
        vertLines: { color: "#1f2937" },
        horzLines: { color: "#1f2937" },
      },
      rightPriceScale: { borderColor: "#374151" },
      timeScale: {
        borderColor: "#374151",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 6,
        barSpacing: 7,
      },
      crosshair: { mode: CrosshairMode.Normal },
      localization: { locale: "fr-FR" },
    })

    const candle = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    }, 0)

    const ema20 = chart.addSeries(LineSeries, { title: "EMA 20", color: "#38bdf8", lineWidth: 2, priceLineVisible: false }, 0)
    const ema50 = chart.addSeries(LineSeries, { title: "EMA 50", color: "#f59e0b", lineWidth: 2, priceLineVisible: false }, 0)
    const sma20 = chart.addSeries(LineSeries, { title: "SMA 20", color: "#a78bfa", lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false }, 0)
    const sma50 = chart.addSeries(LineSeries, { title: "SMA 50", color: "#fb7185", lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false }, 0)
    const bollingerUpper = chart.addSeries(LineSeries, { title: "BB supérieure", color: "#64748b", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, 0)
    const bollingerMiddle = chart.addSeries(LineSeries, { title: "BB moyenne", color: "#94a3b8", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, 0)
    const bollingerLower = chart.addSeries(LineSeries, { title: "BB inférieure", color: "#64748b", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, 0)

    const rsi = chart.addSeries(LineSeries, {
      title: "RSI 14",
      color: "#c084fc",
      lineWidth: 2,
      priceLineVisible: false,
      autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }),
    }, 1)
    rsi.createPriceLine({ price: 70, color: "#ef4444", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "70" })
    rsi.createPriceLine({ price: 30, color: "#22c55e", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "30" })

    const macdHistogram = chart.addSeries(HistogramSeries, { title: "Histogramme", priceLineVisible: false, lastValueVisible: false }, 2)
    const macd = chart.addSeries(LineSeries, { title: "MACD", color: "#38bdf8", lineWidth: 2, priceLineVisible: false }, 2)
    const macdSignal = chart.addSeries(LineSeries, { title: "Signal", color: "#f59e0b", lineWidth: 2, priceLineVisible: false }, 2)

    const stochasticK = chart.addSeries(LineSeries, {
      title: "%K",
      color: "#38bdf8",
      lineWidth: 2,
      priceLineVisible: false,
      autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }),
    }, 3)
    const stochasticD = chart.addSeries(LineSeries, { title: "%D", color: "#f59e0b", lineWidth: 2, priceLineVisible: false }, 3)
    stochasticK.createPriceLine({ price: 80, color: "#ef4444", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "80" })
    stochasticK.createPriceLine({ price: 20, color: "#22c55e", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "20" })

    const markerPlugin = createSeriesMarkers(candle, [])

    chartRef.current = chart
    seriesRef.current = {
      candle,
      ema20,
      ema50,
      sma20,
      sma50,
      bollingerUpper,
      bollingerMiddle,
      bollingerLower,
      rsi,
      macd,
      macdSignal,
      macdHistogram,
      stochasticK,
      stochasticD,
      markerPlugin,
    }

    window.requestAnimationFrame(() => {
      const panes = chart.panes()
      panes[0]?.setStretchFactor(5)
      panes[1]?.setStretchFactor(1.35)
      panes[2]?.setStretchFactor(1.6)
      panes[3]?.setStretchFactor(1.35)
    })

    const handleLogicalRange = (range: LogicalRange | null) => {
      if (!range) return
      followingRealtimeRef.current = range.to >= candleCountRef.current - 3
      const state = useMarketStore.getState()
      if (
        state.mode === "live"
        && state.followRealtime
        && !followingRealtimeRef.current
      ) state.setFollowRealtime(false)
      if (shouldPrefetchHistory(
        range,
        PREFETCH_THRESHOLD,
        state.historyInitialized,
        state.hasMoreBefore,
        state.historyLoading,
      )) void onLoadMoreRef.current()
    }
    chart.timeScale().subscribeVisibleLogicalRangeChange(handleLogicalRange)

    return () => {
      // Lightweight Charts possède ses propres listeners et doit être libéré explicitement.
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(handleLogicalRange)
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [])

  useEffect(() => {
    const refs = seriesRef.current
    const chart = chartRef.current
    if (!refs || !chart || historyVersion === 0) return

    // Un historique remplace toutes les séries et recadre la plage visible.
    const previousRange = chart.timeScale().getVisibleLogicalRange()
    refs.candle.setData(candles.map(candleData))
    const keys = Object.keys(indicators)
    const emaKeys = keys.filter((key) => /^ema_\d+$/.test(key)).sort(periodOrder)
    const smaKeys = keys.filter((key) => /^sma_\d+$/.test(key)).sort(periodOrder)
    const rsiKey = keys.find((key) => /^rsi_\d+$/.test(key))
    refs.ema20.setData((indicators[emaKeys[0] as keyof typeof indicators] ?? []).map(lineData))
    refs.ema50.setData((indicators[emaKeys[1] as keyof typeof indicators] ?? []).map(lineData))
    refs.sma20.setData((indicators[smaKeys[0] as keyof typeof indicators] ?? []).map(lineData))
    refs.sma50.setData((indicators[smaKeys[1] as keyof typeof indicators] ?? []).map(lineData))
    refs.ema20.applyOptions({ title: emaKeys[0]?.replace("_", " ").toUpperCase() ?? "EMA" })
    refs.ema50.applyOptions({ title: emaKeys[1]?.replace("_", " ").toUpperCase() ?? "EMA" })
    refs.sma20.applyOptions({ title: smaKeys[0]?.replace("_", " ").toUpperCase() ?? "SMA" })
    refs.sma50.applyOptions({ title: smaKeys[1]?.replace("_", " ").toUpperCase() ?? "SMA" })
    refs.bollingerUpper.setData((indicators.bollinger_upper ?? []).map(lineData))
    refs.bollingerMiddle.setData((indicators.bollinger_middle ?? []).map(lineData))
    refs.bollingerLower.setData((indicators.bollinger_lower ?? []).map(lineData))
    refs.rsi.setData(
      (rsiKey ? indicators[rsiKey as keyof typeof indicators] ?? [] : []).map(lineData),
    )
    refs.macd.setData((indicators.macd ?? []).map(lineData))
    refs.macdSignal.setData((indicators.macd_signal ?? []).map(lineData))
    refs.macdHistogram.setData((indicators.macd_histogram ?? []).map(histogramData))
    refs.stochasticK.setData((indicators.stochastic_k ?? []).map(lineData))
    refs.stochasticD.setData((indicators.stochastic_d ?? []).map(lineData))
    if (!candles.length) {
      initializedRef.current = false
      return
    }
    if (!initializedRef.current) {
      chart.timeScale().setVisibleLogicalRange({
        from: Math.max(0, candles.length - 200),
        to: candles.length + 4,
      })
      initializedRef.current = true
      followingRealtimeRef.current = true
    } else if (previousRange) {
      chart.timeScale().setVisibleLogicalRange(
        shiftedLogicalRange(previousRange, historyPrependCount),
      )
    }
  }, [historyVersion, historyPrependCount, candles, indicators])

  useEffect(() => {
    const refs = seriesRef.current
    if (!refs || updateVersion === 0 || !latestCandle || mode === "historical") return

    // Une update remplace ou ajoute uniquement le point courant selon son timestamp.
    refs.candle.update(candleData(latestCandle))
    const updateLine = (series: LineApi, point?: IndicatorPoint) => point && series.update(lineData(point))

    const updateKeys = Object.keys(latestIndicators)
    const emaKeys = updateKeys.filter((key) => /^ema_\d+$/.test(key)).sort(periodOrder)
    const smaKeys = updateKeys.filter((key) => /^sma_\d+$/.test(key)).sort(periodOrder)
    const rsiKey = updateKeys.find((key) => /^rsi_\d+$/.test(key))
    updateLine(refs.ema20, latestIndicators[emaKeys[0] as keyof typeof latestIndicators])
    updateLine(refs.ema50, latestIndicators[emaKeys[1] as keyof typeof latestIndicators])
    updateLine(refs.sma20, latestIndicators[smaKeys[0] as keyof typeof latestIndicators])
    updateLine(refs.sma50, latestIndicators[smaKeys[1] as keyof typeof latestIndicators])
    updateLine(refs.bollingerUpper, latestIndicators.bollinger_upper)
    updateLine(refs.bollingerMiddle, latestIndicators.bollinger_middle)
    updateLine(refs.bollingerLower, latestIndicators.bollinger_lower)
    updateLine(refs.rsi, rsiKey ? latestIndicators[rsiKey as keyof typeof latestIndicators] : undefined)
    updateLine(refs.macd, latestIndicators.macd)
    updateLine(refs.macdSignal, latestIndicators.macd_signal)
    updateLine(refs.stochasticK, latestIndicators.stochastic_k)
    updateLine(refs.stochasticD, latestIndicators.stochastic_d)

    if (latestIndicators.macd_histogram) {
      refs.macdHistogram.update(histogramData(latestIndicators.macd_histogram))
    }
    if (followingRealtimeRef.current && followRealtime) {
      chartRef.current?.timeScale().scrollToRealTime()
    }
  }, [updateVersion, latestCandle, latestIndicators, mode, followRealtime])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || chartCommandVersion === 0 || !chartCommand) return
    if (chartCommand === "fit" || chartCommand === "historical") {
      chart.timeScale().fitContent()
      followingRealtimeRef.current = false
    } else if (chartCommand === "beginning") {
      chart.timeScale().setVisibleLogicalRange({
        from: 0,
        to: Math.min(200, candleCountRef.current),
      })
      followingRealtimeRef.current = false
    } else {
      chart.timeScale().scrollToRealTime()
      followingRealtimeRef.current = chartCommand === "realtime"
    }
  }, [chartCommand, chartCommandVersion])

  useEffect(() => {
    const refs = seriesRef.current
    if (!refs) return

    const visibleMarkers = markers
      .filter((marker) => marker.category === "divergence" ? visibility.divergences : visibility.signals)
      .map(chartMarker)

    refs.markerPlugin.setMarkers(visibleMarkers)
  }, [markers, visibility.signals, visibility.divergences])

  useEffect(() => {
    const refs = seriesRef.current
    if (!refs) return

    refs.ema20.applyOptions({ visible: visibility.ema })
    refs.ema50.applyOptions({ visible: visibility.ema })
    refs.sma20.applyOptions({ visible: visibility.sma })
    refs.sma50.applyOptions({ visible: visibility.sma })
    refs.bollingerUpper.applyOptions({ visible: visibility.bollinger })
    refs.bollingerMiddle.applyOptions({ visible: visibility.bollinger })
    refs.bollingerLower.applyOptions({ visible: visibility.bollinger })
    refs.rsi.applyOptions({ visible: visibility.rsi })
    refs.macd.applyOptions({ visible: visibility.macd })
    refs.macdSignal.applyOptions({ visible: visibility.macd })
    refs.macdHistogram.applyOptions({ visible: visibility.macd })
    refs.stochasticK.applyOptions({ visible: visibility.stochastic })
    refs.stochasticD.applyOptions({ visible: visibility.stochastic })
  }, [visibility])

  return <div ref={containerRef} className="h-[72vh] min-h-155 w-full" />
}
