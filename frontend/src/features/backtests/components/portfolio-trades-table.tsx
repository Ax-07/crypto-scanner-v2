import { useEffect } from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  formatDecimalAmount,
  formatDecimalRatio,
  formatSignedAmount,
} from "@/features/backtests/portfolio-formatters"
import { PortfolioTradeDetails, portfolioExitReasonLabel } from "@/features/backtests/components/portfolio-trade-details"
import {
  BACKTEST_PORTFOLIO_TRADE_PAGE_SIZE,
  useBacktestStore,
} from "@/stores/backtest-store"

export function PortfolioTradesTable() {
  const page = useBacktestStore((state) => state.portfolioTrades)
  const loading = useBacktestStore((state) => state.portfolioTradesLoading)
  const error = useBacktestStore((state) => state.portfolioTradesError)
  const loadPage = useBacktestStore((state) => state.loadPortfolioTradesPage)

  useEffect(() => {
    if (!page && !loading && !error) void loadPage(0)
  }, [page, loading, error, loadPage])

  const offset = page?.offset ?? 0
  return (
    <Card>
      <CardHeader>
        <CardTitle>Trades simulés</CardTitle>
        <CardDescription>
          Cycles entrée–sortie paginés par le backend, distincts des outcomes.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading && !page ? (
          <div className="space-y-2"><Skeleton className="h-10" /><Skeleton className="h-10" /></div>
        ) : null}
        {error ? (
          <Alert className="border-destructive">
            <AlertTitle>Trades indisponibles</AlertTitle>
            <AlertDescription className="space-y-2">
              <p>{error}</p>
              <Button type="button" size="sm" variant="outline" onClick={() => void loadPage(offset)}>
                Réessayer
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}
        {page?.items.length ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Entrée</TableHead>
                  <TableHead>Sortie</TableHead>
                  <TableHead>Prix entrée</TableHead>
                  <TableHead>Prix sortie</TableHead>
                  <TableHead>P&amp;L</TableHead>
                  <TableHead>Rendement</TableHead>
                  <TableHead>Durée</TableHead>
                  <TableHead>Raison</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {page.items.map((trade) => (
                  <TableRow key={trade.trade_id}>
                    <TableCell>{new Date(trade.entry_time).toLocaleString("fr-FR")}</TableCell>
                    <TableCell>{new Date(trade.exit_time).toLocaleString("fr-FR")}</TableCell>
                    <TableCell>{formatDecimalAmount(trade.entry_price, trade.quote_asset)}</TableCell>
                    <TableCell>{formatDecimalAmount(trade.exit_price, trade.quote_asset)}</TableCell>
                    <TableCell>{formatSignedAmount(trade.realized_pnl, trade.quote_asset)}</TableCell>
                    <TableCell>{formatDecimalRatio(trade.return_ratio)}</TableCell>
                    <TableCell>{trade.duration_bars} bougie(s)</TableCell>
                    <TableCell>{portfolioExitReasonLabel(trade.exit_reason)}</TableCell>
                    <TableCell><PortfolioTradeDetails trade={trade} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : null}
        {page && !page.items.length ? (
          <p className="text-sm text-muted-foreground">
            Aucun trade fermé. Une simulation moderne vide reste distincte d’un ancien job sans détails.
          </p>
        ) : null}
        {page ? (
          <nav className="flex flex-wrap items-center justify-between gap-3" aria-label="Pagination des trades simulés">
            <span className="text-sm text-muted-foreground">
              {page.total
                ? `${page.offset + 1}–${Math.min(page.offset + page.items.length, page.total)} sur ${page.total}`
                : "0 trade"}
            </span>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={loading || offset === 0}
                onClick={() => void loadPage(Math.max(0, offset - BACKTEST_PORTFOLIO_TRADE_PAGE_SIZE))}
              >
                Page précédente
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={loading || !page.has_more}
                onClick={() => void loadPage(offset + BACKTEST_PORTFOLIO_TRADE_PAGE_SIZE)}
              >
                Page suivante
              </Button>
            </div>
          </nav>
        ) : null}
      </CardContent>
    </Card>
  )
}
