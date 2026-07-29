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
    useBacktestStore.setState({ job: null, observations: [], busy: false, error: null })
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
  })
})
