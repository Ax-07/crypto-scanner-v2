import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { PortfolioTradesTable } from "@/features/backtests/components/portfolio-trades-table"
import { useBacktestStore } from "@/stores/backtest-store"
import { portfolioTradePage } from "@/test/backtest-fixtures"

describe("PortfolioTradesTable", () => {
  beforeEach(() => {
    useBacktestStore.setState({
      portfolioTrades: portfolioTradePage,
      portfolioTradesLoading: false,
      portfolioTradesError: null,
      loadPortfolioTradesPage: vi.fn(),
    })
  })

  it("affiche les trades dans l’ordre reçu et ouvre le détail sans requête", () => {
    const loadPage = useBacktestStore.getState().loadPortfolioTradesPage
    render(<PortfolioTradesTable />)
    expect(screen.getByText("Fin du backtest")).toBeVisible()
    fireEvent.click(screen.getByRole("button", { name: /Voir le trade du/ }))
    expect(screen.getByText("Trade trade-000001")).toBeVisible()
    expect(screen.getByText("Aucune (clôture administrative)")).toBeVisible()
    expect(loadPage).not.toHaveBeenCalled()
  })

  it("affiche un état vide moderne et une pagination nommée", () => {
    useBacktestStore.setState({
      portfolioTrades: { ...portfolioTradePage, items: [], total: 0 },
    })
    render(<PortfolioTradesTable />)
    expect(screen.getByText(/Aucun trade fermé/)).toBeVisible()
    expect(screen.getByRole("navigation", { name: "Pagination des trades simulés" })).toBeVisible()
  })
})
