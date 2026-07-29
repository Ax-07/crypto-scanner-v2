import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { BacktestObservationSummary } from "@/features/backtests/components/backtest-observation-summary"
import { backtestSignal, createObservation } from "@/test/backtest-fixtures"

describe("BacktestObservationSummary", () => {
  it("affiche la décision et la confluence reçues sans les recalculer", () => {
    render(<BacktestObservationSummary observation={createObservation({
      confluence_score: 76.25,
      confluence_grade: "B",
    })} />)
    expect(screen.getByText("Signal accepté")).toBeVisible()
    expect(screen.getByText("Confluence 76,25/100 · Grade B")).toBeVisible()
    expect(screen.queryByText(/probabilité|garanti/i)).not.toBeInTheDocument()
  })

  it("affiche un rejet sans le transformer en sortie", () => {
    render(<BacktestObservationSummary observation={createObservation({
      accepted: false,
    })} />)
    expect(screen.getByText("Signal rejeté")).toBeVisible()
    expect(screen.queryByText("Sortie")).not.toBeInTheDocument()
  })

  it("distingue champ absent et objet vide", () => {
    const withoutSignals = createObservation()
    delete withoutSignals.indicator_signals
    const { rerender } = render(
      <BacktestObservationSummary observation={withoutSignals} />,
    )
    expect(screen.getByText("Signaux historiques indisponibles")).toBeVisible()
    rerender(<BacktestObservationSummary observation={createObservation({
      indicator_signals: {},
    })} />)
    expect(screen.getByText("Aucun signal structuré produit")).toBeVisible()
  })

  it("compte un dictionnaire partiel et ignore les directions indisponibles", () => {
    render(<BacktestObservationSummary observation={createObservation({
      indicator_signals: {
        rsi: backtestSignal,
        macd: {
          ...backtestSignal,
          status: "insufficient_data",
          direction: "neutral",
        },
      },
    })} />)
    expect(screen.getByText("1 disponible · 1 indisponible")).toBeVisible()
    expect(screen.getByText("1 haussier")).toBeVisible()
    expect(screen.queryByText("1 neutre")).not.toBeInTheDocument()
  })

  it("gère une confluence absente", () => {
    render(<BacktestObservationSummary observation={createObservation({
      confluence_score: null,
      confluence_grade: null,
    })} />)
    expect(screen.getByText("Confluence indisponible")).toBeVisible()
  })
})
