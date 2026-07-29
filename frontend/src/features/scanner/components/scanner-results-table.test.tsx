import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { ScannerResultsTable } from "@/features/scanner/components/scanner-results-table"
import { useScannerStore } from "@/stores/scanner-store"
import type { IndicatorSignal } from "@/types/indicator-signals"
import type { ScanConfig, ScanResult } from "@/types/scanner"

const config = {
  use_rsi: true,
  use_ma: true,
  use_macd: true,
  use_bollinger: true,
  use_stochastic: true,
  use_confluence_score: true,
} as ScanConfig

const signal: IndicatorSignal = {
  status: "available",
  direction: "bullish",
  signal: "exit_oversold",
  state: "near_oversold",
  strength: 0.75,
  reason: "Le RSI sort de la zone de survente.",
  raw_value: 31.4,
}

const result = {
  symbol: "ETH/USDC",
  timeframe: "4h",
  last_close_price: 1234,
  last_close_time: "2026-07-29T08:00:00Z",
  rsi: 42,
  trend_score: 2,
  trends: {},
  trend_net_score: 1,
  trend_states: { "4h": "bullish" },
  moving_averages: {},
  macd: 1,
  macd_signal: 0.8,
  macd_histogram: 0.2,
  macd_signal_type: "bullish",
  bb_upper: 1300,
  bb_middle: 1200,
  bb_lower: 1100,
  bb_position: "near_oversold",
  stoch_k: 22,
  stoch_d: 24,
  stoch_signal: "bullish_cross",
  confluence_score: 74,
  confluence_grade: "B",
  confluence_breakdown: {},
  confluence_effective_weights: {},
  confluence_details: {},
  indicator_availability: {},
  indicator_signals: { rsi: signal },
} satisfies ScanResult

describe("ScannerResultsTable", () => {
  it("utilise trois colonnes pour l’état vide sans configuration", () => {
    render(
      <MemoryRouter>
        <ScannerResultsTable config={null} results={[]} />
      </MemoryRouter>,
    )
    expect(screen.getByText("Aucun résultat pour le moment.")).toHaveAttribute(
      "colspan",
      "3",
    )
  })

  it("conserve toutes les colonnes historiques, leurs valeurs et le lien marché", () => {
    render(
      <MemoryRouter>
        <ScannerResultsTable config={config} results={[result]} />
      </MemoryRouter>,
    )
    expect(
      screen.getAllByRole("columnheader").map((header) => header.textContent),
    ).toEqual([
      "Symbole",
      "Prix",
      "RSI",
      "Tendance",
      "MACD",
      "Bollinger",
      "Stochastique",
      "Confluence",
      "Signaux",
    ])
    expect(screen.getByText(/^1\s234$/)).toBeInTheDocument()
    expect(screen.getByText("42.00")).toBeInTheDocument()
    expect(screen.getAllByText("Haussier")).not.toHaveLength(0)
    expect(screen.getByText("Proche survente")).toBeInTheDocument()
    expect(screen.getByText("Croisement haussier")).toBeInTheDocument()
    expect(screen.getByText("74.00 B")).toBeInTheDocument()
    const href = screen.getByRole("link", { name: "ETH/USDC" }).getAttribute("href")
    expect(href).toContain("/market?symbol=ETH%2FUSDC&timeframe=4h")
    expect(href).toContain("profile=")
  })

  it("rend un résultat historique sans signaux sans erreur", () => {
    const historicalResult: ScanResult = { ...result }
    delete historicalResult.indicator_signals

    render(
      <MemoryRouter>
        <ScannerResultsTable config={config} results={[historicalResult]} />
      </MemoryRouter>,
    )

    expect(screen.getByText("Non disponibles")).toBeInTheDocument()
    expect(
      screen.getByRole("button", {
        name: "Voir les signaux de ETH/USDC en 4h",
      }),
    ).toBeInTheDocument()
  })

  it("préserve l’ordre des résultats et un détail local par ligne sans muter le store", () => {
    const secondResult = {
      ...result,
      symbol: "BTC/USDC",
      timeframe: "1h",
      indicator_signals: { macd: signal },
    }
    const storeBefore = useScannerStore.getState()

    render(
      <MemoryRouter>
        <ScannerResultsTable config={config} results={[result, secondResult]} />
      </MemoryRouter>,
    )

    const rows = screen.getAllByRole("row").slice(1)
    expect(rows[0]).toHaveTextContent("ETH/USDC")
    expect(rows[1]).toHaveTextContent("BTC/USDC")

    fireEvent.click(
      screen.getByRole("button", {
        name: "Voir les signaux de BTC/USDC en 1h",
      }),
    )
    expect(
      screen.getByRole("dialog", {
        name: "Signaux techniques — BTC/USDC · 1h",
      }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("dialog", {
        name: "Signaux techniques — ETH/USDC · 4h",
      }),
    ).not.toBeInTheDocument()
    expect(useScannerStore.getState()).toBe(storeBefore)
  })
})
