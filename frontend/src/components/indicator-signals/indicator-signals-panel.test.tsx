import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { IndicatorSignalsPanel } from "@/components/indicator-signals"
import type { IndicatorSignal, IndicatorSignals } from "@/types/indicator-signals"

const availableSignal: IndicatorSignal = {
  status: "available",
  direction: "neutral",
  signal: "neutral",
  state: "neutral",
  strength: 0.5,
  reason: null,
  raw_value: 42,
}

const unavailableSignal: IndicatorSignal = {
  ...availableSignal,
  status: "disabled",
  signal: null,
  state: null,
  raw_value: null,
}

describe("IndicatorSignalsPanel", () => {
  it("renders all indicators in canonical order regardless of input order", () => {
    const signals: IndicatorSignals = {
      stochastic: availableSignal,
      macd: availableSignal,
      rsi: availableSignal,
      bollinger: availableSignal,
      ema: availableSignal,
      sma: availableSignal,
    }
    render(<IndicatorSignalsPanel signals={signals} />)
    expect(screen.getAllByRole("article").map((article) => article.getAttribute("aria-label"))).toEqual([
      "Signal RSI",
      "Signal SMA",
      "Signal EMA",
      "Signal MACD",
      "Signal Bollinger",
      "Signal Stochastique",
    ])
  })

  it("accepts a partial dictionary without reconstructing absent indicators", () => {
    render(<IndicatorSignalsPanel signals={{ ema: availableSignal, rsi: availableSignal }} />)
    expect(screen.getAllByRole("article")).toHaveLength(2)
    expect(screen.queryByRole("article", { name: "Signal MACD" })).not.toBeInTheDocument()
  })

  it("renders the default or customized message for an empty dictionary", () => {
    const { rerender } = render(<IndicatorSignalsPanel signals={{}} />)
    expect(screen.getByText("Aucun signal structuré disponible.")).toBeVisible()
    rerender(<IndicatorSignalsPanel signals={{}} emptyMessage="Aucune donnée technique." />)
    expect(screen.getByText("Aucune donnée technique.")).toBeVisible()
  })

  it("filters unavailable signals without mutating the source object", () => {
    const signals: IndicatorSignals = {
      rsi: unavailableSignal,
      macd: availableSignal,
      bollinger: unavailableSignal,
    }
    const before = JSON.stringify(signals)
    render(<IndicatorSignalsPanel signals={signals} showUnavailable={false} />)
    expect(screen.getAllByRole("article")).toHaveLength(1)
    expect(screen.getByRole("article", { name: "Signal MACD" })).toBeVisible()
    expect(JSON.stringify(signals)).toBe(before)
  })

  it("distinguishes a filtered panel from an empty input", () => {
    render(
      <IndicatorSignalsPanel
        signals={{ rsi: unavailableSignal, macd: unavailableSignal }}
        showUnavailable={false}
      />,
    )
    expect(screen.getByText("Aucun signal disponible avec le filtre actuel.")).toBeVisible()
    expect(screen.queryByText("Aucun signal structuré disponible.")).not.toBeInTheDocument()
  })

  it("passes compact mode and reason visibility to its cards", () => {
    render(
      <IndicatorSignalsPanel
        signals={{ rsi: { ...availableSignal, reason: "Diagnostic détaillé" } }}
        compact
        showReason={false}
        className="test-panel"
      />,
    )
    const panel = screen.getByRole("region", { name: "Signaux techniques structurés" })
    expect(panel).toHaveClass("test-panel")
    const card = within(panel).getByRole("article", { name: "Signal RSI" })
    expect(within(card).getByRole("progressbar")).toBeInTheDocument()
    expect(within(card).queryByText("Diagnostic détaillé")).not.toBeInTheDocument()
  })
})
