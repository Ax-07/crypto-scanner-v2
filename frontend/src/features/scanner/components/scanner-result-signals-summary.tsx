import {
  IndicatorDirectionBadge,
  INDICATOR_ORDER,
} from "@/components/indicator-signals"
import type {
  IndicatorSignalDirection,
  IndicatorSignals,
} from "@/types/indicator-signals"

interface ScannerResultSignalsSummaryProps {
  signals: IndicatorSignals | undefined
}

const DIRECTION_ORDER = ["bullish", "neutral", "bearish"] as const

const DIRECTION_COUNT_LABELS: Record<
  IndicatorSignalDirection,
  { singular: string; plural: string }
> = {
  bullish: { singular: "haussier", plural: "haussiers" },
  neutral: { singular: "neutre", plural: "neutres" },
  bearish: { singular: "baissier", plural: "baissiers" },
}

export function ScannerResultSignalsSummary({
  signals,
}: ScannerResultSignalsSummaryProps) {
  if (signals === undefined) {
    return <p className="text-xs text-muted-foreground">Non disponibles</p>
  }

  const presentSignals = INDICATOR_ORDER.flatMap((indicator) => {
    const signal = signals[indicator]
    return signal ? [signal] : []
  })

  if (presentSignals.length === 0) {
    return <p className="text-xs text-muted-foreground">Aucun signal produit</p>
  }

  const availableSignals = presentSignals.filter(
    (signal) => signal.status === "available",
  )
  const unavailableCount = presentSignals.length - availableSignals.length
  const directionCounts = DIRECTION_ORDER.flatMap((direction) => {
    const count = availableSignals.filter(
      (signal) => signal.direction === direction,
    ).length
    return count > 0 ? [{ direction, count }] : []
  })

  return (
    <div className="min-w-44 max-w-56 space-y-1.5 whitespace-normal">
      <p className="text-xs font-medium">
        {availableSignals.length} disponible
        {availableSignals.length > 1 ? "s" : ""}
        {unavailableCount > 0
          ? ` · ${unavailableCount} indisponible${unavailableCount > 1 ? "s" : ""}`
          : ""}
      </p>
      {directionCounts.length > 0 ? (
        <div className="flex flex-wrap gap-1" aria-label="Directions disponibles">
          {directionCounts.map(({ direction, count }) => {
            const labels = DIRECTION_COUNT_LABELS[direction]
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
        <p className="text-xs text-muted-foreground">
          Aucun indicateur calculable
        </p>
      )}
    </div>
  )
}
