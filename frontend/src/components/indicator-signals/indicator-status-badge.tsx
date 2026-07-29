import {
  CheckCircle2,
  CircleOff,
  Clock3,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { IndicatorSignalStatus } from "@/types/indicator-signals"

import { INDICATOR_STATUS_LABELS } from "./indicator-signal-formatters"

export interface IndicatorStatusBadgeProps {
  status: IndicatorSignalStatus
  compact?: boolean
  className?: string
}

const STATUS_STYLES: Record<IndicatorSignalStatus, string> = {
  available: "border-emerald-600/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  insufficient_data: "border-amber-600/30 bg-amber-500/10 text-amber-800 dark:text-amber-300",
  invalid_data: "border-destructive/30 bg-destructive/10 text-destructive",
  disabled: "border-border bg-muted text-muted-foreground",
}

const STATUS_ICONS: Record<IndicatorSignalStatus, LucideIcon> = {
  available: CheckCircle2,
  insufficient_data: Clock3,
  invalid_data: TriangleAlert,
  disabled: CircleOff,
}

export function IndicatorStatusBadge({
  status,
  compact = false,
  className,
}: IndicatorStatusBadgeProps) {
  const label = INDICATOR_STATUS_LABELS[status]
  const Icon = STATUS_ICONS[status]

  return (
    <Badge
      variant="outline"
      aria-label={`Statut : ${label}`}
      className={cn(STATUS_STYLES[status], compact && "gap-1 px-1.5 py-0.5 text-[10px]", className)}
    >
      <Icon aria-hidden="true" data-testid={`status-icon-${status}`} className="size-3 shrink-0" />
      <span>{label}</span>
    </Badge>
  )
}
