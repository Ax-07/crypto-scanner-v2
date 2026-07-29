import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { IndicatorName, IndicatorSignal } from "@/types/indicator-signals"

import { IndicatorDirectionBadge } from "./indicator-direction-badge"
import { INDICATOR_CONFIG } from "./indicator-signal-config"
import { formatIndicatorRawValue, formatTechnicalLabel } from "./indicator-signal-formatters"
import { IndicatorStatusBadge } from "./indicator-status-badge"
import { IndicatorStrength } from "./indicator-strength"

export interface IndicatorSignalCardProps {
  indicator: IndicatorName
  signal: IndicatorSignal
  compact?: boolean
  showReason?: boolean
  className?: string
}

const UNAVAILABLE_MESSAGES: Record<IndicatorSignal["status"], string> = {
  available: "",
  insufficient_data: "Historique insuffisant pour calculer ce signal.",
  invalid_data: "Les données de cet indicateur ne peuvent pas être exploitées.",
  disabled: "Cet indicateur est désactivé.",
}

function DetailLine({ label, value }: { label: string; value: string }) {
  return (
    <p className="min-w-0 break-words text-sm">
      <span className="text-muted-foreground">{label} : </span>
      <span className="font-medium">{value}</span>
    </p>
  )
}

export function IndicatorSignalCard({
  indicator,
  signal,
  compact = false,
  showReason = true,
  className,
}: IndicatorSignalCardProps) {
  const config = INDICATOR_CONFIG[indicator]
  const available = signal.status === "available"

  return (
    <Card
      role="article"
      aria-label={`Signal ${config.label}`}
      className={cn("min-w-0 overflow-hidden", compact ? "gap-2 rounded-lg" : "gap-3", className)}
    >
      <CardHeader className={cn("flex min-w-0 flex-row items-start justify-between gap-2", compact ? "px-3 pt-3" : undefined)}>
        <div className="min-w-0">
          <CardTitle className="truncate text-sm">{config.label}</CardTitle>
          {!compact ? <p className="mt-1 text-xs text-muted-foreground">{config.description}</p> : null}
        </div>
        <IndicatorStatusBadge status={signal.status} compact={compact} />
      </CardHeader>

      <CardContent className={cn("min-w-0 space-y-3", compact ? "px-3 pb-3" : undefined)}>
        {available ? (
          <>
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <IndicatorDirectionBadge direction={signal.direction} compact={compact} />
              {signal.signal ? (
                <span className="min-w-0 break-words text-sm font-medium">
                  {formatTechnicalLabel(signal.signal)}
                </span>
              ) : null}
            </div>

            {!compact ? (
              <div className="space-y-1.5">
                {signal.state ? <DetailLine label="État" value={formatTechnicalLabel(signal.state)} /> : null}
                <DetailLine
                  label="Valeur"
                  value={signal.raw_value === null
                    ? "indisponible"
                    : formatIndicatorRawValue(indicator, signal.raw_value)}
                />
              </div>
            ) : null}

            <IndicatorStrength value={signal.strength} compact={compact} />

            {!compact && showReason && signal.reason ? (
              <p className="break-words border-t pt-3 text-sm">
                <span className="text-muted-foreground">Raison : </span>
                {signal.reason}
              </p>
            ) : null}
          </>
        ) : (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">{UNAVAILABLE_MESSAGES[signal.status]}</p>
            {showReason && signal.reason ? (
              <p className="break-words text-sm">
                <span className="text-muted-foreground">Raison : </span>
                {signal.reason}
              </p>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
