import { SlidersHorizontal } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { useMarketStore } from "@/stores/market-store"
import type { IndicatorVisibility } from "@/types/market"

const options: Array<{ key: keyof IndicatorVisibility; label: string }> = [
  { key: "ema", label: "EMA 20/50" },
  { key: "sma", label: "SMA 20/50" },
  { key: "bollinger", label: "Bollinger" },
  { key: "rsi", label: "RSI" },
  { key: "macd", label: "MACD" },
  { key: "stochastic", label: "Stochastique" },
  { key: "signals", label: "Signaux" },
  { key: "divergences", label: "Divergences" },
]

export function IndicatorToolbar() {
  const visibility = useMarketStore((state) => state.visibility)
  const toggle = useMarketStore((state) => state.toggleVisibility)

  return (
    <Card>
      <CardHeader className="pb-0">
        <CardTitle className="flex items-center gap-2 text-sm">
          <SlidersHorizontal className="size-4 text-primary" />
          Affichage
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-x-5 gap-y-3 pt-1">
        {options.map(({ key, label }) => {
          const id = `visibility-${key}`
          return (
            <div key={key} className="flex items-center gap-2">
              <Switch id={id} checked={visibility[key]} onCheckedChange={() => toggle(key)} />
              <Label htmlFor={id} className="cursor-pointer text-xs text-muted-foreground">
                {label}
              </Label>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
