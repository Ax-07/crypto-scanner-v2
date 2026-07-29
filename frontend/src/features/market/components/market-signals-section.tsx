import { useState, type KeyboardEvent } from "react"

import { Button } from "@/components/ui/button"
import { MarketSignalSnapshot } from "@/features/market/components/market-signal-snapshot"
import { cn } from "@/lib/utils"
import { useMarketStore } from "@/stores/market-store"

type SnapshotKind = "confirmed" | "provisional"

export interface MarketSignalsSectionProps {
  symbol: string
  timeframe: string
}

export function MarketSignalsSection({ symbol, timeframe }: MarketSignalsSectionProps) {
  const confirmed = useMarketStore((state) => state.snapshot.confirmed)
  const provisional = useMarketStore((state) => state.snapshot.provisional)
  const [active, setActive] = useState<SnapshotKind>("confirmed")

  const selectFromKeyboard = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return
    event.preventDefault()
    const next = event.key === "ArrowRight" || event.key === "End"
      ? "provisional"
      : "confirmed"
    setActive(next)
    document.getElementById(`market-signals-tab-${next}`)?.focus()
  }

  return (
    <section aria-labelledby="market-signals-title" className="min-w-0 space-y-3">
      <div>
        <h2 id="market-signals-title" className="text-lg font-semibold">
          Signaux techniques du marché
        </h2>
        <p className="text-sm text-muted-foreground">
          Comparaison directe des calculs de la dernière clôture et de la bougie ouverte.
        </p>
      </div>
      <div
        aria-label="Choisir le snapshot de signaux"
        className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1 lg:hidden"
        role="tablist"
      >
        {(["confirmed", "provisional"] as const).map((kind) => {
          const selected = active === kind
          return (
            <Button
              id={`market-signals-tab-${kind}`}
              key={kind}
              aria-controls={`market-signals-panel-${kind}`}
              aria-selected={selected}
              role="tab"
              tabIndex={selected ? 0 : -1}
              variant={selected ? "secondary" : "ghost"}
              onClick={() => setActive(kind)}
              onKeyDown={selectFromKeyboard}
              className={cn(kind === "provisional" && "text-amber-700 dark:text-amber-300")}
            >
              {kind === "confirmed" ? "Confirmés" : "Provisoires"}
            </Button>
          )
        })}
      </div>
      <div className="grid min-w-0 gap-4 lg:grid-cols-2 lg:items-start">
        <div
          id="market-signals-panel-confirmed"
          aria-labelledby="market-signals-tab-confirmed"
          role="tabpanel"
          className={cn(active !== "confirmed" && "hidden lg:block")}
        >
          <MarketSignalSnapshot
            kind="confirmed"
            snapshot={confirmed}
            symbol={symbol}
            timeframe={timeframe}
          />
        </div>
        <div
          id="market-signals-panel-provisional"
          aria-labelledby="market-signals-tab-provisional"
          role="tabpanel"
          className={cn(active !== "provisional" && "hidden lg:block")}
        >
          <MarketSignalSnapshot
            kind="provisional"
            snapshot={provisional}
            symbol={symbol}
            timeframe={timeframe}
          />
        </div>
      </div>
    </section>
  )
}
