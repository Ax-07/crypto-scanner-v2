import { Minus, TrendingDown, TrendingUp, type LucideIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { IndicatorSignalDirection } from "@/types/indicator-signals"

import { INDICATOR_DIRECTION_LABELS } from "./indicator-signal-formatters"

export interface IndicatorDirectionBadgeProps {
  direction: IndicatorSignalDirection
  compact?: boolean
  className?: string
}

const DIRECTION_STYLES: Record<IndicatorSignalDirection, string> = {
  bullish: "border-emerald-600/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  bearish: "border-destructive/30 bg-destructive/10 text-destructive",
  neutral: "border-border bg-muted text-muted-foreground",
}

const DIRECTION_ICONS: Record<IndicatorSignalDirection, LucideIcon> = {
  bullish: TrendingUp,
  bearish: TrendingDown,
  neutral: Minus,
}

export function IndicatorDirectionBadge({
  direction,
  compact = false,
  className,
}: IndicatorDirectionBadgeProps) {
  const label = INDICATOR_DIRECTION_LABELS[direction]
  const Icon = DIRECTION_ICONS[direction]

  return (
    <Badge
      variant="outline"
      aria-label={`Direction technique : ${label}`}
      className={cn(DIRECTION_STYLES[direction], compact && "gap-1 px-1.5 py-0.5 text-[10px]", className)}
    >
      <Icon aria-hidden="true" data-testid={`direction-icon-${direction}`} className="size-3 shrink-0" />
      <span>{label}</span>
    </Badge>
  )
}
