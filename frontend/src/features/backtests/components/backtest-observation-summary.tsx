import {
  IndicatorDirectionBadge,
  INDICATOR_ORDER,
} from "@/components/indicator-signals"
import { BacktestDecisionBadge } from "@/features/backtests/components/backtest-decision-badge"
import type {
  IndicatorSignalDirection,
  IndicatorSignals,
} from "@/types/indicator-signals"
import type { SignalObservation } from "@/types/backtest"

const DIRECTION_ORDER = ["bullish", "neutral", "bearish"] as const

const directionLabels: Record<
  IndicatorSignalDirection,
  { singular: string; plural: string }
> = {
  bullish: { singular: "haussier", plural: "haussiers" },
  neutral: { singular: "neutre", plural: "neutres" },
  bearish: { singular: "baissier", plural: "baissiers" },
}

export interface BacktestObservationSummaryProps {
  observation: SignalObservation
}

export function summarizeObservationSignals(signals: IndicatorSignals | undefined) {
  if (signals === undefined) return null
  const present = INDICATOR_ORDER.flatMap((indicator) => {
    const signal = signals[indicator]
    return signal ? [signal] : []
  })
  const available = present.filter((signal) => signal.status === "available")
  return {
    present: present.length,
    available: available.length,
    unavailable: present.length - available.length,
    directions: DIRECTION_ORDER.map((direction) => ({
      direction,
      count: available.filter((signal) => signal.direction === direction).length,
    })).filter(({ count }) => count > 0),
  }
}

export function BacktestObservationSummary({
  observation,
}: BacktestObservationSummaryProps) {
  const summary = summarizeObservationSignals(observation.indicator_signals)

  return (
    <div className="min-w-48 space-y-2 whitespace-normal">
      <BacktestDecisionBadge accepted={observation.accepted} />
      <p className="text-xs font-medium">
        {observation.confluence_score == null
          ? "Confluence indisponible"
          : `Confluence ${observation.confluence_score.toLocaleString("fr-FR", {
              maximumFractionDigits: 2,
            })}/100${observation.confluence_grade
              ? ` · Grade ${observation.confluence_grade}`
              : ""}`}
      </p>
      {summary === null ? (
        <p className="text-xs text-muted-foreground">Signaux historiques indisponibles</p>
      ) : summary.present === 0 ? (
        <p className="text-xs text-muted-foreground">Aucun signal structuré produit</p>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            {summary.available} disponible{summary.available > 1 ? "s" : ""}
            {summary.unavailable > 0
              ? ` · ${summary.unavailable} indisponible${summary.unavailable > 1 ? "s" : ""}`
              : ""}
          </p>
          {summary.directions.length ? (
            <div className="flex flex-wrap gap-1" aria-label="Directions techniques disponibles">
              {summary.directions.map(({ direction, count }) => {
                const labels = directionLabels[direction]
                return (
                  <span key={direction} className="inline-flex items-center gap-1">
                    <IndicatorDirectionBadge direction={direction} compact />
                    <span className="text-xs text-muted-foreground">
                      {count} {count === 1 ? labels.singular : labels.plural}
                    </span>
                  </span>
                )
              })}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">Aucun indicateur calculable</p>
          )}
        </>
      )}
    </div>
  )
}
