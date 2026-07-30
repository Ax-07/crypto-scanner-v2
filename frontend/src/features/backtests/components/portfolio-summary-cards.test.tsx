import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { PortfolioSummaryCards } from "@/features/backtests/components/portfolio-summary-cards"
import { portfolioPublicResult } from "@/test/backtest-fixtures"

describe("PortfolioSummaryCards", () => {
  it("affiche le résultat backend, l’unité, les frais et le drawdown positif", () => {
    render(<PortfolioSummaryCards summary={portfolioPublicResult.summary} />)
    expect(screen.getByText("Gain simulé")).toBeVisible()
    expect(screen.getAllByText(/USDC/).length).toBeGreaterThan(0)
    expect(screen.getByText("Drawdown maximal")).toBeVisible()
    expect(screen.getByText("Frais cumulés")).toBeVisible()
    expect(screen.getByText(/rendements futurs indépendants/)).toBeVisible()
  })

  it("nomme explicitement une perte et tolère un win rate absent", () => {
    render(<PortfolioSummaryCards summary={{
      ...portfolioPublicResult.summary,
      net_profit: "-100",
      total_return_ratio: "-0.01",
      win_rate: null,
      average_trade_return: null,
      winning_trade_count: 0,
      losing_trade_count: 1,
    }} />)
    expect(screen.getByText("Perte simulée")).toBeVisible()
    expect(screen.getByText("Taux de réussite").parentElement).toHaveTextContent("—")
  })
})
