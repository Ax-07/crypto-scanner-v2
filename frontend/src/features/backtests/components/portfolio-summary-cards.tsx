import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  formatDecimalAmount,
  formatDecimalRatio,
  formatSignedAmount,
  parseDecimalForDisplay,
} from "@/features/backtests/portfolio-formatters"
import type { PortfolioSimulationSummary } from "@/types/portfolio"

export function PortfolioSummaryCards({
  summary,
}: {
  summary: PortfolioSimulationSummary
}) {
  const profit = parseDecimalForDisplay(summary.net_profit)
  const resultText = profit === null ? "Résultat indisponible" : profit >= 0 ? "Gain simulé" : "Perte simulée"
  const metrics = [
    ["Capital initial", formatDecimalAmount(summary.initial_capital, summary.quote_asset)],
    ["Equity finale", formatDecimalAmount(summary.final_equity, summary.quote_asset)],
    [resultText, formatSignedAmount(summary.net_profit, summary.quote_asset)],
    ["Rendement total", formatDecimalRatio(summary.total_return_ratio)],
    ["Drawdown maximal", formatDecimalRatio(summary.max_drawdown_ratio)],
    ["Frais cumulés", formatDecimalAmount(summary.total_fees, summary.quote_asset)],
    ["Trades fermés", summary.trade_count.toLocaleString("fr-FR")],
    ["Taux de réussite", formatDecimalRatio(summary.win_rate)],
    ["Exposition", formatDecimalRatio(summary.exposure_ratio)],
    ["P&L réalisé", formatSignedAmount(summary.realized_pnl, summary.quote_asset)],
    ["P&L latent", formatSignedAmount(summary.unrealized_pnl, summary.quote_asset)],
    ["Positions ouvertes", summary.open_position_count.toLocaleString("fr-FR")],
  ] as const

  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map(([label, value]) => (
          <Card key={label}>
            <CardHeader className="gap-1">
              <CardDescription>{label}</CardDescription>
              <CardTitle className="text-xl">{value}</CardTitle>
            </CardHeader>
          </Card>
        ))}
      </div>
      <p className="text-sm text-muted-foreground">
        Le portefeuille simule une séquence de positions. Ces résultats ne sont ni des
        rendements futurs indépendants, ni une performance attribuable à un indicateur isolé.
        Le P&amp;L latent valorise la position au close sans frais de sortie hypothétiques.
      </p>
    </>
  )
}
