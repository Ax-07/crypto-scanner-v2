import { beforeEach, describe, expect, it, vi } from "vitest"

import { backtestApi } from "@/api/backtests"
import { useBacktestStore } from "@/stores/backtest-store"
import type { BacktestJob, SignalObservation } from "@/types/backtest"

vi.mock("@/api/backtests", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/backtests")>()
  return {
    ...original,
    backtestApi: {
      ...original.backtestApi,
      cancel: vi.fn(),
      get: vi.fn(),
      observations: vi.fn(),
    },
  }
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
})
