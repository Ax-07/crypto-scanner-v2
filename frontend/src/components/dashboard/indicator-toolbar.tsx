import { SlidersHorizontal } from "lucide-react"

import { Button } from "@/components/ui/button"
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
  { key: "volatility", label: "Volatilité (ATR/NATR)" },
  { key: "adx", label: "ADX" },
  { key: "supertrend", label: "Supertrend" },
  { key: "donchian", label: "Donchian" },
  { key: "keltner", label: "Keltner" },
  { key: "signals", label: "Signaux" },
  { key: "divergences", label: "Divergences" },
]

const markerThresholdOptions = [
  { value: 1, label: "Tous" },
  { value: 2, label: "2+" },
  { value: 3, label: "3+" },
  { value: 4, label: "4+" },
  { value: 5, label: "5+" },
] as const

export function IndicatorToolbar() {
  const visibility = useMarketStore((state) => state.visibility)
  const toggle = useMarketStore((state) => state.toggleVisibility)
  const minimumSimultaneousMarkers = useMarketStore(
    (state) => state.minimumSimultaneousMarkers,
  )
  const setMinimumSimultaneousMarkers = useMarketStore(
    (state) => state.setMinimumSimultaneousMarkers,
  )

  return (
    <Card>
      <CardHeader className="pb-0">
        <CardTitle className="flex items-center gap-2 text-sm">
          <SlidersHorizontal className="size-4 text-primary" />
          Affichage
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 pt-1">
        <div className="flex flex-wrap gap-x-5 gap-y-3">
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
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t pt-3">
          <span className="text-xs font-medium text-muted-foreground">
            Signaux simultanés
          </span>
          <div className="flex flex-wrap gap-1" role="group" aria-label="Nombre minimum de signaux simultanés">
            {markerThresholdOptions.map(({ value, label }) => (
              <Button
                key={value}
                type="button"
                size="xs"
                variant={minimumSimultaneousMarkers === value ? "default" : "outline"}
                aria-pressed={minimumSimultaneousMarkers === value}
                onClick={() => setMinimumSimultaneousMarkers(value)}
              >
                {label}
              </Button>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
