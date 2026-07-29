import {
  IndicatorDirectionBadge,
  INDICATOR_DIRECTION_ORDER,
  formatIndicatorDirectionCount,
  getIndicatorSignalsCollectionState,
  summarizeIndicatorSignals,
} from "@/components/indicator-signals"
import type { IndicatorSignals } from "@/types/indicator-signals"

interface ScannerResultSignalsSummaryProps {
  signals: IndicatorSignals | undefined
}

export function ScannerResultSignalsSummary({
  signals,
}: ScannerResultSignalsSummaryProps) {
  const state = getIndicatorSignalsCollectionState(signals)
  if (signals === undefined) {
    return <p className="text-xs text-muted-foreground">Non disponibles</p>
  }

  if (state === "empty") {
    return <p className="text-xs text-muted-foreground">Aucun signal produit</p>
  }

  const summary = summarizeIndicatorSignals(signals)
  const directionCounts = INDICATOR_DIRECTION_ORDER.flatMap((direction) => {
    const count = summary[direction]
    return count > 0 ? [{ direction, count }] : []
  })

  return (
    <div className="min-w-44 max-w-56 space-y-1.5 whitespace-normal">
      <p className="text-xs font-medium">
        {summary.available} disponible
        {summary.available > 1 ? "s" : ""}
        {summary.unavailable > 0
          ? ` · ${summary.unavailable} indisponible${summary.unavailable > 1 ? "s" : ""}`
          : ""}
      </p>
      {directionCounts.length > 0 ? (
        <div className="flex flex-wrap gap-1" aria-label="Directions disponibles">
          {directionCounts.map(({ direction, count }) => {
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
        <p className="text-xs text-muted-foreground">
          Aucun indicateur calculable
        </p>
      )}
    </div>
  )
}
