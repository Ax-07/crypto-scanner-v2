import { CircleCheck, CircleX } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export interface BacktestDecisionBadgeProps {
  accepted: boolean
  className?: string
}

export function BacktestDecisionBadge({
  accepted,
  className,
}: BacktestDecisionBadgeProps) {
  const Icon = accepted ? CircleCheck : CircleX
  const label = accepted ? "Signal accepté" : "Signal rejeté"

  return (
    <Badge
      variant={accepted ? "success" : "secondary"}
      className={cn("whitespace-normal", className)}
      aria-label={`Décision du moteur : ${label}`}
    >
      <Icon aria-hidden="true" className="size-3.5 shrink-0" />
      {label}
    </Badge>
  )
}
