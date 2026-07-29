import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"

export interface IndicatorStrengthProps {
  value: number
  showValue?: boolean
  compact?: boolean
  className?: string
}

function normalizeStrength(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.round(Math.min(1, Math.max(0, value)) * 100)
}

export function getStrengthCategory(value: number): string {
  if (value < 25) return "Très faible"
  if (value < 50) return "Faible"
  if (value < 75) return "Modérée"
  if (value < 90) return "Forte"
  return "Très forte"
}

export function IndicatorStrength({
  value,
  showValue = true,
  compact = false,
  className,
}: IndicatorStrengthProps) {
  const normalizedValue = normalizeStrength(value)
  const label = `Intensité technique : ${normalizedValue} sur 100`

  return (
    <div className={cn("min-w-0", compact ? "space-y-1" : "space-y-1.5", className)}>
      {showValue ? (
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="font-medium">Intensité {normalizedValue}/100</span>
          {!compact ? <span className="text-muted-foreground">{getStrengthCategory(normalizedValue)}</span> : null}
        </div>
      ) : null}
      <Progress
        value={normalizedValue}
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={normalizedValue}
        className={compact ? "h-1.5" : undefined}
      />
    </div>
  )
}
