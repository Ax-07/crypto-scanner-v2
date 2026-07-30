import { useEffect, useRef } from "react"
import {
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  type HistogramData,
  type LineData,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  formatDecimalAmount,
  formatDecimalRatio,
  parseDecimalForDisplay,
} from "@/features/backtests/portfolio-formatters"
import { useBacktestStore } from "@/stores/backtest-store"
import type { PortfolioSimulationSummary } from "@/types/portfolio"

const chartTime = (value: string) => Math.floor(Date.parse(value) / 1000) as UTCTimestamp

export function PortfolioEquityChart({
  summary,
}: {
  summary: PortfolioSimulationSummary
}) {
  const page = useBacktestStore((state) => state.portfolioEquity)
  const loading = useBacktestStore((state) => state.portfolioEquityLoading)
  const error = useBacktestStore((state) => state.portfolioEquityError)
  const load = useBacktestStore((state) => state.loadPortfolioEquity)

  useEffect(() => {
    if (!page && !loading && !error) void load()
  }, [page, loading, error, load])

  return (
    <Card>
      <CardHeader>
        <CardTitle>Courbe d’equity</CardTitle>
        <CardDescription>
          Equity, cash et drawdown reçus du backend en mode échantillonné.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? <Skeleton className="h-80 w-full" /> : null}
        {error ? (
          <Alert className="border-destructive">
            <AlertTitle>Courbe indisponible</AlertTitle>
            <AlertDescription className="space-y-2">
              <p>{error}</p>
              <Button type="button" size="sm" variant="outline" onClick={() => void load()}>
                Réessayer
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}
        {!loading && !error && page?.items.length ? (
          <EquityChartCanvas points={page.items} />
        ) : null}
        {!loading && !error && page && !page.items.length ? (
          <p className="text-sm text-muted-foreground">Aucun point d’equity disponible.</p>
        ) : null}
        <dl className="grid gap-2 text-sm sm:grid-cols-2 xl:grid-cols-5">
          <ChartMetric label="Equity initiale" value={formatDecimalAmount(summary.initial_capital, summary.quote_asset)} />
          <ChartMetric label="Equity finale" value={formatDecimalAmount(summary.final_equity, summary.quote_asset)} />
          <ChartMetric label="Drawdown maximal" value={formatDecimalRatio(summary.max_drawdown_ratio)} />
          <ChartMetric label="Points affichés" value={(page?.items.length ?? 0).toLocaleString("fr-FR")} />
          <ChartMetric label="Points source" value={(page?.source_point_count ?? 0).toLocaleString("fr-FR")} />
        </dl>
        {page?.sampled ? (
          <p className="text-xs text-muted-foreground">
            Série échantillonnée : le backend conserve la série brute et ses extrema globaux.
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

function EquityChartCanvas({
  points,
}: {
  points: NonNullable<ReturnType<typeof useBacktestStore.getState>["portfolioEquity"]>["items"]
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const chart = createChart(ref.current, {
      autoSize: true,
      height: 320,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#94a3b8",
      },
      localization: { locale: "fr-FR" },
      timeScale: { timeVisible: true },
    })
    const equity = chart.addSeries(LineSeries, { title: "Equity", color: "#22c55e", lineWidth: 2 }, 0)
    const cash = chart.addSeries(LineSeries, { title: "Cash", color: "#38bdf8", lineWidth: 2 }, 0)
    const drawdown = chart.addSeries(HistogramSeries, {
      title: "Drawdown",
      color: "#ef4444",
      priceFormat: { type: "percent" },
    }, 1)
    const line = (key: "equity" | "cash"): LineData<Time>[] => points.flatMap((point) => {
      const value = parseDecimalForDisplay(point[key])
      return value === null ? [] : [{ time: chartTime(point.timestamp), value }]
    })
    const drawdownData: HistogramData<Time>[] = points.flatMap((point) => {
      const value = parseDecimalForDisplay(point.drawdown_ratio)
      return value === null ? [] : [{
        time: chartTime(point.timestamp),
        value: value * 100,
        color: value > 0 ? "#ef4444" : "#64748b",
      }]
    })
    equity.setData(line("equity"))
    cash.setData(line("cash"))
    drawdown.setData(drawdownData)
    const tooltip = document.createElement("div")
    tooltip.className = "pointer-events-none absolute left-2 top-2 z-10 rounded border bg-background/95 p-2 text-xs shadow"
    tooltip.hidden = true
    tooltip.setAttribute("aria-hidden", "true")
    ref.current.appendChild(tooltip)
    const seriesValue = (data: unknown) => {
      if (!data || typeof data !== "object" || !("value" in data) || typeof data.value !== "number") {
        return null
      }
      return data.value
    }
    const updateTooltip: Parameters<typeof chart.subscribeCrosshairMove>[0] = (parameter) => {
      if (!parameter.time || !parameter.point) {
        tooltip.hidden = true
        return
      }
      const equityValue = seriesValue(parameter.seriesData.get(equity))
      const cashValue = seriesValue(parameter.seriesData.get(cash))
      const drawdownValue = seriesValue(parameter.seriesData.get(drawdown))
      tooltip.hidden = false
      tooltip.textContent = [
        new Date(Number(parameter.time) * 1000).toLocaleString("fr-FR"),
        `Equity : ${equityValue === null ? "—" : equityValue.toLocaleString("fr-FR")}`,
        `Cash : ${cashValue === null ? "—" : cashValue.toLocaleString("fr-FR")}`,
        `Drawdown : ${drawdownValue === null ? "—" : `${drawdownValue.toLocaleString("fr-FR")} %`}`,
      ].join(" · ")
    }
    chart.subscribeCrosshairMove(updateTooltip)
    chart.timeScale().fitContent()
    return () => {
      chart.unsubscribeCrosshairMove(updateTooltip)
      chart.remove()
    }
  }, [points])
  return (
    <div
      ref={ref}
      className="relative h-80 w-full"
      role="img"
      aria-label="Courbe d’equity et de cash, avec drawdown positif"
    />
  )
}

function ChartMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  )
}
