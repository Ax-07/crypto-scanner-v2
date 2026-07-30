import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { PortfolioEquityChart } from "@/features/backtests/components/portfolio-equity-chart"
import { useBacktestStore } from "@/stores/backtest-store"
import { portfolioEquityPage, portfolioPublicResult } from "@/test/backtest-fixtures"

const chartMocks = vi.hoisted(() => {
  const remove = vi.fn()
  const unsubscribeCrosshairMove = vi.fn()
  const setData = vi.fn()
  const createChart = vi.fn(() => ({
    addSeries: vi.fn(() => ({ setData })),
    subscribeCrosshairMove: vi.fn(),
    unsubscribeCrosshairMove,
    timeScale: () => ({ fitContent: vi.fn() }),
    remove,
  }))
  return { createChart, remove, setData, unsubscribeCrosshairMove }
})

vi.mock("lightweight-charts", () => ({
  ColorType: { Solid: "solid" },
  HistogramSeries: "histogram",
  LineSeries: "line",
  createChart: chartMocks.createChart,
}))

describe("PortfolioEquityChart", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useBacktestStore.setState({
      portfolioEquity: {
        items: [],
        total: 0,
        offset: 0,
        limit: 1000,
        has_more: false,
        sampled: true,
        source_point_count: 0,
      },
      portfolioEquityLoading: false,
      portfolioEquityError: null,
      loadPortfolioEquity: vi.fn(),
    })
  })

  it("affiche l’état vide et le résumé textuel sans série infinie", () => {
    render(<PortfolioEquityChart summary={portfolioPublicResult.summary} />)
    expect(screen.getByText("Aucun point d’equity disponible.")).toBeVisible()
    expect(screen.getByText("Equity initiale")).toBeVisible()
    expect(screen.getByText("Drawdown maximal")).toBeVisible()
    expect(screen.getByText(/Série échantillonnée/)).toBeVisible()
  })

  it("affiche une erreur indépendante", () => {
    useBacktestStore.setState({
      portfolioEquity: null,
      portfolioEquityError: "Réseau indisponible",
    })
    render(<PortfolioEquityChart summary={portfolioPublicResult.summary} />)
    expect(screen.getByText("Courbe indisponible")).toBeVisible()
    expect(screen.getByText("Réseau indisponible")).toBeVisible()
  })

  it("remplace les séries et détruit le graphique au démontage", () => {
    useBacktestStore.setState({
      portfolioEquity: portfolioEquityPage,
    })
    const { unmount } = render(
      <PortfolioEquityChart summary={portfolioPublicResult.summary} />,
    )

    expect(chartMocks.createChart).toHaveBeenCalledOnce()
    expect(chartMocks.setData).toHaveBeenCalledTimes(3)
    expect(screen.getByRole("img", {
      name: "Courbe d’equity et de cash, avec drawdown positif",
    })).toBeVisible()

    unmount()
    expect(chartMocks.unsubscribeCrosshairMove).toHaveBeenCalledOnce()
    expect(chartMocks.remove).toHaveBeenCalledOnce()
  })
})
