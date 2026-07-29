import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { BacktestObservationDetails } from "@/features/backtests/components/backtest-observation-details"
import { BacktestObservationSummary } from "@/features/backtests/components/backtest-observation-summary"
import {
  BACKTEST_OBSERVATION_PAGE_SIZE,
  useBacktestStore,
} from "@/stores/backtest-store"
import type { BacktestJob } from "@/types/backtest"

const priceFormatter = new Intl.NumberFormat("fr-FR", {
  maximumFractionDigits: 8,
})

export interface BacktestObservationsTableProps {
  job: BacktestJob
}

export function BacktestObservationsTable({ job }: BacktestObservationsTableProps) {
  const observations = useBacktestStore((state) => state.observations)
  const total = useBacktestStore((state) => state.observationsTotal)
  const offset = useBacktestStore((state) => state.observationsOffset)
  const loading = useBacktestStore((state) => state.observationsLoading)
  const error = useBacktestStore((state) => state.observationsError)
  const loadPage = useBacktestStore((state) => state.loadObservationsPage)
  const terminal = ["completed", "cancelled", "failed", "interrupted"].includes(job.status)
  const first = total === 0 ? 0 : offset + 1
  const last = Math.min(offset + observations.length, total)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Observations techniques</CardTitle>
        <CardDescription>
          Signaux candidats acceptés ou rejetés par les filtres du moteur. Il ne
          s’agit pas d’ordres ou de trades.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-lg border bg-muted/30 p-3 text-sm text-muted-foreground">
          Un signal technique, la décision d’acceptation du moteur et le rendement
          futur sont trois informations distinctes.
        </div>
        {!terminal ? (
          <div aria-label="Chargement des observations" className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <p className="text-sm text-muted-foreground">
              Les observations seront chargées à la fin du rejeu.
            </p>
          </div>
        ) : error ? (
          <Alert className="border-destructive">
            <AlertTitle>Observations indisponibles</AlertTitle>
            <AlertDescription className="space-y-2">
              <p>{error}</p>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => void loadPage(offset)}
              >
                Réessayer
              </Button>
            </AlertDescription>
          </Alert>
        ) : loading && observations.length === 0 ? (
          <div aria-label="Chargement des observations" className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : observations.length === 0 ? (
          <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
            Aucune observation sur cette page.
          </p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Marché</TableHead>
                    <TableHead>Prix observé</TableHead>
                    <TableHead>Décision et signaux</TableHead>
                    <TableHead>Motif</TableHead>
                    <TableHead>
                      <span className="sr-only">Actions</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {observations.map((observation) => (
                    <TableRow key={observation.id}>
                      <TableCell className="whitespace-nowrap">
                        {new Date(observation.decision_time).toLocaleString("fr-FR")}
                      </TableCell>
                      <TableCell>
                        <span className="font-medium">{observation.symbol}</span>
                        <span className="block text-xs text-muted-foreground">
                          {observation.timeframe}
                        </span>
                      </TableCell>
                      <TableCell className="tabular-nums">
                        {Number.isFinite(observation.close)
                          ? priceFormatter.format(observation.close)
                          : "—"}
                      </TableCell>
                      <TableCell>
                        <BacktestObservationSummary observation={observation} />
                      </TableCell>
                      <TableCell className="max-w-64 whitespace-normal break-words text-xs">
                        {observation.rejection_reason
                          ?? observation.rejection_stage
                          ?? "Aucun rejet"}
                      </TableCell>
                      <TableCell>
                        <BacktestObservationDetails
                          observation={observation}
                          entryPolicy={job.config.entry_policy}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <nav
              aria-label="Pagination des observations"
              className="flex flex-wrap items-center justify-between gap-3"
            >
              <p className="text-sm text-muted-foreground">
                Observations {first}–{last} sur {total}
              </p>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  disabled={offset === 0 || loading}
                  onClick={() => void loadPage(
                    Math.max(0, offset - BACKTEST_OBSERVATION_PAGE_SIZE),
                  )}
                >
                  Précédentes
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={offset + observations.length >= total || loading}
                  onClick={() => void loadPage(offset + BACKTEST_OBSERVATION_PAGE_SIZE)}
                >
                  Suivantes
                </Button>
              </div>
            </nav>
          </>
        )}
        <p className="text-xs text-muted-foreground">
          L’export observations.csv inclut les signaux structurés au format JSON.
          Aucun CSV n’est interprété dans le navigateur.
        </p>
      </CardContent>
    </Card>
  )
}
