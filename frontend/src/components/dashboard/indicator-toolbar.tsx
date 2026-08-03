import { SlidersHorizontal } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import {
  useMarketStore,
  type MinimumSimultaneousMarkers,
} from "@/stores/market-store"
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

const simultaneousMarkerOptions: Array<{
  value: MinimumSimultaneousMarkers
  label: string
}> = [
  { value: 1, label: "Tous (1+)" },
  { value: 2, label: "2+" },
  { value: 3, label: "3+" },
  { value: 4, label: "4+" },
  { value: 5, label: "5+" },
]

function parseMinimumSimultaneousMarkers(
  value: string,
): MinimumSimultaneousMarkers {
  const minimum = Number(value)

  if (
    minimum === 2 ||
    minimum === 3 ||
    minimum === 4 ||
    minimum === 5
  ) {
    return minimum
  }

  return 1
}

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
                <div className="flex items-center gap-2">
          <Label
            htmlFor="minimum-simultaneous-markers"
            className="text-xs text-muted-foreground"
          >
            Signaux simultanés
          </Label>

          <Select
            value={String(minimumSimultaneousMarkers)}
            onValueChange={(value) =>
              setMinimumSimultaneousMarkers(
                parseMinimumSimultaneousMarkers(value),
              )
            }
          >
            <SelectTrigger
              id="minimum-simultaneous-markers"
              size="sm"
              className="w-36"
              aria-label="Nombre minimum d’indicateurs simultanés"
            >
              <SelectValue />
            </SelectTrigger>

            <SelectContent>
              {simultaneousMarkerOptions.map(({ value, label }) => (
                <SelectItem key={value} value={String(value)}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardContent>
    </Card>
  )
}
