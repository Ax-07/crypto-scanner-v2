import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { MarketPage } from "@/pages/market-page"
import { useMarketStore } from "@/stores/market-store"

vi.mock("@/features/market/use-market-history", () => ({
  useMarketHistory: () => ({
    loadMore: vi.fn(),
    loadMoreAfter: vi.fn(),
    goToBeginning: vi.fn(),
    jumpToDate: vi.fn(),
    returnToLive: vi.fn(),
    retry: vi.fn(),
    loadingAll: false,
  }),
}))
vi.mock("@/features/market/use-market-socket", () => ({
  useMarketSocket: vi.fn(),
}))
vi.mock("@/features/market/components/market-toolbar", () => ({
  MarketToolbar: () => <div data-testid="market-toolbar">Toolbar marché</div>,
}))
vi.mock("@/components/dashboard/market-metrics", () => ({
  MarketMetrics: () => <div data-testid="market-metrics">Métriques</div>,
}))
vi.mock("@/components/dashboard/indicator-toolbar", () => ({
  IndicatorToolbar: () => <div data-testid="indicator-toolbar">Toolbar indicateurs</div>,
}))
vi.mock("@/components/dashboard/trading-chart", () => ({
  TradingChart: () => <div data-testid="trading-chart">Graphique</div>,
}))

describe("MarketPage", () => {
  beforeEach(() => {
    useMarketStore.getState().resetMarket("BTC/USDC", "1h")
    useMarketStore.setState({
      historyInitialized: true,
      snapshot: {
        confirmed: { price: 100, indicator_signals: {} },
        provisional: { price: 101, indicator_signals: {}, is_forming: true },
      },
    })
  })

  it("préserve toolbar, métriques et graphique pilotés par l’URL avant les signaux", () => {
    render(
      <MemoryRouter initialEntries={["/market?symbol=BTC%2FUSDC&timeframe=1h"]}>
        <MarketPage />
      </MemoryRouter>,
    )
    expect(screen.getByTestId("market-toolbar")).toBeVisible()
    expect(screen.getByTestId("market-metrics")).toBeVisible()
    expect(screen.getByTestId("indicator-toolbar")).toBeVisible()
    expect(screen.getByTestId("trading-chart")).toBeVisible()
    expect(screen.getAllByText("BTC/USDC").length).toBeGreaterThan(0)
    expect(screen.getAllByText("1h").length).toBeGreaterThan(0)

    const chart = screen.getByTestId("trading-chart")
    const signals = screen.getByRole("heading", { name: "Signaux techniques du marché" })
    expect(chart.compareDocumentPosition(signals) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})
