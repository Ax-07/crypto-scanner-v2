import { cn } from "@/lib/utils"
import type { IndicatorName, IndicatorSignals } from "@/types/indicator-signals"

import { INDICATOR_ORDER } from "./indicator-signal-config"
import { IndicatorSignalCard } from "./indicator-signal-card"

export interface IndicatorSignalsPanelProps {
  signals: IndicatorSignals
  compact?: boolean
  showUnavailable?: boolean
  showReason?: boolean
  className?: string
  emptyMessage?: string
}

export function IndicatorSignalsPanel({
  signals,
  compact = false,
  showUnavailable = true,
  showReason = true,
  className,
  emptyMessage = "Aucun signal structuré disponible.",
}: IndicatorSignalsPanelProps) {
  const presentIndicators = INDICATOR_ORDER.filter(
    (indicator): indicator is IndicatorName => signals[indicator] !== undefined,
  )
  const visibleIndicators = showUnavailable
    ? presentIndicators
    : presentIndicators.filter((indicator) => signals[indicator]?.status === "available")

  if (visibleIndicators.length === 0) {
    return (
      <p className={cn("rounded-lg border border-dashed p-4 text-sm text-muted-foreground", className)}>
        {presentIndicators.length > 0
          ? "Aucun signal disponible avec le filtre actuel."
          : emptyMessage}
      </p>
    )
  }

  return (
    <section
      aria-label="Signaux techniques structurés"
      className={cn(
        "grid min-w-0 grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3",
        compact && "gap-2",
        className,
      )}
    >
      {visibleIndicators.map((indicator) => (
        <IndicatorSignalCard
          key={indicator}
          indicator={indicator}
          signal={signals[indicator]!}
          compact={compact}
          showReason={showReason}
        />
      ))}
    </section>
  )
}
