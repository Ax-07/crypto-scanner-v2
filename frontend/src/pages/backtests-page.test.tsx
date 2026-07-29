import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { backtestApi } from "@/api/backtests"
import { scannerApi } from "@/api/scanner"
import { BacktestsPage } from "@/pages/backtests-page"
import { useBacktestStore } from "@/stores/backtest-store"
import { createBacktestJob, createObservation } from "@/test/backtest-fixtures"
import type { ScanConfig } from "@/types/scanner"

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
})
