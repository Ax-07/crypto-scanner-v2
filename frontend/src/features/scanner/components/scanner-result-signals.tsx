import { useState } from "react"

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
import { ScannerResultSignalsDetails } from "@/features/scanner/components/scanner-result-signals-details"
import { ScannerResultSignalsSummary } from "@/features/scanner/components/scanner-result-signals-summary"
import type { ScanResult } from "@/types/scanner"

interface ScannerResultSignalsProps {
  result: ScanResult
}

export function ScannerResultSignals({ result }: ScannerResultSignalsProps) {
  const [open, setOpen] = useState(false)
  const accessibleName = `Voir les signaux de ${result.symbol} en ${result.timeframe}`

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <div className="space-y-2">
        <ScannerResultSignalsSummary signals={result.indicator_signals} />
        <SheetTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label={accessibleName}
            onClick={(event) => event.stopPropagation()}
          >
            Voir les signaux
          </Button>
        </SheetTrigger>
      </div>
      <SheetContent
        className="w-full overflow-y-auto sm:max-w-4xl"
        showCloseButton={false}
      >
        <SheetHeader>
          <SheetTitle>
            Signaux techniques — {result.symbol} · {result.timeframe}
          </SheetTitle>
          <SheetDescription>
            Détail des signaux structurés reçus pour ce résultat du scanner.
          </SheetDescription>
        </SheetHeader>
        <div className="px-4">
          <ScannerResultSignalsDetails result={result} />
        </div>
        <SheetFooter>
          <SheetClose asChild>
            <Button type="button" variant="outline">
              Fermer
            </Button>
          </SheetClose>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
