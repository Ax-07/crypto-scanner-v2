import { act, fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { BacktestObservationsTable } from "@/features/backtests/components/backtest-observations-table"
import { useBacktestStore } from "@/stores/backtest-store"
import { createBacktestJob, createObservation } from "@/test/backtest-fixtures"

describe("BacktestObservationsTable", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useBacktestStore.setState({
      job: createBacktestJob(),
      observations: [createObservation(), createObservation({
        id: 2,
        symbol: "ETH/USDC",
        decision_time: "2026-07-29T16:00:00Z",
      })],
      observationsTotal: 52,
      observationsOffset: 0,
      observationsLoading: false,
      observationsError: null,
    })
  })

  it("conserve l’ordre reçu et ouvre un détail sans muter le store", () => {
    const before = useBacktestStore.getState().observations
    render(<BacktestObservationsTable job={createBacktestJob()} />)
    const rows = screen.getAllByRole("row").slice(1)
    expect(rows[0]).toHaveTextContent("BTC/USDC")
    expect(rows[1]).toHaveTextContent("ETH/USDC")
    fireEvent.click(screen.getAllByRole("button", { name: /Voir les signaux/ })[1])
    expect(screen.getByRole("dialog")).toHaveTextContent("ETH/USDC")
    expect(useBacktestStore.getState().observations).toBe(before)
  })

  it("pagine avec l’action existante sans requête à l’ouverture", () => {
    const loadPage = vi.fn().mockResolvedValue(undefined)
    useBacktestStore.setState({ loadObservationsPage: loadPage })
    render(<BacktestObservationsTable job={createBacktestJob()} />)
    fireEvent.click(screen.getAllByRole("button", { name: /Voir les signaux/ })[0])
    expect(loadPage).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "Fermer" }))
    fireEvent.click(screen.getByRole("button", { name: "Suivantes" }))
    expect(loadPage).toHaveBeenCalledWith(50)
  })

  it("affiche chargement, erreur et liste vide", () => {
    useBacktestStore.setState({ observations: [], observationsLoading: true })
    const { rerender } = render(<BacktestObservationsTable job={createBacktestJob()} />)
    expect(screen.getByLabelText("Chargement des observations")).toBeVisible()

    act(() => useBacktestStore.setState({
      observationsLoading: false,
      observationsError: "API indisponible",
    }))
    expect(screen.getByRole("alert")).toHaveTextContent("API indisponible")

    act(() => useBacktestStore.setState({ observationsError: null }))
    rerender(<BacktestObservationsTable job={createBacktestJob()} />)
    expect(screen.getByText("Aucune observation sur cette page.")).toBeVisible()
  })

  it("préserve les observations historiques sans signaux", () => {
    const legacy = createObservation()
    delete legacy.indicator_signals
    useBacktestStore.setState({ observations: [legacy], observationsTotal: 1 })
    render(<BacktestObservationsTable job={createBacktestJob()} />)
    expect(screen.getByText("Signaux historiques indisponibles")).toBeVisible()
  })

  it("affiche l’état en cours sans masquer la progression globale", () => {
    render(<BacktestObservationsTable job={createBacktestJob({ status: "running" })} />)
    expect(screen.getByText(/observations seront chargées à la fin/i)).toBeVisible()
  })
})
