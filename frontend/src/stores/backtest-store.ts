import { create } from "zustand"

import { backtestApi, backtestJobSchema, portfolioErrorMessage } from "@/api/backtests"
import type { BacktestConfig, BacktestJob, SignalObservation } from "@/types/backtest"
import type {
  PortfolioEquityPage,
  PortfolioRunMetadata,
  PortfolioTradePage,
} from "@/types/portfolio"

type State = {
  job: BacktestJob | null
  observations: SignalObservation[]
  observationsTotal: number
  observationsOffset: number
  observationsLoading: boolean
  observationsError: string | null
  portfolioMetadata: PortfolioRunMetadata | null
  portfolioMetadataLoading: boolean
  portfolioMetadataError: string | null
  portfolioTrades: PortfolioTradePage | null
  portfolioTradesLoading: boolean
  portfolioTradesError: string | null
  portfolioEquity: PortfolioEquityPage | null
  portfolioEquityLoading: boolean
  portfolioEquityError: string | null
  busy: boolean
  error: string | null
  start: (config: BacktestConfig) => Promise<void>
  cancel: () => Promise<void>
  load: (id: string) => Promise<void>
  resume: () => Promise<void>
  loadObservationsPage: (offset: number) => Promise<void>
  loadPortfolioMetadata: () => Promise<void>
  loadPortfolioTradesPage: (offset: number) => Promise<void>
  loadPortfolioEquity: () => Promise<void>
  reset: () => void
}

export const BACKTEST_OBSERVATION_PAGE_SIZE = 50
export const BACKTEST_PORTFOLIO_TRADE_PAGE_SIZE = 50
export const BACKTEST_PORTFOLIO_EQUITY_MAX_POINTS = 1000

let socket: WebSocket | null = null
function closeSocket() {
  if (!socket) return
  socket.onmessage = null
  socket.close()
  socket = null
}

type StateSetter = (patch: Partial<State>) => void
type StateGetter = () => State

const emptyPortfolioState = {
  portfolioMetadata: null,
  portfolioMetadataLoading: false,
  portfolioMetadataError: null,
  portfolioTrades: null,
  portfolioTradesLoading: false,
  portfolioTradesError: null,
  portfolioEquity: null,
  portfolioEquityLoading: false,
  portfolioEquityError: null,
}

async function loadPortfolioMetadata(
  jobId: string,
  set: StateSetter,
  get: StateGetter,
) {
  const job = get().job
  if (
    !job
    || job.id !== jobId
    || job.status !== "completed"
    || !job.config.portfolio_simulation
  ) return
  set({ portfolioMetadataLoading: true, portfolioMetadataError: null })
  try {
    const metadata = await backtestApi.portfolio(jobId)
    if (get().job?.id !== jobId) return
    set({ portfolioMetadata: metadata, portfolioMetadataLoading: false })
  } catch (error) {
    if (get().job?.id !== jobId) return
    set({
      portfolioMetadataLoading: false,
      portfolioMetadataError: portfolioErrorMessage(error),
    })
  }
}

async function loadPortfolioTradesPage(
  jobId: string,
  offset: number,
  set: StateSetter,
  get: StateGetter,
) {
  const safeOffset = Math.max(0, offset)
  set({ portfolioTradesLoading: true, portfolioTradesError: null })
  try {
    const page = await backtestApi.trades(
      jobId,
      safeOffset,
      BACKTEST_PORTFOLIO_TRADE_PAGE_SIZE,
    )
    if (get().job?.id !== jobId) return
    set({ portfolioTrades: page, portfolioTradesLoading: false })
  } catch (error) {
    if (get().job?.id !== jobId) return
    set({
      portfolioTradesLoading: false,
      portfolioTradesError: portfolioErrorMessage(error),
    })
  }
}

async function loadPortfolioEquity(
  jobId: string,
  set: StateSetter,
  get: StateGetter,
) {
  set({ portfolioEquityLoading: true, portfolioEquityError: null })
  try {
    const page = await backtestApi.equity(jobId, {
      mode: "sampled",
      maxPoints: BACKTEST_PORTFOLIO_EQUITY_MAX_POINTS,
    })
    if (get().job?.id !== jobId) return
    set({ portfolioEquity: page, portfolioEquityLoading: false })
  } catch (error) {
    if (get().job?.id !== jobId) return
    set({
      portfolioEquityLoading: false,
      portfolioEquityError: portfolioErrorMessage(error),
    })
  }
}

async function loadObservationPage(
  jobId: string,
  offset: number,
  set: StateSetter,
  get: StateGetter,
) {
  const safeOffset = Math.max(0, offset)
  set({ observationsLoading: true, observationsError: null })
  try {
    const page = await backtestApi.observations(
      jobId,
      safeOffset,
      BACKTEST_OBSERVATION_PAGE_SIZE,
    )
    if (get().job?.id !== jobId) return
    set({
      observations: page.items,
      observationsTotal: page.total,
      observationsOffset: safeOffset,
      observationsLoading: false,
    })
  } catch (error) {
    if (get().job?.id !== jobId) return
    set({
      observationsLoading: false,
      observationsError: error instanceof Error
        ? error.message
        : "Chargement des observations impossible",
    })
  }
}

function watchJob(job: BacktestJob, set: StateSetter, get: StateGetter) {
  const current = new WebSocket(backtestApi.websocketUrl(job.id))
  socket = current
  current.onmessage = async (event) => {
    if (socket !== current) return
    try {
      const next = backtestJobSchema.parse(JSON.parse(String(event.data))) as BacktestJob
      const terminal = ["completed", "failed", "cancelled", "interrupted"].includes(next.status)
      set({ job: next, busy: !terminal, error: next.error })
      if (["completed", "cancelled"].includes(next.status)) {
        await loadObservationPage(next.id, 0, set, get)
      }
      if (next.status === "completed" && next.config.portfolio_simulation) {
        await loadPortfolioMetadata(next.id, set, get)
      }
      if (terminal) closeSocket()
    } catch {
      set({ busy: false, error: "Message de progression invalide" })
      closeSocket()
    }
  }
  current.onerror = () => set({ error: "Connexion de progression interrompue" })
}

export const useBacktestStore = create<State>()((set, get) => ({
  job: null,
  observations: [],
  observationsTotal: 0,
  observationsOffset: 0,
  observationsLoading: false,
  observationsError: null,
  ...emptyPortfolioState,
  busy: false,
  error: null,
  start: async (config) => {
    closeSocket()
    set({
      busy: true,
      error: null,
      observations: [],
      observationsTotal: 0,
      observationsOffset: 0,
      observationsError: null,
      ...emptyPortfolioState,
    })
    try {
      const job = await backtestApi.start(config)
      set({ job })
      watchJob(job, set, get)
    } catch (error) {
      set({ busy: false, error: error instanceof Error ? error.message : "Backtest impossible" })
      throw error
    }
  },
  cancel: async () => {
    const job = get().job
    if (!job) return
    const cancelled = await backtestApi.cancel(job.id)
    set({ job: cancelled, busy: false })
    set({ ...emptyPortfolioState })
    closeSocket()
    await loadObservationPage(cancelled.id, 0, set, get)
  },
  load: async (id) => {
    closeSocket()
    set({
      job: null,
      busy: true,
      error: null,
      observations: [],
      observationsTotal: 0,
      observationsOffset: 0,
      observationsError: null,
      ...emptyPortfolioState,
    })
    try {
      const job = await backtestApi.get(id)
      const terminal = ["completed", "failed", "cancelled", "interrupted"].includes(job.status)
      set({ job, busy: !terminal })
      if (["completed", "cancelled"].includes(job.status)) {
        await loadObservationPage(job.id, 0, set, get)
      }
      if (job.status === "completed" && job.config.portfolio_simulation) {
        await loadPortfolioMetadata(job.id, set, get)
      }
      if (!terminal) watchJob(job, set, get)
    } catch (error) {
      set({ busy: false, error: error instanceof Error ? error.message : "Chargement impossible" })
    }
  },
  resume: async () => {
    const current = get().job
    if (!current) return
    closeSocket()
    set({ busy: true, error: null, ...emptyPortfolioState })
    try {
      const job = await backtestApi.resume(current.id)
      set({ job })
      watchJob(job, set, get)
    } catch (error) {
      set({ busy: false, error: error instanceof Error ? error.message : "Reprise impossible" })
    }
  },
  loadObservationsPage: async (offset) => {
    const job = get().job
    if (!job) return
    await loadObservationPage(job.id, offset, set, get)
  },
  loadPortfolioMetadata: async () => {
    const job = get().job
    if (!job) return
    await loadPortfolioMetadata(job.id, set, get)
  },
  loadPortfolioTradesPage: async (offset) => {
    const job = get().job
    if (!job || !get().portfolioMetadata) return
    await loadPortfolioTradesPage(job.id, offset, set, get)
  },
  loadPortfolioEquity: async () => {
    const job = get().job
    if (!job || !get().portfolioMetadata) return
    await loadPortfolioEquity(job.id, set, get)
  },
  reset: () => {
    closeSocket()
    set({
      job: null,
      observations: [],
      observationsTotal: 0,
      observationsOffset: 0,
      observationsLoading: false,
      observationsError: null,
      busy: false,
      error: null,
      ...emptyPortfolioState,
    })
  },
}))
