import type {
  Candle,
  IndicatorHistory,
  IndicatorPoint,
  IndicatorUpdates,
  MarketMarker,
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

export function mergeMarkers(current: MarketMarker[], incoming: MarketMarker[]) {
  if (!incoming.length) return current
  const byKey = new Map(current.map((marker) => [markerKey(marker), marker]))
  incoming.forEach((marker) => byKey.set(markerKey(marker), marker))
  return [...byKey.values()].sort(
    (left, right) => left.time - right.time || left.text.localeCompare(right.text),
  )
}
