import {
  IndicatorDirectionBadge,
  INDICATOR_DIRECTION_ORDER,
  formatIndicatorDirectionCount,
  getIndicatorSignalsCollectionState,
  summarizeIndicatorSignals,
} from "@/components/indicator-signals"
import { BacktestDecisionBadge } from "@/features/backtests/components/backtest-decision-badge"
import type { SignalObservation } from "@/types/backtest"

export interface BacktestObservationSummaryProps {
  observation: SignalObservation
}

export function BacktestObservationSummary({
  observation,
}: BacktestObservationSummaryProps) {
  const state = getIndicatorSignalsCollectionState(observation.indicator_signals)
  const summary = observation.indicator_signals === undefined
    ? null
    : summarizeIndicatorSignals(observation.indicator_signals)
  const directions = summary === null
    ? []
    : INDICATOR_DIRECTION_ORDER.flatMap((direction) => {
        const count = summary[direction]
        return count > 0 ? [{ direction, count }] : []
      })

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
      {state === "legacy_absent" ? (
        <p className="text-xs text-muted-foreground">Signaux historiques indisponibles</p>
      ) : state === "empty" ? (
        <p className="text-xs text-muted-foreground">Aucun signal structuré produit</p>
      ) : summary !== null ? (
        <>
          <p className="text-xs text-muted-foreground">
            {summary.available} disponible{summary.available > 1 ? "s" : ""}
            {summary.unavailable > 0
              ? ` · ${summary.unavailable} indisponible${summary.unavailable > 1 ? "s" : ""}`
              : ""}
          </p>
          {directions.length ? (
            <div className="flex flex-wrap gap-1" aria-label="Directions techniques disponibles">
              {directions.map(({ direction, count }) => {
                return (
                  <span key={direction} className="inline-flex items-center gap-1">
                    <IndicatorDirectionBadge direction={direction} compact />
                    <span className="text-xs text-muted-foreground">
                      {formatIndicatorDirectionCount(direction, count)}
                    </span>
                  </span>
                )
              })}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">Aucun indicateur calculable</p>
          )}
        </>
      ) : null}
    </div>
  )
}
