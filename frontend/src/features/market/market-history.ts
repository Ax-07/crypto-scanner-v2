import type {
  Candle,
  IndicatorHistory,
  IndicatorPoint,
  IndicatorUpdates,
  MarketMarker,
  MarkerIndicator,
} from "@/types/market"

function mergeByTime<T extends { time: number }>(current: T[], incoming: T[]): T[] {
  if (!incoming.length) return current
  const byTime = new Map(current.map((item) => [item.time, item]))
  incoming.forEach((item) => byTime.set(item.time, item))
  return [...byTime.values()].sort((left, right) => left.time - right.time)
}

export function mergeCandles(current: Candle[], incoming: Candle[]) {
  const firstTime = current[0]?.time ?? Number.POSITIVE_INFINITY
  const known = new Set(current.map((candle) => candle.time))
  const prependedCount = incoming.reduce(
    (count, candle) => count + Number(candle.time < firstTime && !known.has(candle.time)),
    0,
  )
  return { candles: mergeByTime(current, incoming), prependedCount }
}

export function upsertRealtimeCandle(current: Candle[], incoming: Candle): Candle[] {
  const length = current.length
  if (!length) return [incoming]
  const last = current[length - 1]
  if (incoming.time > last.time) return [...current, incoming]
  if (incoming.time === last.time) {
    const next = current.slice()
    next[length - 1] = incoming
    return next
  }
  let low = 0
  let high = length - 1
  while (low <= high) {
    const middle = (low + high) >>> 1
    const time = current[middle].time
    if (time === incoming.time) {
      const next = current.slice()
      next[middle] = incoming
      return next
    }
    if (time < incoming.time) low = middle + 1
    else high = middle - 1
  }
  const next = current.slice()
  next.splice(low, 0, incoming)
  return next
}

export function mergeIndicatorHistory(
  current: IndicatorHistory,
  incoming: IndicatorHistory,
): IndicatorHistory {
  const result: IndicatorHistory = { ...current }
  for (const key of Object.keys(incoming) as Array<keyof IndicatorHistory>) {
    result[key] = mergeByTime(current[key] ?? [], incoming[key] ?? [])
  }
  return result
}

export function applyIndicatorUpdates(
  current: IndicatorHistory,
  updates: IndicatorUpdates,
): IndicatorHistory {
  const result: IndicatorHistory = { ...current }
  for (const key of Object.keys(updates) as Array<keyof IndicatorUpdates>) {
    const point: IndicatorPoint | undefined = updates[key]
    if (point) result[key] = upsertPoint(current[key] ?? [], point)
  }
  return result
}

function upsertPoint(current: IndicatorPoint[], point: IndicatorPoint) {
  const last = current[current.length - 1]
  if (!last || point.time > last.time) return [...current, point]
  if (point.time === last.time) return [...current.slice(0, -1), point]
  return mergeByTime(current, [point])
}

function markerKey(marker: MarketMarker) {
  return [
    marker.time,
    marker.text,
    marker.category ?? "",
    marker.source ?? "",
    marker.divergence_type ?? "",
  ].join("|")
}

function inferMarkerIndicator(
  marker: MarketMarker,
): MarkerIndicator | undefined {
  if (marker.indicator) {
    return marker.indicator
  }

  const text = marker.text.trim().toLowerCase()

  if (text.includes("supertrend")) return "supertrend"
  if (text.includes("macd")) return "macd"
  if (text.includes("ema")) return "ema"
  if (text.includes("rsi")) return "rsi"
  if (text.includes("stoch")) return "stochastic"
  if (text.includes("bollinger")) return "bollinger"
  if (text.includes("donchian")) return "donchian"
  if (text.includes("keltner")) return "keltner"

  if (
    text.includes("adx") ||
    text.includes("+di") ||
    text.includes("-di")
  ) {
    return "adx"
  }

if (
  text.includes("natr")
  || /\batr\b/.test(text)
  || text.includes("volatilité")
  || text.includes("volatilite")
  || text.includes("volatility")
) {
  return "atr"
}

  return undefined
}

export function normalizeMarker(marker: MarketMarker): MarketMarker {
  const indicator = inferMarkerIndicator(marker)

  if (!indicator) {
    return marker
  }

  return {
    ...marker,
    indicator,
  }
}

export function mergeMarkers(
  current: MarketMarker[],
  incoming: MarketMarker[],
): MarketMarker[] {
  if (!incoming.length) {
    return current.map(normalizeMarker)
  }

  const byKey = new Map<string, MarketMarker>()

  for (const marker of current) {
    const normalized = normalizeMarker(marker)
    byKey.set(markerKey(normalized), normalized)
  }

  for (const marker of incoming) {
    const normalized = normalizeMarker(marker)
    byKey.set(markerKey(normalized), normalized)
  }

  return [...byKey.values()].sort(
    (left, right) =>
      left.time - right.time ||
      left.text.localeCompare(right.text),
  )
}
