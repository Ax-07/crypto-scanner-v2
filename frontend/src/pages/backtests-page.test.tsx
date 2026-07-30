import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { backtestApi } from "@/api/backtests"
import { scannerApi } from "@/api/scanner"
import { BacktestsPage } from "@/pages/backtests-page"
import { useBacktestStore } from "@/stores/backtest-store"
import {
  createBacktestJob,
  createObservation,
  portfolioEquityPage,
  portfolioMetadata,
  portfolioPublicResult,
  portfolioTradePage,
} from "@/test/backtest-fixtures"
import type { ScanConfig } from "@/types/scanner"

vi.mock("lightweight-charts", () => ({
  ColorType: { Solid: "solid" },
  HistogramSeries: "histogram",
  LineSeries: "line",
  createChart: () => ({
    addSeries: () => ({ setData: vi.fn() }),
    subscribeCrosshairMove: vi.fn(),
    unsubscribeCrosshairMove: vi.fn(),
    timeScale: () => ({ fitContent: vi.fn() }),
    remove: vi.fn(),
  }),
}))

describe("BacktestsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.stubGlobal("ResizeObserver", class {
      observe() {}
      unobserve() {}
      disconnect() {}
    })
    vi.spyOn(scannerApi, "getDefaultConfig").mockResolvedValue({} as ScanConfig)
    vi.spyOn(backtestApi, "list").mockResolvedValue({ items: [], total: 0 })
    useBacktestStore.setState({
      job: null,
      observations: [],
      observationsTotal: 0,
      observationsOffset: 0,
      observationsLoading: false,
      observationsError: null,
      busy: false,
      error: null,
    })
  })

  it("préserve le formulaire et le lancement du backtest", async () => {
    const start = vi.fn().mockResolvedValue(undefined)
    useBacktestStore.setState({ start })
    render(<BacktestsPage />)
    const launch = screen.getByRole("button", { name: "Lancer le backtest" })
    fireEvent.change(
      screen.getByLabelText("Symboles (séparés par des virgules)"),
      { target: { value: "ETH/USDC" } },
    )
    await waitFor(() => expect(scannerApi.getDefaultConfig).toHaveBeenCalled())
    fireEvent.submit(launch.closest("form")!)
    await waitFor(() => expect(start).toHaveBeenCalledOnce())
  })

  it("active la simulation, dérive la cotation et sérialise les pourcentages", async () => {
    const start = vi.fn().mockResolvedValue(undefined)
    useBacktestStore.setState({ start })
    render(<BacktestsPage />)
    fireEvent.change(screen.getByLabelText("Symboles (séparés par des virgules)"), {
      target: { value: "ETH/EUR" },
    })
    fireEvent.click(screen.getByRole("switch", { name: "Activer la simulation de portefeuille" }))
    expect(screen.getByLabelText("Actif de cotation")).toHaveValue("EUR")
    fireEvent.change(screen.getByLabelText("Taille de position (%)"), { target: { value: "50" } })
    fireEvent.change(screen.getByLabelText("Slippage (%)"), { target: { value: "0,05" } })
    await waitFor(() => expect(scannerApi.getDefaultConfig).toHaveBeenCalled())
    fireEvent.click(screen.getByRole("button", { name: "Lancer le backtest" }))
    await waitFor(() => expect(start).toHaveBeenCalledOnce())
    expect(start.mock.calls[0][0].portfolio_simulation).toEqual({
      version: 1,
      quote_asset: "EUR",
      initial_capital: "10000",
      position_sizing: { mode: "percent_cash", value: "50" },
      execution_policy: "next_open",
      fee_rate: "0.001",
      slippage_rate: "0.0005",
      end_of_test_policy: "force_close",
    })
  })

  it("préserve progression, métriques, exports et observations paginées", async () => {
    const job = createBacktestJob({
      summary: {
        observation_count: 1,
        accepted_count: 1,
        rejected_count: 0,
        censored_count: 0,
        warnings: [],
        horizons: {},
        segments: {},
        filter_funnel: [],
        provisional_supported: false,
        trade_simulation_included: false,
      },
    })
    useBacktestStore.setState({
      job,
      observations: [createObservation()],
      observationsTotal: 1,
    })
    render(<BacktestsPage />)

    expect(screen.getByText("Progression")).toBeVisible()
    expect(screen.getByText("Exports reproductibles")).toBeVisible()
    expect(screen.getByRole("link", { name: "observations.csv" })).toHaveAttribute(
      "href",
      expect.stringContaining("dataset=observations"),
    )
    expect(screen.getByText("Observations techniques")).toBeVisible()
    expect(screen.getByText("Observations 1–1 sur 1")).toBeVisible()
  })

  it("préserve l’annulation pendant un rejeu", () => {
    const cancel = vi.fn().mockResolvedValue(undefined)
    useBacktestStore.setState({
      job: createBacktestJob({ status: "running" }),
      busy: true,
      cancel,
    })
    render(<BacktestsPage />)
    fireEvent.click(screen.getByRole("button", { name: "Annuler" }))
    expect(cancel).toHaveBeenCalledOnce()
  })

  it("parcourt un résultat portefeuille complet sans confondre les outcomes", async () => {
    const download = vi.spyOn(backtestApi, "downloadPortfolioExport").mockResolvedValue()
    const portfolioConfig = {
      version: 1 as const,
      quote_asset: "USDC",
      initial_capital: "10000",
      position_sizing: { mode: "percent_cash" as const, value: "100" },
      execution_policy: "next_open" as const,
      fee_rate: "0.001",
      slippage_rate: "0",
      end_of_test_policy: "force_close" as const,
    }
    const completed = createBacktestJob({
      config: {
        ...createBacktestJob().config,
        portfolio_simulation: portfolioConfig,
      },
      summary: {
        observation_count: 2,
        accepted_count: 1,
        rejected_count: 1,
        censored_count: 0,
        warnings: [],
        horizons: {
          "1": { count: 2, mean: 0.01, positive_rate: 0.5 },
        },
        segments: {},
        filter_funnel: [],
        provisional_supported: false,
        trade_simulation_included: true,
        portfolio_simulation: portfolioPublicResult,
      },
    })
    useBacktestStore.setState({
      job: completed,
      portfolioMetadata,
      portfolioTrades: portfolioTradePage,
      portfolioEquity: portfolioEquityPage,
      portfolioMetadataLoading: false,
      portfolioMetadataError: null,
      portfolioTradesLoading: false,
      portfolioTradesError: null,
      portfolioEquityLoading: false,
      portfolioEquityError: null,
      loadPortfolioTradesPage: vi.fn(),
      loadPortfolioEquity: vi.fn(),
    })

    render(<BacktestsPage />)

    expect(screen.getByText("Analyse des rendements futurs")).toBeVisible()
    expect(screen.getAllByRole("heading", {
      name: "Simulation de portefeuille",
    })).toHaveLength(2)
    expect(screen.getAllByText("Equity finale")).toHaveLength(2)
    expect(screen.getByText("Trades simulés")).toBeVisible()
    expect(screen.getByRole("img", {
      name: "Courbe d’equity et de cash, avec drawdown positif",
    })).toBeVisible()

    fireEvent.click(screen.getByRole("button", { name: /Voir le trade du/ }))
    expect(await screen.findByText(`Trade ${portfolioTradePage.items[0].trade_id}`)).toBeVisible()
    fireEvent.click(screen.getByRole("button", { name: "Fermer" }))

    fireEvent.click(screen.getByRole("button", { name: "Exporter les trades" }))
    await waitFor(() => expect(download).toHaveBeenCalledWith(completed.id, "trades"))
    fireEvent.click(screen.getByRole("button", { name: "Exporter l’equity brute" }))
    await waitFor(() => expect(download).toHaveBeenCalledWith(completed.id, "equity"))
  })
})
