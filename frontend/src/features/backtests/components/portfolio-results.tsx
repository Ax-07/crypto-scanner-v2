import { useState } from "react"

import { backtestApi, portfolioErrorMessage } from "@/api/backtests"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { PortfolioEquityChart } from "@/features/backtests/components/portfolio-equity-chart"
import { PortfolioSummaryCards } from "@/features/backtests/components/portfolio-summary-cards"
import { PortfolioTradesTable } from "@/features/backtests/components/portfolio-trades-table"
import { formatDecimalAmount, formatDecimalRatio } from "@/features/backtests/portfolio-formatters"
import { useBacktestStore } from "@/stores/backtest-store"
import type { BacktestJob } from "@/types/backtest"
import type { PortfolioSimulationConfig } from "@/types/portfolio"

export function PortfolioResults({ job }: { job: BacktestJob }) {
  const metadata = useBacktestStore((state) => state.portfolioMetadata)
  const metadataLoading = useBacktestStore((state) => state.portfolioMetadataLoading)
  const metadataError = useBacktestStore((state) => state.portfolioMetadataError)
  const reloadMetadata = useBacktestStore((state) => state.loadPortfolioMetadata)
  const [exporting, setExporting] = useState<"trades" | "equity" | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)
  const configured = job.config.portfolio_simulation
  const publicResult = job.summary?.portfolio_simulation
  if (!configured) return null

  if (job.status === "failed") {
    return (
      <PortfolioShell>
        <PortfolioConfiguration config={configured} />
        <Alert className="border-destructive">
          <AlertTitle>Simulation non terminée</AlertTitle>
          <AlertDescription>{job.error ?? "Le backtest a échoué."}</AlertDescription>
        </Alert>
      </PortfolioShell>
    )
  }
  if (job.status === "cancelled") {
    return (
      <PortfolioShell>
        <PortfolioConfiguration config={configured} />
        <p className="text-sm text-muted-foreground">
          La simulation de portefeuille n’a pas produit de résultat final.
        </p>
      </PortfolioShell>
    )
  }
  if (job.status !== "completed") {
    return (
      <PortfolioShell>
        <PortfolioConfiguration config={configured} />
        <p className="text-sm text-muted-foreground">
          La simulation de portefeuille sera calculée à la fin du replay.
        </p>
      </PortfolioShell>
    )
  }
  if (!publicResult) return null

  const download = async (dataset: "trades" | "equity") => {
    setExporting(dataset)
    setExportError(null)
    try {
      await backtestApi.downloadPortfolioExport(job.id, dataset)
    } catch (error) {
      setExportError(portfolioErrorMessage(error))
    } finally {
      setExporting(null)
    }
  }

  return (
    <PortfolioShell>
      <PortfolioConfiguration config={configured} />
      <PortfolioSummaryCards summary={publicResult.summary} />
      {metadataLoading ? <Skeleton className="h-24 w-full" /> : null}
      {metadataError ? (
        <Alert>
          <AlertTitle>Détails persistants indisponibles</AlertTitle>
          <AlertDescription className="space-y-2">
            <p>{metadataError}</p>
            <Button type="button" size="sm" variant="outline" onClick={() => void reloadMetadata()}>
              Réessayer
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      {metadata ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Exports du portefeuille</CardTitle>
              <CardDescription>
                CSV v1 fournis par le backend. L’export equity contient la série brute complète.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 sm:flex-row">
              <Button
                type="button"
                variant="outline"
                disabled={exporting !== null}
                onClick={() => void download("trades")}
              >
                {exporting === "trades" ? "Téléchargement…" : "Exporter les trades"}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={exporting !== null}
                onClick={() => void download("equity")}
              >
                {exporting === "equity" ? "Téléchargement…" : "Exporter l’equity brute"}
              </Button>
            </CardContent>
          </Card>
          {exportError ? (
            <Alert className="border-destructive">
              <AlertTitle>Export impossible</AlertTitle>
              <AlertDescription>{exportError}</AlertDescription>
            </Alert>
          ) : null}
          <PortfolioEquityChart summary={publicResult.summary} />
          <PortfolioTradesTable />
        </>
      ) : null}
    </PortfolioShell>
  )
}

function PortfolioConfiguration({ config }: { config: PortfolioSimulationConfig }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Configuration utilisée</CardTitle>
        <CardDescription>
          Paramètres réellement enregistrés avec ce job.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
        <ConfigValue label="Capital initial" value={formatDecimalAmount(config.initial_capital, config.quote_asset)} />
        <ConfigValue label="Taille de position" value={`${config.position_sizing.value} % du cash`} />
        <ConfigValue label="Frais par côté" value={formatDecimalRatio(config.fee_rate)} />
        <ConfigValue label="Slippage" value={formatDecimalRatio(config.slippage_rate)} />
        <ConfigValue label="Exécution" value="Ouverture suivante" />
        <ConfigValue label="Fin de période" value="Clôture forcée" />
        <ConfigValue label="Position" value="Spot long, une position maximum" />
        <ConfigValue label="Actif de cotation" value={config.quote_asset} />
      </CardContent>
    </Card>
  )
}

function ConfigValue({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-muted-foreground">{label}</span>
      <p className="font-medium">{value}</p>
    </div>
  )
}

function PortfolioShell({ children }: { children: React.ReactNode }) {
  return (
    <section className="space-y-4" aria-labelledby="portfolio-results-title">
      <div>
        <h2 id="portfolio-results-title" className="text-xl font-semibold">
          Simulation de portefeuille
        </h2>
        <p className="text-sm text-muted-foreground">
          Séquence de positions qui fait évoluer un capital fictif.
        </p>
      </div>
      {children}
    </section>
  )
}
