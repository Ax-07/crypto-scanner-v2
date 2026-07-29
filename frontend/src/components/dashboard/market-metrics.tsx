import { Activity, Gauge, GitCompareArrows, Radio, Target, TrendingUp } from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"
import { useMarketStore } from "@/stores/market-store"

const labels: Record<string, string> = {
  bullish: "Haussier",
  bearish: "Baissier",
  neutral: "Neutre",
  unavailable: "Indisponible",
  insufficient_data: "Données insuffisantes",
  invalid_data: "Données invalides",
  disabled: "Désactivé",
  oversold: "Survente",
  overbought: "Surachat",
  near_oversold: "Proche survente",
  near_overbought: "Proche surachat",
  bullish_cross: "Croisement haussier",
  bearish_cross: "Croisement baissier",
}

function humanize(value?: string | null) {
  return value ? labels[value] ?? value : "—"
}

function formatNumber(value?: number | null, digits = 2) {
  return value == null
    ? "—"
    : value.toLocaleString("fr-FR", { maximumFractionDigits: digits })
}

export function MarketMetrics() {
  const snapshot = useMarketStore((state) => state.snapshot)
  const confirmed = snapshot.confirmed ?? snapshot
  const provisional = snapshot.provisional
  const divergenceCount = useMarketStore(
    (state) => state.markers.filter((marker) => marker.category === "divergence").length,
  )
  const metrics = [
    { key: "rsi", label: `RSI ${snapshot.profile?.rsi_period ?? 14}`, value: formatNumber(confirmed.rsi), forming: formatNumber(provisional?.rsi), icon: Gauge },
    { key: "trend", label: "Tendance", value: humanize(confirmed.trend), forming: humanize(provisional?.trend), icon: TrendingUp },
    { key: "macd", label: "MACD", value: humanize(confirmed.macd), forming: humanize(provisional?.macd), icon: Activity },
    { key: "bollinger", label: "Bollinger", value: humanize(confirmed.bollinger), forming: humanize(provisional?.bollinger), icon: Target },
    { key: "stochastic", label: "Stochastique", value: humanize(confirmed.stochastic), forming: humanize(provisional?.stochastic), icon: Radio },
    {
      key: "confluence",
      label: "Confluence",
      value: confirmed.confluence
        ? `${formatNumber(confirmed.confluence.score, 1)} · ${confirmed.confluence.grade}`
        : "Indisponible",
      forming: provisional?.confluence
        ? `${formatNumber(provisional.confluence.score, 1)} · ${provisional.confluence.grade}`
        : "—",
      icon: GitCompareArrows,
    },
    { key: "divergences", label: "Divergences", value: String(divergenceCount), forming: "—", icon: GitCompareArrows },
  ]

  return <>
    <section className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
      {metrics.map(({ key, label, value, forming, icon: Icon }) => (
        <Card key={label} className="gap-0">
          <CardContent className="flex items-center gap-3 p-3">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <Icon className="size-4" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-[11px] text-muted-foreground">{label} confirmé</p>
              <p className="truncate text-sm font-semibold tabular-nums">{value}</p>
              {provisional ? <p className="truncate text-[10px] text-amber-600">
                En formation : {forming}
              </p> : null}
              {confirmed.availability?.[key] && confirmed.availability[key] !== "available"
                ? <p className="text-[10px] text-muted-foreground">
                    {humanize(confirmed.availability[key])}
                  </p>
                : null}
            </div>
          </CardContent>
        </Card>
      ))}
    </section>
    {confirmed.confluence?.details ? <Card className="gap-0">
      <CardContent className="p-3">
        <details>
          <summary className="cursor-pointer text-sm font-medium">Détail du score de confluence</summary>
          <p className="mt-1 text-xs text-muted-foreground">
            Score technique, pas une probabilité de réussite.
          </p>
          <div className="mt-3 grid gap-2 text-xs">
            {Object.entries(confirmed.confluence.details).map(([name, detail]) => (
              <div key={name} className="grid grid-cols-4 gap-2 border-t pt-2">
                <span className="font-medium capitalize">{name}</span>
                <span>{detail.status === "available" ? `Facteur ${formatNumber(detail.factor)}` : "Indisponible"}</span>
                <span>Poids {formatNumber(detail.effective_weight)} %</span>
                <span>Contribution {formatNumber(detail.contribution)}</span>
              </div>
            ))}
          </div>
        </details>
      </CardContent>
    </Card> : null}
  </>
}
