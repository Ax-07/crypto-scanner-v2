import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { BacktestObservationDetails } from "@/features/backtests/components/backtest-observation-details"
import { backtestSignal, createObservation } from "@/test/backtest-fixtures"
import type { IndicatorName } from "@/types/indicator-signals"

const indicatorNames: IndicatorName[] = [
  "rsi", "sma", "ema", "macd", "bollinger", "stochastic",
]

function openDetails(observation = createObservation(), entryPolicy: "signal_close" | "next_open" = "signal_close") {
  render(
    <BacktestObservationDetails
      observation={observation}
      entryPolicy={entryPolicy}
    />,
  )
  const trigger = screen.getByRole("button", { name: /Voir les signaux de l’observation/ })
  fireEvent.click(trigger)
  return trigger
}

describe("BacktestObservationDetails", () => {
  it("ouvre les six indicateurs dans l’ordre canonique avec décision et confluence", () => {
    const signals = Object.fromEntries(
      indicatorNames.map((name) => [name, {
        ...backtestSignal,
        reason: `Raison technique ${name}`,
      }]),
    )
    openDetails(createObservation({
      accepted: false,
      rejection_stage: "confluence",
      rejection_reason: "confluence_sous_seuil",
      indicator_signals: signals,
    }))

    expect(screen.getByRole("dialog", {
      name: "Observation technique — BTC/USDC · 4h",
    })).toBeVisible()
    expect(screen.getByText("Signal rejeté")).toBeVisible()
    expect(screen.getByText("confluence_sous_seuil")).toBeVisible()
    expect(screen.getByText("74/100 · Grade B")).toBeVisible()
    expect(screen.getByText("15")).toBeVisible()
    expect(screen.getAllByRole("article").map(
      (article) => article.getAttribute("aria-label"),
    )).toEqual([
      "Signal RSI",
      "Signal SMA",
      "Signal EMA",
      "Signal MACD",
      "Signal Bollinger",
      "Signal Stochastique",
    ])
  })

  it("explique causalité, signal versus performance et absence de trades", () => {
    openDetails()
    expect(screen.getByText(/aucune bougie future/i)).toBeVisible()
    expect(screen.getByText(/Un signal technique décrit l’état du marché/i)).toBeVisible()
    expect(screen.getByText(/Aucun trade n’est associé/i)).toBeVisible()
    expect(screen.getByText(/prix d’entrée théorique est cette clôture/i)).toBeVisible()
    expect(screen.getByText(
      /L’intensité représente la force technique.*ne représente pas une probabilité de gain/i,
    )).toBeVisible()
    expect(screen.queryByText(/taux de réussite|confiance|fiabilité|chance de gain/i))
      .not.toBeInTheDocument()
  })

  it("distingue le prix observé du prix next_open", () => {
    openDetails(createObservation(), "next_open")
    expect(screen.getByText(/l’ouverture suivante.*dataset outcomes/i)).toBeVisible()
  })

  it("affiche une ancienne observation sans champ structuré", () => {
    const legacy = createObservation()
    delete legacy.indicator_signals
    openDetails(legacy)
    expect(screen.getByText(/ne sont pas disponibles pour cette observation/)).toBeVisible()
  })

  it("transmet un dictionnaire partiel et un statut indisponible", () => {
    openDetails(createObservation({
      indicator_signals: {
        bollinger: {
          ...backtestSignal,
          status: "invalid_data",
          direction: "neutral",
          reason: "Bandes dégénérées",
        },
      },
    }))
    expect(screen.getAllByRole("article")).toHaveLength(1)
    expect(screen.getByRole("article", { name: "Signal Bollinger" }))
      .toHaveTextContent("Données invalides")
    expect(screen.getByText("Bandes dégénérées")).toBeVisible()
  })

  it("ferme avec Échap et rend le focus au déclencheur", async () => {
    const trigger = openDetails(createObservation({ indicator_signals: {} }))
    expect(screen.getByText(/Aucun signal structuré n’a été produit/)).toBeVisible()
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" })
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    await waitFor(() => expect(trigger).toHaveFocus())
  })
})
