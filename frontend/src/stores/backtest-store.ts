import { create } from "zustand"

import { backtestApi, backtestJobSchema } from "@/api/backtests"
import type { BacktestConfig, BacktestJob, SignalObservation } from "@/types/backtest"

type State = {
  job: BacktestJob | null
  observations: SignalObservation[]
  busy: boolean
  error: string | null
  start: (config: BacktestConfig) => Promise<void>
  cancel: () => Promise<void>
  load: (id: string) => Promise<void>
  resume: () => Promise<void>
}

let socket: WebSocket | null = null
function closeSocket() {
  if (!socket) return
  socket.onmessage = null
  socket.close()
  socket = null
}

function watchJob(job: BacktestJob, set: (patch: Partial<State>) => void) {
  const current = new WebSocket(backtestApi.websocketUrl(job.id))
  socket = current
  current.onmessage = async (event) => {
    if (socket !== current) return
    try {
      const next = backtestJobSchema.parse(JSON.parse(String(event.data))) as BacktestJob
      const terminal = ["completed", "failed", "cancelled", "interrupted"].includes(next.status)
      set({ job: next, busy: !terminal, error: next.error })
      if (["completed", "cancelled"].includes(next.status)) {
        const page = await backtestApi.observations(next.id)
        if (socket === current) set({ observations: page.items })
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
  job: null, observations: [], busy: false, error: null,
  start: async (config) => {
    closeSocket()
    set({ busy: true, error: null, observations: [] })
    try {
      const job = await backtestApi.start(config)
      set({ job })
      watchJob(job, set)
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
  },
  load: async (id) => {
    closeSocket()
    set({ busy: true, error: null, observations: [] })
    try {
      const job = await backtestApi.get(id)
      const terminal = ["completed", "failed", "cancelled", "interrupted"].includes(job.status)
      const page = job.status === "completed"
        ? await backtestApi.observations(job.id)
        : { items: [] as SignalObservation[] }
      set({ job, observations: page.items, busy: !terminal })
      if (!terminal) watchJob(job, set)
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
      watchJob(job, set)
    } catch (error) {
      set({ busy: false, error: error instanceof Error ? error.message : "Reprise impossible" })
    }
  },
}))
