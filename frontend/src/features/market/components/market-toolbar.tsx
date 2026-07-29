import { useEffect, useState } from "react"
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  Loader2,
  Maximize2,
  Radio,
} from "lucide-react"

import { scannerApi } from "@/api/scanner"
import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { MarketDateNavigation } from "@/features/market/components/market-date-navigation"
import { MARKET_TIMEFRAMES } from "@/features/market/market-search-params"
import type { ChartCommand, MarketMode } from "@/types/market"
import type { Timeframe } from "@/types/scanner"

type Props = {
  symbol: string
  timeframe: Timeframe
  mode: MarketMode
  onChange: (next: { symbol: string; timeframe: Timeframe }) => void
  onLoadMore: () => void
  onLoadMoreAfter: () => void
  onGoBeginning: () => void
  onJumpToDate: (anchorTime: number) => void
  onReturnToLive: () => void
  onChartCommand: (command: ChartCommand) => void
  historyLoading: boolean
  loadingBefore: boolean
  loadingAfter: boolean
  jumpingToDate: boolean
  loadingAll: boolean
  hasMoreBefore: boolean
  hasMoreAfter: boolean
}

export function MarketToolbar({
  symbol,
  timeframe,
  mode,
  onChange,
  onLoadMore,
  onLoadMoreAfter,
  onGoBeginning,
  onJumpToDate,
  onReturnToLive,
  onChartCommand,
  historyLoading,
  loadingBefore,
  loadingAfter,
  jumpingToDate,
  loadingAll,
  hasMoreBefore,
  hasMoreAfter,
}: Props) {
  const [symbols, setSymbols] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState("")

  useEffect(() => {
    const controller = new AbortController()
    scannerApi.getMarkets("USDC", "spot", controller.signal)
      .then(setSymbols)
      .catch(() => undefined)
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [])

  const options = symbols.filter(
    (item) => !query || item.toLowerCase().includes(query.toLowerCase()),
  )
  return <div className="grid gap-3 sm:grid-cols-[minmax(12rem,1fr)_auto] sm:items-end">
    <Field>
      <FieldLabel htmlFor="market-symbol">Paire</FieldLabel>
      <div className="relative">
        <Input
          id="market-symbol"
          list="market-symbols"
          value={query || symbol}
          onChange={(event) => setQuery(event.target.value.toUpperCase())}
          onBlur={() => {
            const next = query.trim().toUpperCase()
            if (symbols.includes(next)) onChange({ symbol: next, timeframe })
            setQuery("")
          }}
          aria-label="Paire de marché"
        />
        {loading ? <Loader2 className="absolute right-3 top-2.5 size-4 animate-spin text-muted-foreground" /> : null}
        <datalist id="market-symbols">
          {options.map((item) => <option key={item} value={item} />)}
        </datalist>
      </div>
    </Field>
    <Field>
      <FieldLabel htmlFor="market-timeframe">Timeframe</FieldLabel>
      <select
        id="market-timeframe"
        className="h-9 rounded-md border bg-background px-3 text-sm"
        value={timeframe}
        onChange={(event) => onChange({
          symbol,
          timeframe: event.target.value as Timeframe,
        })}
      >
        {MARKET_TIMEFRAMES.map((item) => <option key={item}>{item}</option>)}
      </select>
    </Field>
    <div className="sm:col-span-2">
      <MarketDateNavigation jumping={jumpingToDate} onJump={onJumpToDate} />
    </div>
    <div className="flex flex-wrap gap-2 sm:col-span-2">
      <Button size="sm" onClick={onReturnToLive} disabled={historyLoading && mode === "live"}>
        <Radio />Revenir au direct
      </Button>
      <Button size="sm" variant="outline" onClick={() => onChartCommand("fit")}>
        <Maximize2 />Ajuster la vue
      </Button>
      <Button
        size="sm"
        variant="outline"
        disabled={historyLoading || !hasMoreBefore}
        onClick={onLoadMore}
      >
        {loadingBefore ? <Loader2 className="animate-spin" /> : <ChevronLeft />}
        Charger plus ancien
      </Button>
      {mode === "historical" ? <Button
        size="sm"
        variant="outline"
        disabled={historyLoading || !hasMoreAfter}
        onClick={onLoadMoreAfter}
      >
        {loadingAfter ? <Loader2 className="animate-spin" /> : <ChevronRight />}
        Charger plus récent
      </Button> : null}
      <Button
        size="sm"
        variant="outline"
        disabled={(historyLoading && !loadingAll) || (!hasMoreBefore && !loadingAll)}
        onClick={onGoBeginning}
      >
        <ChevronsLeft />{loadingAll ? "Annuler" : "Aller au début"}
      </Button>
    </div>
  </div>
}
