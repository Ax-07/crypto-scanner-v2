import { INDICATOR_ORDER } from "@/components/indicator-signals/indicator-signal-config"
import type {
  IndicatorSignalDirection,
  IndicatorSignals,
} from "@/types/indicator-signals"

export interface IndicatorSignalsSummary {
  total: number
  available: number
  unavailable: number
  bullish: number
  bearish: number
  neutral: number
}

export type IndicatorSignalsCollectionState =
  | "legacy_absent"
  | "empty"
  | "available"

export const INDICATOR_DIRECTION_ORDER = [
  "bullish",
  "neutral",
  "bearish",
] as const satisfies readonly IndicatorSignalDirection[]

const DIRECTION_COUNT_LABELS: Record<
  IndicatorSignalDirection,
  { singular: string; plural: string }
> = {
  bullish: { singular: "haussier", plural: "haussiers" },
  neutral: { singular: "neutre", plural: "neutres" },
  bearish: { singular: "baissier", plural: "baissiers" },
}

export function summarizeIndicatorSignals(
  signals: IndicatorSignals,
): IndicatorSignalsSummary {
  const summary: IndicatorSignalsSummary = {
    total: 0,
    available: 0,
    unavailable: 0,
    bullish: 0,
    bearish: 0,
    neutral: 0,
  }

  for (const indicator of INDICATOR_ORDER) {
    const signal = signals[indicator]
    if (signal === undefined) continue

    summary.total += 1
    if (signal.status !== "available") {
      summary.unavailable += 1
      continue
    }

    summary.available += 1
    summary[signal.direction] += 1
  }

  return summary
}

export function getIndicatorSignalsCollectionState(
  signals: IndicatorSignals | undefined,
): IndicatorSignalsCollectionState {
  if (signals === undefined) return "legacy_absent"
  return INDICATOR_ORDER.some((indicator) => signals[indicator] !== undefined)
    ? "available"
    : "empty"
}

export function formatIndicatorSignalsCollectionMessage({
  state,
  context,
}: {
  state: IndicatorSignalsCollectionState
  context: string
}): string {
  if (state === "legacy_absent") {
    return `Les signaux structurés ne sont pas disponibles pour ${context}.`
  }
  if (state === "empty") {
    return `Aucun signal structuré n’a été produit pour ${context}.`
  }
  return ""
}

export function formatIndicatorDirectionCount(
  direction: IndicatorSignalDirection,
  count: number,
): string {
  const labels = DIRECTION_COUNT_LABELS[direction]
  return `${count} ${count === 1 ? labels.singular : labels.plural}`
}
