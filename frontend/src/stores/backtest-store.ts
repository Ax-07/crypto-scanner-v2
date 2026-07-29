import { create } from "zustand"

import { backtestApi, backtestJobSchema } from "@/api/backtests"
import type { BacktestConfig, BacktestJob, SignalObservation } from "@/types/backtest"

type State = {
  job: BacktestJob | null
  observations: SignalObservation[]
  observationsTotal: number
  observationsOffset: number
  observationsLoading: boolean
  observationsError: string | null
  busy: boolean
  error: string | null
  start: (config: BacktestConfig) => Promise<void>
  cancel: () => Promise<void>
  load: (id: string) => Promise<void>
  resume: () => Promise<void>
  loadObservationsPage: (offset: number) => Promise<void>
}

export const BACKTEST_OBSERVATION_PAGE_SIZE = 50

let socket: WebSocket | null = null
function closeSocket() {
  if (!socket) return
  socket.onmessage = null
  socket.close()
  socket = null
}

type StateSetter = (patch: Partial<State>) => void
type StateGetter = () => State

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
    closeSocket()
    await loadObservationPage(cancelled.id, 0, set, get)
  },
  load: async (id) => {
    closeSocket()
    set({
      busy: true,
      error: null,
      observations: [],
      observationsTotal: 0,
      observationsOffset: 0,
      observationsError: null,
    })
    try {
      const job = await backtestApi.get(id)
      const terminal = ["completed", "failed", "cancelled", "interrupted"].includes(job.status)
      set({ job, busy: !terminal })
      if (["completed", "cancelled"].includes(job.status)) {
        await loadObservationPage(job.id, 0, set, get)
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
    set({ busy: true, error: null })
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
}))
