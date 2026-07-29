import { useState } from "react"

import { IndicatorSignalsPanel } from "@/components/indicator-signals"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { BacktestDecisionBadge } from "@/features/backtests/components/backtest-decision-badge"
import type { BacktestConfig, SignalObservation } from "@/types/backtest"

const numberFormatter = new Intl.NumberFormat("fr-FR", {
  maximumFractionDigits: 8,
})

export interface BacktestObservationDetailsProps {
  observation: SignalObservation
  entryPolicy: BacktestConfig["entry_policy"]
}

function formatNumber(value: number | null | undefined) {
  return value == null || !Number.isFinite(value) ? "—" : numberFormatter.format(value)
}

export function BacktestObservationDetails({
  observation,
  entryPolicy,
}: BacktestObservationDetailsProps) {
  const [open, setOpen] = useState(false)
  const date = new Date(observation.decision_time).toLocaleString("fr-FR")
  const accessibleName = `Voir les signaux de l’observation du ${date}`
  const factorNames = Array.from(new Set([
    ...Object.keys(observation.confluence_factors),
    ...Object.keys(observation.confluence_breakdown ?? {}),
    ...Object.keys(observation.effective_weights),
  ]))

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button type="button" size="sm" variant="outline" aria-label={accessibleName}>
          Voir le détail
        </Button>
      </SheetTrigger>
      <SheetContent
        className="w-full overflow-y-auto sm:max-w-4xl"
        showCloseButton={false}
      >
        <SheetHeader>
          <SheetTitle>
            Observation technique — {observation.symbol} · {observation.timeframe}
          </SheetTitle>
          <SheetDescription>
            Informations disponibles au {date}, avant le calcul des rendements futurs.
          </SheetDescription>
        </SheetHeader>
        <div className="space-y-5 px-4">
          <section aria-labelledby="observation-context-title" className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <h3 id="observation-context-title" className="font-semibold">
                Décision de stratégie
              </h3>
              <BacktestDecisionBadge accepted={observation.accepted} />
              <Badge variant="outline">Snapshot {observation.snapshot_status}</Badge>
            </div>
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs text-muted-foreground">Date de décision</dt>
                <dd>{date}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Clôture observée</dt>
                <dd className="tabular-nums">{formatNumber(observation.close)}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Symbole et timeframe</dt>
                <dd>{observation.symbol} · {observation.timeframe}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Confluence reçue</dt>
                <dd>
                  {observation.confluence_score == null
                    ? "Indisponible"
                    : `${formatNumber(observation.confluence_score)}/100${observation.confluence_grade
                        ? ` · Grade ${observation.confluence_grade}`
                        : ""}`}
                </dd>
              </div>
              {!observation.accepted ? (
                <>
                  <div>
                    <dt className="text-xs text-muted-foreground">Étape de rejet</dt>
                    <dd className="break-words">{observation.rejection_stage ?? "Non précisée"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Motif du rejet</dt>
                    <dd className="break-words">{observation.rejection_reason ?? "Non précisé"}</dd>
                  </div>
                </>
              ) : null}
            </dl>
          </section>

          {factorNames.length ? (
            <section aria-labelledby="observation-confluence-title" className="space-y-2">
              <h3 id="observation-confluence-title" className="font-semibold">
                Détail de confluence
              </h3>
              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted/60">
                    <tr>
                      <th className="p-2">Facteur</th>
                      <th className="p-2">Valeur</th>
                      <th className="p-2">Poids effectif</th>
                      <th className="p-2">Contribution</th>
                    </tr>
                  </thead>
                  <tbody>
                    {factorNames.map((name) => (
                      <tr key={name} className="border-t">
                        <th className="p-2 font-medium capitalize">{name}</th>
                        <td className="p-2">{formatNumber(observation.confluence_factors[name])}</td>
                        <td className="p-2">{formatNumber(observation.effective_weights[name])}</td>
                        <td className="p-2">{formatNumber(observation.confluence_breakdown?.[name])}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-muted-foreground">
                Score, grade, facteurs, poids et contributions proviennent du backend et ne
                sont pas recalculés dans l’interface.
              </p>
            </section>
          ) : null}

          <section aria-labelledby="observation-signals-title" className="space-y-3">
            <h3 id="observation-signals-title" className="font-semibold">
              Signaux techniques
            </h3>
            {observation.indicator_signals === undefined ? (
              <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                Les signaux structurés ne sont pas disponibles pour cette observation.
              </p>
            ) : (
              <IndicatorSignalsPanel
                signals={observation.indicator_signals}
                emptyMessage="Aucun signal structuré n’a été produit pour cette observation."
              />
            )}
          </section>

          <section
            aria-labelledby="observation-causality-title"
            className="space-y-2 rounded-lg border bg-muted/30 p-4 text-sm"
          >
            <h3 id="observation-causality-title" className="font-semibold">
              Causalité et performance
            </h3>
            <p>
              Ces signaux correspondent uniquement aux informations disponibles à cet
              instant de la simulation. Ils ne tiennent compte d’aucune bougie future.
            </p>
            <p>
              Un signal technique décrit l’état du marché au moment de la décision.
              Les rendements futurs dépendent ensuite de l’évolution du prix, de
              l’horizon, des frais et du slippage.
            </p>
            <p>
              {entryPolicy === "signal_close"
                ? "Pour les outcomes, le prix d’entrée théorique est cette clôture observée."
                : "Pour les outcomes, le prix d’entrée théorique est l’ouverture suivante ; il appartient au dataset outcomes, pas à cette observation."}
            </p>
            <p>
              Aucun trade n’est associé : ce replay ne simule ni position, ni capital,
              ni ordre d’entrée ou de sortie.
            </p>
          </section>
        </div>
        <SheetFooter>
          <SheetClose asChild>
            <Button type="button" variant="outline">Fermer</Button>
          </SheetClose>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
