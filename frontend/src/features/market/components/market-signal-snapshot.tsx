import { CircleCheck, Clock3 } from "lucide-react"

import {
  IndicatorSignalsPanel,
  IndicatorStrengthNote,
  formatIndicatorSignalsCollectionMessage,
  getIndicatorSignalsCollectionState,
} from "@/components/indicator-signals"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { SignalView } from "@/types/market"

export interface MarketSignalSnapshotProps {
  kind: "confirmed" | "provisional"
  snapshot: SignalView | null | undefined
  symbol: string
  timeframe: string
  className?: string
}

const numberFormatter = new Intl.NumberFormat("fr-FR", {
  maximumFractionDigits: 8,
})

function formatTimestamp(timestamp: number | null | undefined) {
  return timestamp == null
    ? null
    : new Date(timestamp * 1_000).toLocaleString("fr-FR")
}

export function MarketSignalSnapshot({
  kind,
  snapshot,
  symbol,
  timeframe,
  className,
}: MarketSignalSnapshotProps) {
  const provisional = kind === "provisional"
  const title = provisional ? "Signaux provisoires" : "Signaux confirmés"
  const timestamp = formatTimestamp(snapshot?.timestamp)
  const collectionState = getIndicatorSignalsCollectionState(
    snapshot?.indicator_signals,
  )

  return (
    <Card
      className={cn(
        "min-w-0",
        provisional && "border-amber-500/40 bg-amber-500/5",
        className,
      )}
    >
      <CardHeader>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <CardTitle className="text-base">
            <h3>{title}</h3>
          </CardTitle>
          <Badge variant={provisional ? "warning" : "success"}>
            {provisional
              ? <Clock3 aria-hidden="true" className="size-3.5" />
              : <CircleCheck aria-hidden="true" className="size-3.5" />}
            {provisional ? "Provisoire" : "Confirmé"}
          </Badge>
        </div>
        <CardDescription>
          {provisional
            ? "Ces signaux utilisent la bougie en cours et peuvent changer avant sa clôture."
            : "Calculés à partir des dernières données confirmées."}
        </CardDescription>
      </CardHeader>
      <CardContent className="min-w-0 space-y-4">
        {!snapshot ? (
          <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
            {provisional
              ? "Aucun snapshot provisoire disponible."
              : "Aucun snapshot confirmé reçu pour le moment."}
          </p>
        ) : (
          <>
            <dl className="grid min-w-0 grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
              <div className="min-w-0">
                <dt className="text-xs text-muted-foreground">Marché</dt>
                <dd className="break-words font-medium">{symbol}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Timeframe</dt>
                <dd className="font-medium">{timeframe}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Prix du snapshot</dt>
                <dd className="font-medium tabular-nums">
                  {snapshot.price == null ? "—" : numberFormatter.format(snapshot.price)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Confluence</dt>
                <dd className="font-medium tabular-nums">
                  {snapshot.confluence
                    ? `${numberFormatter.format(snapshot.confluence.score)}/100 · Grade ${snapshot.confluence.grade}`
                    : "Indisponible"}
                </dd>
              </div>
              {timestamp ? (
                <div className="col-span-2 min-w-0 sm:col-span-4">
                  <dt className="text-xs text-muted-foreground">
                    {provisional ? "Mise à jour de la bougie ouverte" : "Dernière clôture"}
                  </dt>
                  <dd className="break-words font-medium">{timestamp}</dd>
                </div>
              ) : null}
            </dl>
            {collectionState !== "available" || snapshot.indicator_signals === undefined ? (
              <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                {formatIndicatorSignalsCollectionMessage({
                  state: collectionState,
                  context: "ce snapshot",
                })}
              </p>
            ) : (
              <IndicatorSignalsPanel signals={snapshot.indicator_signals} />
            )}
            <IndicatorStrengthNote />
            <p className="rounded-md bg-muted/60 p-3 text-xs leading-relaxed text-muted-foreground">
              Les signaux SMA et EMA sont affichés individuellement. Le facteur « Tendance »
              de la confluence conserve le calcul historique du marché.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  )
}
