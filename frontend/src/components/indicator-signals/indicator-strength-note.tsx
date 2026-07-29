import { cn } from "@/lib/utils"

export interface IndicatorStrengthNoteProps {
  className?: string
}

export function IndicatorStrengthNote({
  className,
}: IndicatorStrengthNoteProps) {
  return (
    <p className={cn("text-xs text-muted-foreground", className)}>
      L’intensité représente la force technique du signal selon les règles de
      l’indicateur. Elle ne représente pas une probabilité de gain.
    </p>
  )
}
