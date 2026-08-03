/**
 * Adaptateur impératif entre le store marché et Lightweight Charts.
 * Il distingue le remplacement d'un historique des mises à jour incrémentales.
 *
 * Les indicateurs superposés au prix restent attachés au panneau principal.
 * Les indicateurs oscillateurs créent et suppriment réellement leurs panneaux
 * selon leur visibilité afin de ne jamais conserver de panneau vide.
 */
import { useEffect, useRef } from "react";
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
  type LineData,
  type Logical,
  type LogicalRange,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

import { useMarketStore } from "@/stores/market-store";
import type { Candle, IndicatorHistory, IndicatorPoint, IndicatorUpdates, MarketMarker } from "@/types/market";

type CandleApi = ISeriesApi<"Candlestick">;
type LineApi = ISeriesApi<"Line">;
type HistogramApi = ISeriesApi<"Histogram">;

interface SeriesRefs {
  candle: CandleApi;
  ema20: LineApi;
  ema50: LineApi;
  sma20: LineApi;
  sma50: LineApi;
  bollingerUpper: LineApi;
  bollingerMiddle: LineApi;
  bollingerLower: LineApi;
  supertrend: LineApi;
  donchianUpper: LineApi;
  donchianMiddle: LineApi;
  donchianLower: LineApi;
  keltnerUpper: LineApi;
  keltnerMiddle: LineApi;
  keltnerLower: LineApi;

  rsi: LineApi | null;
  macd: LineApi | null;
  macdSignal: LineApi | null;
  macdHistogram: HistogramApi | null;
  stochasticK: LineApi | null;
  stochasticD: LineApi | null;
  adx: LineApi | null;
  adxPlusDi: LineApi | null;
  adxMinusDi: LineApi | null;
  atr: LineApi | null;
  natr: LineApi | null;

  markerPlugin: ISeriesMarkersPluginApi<Time>;
}

type Props = { onLoadMore: () => void | Promise<number> };

const PREFETCH_THRESHOLD = (() => {
  const value = Number(import.meta.env.VITE_MARKET_PREFETCH_THRESHOLD_BARS);
  return Number.isInteger(value) && value >= 0 ? value : 100;
})();

/** Nombre de bougies affichées lors du premier chargement. */
const INITIAL_VISIBLE_BARS = 100;

/**
 * Marge visuelle à droite du temps réel.
 *
 * Elle est exprimée en pixels : le nombre de bougies vides correspondant
 * s'adapte donc automatiquement au niveau de zoom.
 */
const RIGHT_OFFSET_PIXELS = 32;

type MarkerSide = "above" | "below";

interface StackedMarker {
  marker: MarketMarker;
  side: MarkerSide;
  stackIndex: number;
}

/** Distance entre la bougie et le premier marqueur de la pile. */
const MARKER_BASE_RANGE_RATIO = 0.7;
const MARKER_BASE_PRICE_RATIO = 0.003;

/** Distance supplémentaire appliquée à chaque niveau de la pile. */
const MARKER_STACK_RANGE_RATIO = 0.55;
const MARKER_STACK_PRICE_RATIO = 0.0025;

/**
 * Compare deux périodes sous forme de chaînes de caractères.
 * @param left La première période (ex: "ema_20").
 * @param right La deuxième période (ex: "ema_50").
 * @returns Un nombre négatif si left < right, zéro si égal, positif si left > right.
 */
const periodOrder = (left: string, right: string) => Number(left.split("_")[1]) - Number(right.split("_")[1]);

/** Convertit un timestamp en UTCTimestamp pour Lightweight Charts. */
function chartTime(time: number): UTCTimestamp {
  return time as UTCTimestamp;
}

/** Convertit une bougie du store vers le format Lightweight Charts. */
function candleData(candle: Candle): CandlestickData<Time> {
  return { ...candle, time: chartTime(candle.time) };
}

/** Convertit un point d'indicateur vers une donnée de ligne. */
function lineData(point: IndicatorPoint): LineData<Time> {
  return { time: chartTime(point.time), value: point.value };
}

/** Convertit un point d'indicateur vers une donnée d'histogramme. */
function histogramData(point: IndicatorPoint): HistogramData<Time> {
  return {
    time: chartTime(point.time),
    value: point.value,
    color: point.value >= 0 ? "#22c55e" : "#ef4444",
  };
}

/**
 * Place les signaux ordinaires près de la bougie, les marqueurs neutres ensuite,
 * puis les divergences à l'extérieur de la pile.
 */
function markerStackPriority(marker: MarketMarker): number {
  if (marker.category === "divergence") {
    return 2;
  }

  if (marker.position === "inBar") {
    return 1;
  }

  return 0;
}

/** Produit un ordre déterministe dans chaque pile de marqueurs. */
function compareMarkersForStack(left: MarketMarker, right: MarketMarker): number {
  return (
    markerStackPriority(left) - markerStackPriority(right) ||
    (left.indicator ?? "").localeCompare(right.indicator ?? "") ||
    left.text.localeCompare(right.text)
  );
}

/**
 * Regroupe les marqueurs par bougie et construit deux piles indépendantes :
 * une au-dessus et une au-dessous de la bougie.
 *
 * Les marqueurs `inBar` sont déplacés vers la pile la moins chargée afin de ne
 * plus se superposer à la bougie ni entre eux.
 */
function stackMarkers(markers: MarketMarker[]): StackedMarker[] {
  const markersByTime = new Map<number, MarketMarker[]>();

  for (const marker of markers) {
    const current = markersByTime.get(marker.time);

    if (current) {
      current.push(marker);
    } else {
      markersByTime.set(marker.time, [marker]);
    }
  }

  const result: StackedMarker[] = [];
  const groups = [...markersByTime.entries()].sort(([leftTime], [rightTime]) => leftTime - rightTime);

  for (const [, group] of groups) {
    const above = group.filter((marker) => marker.position === "aboveBar").sort(compareMarkersForStack);

    const below = group.filter((marker) => marker.position === "belowBar").sort(compareMarkersForStack);

    const inside = group.filter((marker) => marker.position === "inBar").sort(compareMarkersForStack);

    for (const marker of inside) {
      if (above.length <= below.length) {
        above.push(marker);
      } else {
        below.push(marker);
      }
    }

    above.sort(compareMarkersForStack);
    below.sort(compareMarkersForStack);

    above.forEach((marker, stackIndex) => {
      result.push({ marker, side: "above", stackIndex });
    });

    below.forEach((marker, stackIndex) => {
      result.push({ marker, side: "below", stackIndex });
    });
  }

  return result;
}

/** Convertit un marqueur empilé vers le format Lightweight Charts. */
function chartMarker(stackedMarker: StackedMarker, candleByTime: ReadonlyMap<number, Candle>): SeriesMarker<Time> {
  const { marker, side, stackIndex } = stackedMarker;
  const candle = candleByTime.get(marker.time);

  if (!candle) {
    return {
      time: chartTime(marker.time),
      position: marker.position,
      shape: marker.shape,
      color: marker.color,
      text: marker.text,
      size: 1,
    };
  }

  const absoluteClose = Math.max(Math.abs(candle.close), Number.EPSILON);
  const candleRange = Math.max(candle.high - candle.low, absoluteClose * 0.001);

  const baseOffset = Math.max(candleRange * MARKER_BASE_RANGE_RATIO, absoluteClose * MARKER_BASE_PRICE_RATIO);

  const stackStep = Math.max(candleRange * MARKER_STACK_RANGE_RATIO, absoluteClose * MARKER_STACK_PRICE_RATIO);

  const priceOffset = baseOffset + stackIndex * stackStep;

  if (side === "below") {
    return {
      time: chartTime(marker.time),
      position: "atPriceBottom",
      price: candle.low - priceOffset,
      shape: marker.shape,
      color: marker.color,
      text: marker.text,
      size: 1,
    };
  }

  return {
    time: chartTime(marker.time),
    position: "atPriceTop",
    price: candle.high + priceOffset,
    shape: marker.shape,
    color: marker.color,
    text: marker.text,
    size: 1,
  };
}

/** Détermine si un marqueur est visible en fonction de la configuration de visibilité actuelle. */
function isMarkerVisible(
  marker: MarketMarker,
  visibility: ReturnType<typeof useMarketStore.getState>["visibility"],
): boolean {
  if (marker.category === "divergence") {
    if (!visibility.divergences) {
      return false;
    }

    switch (marker.source) {
      case "RSI":
        return visibility.rsi;

      case "MACD":
        return visibility.macd;

      default:
        return false;
    }
  }

  if (!visibility.signals) {
    return false;
  }

  switch (marker.indicator) {
    case "ema":
      return visibility.ema;

    case "macd":
      return visibility.macd;

    case "supertrend":
      return visibility.supertrend;

    case "rsi":
      return visibility.rsi;

    case "stochastic":
      return visibility.stochastic;

    case "bollinger":
      return visibility.bollinger;

    case "adx":
      return visibility.adx;

    case "atr":
      return visibility.volatility;

    case "donchian":
      return visibility.donchian;

    case "keltner":
      return visibility.keltner;

    default:
      return false;
  }
}

/** Retourne la clé RSI active dans un dictionnaire d'indicateurs. */
function findRsiKey(indicators: IndicatorHistory | IndicatorUpdates) {
  return Object.keys(indicators).find((key) => /^rsi_\d+$/.test(key));
}

/** Charge un historique de ligne puis applique éventuellement le point temps réel. */
function setLineData(series: LineApi, history: IndicatorPoint[] | undefined, latest?: IndicatorPoint) {
  series.setData((history ?? []).map(lineData));
  if (latest) series.update(lineData(latest));
}

/** Charge un historique d'histogramme puis applique éventuellement le point temps réel. */
function setHistogramData(series: HistogramApi, history: IndicatorPoint[] | undefined, latest?: IndicatorPoint) {
  series.setData((history ?? []).map(histogramData));
  if (latest) series.update(histogramData(latest));
}

/**
 * Décale une plage logique après l'ajout ou le retrait de bougies au début.
 */
export function shiftedLogicalRange(range: LogicalRange, prependedCount: number): LogicalRange {
  return {
    from: (Number(range.from) + prependedCount) as Logical,
    to: (Number(range.to) + prependedCount) as Logical,
  };
}

/** Détermine si un nouveau bloc d'historique doit être préchargé. */
export function shouldPrefetchHistory(
  range: LogicalRange | null,
  threshold: number,
  initialized: boolean,
  hasMoreBefore: boolean,
  loading: boolean,
) {
  return Boolean(range && Number(range.from) <= threshold && initialized && hasMoreBefore && !loading);
}

/**
 * Synchronise un graphique multi-panneaux avec l'historique et les mises à jour.
 * L'instance impérative est créée une fois puis détruite au démontage.
 */
export function TradingChart({ onLoadMore }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<SeriesRefs | null>(null);
  const onLoadMoreRef = useRef(onLoadMore);
  const candleCountRef = useRef(0);
  const followingRealtimeRef = useRef(true);
  const initializedRef = useRef(false);

  const candles = useMarketStore((state) => state.candles);
  const indicators = useMarketStore((state) => state.indicators);
  const markers = useMarketStore((state) => state.markers);
  const latestCandle = useMarketStore((state) => state.latestCandle);
  const latestIndicators = useMarketStore((state) => state.latestIndicators);
  const historyVersion = useMarketStore((state) => state.historyVersion);
  const historyPrependCount = useMarketStore((state) => state.historyPrependCount);
  const updateVersion = useMarketStore((state) => state.updateVersion);
  const visibility = useMarketStore((state) => state.visibility);
  const chartCommand = useMarketStore((state) => state.chartCommand);
  const chartCommandVersion = useMarketStore((state) => state.chartCommandVersion);
  const mode = useMarketStore((state) => state.mode);
  const followRealtime = useMarketStore((state) => state.followRealtime);

  useEffect(() => {
    onLoadMoreRef.current = onLoadMore;
  }, [onLoadMore]);

  useEffect(() => {
    candleCountRef.current = candles.length;
  }, [candles.length]);

  /** Création du graphique et des séries permanentes du panneau prix. */
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const initialWidth = Math.max(1, Math.floor(container.clientWidth));
    const initialHeight = Math.max(1, Math.floor(container.clientHeight));

    const chart = createChart(container, {
      autoSize: false,
      width: initialWidth,
      height: initialHeight,
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
      leftPriceScale: { visible: false, borderColor: "#374151" },
      timeScale: {
        borderColor: "#374151",
        timeVisible: true,
        secondsVisible: false,
        rightOffsetPixels: RIGHT_OFFSET_PIXELS,
        barSpacing: 7,
      },
      crosshair: { mode: CrosshairMode.Normal },
      localization: { locale: "fr-FR" },
    });

    const candle = chart.addSeries(
      CandlestickSeries,
      {
        upColor: "#22c55e",
        downColor: "#ef4444",
        borderVisible: false,
        wickUpColor: "#22c55e",
        wickDownColor: "#ef4444",
      },
      0,
    );

    const ema20 = chart.addSeries(
      LineSeries,
      {
        title: "EMA 20",
        color: "#38bdf8",
        lineWidth: 2,
        priceLineVisible: false,
      },
      0,
    );
    const ema50 = chart.addSeries(
      LineSeries,
      {
        title: "EMA 50",
        color: "#f59e0b",
        lineWidth: 2,
        priceLineVisible: false,
      },
      0,
    );
    const sma20 = chart.addSeries(
      LineSeries,
      {
        title: "SMA 20",
        color: "#a78bfa",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
      },
      0,
    );
    const sma50 = chart.addSeries(
      LineSeries,
      {
        title: "SMA 50",
        color: "#fb7185",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
      },
      0,
    );

    const bollingerUpper = chart.addSeries(
      LineSeries,
      {
        title: "BB supérieure",
        color: "#64748b",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      },
      0,
    );
    const bollingerMiddle = chart.addSeries(
      LineSeries,
      {
        title: "BB moyenne",
        color: "#94a3b8",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      },
      0,
    );
    const bollingerLower = chart.addSeries(
      LineSeries,
      {
        title: "BB inférieure",
        color: "#64748b",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      },
      0,
    );

    const supertrend = chart.addSeries(
      LineSeries,
      {
        title: "Supertrend",
        color: "#facc15",
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
      },
      0,
    );

    const donchianUpper = chart.addSeries(
      LineSeries,
      {
        title: "Donchian supérieure",
        color: "#38bdf8",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      },
      0,
    );
    const donchianMiddle = chart.addSeries(
      LineSeries,
      {
        title: "Donchian médian",
        color: "#94a3b8",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
      },
      0,
    );
    const donchianLower = chart.addSeries(
      LineSeries,
      {
        title: "Donchian inférieure",
        color: "#64748b",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      },
      0,
    );

    const keltnerUpper = chart.addSeries(
      LineSeries,
      {
        title: "Keltner supérieur",
        color: "#a78bfa",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      },
      0,
    );
    const keltnerMiddle = chart.addSeries(
      LineSeries,
      {
        title: "Keltner médian",
        color: "#c4b5fd",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
      },
      0,
    );
    const keltnerLower = chart.addSeries(
      LineSeries,
      {
        title: "Keltner inférieur",
        color: "#a78bfa",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      },
      0,
    );

    const markerPlugin = createSeriesMarkers(candle, []);

    chartRef.current = chart;
    seriesRef.current = {
      candle,
      ema20,
      ema50,
      sma20,
      sma50,
      bollingerUpper,
      bollingerMiddle,
      bollingerLower,
      supertrend,
      donchianUpper,
      donchianMiddle,
      donchianLower,
      keltnerUpper,
      keltnerMiddle,
      keltnerLower,
      rsi: null,
      macd: null,
      macdSignal: null,
      macdHistogram: null,
      stochasticK: null,
      stochasticD: null,
      adx: null,
      adxPlusDi: null,
      adxMinusDi: null,
      atr: null,
      natr: null,
      markerPlugin,
    };

    chart.panes()[0]?.setStretchFactor(5);

    const handleLogicalRange = (range: LogicalRange | null) => {
      if (!range) return;

      followingRealtimeRef.current = range.to >= candleCountRef.current - 3;
      const state = useMarketStore.getState();

      if (state.mode === "live" && state.followRealtime && !followingRealtimeRef.current) {
        state.setFollowRealtime(false);
      }

      if (
        shouldPrefetchHistory(
          range,
          PREFETCH_THRESHOLD,
          state.historyInitialized,
          state.hasMoreBefore,
          state.historyLoading,
        )
      ) {
        void onLoadMoreRef.current();
      }
    };

    chart.timeScale().subscribeVisibleLogicalRangeChange(handleLogicalRange);

    // Lightweight Charts 5.2 peut entrer dans un état intermédiaire invalide
    // lorsque son ResizeObserver interne redimensionne le graphique pendant
    // la suppression/recréation de panneaux. Le redimensionnement est donc
    // piloté ici, après stabilisation du DOM dans requestAnimationFrame.
    let resizeFrame: number | null = null;
    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;

      const width = Math.floor(entry.contentRect.width);
      const height = Math.floor(entry.contentRect.height);
      if (width <= 0 || height <= 0) return;

      if (resizeFrame !== null) {
        window.cancelAnimationFrame(resizeFrame);
      }

      resizeFrame = window.requestAnimationFrame(() => {
        resizeFrame = null;
        if (chartRef.current !== chart) return;
        chart.resize(width, height);
      });
    });

    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      if (resizeFrame !== null) {
        window.cancelAnimationFrame(resizeFrame);
      }
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(handleLogicalRange);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  /**
   * Reconstruit les panneaux secondaires dans un ordre stable.
   * Supprimer un panneau supprime également toutes ses séries.
   */
  useEffect(() => {
    const chart = chartRef.current;
    const refs = seriesRef.current;
    if (!chart || !refs) return;

    // Suppression en partant du dernier panneau afin de conserver le panneau prix.
    while (chart.panes().length > 1) {
      chart.removePane(chart.panes().length - 1);
    }

    refs.rsi = null;
    refs.macd = null;
    refs.macdSignal = null;
    refs.macdHistogram = null;
    refs.stochasticK = null;
    refs.stochasticD = null;
    refs.adx = null;
    refs.adxPlusDi = null;
    refs.adxMinusDi = null;
    refs.atr = null;
    refs.natr = null;

    const state = useMarketStore.getState();
    const currentIndicators = state.indicators;
    const currentLatest: IndicatorUpdates = state.mode === "historical" ? {} : state.latestIndicators;

    const createPane = (stretchFactor: number) => {
      const pane = chart.addPane(true);
      pane.setStretchFactor(stretchFactor);
      return pane.paneIndex();
    };

    // Ordre fixe : prix, RSI, MACD, Stochastique, ADX/DMI, ATR/NATR.
    if (visibility.rsi) {
      const paneIndex = createPane(1.35);
      const rsi = chart.addSeries(
        LineSeries,
        {
          title: "RSI 14",
          color: "#c084fc",
          lineWidth: 2,
          priceLineVisible: false,
          autoscaleInfoProvider: () => ({
            priceRange: { minValue: 0, maxValue: 100 },
          }),
        },
        paneIndex,
      );

      rsi.createPriceLine({
        price: 70,
        color: "#ef4444",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "70",
      });
      rsi.createPriceLine({
        price: 30,
        color: "#22c55e",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "30",
      });

      const rsiKey = findRsiKey(currentIndicators);
      const latestRsiKey = findRsiKey(currentLatest);
      setLineData(
        rsi,
        rsiKey ? currentIndicators[rsiKey as keyof typeof currentIndicators] : undefined,
        latestRsiKey ? currentLatest[latestRsiKey as keyof typeof currentLatest] : undefined,
      );
      refs.rsi = rsi;
    }

    if (visibility.macd) {
      const paneIndex = createPane(1.6);
      const macdHistogram = chart.addSeries(
        HistogramSeries,
        {
          title: "Histogramme",
          priceLineVisible: false,
          lastValueVisible: false,
        },
        paneIndex,
      );
      const macd = chart.addSeries(
        LineSeries,
        {
          title: "MACD",
          color: "#38bdf8",
          lineWidth: 2,
          priceLineVisible: false,
        },
        paneIndex,
      );
      const macdSignal = chart.addSeries(
        LineSeries,
        {
          title: "Signal",
          color: "#f59e0b",
          lineWidth: 2,
          priceLineVisible: false,
        },
        paneIndex,
      );

      setHistogramData(macdHistogram, currentIndicators.macd_histogram, currentLatest.macd_histogram);
      setLineData(macd, currentIndicators.macd, currentLatest.macd);
      setLineData(macdSignal, currentIndicators.macd_signal, currentLatest.macd_signal);

      refs.macdHistogram = macdHistogram;
      refs.macd = macd;
      refs.macdSignal = macdSignal;
    }

    if (visibility.stochastic) {
      const paneIndex = createPane(1.35);
      const stochasticK = chart.addSeries(
        LineSeries,
        {
          title: "%K",
          color: "#38bdf8",
          lineWidth: 2,
          priceLineVisible: false,
          autoscaleInfoProvider: () => ({
            priceRange: { minValue: 0, maxValue: 100 },
          }),
        },
        paneIndex,
      );
      const stochasticD = chart.addSeries(
        LineSeries,
        {
          title: "%D",
          color: "#f59e0b",
          lineWidth: 2,
          priceLineVisible: false,
        },
        paneIndex,
      );

      stochasticK.createPriceLine({
        price: 80,
        color: "#ef4444",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "80",
      });
      stochasticK.createPriceLine({
        price: 20,
        color: "#22c55e",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "20",
      });

      setLineData(stochasticK, currentIndicators.stochastic_k, currentLatest.stochastic_k);
      setLineData(stochasticD, currentIndicators.stochastic_d, currentLatest.stochastic_d);

      refs.stochasticK = stochasticK;
      refs.stochasticD = stochasticD;
    }

    if (visibility.adx) {
      const paneIndex = createPane(1.5);
      const adx = chart.addSeries(
        LineSeries,
        {
          title: "ADX",
          color: "#38bdf8",
          lineWidth: 2,
          priceLineVisible: false,
          autoscaleInfoProvider: () => ({
            priceRange: { minValue: 0, maxValue: 100 },
          }),
        },
        paneIndex,
      );
      const adxPlusDi = chart.addSeries(
        LineSeries,
        {
          title: "+DI",
          color: "#22c55e",
          lineWidth: 1,
          priceLineVisible: false,
        },
        paneIndex,
      );
      const adxMinusDi = chart.addSeries(
        LineSeries,
        {
          title: "-DI",
          color: "#ef4444",
          lineWidth: 1,
          priceLineVisible: false,
        },
        paneIndex,
      );

      adx.createPriceLine({
        price: 20,
        color: "#64748b",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "20",
      });
      adx.createPriceLine({
        price: 25,
        color: "#f59e0b",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "25",
      });

      setLineData(adx, currentIndicators.adx, currentLatest.adx);
      setLineData(adxPlusDi, currentIndicators.adx_plus_di, currentLatest.adx_plus_di);
      setLineData(adxMinusDi, currentIndicators.adx_minus_di, currentLatest.adx_minus_di);

      refs.adx = adx;
      refs.adxPlusDi = adxPlusDi;
      refs.adxMinusDi = adxMinusDi;
    }

    if (visibility.volatility) {
      const paneIndex = createPane(1.35);

      // ATR et NATR partagent le même panneau et le même bouton d'affichage.
      // ATR conserve l'échelle droite visible. NATR utilise une échelle interne
      // indépendante afin de ne jamais réserver de marge sur la gauche.
      const atr = chart.addSeries(
        LineSeries,
        {
          title: "ATR",
          color: "#f59e0b",
          lineWidth: 2,
          priceLineVisible: false,
          priceScaleId: "right",
          priceFormat: {
            type: "price",
            precision: 2,
            minMove: 0.01,
          },
        },
        paneIndex,
      );
      const natr = chart.addSeries(
        LineSeries,
        {
          title: "NATR %",
          color: "#c084fc",
          lineWidth: 2,
          priceLineVisible: false,
          priceScaleId: "natr-overlay",
          priceFormat: {
            type: "price",
            precision: 2,
            minMove: 0.01,
          },
        },
        paneIndex,
      );

      atr.priceScale().applyOptions({
        visible: true,
        borderColor: "#374151",
      });
      natr.priceScale().applyOptions({
        visible: false,
      });

      setLineData(atr, currentIndicators.atr, currentLatest.atr);
      setLineData(natr, currentIndicators.natr, currentLatest.natr);

      refs.atr = atr;
      refs.natr = natr;
    }

    chart.panes()[0]?.setStretchFactor(5);
  }, [visibility.rsi, visibility.macd, visibility.stochastic, visibility.adx, visibility.volatility]);

  /** Remplace toutes les séries lors d'un changement d'historique. */
  useEffect(() => {
    const refs = seriesRef.current;
    const chart = chartRef.current;
    if (!refs || !chart || historyVersion === 0) return;

    const previousRange = chart.timeScale().getVisibleLogicalRange();
    refs.candle.setData(candles.map(candleData));

    const keys = Object.keys(indicators);
    const emaKeys = keys.filter((key) => /^ema_\d+$/.test(key)).sort(periodOrder);
    const smaKeys = keys.filter((key) => /^sma_\d+$/.test(key)).sort(periodOrder);
    const rsiKey = keys.find((key) => /^rsi_\d+$/.test(key));

    refs.ema20.setData((indicators[emaKeys[0] as keyof typeof indicators] ?? []).map(lineData));
    refs.ema50.setData((indicators[emaKeys[1] as keyof typeof indicators] ?? []).map(lineData));
    refs.sma20.setData((indicators[smaKeys[0] as keyof typeof indicators] ?? []).map(lineData));
    refs.sma50.setData((indicators[smaKeys[1] as keyof typeof indicators] ?? []).map(lineData));

    refs.ema20.applyOptions({
      title: emaKeys[0]?.replace("_", " ").toUpperCase() ?? "EMA",
    });
    refs.ema50.applyOptions({
      title: emaKeys[1]?.replace("_", " ").toUpperCase() ?? "EMA",
    });
    refs.sma20.applyOptions({
      title: smaKeys[0]?.replace("_", " ").toUpperCase() ?? "SMA",
    });
    refs.sma50.applyOptions({
      title: smaKeys[1]?.replace("_", " ").toUpperCase() ?? "SMA",
    });

    refs.bollingerUpper.setData((indicators.bollinger_upper ?? []).map(lineData));
    refs.bollingerMiddle.setData((indicators.bollinger_middle ?? []).map(lineData));
    refs.bollingerLower.setData((indicators.bollinger_lower ?? []).map(lineData));
    refs.supertrend.setData((indicators.supertrend ?? []).map(lineData));
    refs.donchianUpper.setData((indicators.donchian_upper_channel ?? []).map(lineData));
    refs.donchianMiddle.setData((indicators.donchian_middle_channel ?? []).map(lineData));
    refs.donchianLower.setData((indicators.donchian_lower_channel ?? []).map(lineData));
    refs.keltnerUpper.setData((indicators.keltner_upper_channel ?? []).map(lineData));
    refs.keltnerMiddle.setData((indicators.keltner_middle_line ?? []).map(lineData));
    refs.keltnerLower.setData((indicators.keltner_lower_channel ?? []).map(lineData));

    if (refs.rsi) {
      refs.rsi.setData((rsiKey ? (indicators[rsiKey as keyof typeof indicators] ?? []) : []).map(lineData));
    }
    if (refs.macd) {
      refs.macd.setData((indicators.macd ?? []).map(lineData));
    }
    if (refs.macdSignal) {
      refs.macdSignal.setData((indicators.macd_signal ?? []).map(lineData));
    }
    if (refs.macdHistogram) {
      refs.macdHistogram.setData((indicators.macd_histogram ?? []).map(histogramData));
    }
    if (refs.stochasticK) {
      refs.stochasticK.setData((indicators.stochastic_k ?? []).map(lineData));
    }
    if (refs.stochasticD) {
      refs.stochasticD.setData((indicators.stochastic_d ?? []).map(lineData));
    }
    if (refs.adx) {
      refs.adx.setData((indicators.adx ?? []).map(lineData));
    }
    if (refs.adxPlusDi) {
      refs.adxPlusDi.setData((indicators.adx_plus_di ?? []).map(lineData));
    }
    if (refs.adxMinusDi) {
      refs.adxMinusDi.setData((indicators.adx_minus_di ?? []).map(lineData));
    }
    if (refs.atr) {
      refs.atr.setData((indicators.atr ?? []).map(lineData));
    }
    if (refs.natr) {
      refs.natr.setData((indicators.natr ?? []).map(lineData));
    }

    if (!candles.length) {
      initializedRef.current = false;
      return;
    }

    if (!initializedRef.current) {
      chart.timeScale().setVisibleLogicalRange({
        from: Math.max(0, candles.length - INITIAL_VISIBLE_BARS),
        to: candles.length - 1,
      });

      /*
       * Replace la dernière bougie sur la position temps réel.
       * rightOffsetPixels applique ensuite la marge visuelle configurée,
       * sans modifier le niveau de zoom choisi ci-dessus.
       */
      chart.timeScale().scrollToRealTime();

      initializedRef.current = true;
      followingRealtimeRef.current = true;
    } else if (previousRange) {
      chart.timeScale().setVisibleLogicalRange(shiftedLogicalRange(previousRange, historyPrependCount));
    }
  }, [historyVersion, historyPrependCount, candles, indicators]);

  /** Applique uniquement le dernier point reçu en temps réel. */
  useEffect(() => {
    const refs = seriesRef.current;
    if (!refs || updateVersion === 0 || !latestCandle || mode === "historical") {
      return;
    }

    refs.candle.update(candleData(latestCandle));
    const updateLine = (series: LineApi | null, point?: IndicatorPoint) => {
      if (series && point) series.update(lineData(point));
    };

    const updateKeys = Object.keys(latestIndicators);
    const emaKeys = updateKeys.filter((key) => /^ema_\d+$/.test(key)).sort(periodOrder);
    const smaKeys = updateKeys.filter((key) => /^sma_\d+$/.test(key)).sort(periodOrder);
    const rsiKey = updateKeys.find((key) => /^rsi_\d+$/.test(key));

    updateLine(refs.ema20, latestIndicators[emaKeys[0] as keyof typeof latestIndicators]);
    updateLine(refs.ema50, latestIndicators[emaKeys[1] as keyof typeof latestIndicators]);
    updateLine(refs.sma20, latestIndicators[smaKeys[0] as keyof typeof latestIndicators]);
    updateLine(refs.sma50, latestIndicators[smaKeys[1] as keyof typeof latestIndicators]);
    updateLine(refs.bollingerUpper, latestIndicators.bollinger_upper);
    updateLine(refs.bollingerMiddle, latestIndicators.bollinger_middle);
    updateLine(refs.bollingerLower, latestIndicators.bollinger_lower);
    updateLine(refs.supertrend, latestIndicators.supertrend);
    updateLine(refs.donchianUpper, latestIndicators.donchian_upper_channel);
    updateLine(refs.donchianMiddle, latestIndicators.donchian_middle_channel);
    updateLine(refs.donchianLower, latestIndicators.donchian_lower_channel);
    updateLine(refs.keltnerUpper, latestIndicators.keltner_upper_channel);
    updateLine(refs.keltnerMiddle, latestIndicators.keltner_middle_line);
    updateLine(refs.keltnerLower, latestIndicators.keltner_lower_channel);

    updateLine(refs.rsi, rsiKey ? latestIndicators[rsiKey as keyof typeof latestIndicators] : undefined);
    updateLine(refs.macd, latestIndicators.macd);
    updateLine(refs.macdSignal, latestIndicators.macd_signal);
    updateLine(refs.stochasticK, latestIndicators.stochastic_k);
    updateLine(refs.stochasticD, latestIndicators.stochastic_d);
    updateLine(refs.adx, latestIndicators.adx);
    updateLine(refs.adxPlusDi, latestIndicators.adx_plus_di);
    updateLine(refs.adxMinusDi, latestIndicators.adx_minus_di);
    updateLine(refs.atr, latestIndicators.atr);
    updateLine(refs.natr, latestIndicators.natr);

    if (refs.macdHistogram && latestIndicators.macd_histogram) {
      refs.macdHistogram.update(histogramData(latestIndicators.macd_histogram));
    }

    if (followingRealtimeRef.current && followRealtime) {
      chartRef.current?.timeScale().scrollToRealTime();
    }
  }, [updateVersion, latestCandle, latestIndicators, mode, followRealtime]);

  /** Exécute les commandes de navigation explicites du store. */
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || chartCommandVersion === 0 || !chartCommand) return;

    if (chartCommand === "fit" || chartCommand === "historical") {
      chart.timeScale().fitContent();
      followingRealtimeRef.current = false;
    } else if (chartCommand === "beginning") {
      chart.timeScale().setVisibleLogicalRange({
        from: 0,
        to: Math.min(200, candleCountRef.current),
      });
      followingRealtimeRef.current = false;
    } else {
      chart.timeScale().scrollToRealTime();
      followingRealtimeRef.current = chartCommand === "realtime";
    }
  }, [chartCommand, chartCommandVersion]);

  /** Filtre et empile les marqueurs selon les réglages d'affichage. */
  useEffect(() => {
    const refs = seriesRef.current;
    if (!refs) return;

    const candleByTime = new Map(candles.map((candle) => [candle.time, candle]));

    const filteredMarkers = markers.filter((marker) => isMarkerVisible(marker, visibility));

    const visibleMarkers = stackMarkers(filteredMarkers).map((marker) => chartMarker(marker, candleByTime));

    refs.markerPlugin.setMarkers(visibleMarkers);
  }, [markers, visibility, candles]);

  /** Masque ou affiche les indicateurs superposés au panneau prix. */
  useEffect(() => {
    const refs = seriesRef.current;
    if (!refs) return;

    refs.ema20.applyOptions({ visible: visibility.ema });
    refs.ema50.applyOptions({ visible: visibility.ema });
    refs.sma20.applyOptions({ visible: visibility.sma });
    refs.sma50.applyOptions({ visible: visibility.sma });
    refs.bollingerUpper.applyOptions({ visible: visibility.bollinger });
    refs.bollingerMiddle.applyOptions({ visible: visibility.bollinger });
    refs.bollingerLower.applyOptions({ visible: visibility.bollinger });
    refs.supertrend.applyOptions({ visible: visibility.supertrend });
    refs.donchianUpper.applyOptions({ visible: visibility.donchian });
    refs.donchianMiddle.applyOptions({ visible: visibility.donchian });
    refs.donchianLower.applyOptions({ visible: visibility.donchian });
    refs.keltnerUpper.applyOptions({ visible: visibility.keltner });
    refs.keltnerMiddle.applyOptions({ visible: visibility.keltner });
    refs.keltnerLower.applyOptions({ visible: visibility.keltner });
  }, [
    visibility.ema,
    visibility.sma,
    visibility.bollinger,
    visibility.supertrend,
    visibility.donchian,
    visibility.keltner,
  ]);

  return <div ref={containerRef} className="h-[72vh] min-h-155 w-full" />;
}
