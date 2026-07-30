import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { PortfolioResults } from "@/features/backtests/components/portfolio-results"
import { useBacktestStore } from "@/stores/backtest-store"
import { createBacktestJob, portfolioPublicResult } from "@/test/backtest-fixtures"

const config = {
  version: 1 as const,
  quote_asset: "USDC",
  initial_capital: "10000",
  position_sizing: { mode: "percent_cash" as const, value: "100" },
  execution_policy: "next_open" as const,
  fee_rate: "0.001",
  slippage_rate: "0",
  end_of_test_policy: "force_close" as const,
}

const portfolioJob = (status: "running" | "completed" | "cancelled" | "failed") =>
  createBacktestJob({
    status,
    config: { ...createBacktestJob().config, portfolio_simulation: config },
    summary: status === "completed" ? {
      observation_count: 1,
      accepted_count: 1,
      rejected_count: 0,
      censored_count: 0,
      warnings: [],
      horizons: {},
      segments: {},
      filter_funnel: [],
      provisional_supported: false,
      trade_simulation_included: true,
      portfolio_simulation: portfolioPublicResult,
    } : null,
  })

describe("PortfolioResults", () => {
  beforeEach(() => {
    useBacktestStore.setState({
      portfolioMetadata: null,
      portfolioMetadataLoading: false,
      portfolioMetadataError: null,
      portfolioTrades: null,
      portfolioEquity: null,
      loadPortfolioEquity: vi.fn(),
      loadPortfolioTradesPage: vi.fn(),
    })
  })

  it("ne rend rien pour un job historique sans portefeuille", () => {
    const { container } = render(<PortfolioResults job={createBacktestJob()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("affiche l’attente sans inventer de résumé pour un job en cours", () => {
    render(<PortfolioResults job={portfolioJob("running")} />)
    expect(screen.getByText(/calculée à la fin du replay/)).toBeVisible()
    expect(screen.queryByText("Equity finale")).not.toBeInTheDocument()
  })

  it("conserve le résumé lorsqu’un ancien job n’a pas de détails", () => {
    useBacktestStore.setState({
      portfolioMetadataError:
        "Le résumé est disponible, mais les détails de cette ancienne simulation n’ont pas été persistés.",
    })
    render(<PortfolioResults job={portfolioJob("completed")} />)
    expect(screen.getByText("Equity finale")).toBeVisible()
    expect(screen.getByText("Détails persistants indisponibles")).toBeVisible()
    expect(screen.queryByText("Trades simulés")).not.toBeInTheDocument()
  })

  it("gère distinctement annulation et échec", () => {
    const { rerender } = render(<PortfolioResults job={portfolioJob("cancelled")} />)
    expect(screen.getByText(/n’a pas produit de résultat final/)).toBeVisible()
    rerender(<PortfolioResults job={{ ...portfolioJob("failed"), error: "portfolio_time_gap" }} />)
    expect(screen.getByText("portfolio_time_gap")).toBeVisible()
  })
})
