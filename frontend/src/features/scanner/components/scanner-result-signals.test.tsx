import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ScannerResultSignals } from "@/features/scanner/components/scanner-result-signals"
import { ScannerResultSignalsSummary } from "@/features/scanner/components/scanner-result-signals-summary"
import type { IndicatorSignal, IndicatorSignals } from "@/types/indicator-signals"
import type { ScanResult } from "@/types/scanner"

function createIndicatorSignal(
  overrides: Partial<IndicatorSignal> = {},
): IndicatorSignal {
  return {
    status: "available",
    direction: "bullish",
    signal: "bullish_cross",
    state: "above_signal",
    strength: 0.75,
    reason: "Signal technique confirmé.",
    raw_value: 42,
    ...overrides,
  }
}

function createScanResult(overrides: Partial<ScanResult> = {}): ScanResult {
  return {
    symbol: "BTC/USDC",
    timeframe: "4h",
    rsi: 31.4,
    last_close_price: 102,
    last_close_time: "2026-07-29T08:00:00Z",
    trend_score: 2,
    trends: {},
    trend_states: {},
    trend_net_score: 1,
    moving_averages: {},
    macd: 1.2,
    macd_signal: 0.8,
    macd_histogram: 0.4,
    macd_signal_type: "bullish",
    bb_upper: 105,
    bb_middle: 100,
    bb_lower: 95,
    bb_position: "near_oversold",
    stoch_k: 22,
    stoch_d: 25,
    stoch_signal: "bullish_cross",
    confluence_score: 74,
    confluence_grade: "B",
    confluence_breakdown: {},
    confluence_effective_weights: {},
    confluence_details: {},
    indicator_availability: {},
    ...overrides,
  }
}

describe("ScannerResultSignalsSummary", () => {
  it("décrit des directions mixtes sans recommandation ni score recalculé", () => {
    const signals: IndicatorSignals = {
      rsi: createIndicatorSignal({ direction: "bullish" }),
      sma: createIndicatorSignal({ direction: "bullish" }),
      macd: createIndicatorSignal({ direction: "neutral" }),
      stochastic: createIndicatorSignal({ direction: "bearish" }),
    }

    render(<ScannerResultSignalsSummary signals={signals} />)

    expect(screen.getByText("4 disponibles")).toBeInTheDocument()
    expect(screen.getByText("2 haussiers")).toBeInTheDocument()
    expect(screen.getByText("1 neutre")).toBeInTheDocument()
    expect(screen.getByText("1 baissier")).toBeInTheDocument()
    expect(screen.queryByText(/acheter|vendre/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/confluence|\/100/i)).not.toBeInTheDocument()
  })

  it("compte seulement les indicateurs présents dans un dictionnaire partiel", () => {
    render(
      <ScannerResultSignalsSummary
        signals={{ macd: createIndicatorSignal({ direction: "neutral" }) }}
      />,
    )

    expect(screen.getByText("1 disponible")).toBeInTheDocument()
    expect(screen.getByText("1 neutre")).toBeInTheDocument()
    expect(screen.queryByText("RSI")).not.toBeInTheDocument()
  })

  it("distingue le champ absent de l’objet vide", () => {
    const { rerender } = render(
      <ScannerResultSignalsSummary signals={undefined} />,
    )
    expect(screen.getByText("Non disponibles")).toBeInTheDocument()

    rerender(<ScannerResultSignalsSummary signals={{}} />)
    expect(screen.getByText("Aucun signal produit")).toBeInTheDocument()
    expect(screen.queryByText("Non disponibles")).not.toBeInTheDocument()
  })

  it("décrit tous les indicateurs indisponibles sans inventer de direction", () => {
    render(
      <ScannerResultSignalsSummary
        signals={{
          rsi: createIndicatorSignal({
            status: "insufficient_data",
            direction: "neutral",
          }),
          macd: createIndicatorSignal({
            status: "invalid_data",
            direction: "neutral",
          }),
        }}
      />,
    )

    expect(screen.getByText("0 disponible · 2 indisponibles")).toBeInTheDocument()
    expect(screen.getByText("Aucun indicateur calculable")).toBeInTheDocument()
    expect(
      screen.queryByLabelText("Direction technique : Neutre"),
    ).not.toBeInTheDocument()
  })
})

describe("ScannerResultSignals", () => {
  it("ouvre le détail complet dans l’ordre canonique avec champs nuls et raisons longues", () => {
    const longReason =
      "La série reçue contient une valeur invalide et ne permet pas de produire un calcul technique fiable."
    const result = createScanResult({
      indicator_signals: {
        stochastic: createIndicatorSignal({
          status: "insufficient_data",
          direction: "neutral",
          reason: "Historique trop court.",
        }),
        ema: createIndicatorSignal({
          signal: "bullish_alignment",
          raw_value: 101.1,
        }),
        macd: createIndicatorSignal({ signal: "bullish_cross", raw_value: null }),
        rsi: createIndicatorSignal({
          signal: "exit_oversold",
          state: null,
          reason: null,
          raw_value: 31.4,
        }),
        sma: createIndicatorSignal({
          signal: "price_above",
          raw_value: 100.8,
        }),
        bollinger: createIndicatorSignal({
          status: "invalid_data",
          direction: "neutral",
          reason: longReason,
        }),
      },
    })

    render(<ScannerResultSignals result={result} />)
    fireEvent.click(
      screen.getByRole("button", {
        name: "Voir les signaux de BTC/USDC en 4h",
      }),
    )

    expect(
      screen.getByRole("dialog", {
        name: "Signaux techniques — BTC/USDC · 4h",
      }),
    ).toBeInTheDocument()
    expect(screen.getByRole("article", { name: "Signal RSI" })).toBeInTheDocument()
    expect(screen.getByRole("article", { name: "Signal MACD" })).toHaveTextContent(
      "Valeur : indisponible",
    )
    expect(
      screen.getByRole("article", { name: "Signal Bollinger" }),
    ).toHaveTextContent("Données invalides")
    expect(
      screen.getByRole("article", { name: "Signal Stochastique" }),
    ).toHaveTextContent("Données insuffisantes")
    expect(screen.getByText(longReason)).toBeInTheDocument()

    const articles = screen.getAllByRole("article")
    expect(articles.map((article) => article.getAttribute("aria-label"))).toEqual([
      "Signal RSI",
      "Signal SMA",
      "Signal EMA",
      "Signal MACD",
      "Signal Bollinger",
      "Signal Stochastique",
    ])
    expect(screen.getByText(/ne représente pas une probabilité de gain/i)).toBeInTheDocument()
    expect(screen.getByText(/Score de confluence : 74.00\/100/)).toBeInTheDocument()
  })

  it("ferme avec le bouton puis rend le focus au déclencheur", async () => {
    render(
      <ScannerResultSignals
        result={createScanResult({
          indicator_signals: { rsi: createIndicatorSignal() },
        })}
      />,
    )
    const trigger = screen.getByRole("button", {
      name: "Voir les signaux de BTC/USDC en 4h",
    })
    fireEvent.click(trigger)
    fireEvent.click(screen.getByRole("button", { name: "Fermer" }))

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it("se ferme au clavier avec Échap", async () => {
    render(
      <ScannerResultSignals result={createScanResult({ indicator_signals: {} })} />,
    )
    fireEvent.click(
      screen.getByRole("button", {
        name: "Voir les signaux de BTC/USDC en 4h",
      }),
    )
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" })

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
  })

  it("affiche le message historique lorsque le champ est absent", () => {
    render(<ScannerResultSignals result={createScanResult()} />)
    fireEvent.click(
      screen.getByRole("button", {
        name: "Voir les signaux de BTC/USDC en 4h",
      }),
    )

    expect(
      screen.getByText(
        "Les signaux structurés ne sont pas disponibles pour ce résultat.",
      ),
    ).toBeInTheDocument()
  })

  it("affiche le message moderne distinct lorsque l’objet est vide", () => {
    render(
      <ScannerResultSignals result={createScanResult({ indicator_signals: {} })} />,
    )
    fireEvent.click(
      screen.getByRole("button", {
        name: "Voir les signaux de BTC/USDC en 4h",
      }),
    )

    expect(
      screen.getByText("Aucun signal structuré n’a été produit pour ce résultat."),
    ).toBeInTheDocument()
  })
})
