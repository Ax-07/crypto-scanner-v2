import { beforeEach, describe, expect, it, vi } from "vitest"

import { backtestApi } from "@/api/backtests"
import { useBacktestStore } from "@/stores/backtest-store"
import type { BacktestJob, SignalObservation } from "@/types/backtest"
import {
  createBacktestJob,
  portfolioEquityPage,
  portfolioMetadata,
  portfolioPublicResult,
  portfolioTradePage,
} from "@/test/backtest-fixtures"

vi.mock("@/api/backtests", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/backtests")>()
  return {
    ...original,
    backtestApi: {
      ...original.backtestApi,
      cancel: vi.fn(),
      get: vi.fn(),
      observations: vi.fn(),
      portfolio: vi.fn(),
      trades: vi.fn(),
      equity: vi.fn(),
    },
  }
})

const portfolioJob = createBacktestJob({
  config: {
    ...createBacktestJob().config,
    portfolio_simulation: {
      version: 1,
      quote_asset: "USDC",
      initial_capital: "10000",
      position_sizing: { mode: "percent_cash", value: "100" },
      execution_policy: "next_open",
      fee_rate: "0.001",
      slippage_rate: "0",
      end_of_test_policy: "force_close",
    },
  },
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
    trade_simulation_included: true,
    portfolio_simulation: portfolioPublicResult,
  },
})

const job = {
  id: "job-1",
  status: "completed",
  summary: null,
} as BacktestJob

const observation = {
  id: 1,
  job_id: "job-1",
  symbol: "BTC/USDC",
  timeframe: "1h",
  close: 100,
  indicator_signals: {
    rsi: {
      status: "available",
      direction: "bullish",
      signal: "exit_oversold",
      state: "near_oversold",
      strength: 0.75,
      reason: "Sortie de survente",
      raw_value: 31.4,
    },
  },
} as SignalObservation

describe("backtest store structured signals", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useBacktestStore.setState({
      job: null,
      observations: [],
      observationsTotal: 0,
      observationsOffset: 0,
      observationsLoading: false,
      observationsError: null,
      busy: false,
      error: null,
      portfolioMetadata: null,
      portfolioMetadataLoading: false,
      portfolioMetadataError: null,
      portfolioTrades: null,
      portfolioTradesLoading: false,
      portfolioTradesError: null,
      portfolioEquity: null,
      portfolioEquityLoading: false,
      portfolioEquityError: null,
    })
  })

  it("conserve les signaux validés chargés depuis l'API", async () => {
    vi.mocked(backtestApi.get).mockResolvedValue(job)
    vi.mocked(backtestApi.observations).mockResolvedValue({
      items: [observation],
      total: 1,
    })

    await useBacktestStore.getState().load(job.id)

    expect(useBacktestStore.getState().observations[0].indicator_signals)
      .toEqual(observation.indicator_signals)
    expect(useBacktestStore.getState().observationsTotal).toBe(1)
  })

  it("charge une page sans effacer les métriques du job", async () => {
    useBacktestStore.setState({ job })
    vi.mocked(backtestApi.observations).mockResolvedValue({
      items: [{ ...observation, id: 51 }],
      total: 75,
    })

    await useBacktestStore.getState().loadObservationsPage(50)

    expect(backtestApi.observations).toHaveBeenCalledWith("job-1", 50, 50)
    expect(useBacktestStore.getState().job).toBe(job)
    expect(useBacktestStore.getState().observationsOffset).toBe(50)
    expect(useBacktestStore.getState().observationsTotal).toBe(75)
    expect(useBacktestStore.getState().observations[0].id).toBe(51)
  })

  it("charge les observations partielles après une annulation", async () => {
    const runningJob = { ...job, status: "running" } as BacktestJob
    const cancelledJob = { ...job, status: "cancelled" } as BacktestJob
    useBacktestStore.setState({ job: runningJob, busy: true })
    vi.mocked(backtestApi.cancel).mockResolvedValue(cancelledJob)
    vi.mocked(backtestApi.observations).mockResolvedValue({
      items: [observation],
      total: 1,
    })

    await useBacktestStore.getState().cancel()

    expect(backtestApi.observations).toHaveBeenCalledWith("job-1", 0, 50)
    expect(useBacktestStore.getState().job).toEqual(cancelledJob)
    expect(useBacktestStore.getState().observations).toEqual([observation])
  })

  it("conserve la page valide lorsqu’une nouvelle page échoue", async () => {
    useBacktestStore.setState({ job, observations: [observation], observationsTotal: 75 })
    vi.mocked(backtestApi.observations).mockRejectedValue(new Error("Réseau indisponible"))

    await useBacktestStore.getState().loadObservationsPage(50)

    expect(useBacktestStore.getState().observations).toEqual([observation])
    expect(useBacktestStore.getState().observationsError).toBe("Réseau indisponible")
    expect(useBacktestStore.getState().observationsLoading).toBe(false)
  })

  it("charge les détails uniquement pour un job portefeuille terminé", async () => {
    vi.mocked(backtestApi.get).mockResolvedValue(portfolioJob)
    vi.mocked(backtestApi.observations).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(backtestApi.portfolio).mockResolvedValue(portfolioMetadata)
    vi.mocked(backtestApi.trades).mockResolvedValue(portfolioTradePage)
    vi.mocked(backtestApi.equity).mockResolvedValue(portfolioEquityPage)

    await useBacktestStore.getState().load(portfolioJob.id)
    await useBacktestStore.getState().loadPortfolioTradesPage(0)
    await useBacktestStore.getState().loadPortfolioEquity()

    expect(useBacktestStore.getState().portfolioMetadata).toEqual(portfolioMetadata)
    expect(useBacktestStore.getState().portfolioTrades).toEqual(portfolioTradePage)
    expect(useBacktestStore.getState().portfolioEquity).toEqual(portfolioEquityPage)
  })

  it("ne demande aucun endpoint portefeuille pour un job historique", async () => {
    vi.mocked(backtestApi.get).mockResolvedValue(createBacktestJob())
    vi.mocked(backtestApi.observations).mockResolvedValue({ items: [], total: 0 })

    await useBacktestStore.getState().load("job-1")

    expect(backtestApi.portfolio).not.toHaveBeenCalled()
    expect(backtestApi.equity).not.toHaveBeenCalled()
    expect(backtestApi.trades).not.toHaveBeenCalled()
  })

  it("ignore une réponse metadata tardive après changement de job", async () => {
    let resolveMetadata!: (value: typeof portfolioMetadata) => void
    vi.mocked(backtestApi.portfolio).mockReturnValue(new Promise((resolve) => {
      resolveMetadata = resolve
    }))
    useBacktestStore.setState({ job: portfolioJob })

    const pending = useBacktestStore.getState().loadPortfolioMetadata()
    useBacktestStore.setState({ job: createBacktestJob({ id: "job-2" }) })
    resolveMetadata(portfolioMetadata)
    await pending

    expect(useBacktestStore.getState().portfolioMetadata).toBeNull()
  })

  it("ignore une réponse metadata tardive pendant le chargement d’un autre job", async () => {
    let resolveMetadata!: (value: typeof portfolioMetadata) => void
    let resolveJob!: (value: BacktestJob) => void
    vi.mocked(backtestApi.portfolio).mockReturnValue(new Promise((resolve) => {
      resolveMetadata = resolve
    }))
    vi.mocked(backtestApi.get).mockReturnValue(new Promise((resolve) => {
      resolveJob = resolve
    }))
    useBacktestStore.setState({ job: portfolioJob })

    const pendingMetadata = useBacktestStore.getState().loadPortfolioMetadata()
    const pendingLoad = useBacktestStore.getState().load("job-2")
    resolveMetadata(portfolioMetadata)
    await pendingMetadata

    expect(useBacktestStore.getState().portfolioMetadata).toBeNull()

    resolveJob(createBacktestJob({ id: "job-2" }))
    await pendingLoad
    expect(useBacktestStore.getState().portfolioMetadata).toBeNull()
  })

  it("ignore les pages trades et equity tardives pendant un changement de job", async () => {
    let resolveTrades!: (value: typeof portfolioTradePage) => void
    let resolveEquity!: (value: typeof portfolioEquityPage) => void
    let resolveJob!: (value: BacktestJob) => void
    vi.mocked(backtestApi.trades).mockReturnValue(new Promise((resolve) => {
      resolveTrades = resolve
    }))
    vi.mocked(backtestApi.equity).mockReturnValue(new Promise((resolve) => {
      resolveEquity = resolve
    }))
    vi.mocked(backtestApi.get).mockReturnValue(new Promise((resolve) => {
      resolveJob = resolve
    }))
    useBacktestStore.setState({
      job: portfolioJob,
      portfolioMetadata,
    })

    const pendingTrades = useBacktestStore.getState().loadPortfolioTradesPage(0)
    const pendingEquity = useBacktestStore.getState().loadPortfolioEquity()
    const pendingLoad = useBacktestStore.getState().load("job-2")
    resolveTrades(portfolioTradePage)
    resolveEquity(portfolioEquityPage)
    await Promise.all([pendingTrades, pendingEquity])

    expect(useBacktestStore.getState().portfolioTrades).toBeNull()
    expect(useBacktestStore.getState().portfolioEquity).toBeNull()

    resolveJob(createBacktestJob({ id: "job-2" }))
    await pendingLoad
  })

  it("ignore les erreurs portfolio tardives pendant un changement de job", async () => {
    let rejectMetadata!: (reason: Error) => void
    let rejectTrades!: (reason: Error) => void
    let rejectEquity!: (reason: Error) => void
    let resolveJob!: (value: BacktestJob) => void
    vi.mocked(backtestApi.portfolio).mockReturnValue(new Promise((_, reject) => {
      rejectMetadata = reject
    }))
    vi.mocked(backtestApi.trades).mockReturnValue(new Promise((_, reject) => {
      rejectTrades = reject
    }))
    vi.mocked(backtestApi.equity).mockReturnValue(new Promise((_, reject) => {
      rejectEquity = reject
    }))
    vi.mocked(backtestApi.get).mockReturnValue(new Promise((resolve) => {
      resolveJob = resolve
    }))
    useBacktestStore.setState({
      job: portfolioJob,
      portfolioMetadata,
    })

    const pending = [
      useBacktestStore.getState().loadPortfolioMetadata(),
      useBacktestStore.getState().loadPortfolioTradesPage(0),
      useBacktestStore.getState().loadPortfolioEquity(),
    ]
    const pendingLoad = useBacktestStore.getState().load("job-2")
    rejectMetadata(new Error("metadata A"))
    rejectTrades(new Error("trades A"))
    rejectEquity(new Error("equity A"))
    await Promise.all(pending)

    expect(useBacktestStore.getState().portfolioMetadataError).toBeNull()
    expect(useBacktestStore.getState().portfolioTradesError).toBeNull()
    expect(useBacktestStore.getState().portfolioEquityError).toBeNull()

    resolveJob(createBacktestJob({ id: "job-2" }))
    await pendingLoad
  })
})
