import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import {
  formatDecimalAmount,
  formatDecimalRatio,
  formatSignedAmount,
} from "@/features/backtests/portfolio-formatters"
import type { PortfolioTrade } from "@/types/portfolio"

export const portfolioExitReasonLabel = (reason: PortfolioTrade["exit_reason"]) =>
  reason === "validation_lost" ? "Perte de validation" : "Fin du backtest"

export function PortfolioTradeDetails({ trade }: { trade: PortfolioTrade }) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant="outline"
          aria-label={`Voir le trade du ${new Date(trade.entry_time).toLocaleString("fr-FR")} au ${new Date(trade.exit_time).toLocaleString("fr-FR")}`}
        >
          Détail
        </Button>
      </SheetTrigger>
      <SheetContent className="w-full overflow-y-auto sm:max-w-4xl">
        <SheetHeader>
          <SheetTitle>Trade {trade.trade_id}</SheetTitle>
          <SheetDescription>
            Cycle simulé reçu du backend ; aucune donnée n’est recalculée dans cette vue.
          </SheetDescription>
        </SheetHeader>
        <dl className="grid gap-4 p-4 sm:grid-cols-2">
          <Detail label="Symbole" value={trade.symbol} />
          <Detail label="Actif de cotation" value={trade.quote_asset} />
          <Detail label="Entrée" value={new Date(trade.entry_time).toLocaleString("fr-FR")} />
          <Detail label="Sortie" value={new Date(trade.exit_time).toLocaleString("fr-FR")} />
          <Detail label="Prix d’entrée" value={formatDecimalAmount(trade.entry_price, trade.quote_asset)} />
          <Detail label="Prix de sortie" value={formatDecimalAmount(trade.exit_price, trade.quote_asset)} />
          <Detail label="Quantité" value={formatDecimalAmount(trade.quantity)} />
          <Detail label="P&L réalisé" value={formatSignedAmount(trade.realized_pnl, trade.quote_asset)} />
          <Detail label="Rendement" value={formatDecimalRatio(trade.return_ratio)} />
          <Detail label="Durée" value={`${trade.duration_bars.toLocaleString("fr-FR")} bougie(s)`} />
          <Detail label="Frais d’entrée" value={formatDecimalAmount(trade.entry_fee, trade.quote_asset)} />
          <Detail label="Frais de sortie" value={formatDecimalAmount(trade.exit_fee, trade.quote_asset)} />
          <Detail label="Raison de sortie" value={portfolioExitReasonLabel(trade.exit_reason)} />
          <Detail label="Observation d’entrée" value={trade.entry_observation_id} />
          <Detail label="Observation de sortie" value={trade.exit_observation_id ?? "Aucune (clôture administrative)"} />
          <Detail label="Position" value={trade.position_id} />
        </dl>
        <p className="px-4 text-sm text-muted-foreground">
          Les observations liées restent des états techniques. Leur acceptation n’est pas
          elle-même un ordre et les rendements futurs restent indépendants de ce trade.
        </p>
        <div className="p-4">
          <SheetClose asChild>
            <Button type="button" variant="outline">Fermer</Button>
          </SheetClose>
        </div>
      </SheetContent>
    </Sheet>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="break-all font-medium">{value}</dd>
    </div>
  )
}
