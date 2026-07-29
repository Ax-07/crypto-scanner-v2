import {
  IndicatorSignalsPanel,
  IndicatorStrengthNote,
  formatIndicatorSignalsCollectionMessage,
  getIndicatorSignalsCollectionState,
} from "@/components/indicator-signals"
import { Badge } from "@/components/ui/badge"
import type { ScanResult } from "@/types/scanner"

interface ScannerResultSignalsDetailsProps {
  result: ScanResult
}

export function ScannerResultSignalsDetails({
  result,
}: ScannerResultSignalsDetailsProps) {
  const collectionState = getIndicatorSignalsCollectionState(result.indicator_signals)

  return (
    <div className="space-y-4">
      <section
        aria-label="Contexte historique du résultat"
        className="rounded-lg border bg-muted/30 p-3"
      >
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium">Contexte historique</p>
          {result.confluence_score !== null ? (
            <Badge variant="outline">
              Score de confluence : {result.confluence_score.toFixed(2)}/100
              {result.confluence_grade ? ` · grade ${result.confluence_grade}` : ""}
            </Badge>
          ) : (
            <span className="text-sm text-muted-foreground">
              Score de confluence indisponible
            </span>
          )}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Le score de confluence et les anciennes classifications restent des
          données historiques distinctes des signaux structurés ci-dessous.
        </p>
      </section>

      {collectionState !== "available" || result.indicator_signals === undefined ? (
        <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
          {formatIndicatorSignalsCollectionMessage({
            state: collectionState,
            context: "ce résultat",
          })}
        </p>
      ) : (
        <IndicatorSignalsPanel
          signals={result.indicator_signals}
        />
      )}

      <IndicatorStrengthNote />
    </div>
  )
}
