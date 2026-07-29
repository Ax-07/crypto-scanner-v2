/**
 * État global et orchestration du job scanner.
 * L'état temporaire de saisie reste dans React Hook Form et les sockets restent hors Zustand.
 */
import { create } from "zustand"

import { scannerApi, scannerJobMessageSchema } from "@/api/scanner"
import type { ScanConfig, ScanJob, ScanResult } from "@/types/scanner"

type ScannerUiStatus = "idle" | "loading-config" | "starting" | "running" | "cancelling" | "completed" | "failed"

type ScannerState = {
  config: ScanConfig | null
  job: ScanJob | null
  results: ScanResult[]
  status: ScannerUiStatus
  error: string | null
  loadConfig: (signal?: AbortSignal) => Promise<void>
  startScan: (config?: ScanConfig) => Promise<void>
  cancelScan: () => Promise<void>
}

let scanSocket: WebSocket | null = null
let configRequest: Promise<void> | null = null

/** Ferme le flux courant et neutralise ses callbacks avant de libérer sa référence. */
function closeScanSocket() {
  if (!scanSocket) return
  scanSocket.onmessage = null
  scanSocket.onerror = null
  scanSocket.onclose = null
  scanSocket.close()
  scanSocket = null
}

/**
 * État durable du workspace scanner.
 * La socket reste privée au module afin de ne jamais entrer dans l'état Zustand.
 */
export const useScannerStore = create<ScannerState>()((set, get) => ({
  config: null,
  job: null,
  results: [],
  status: "idle",
  error: null,

  /** Charge et déduplique la configuration par défaut du backend. */
  loadConfig: async (signal) => {
    // La promesse partagée déduplique notamment le double effet de React Strict Mode.
    if (get().config || configRequest) return configRequest ?? Promise.resolve()
    set({ status: "loading-config", error: null })
    configRequest = scannerApi.getDefaultConfig(signal)
      .then((config) => set({ config, status: "idle" }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return
        set({ error: error instanceof Error ? error.message : "Configuration indisponible", status: "failed" })
      })
      .finally(() => { configRequest = null })
    return configRequest
  },

  /** Démarre un job avec un snapshot validé après fermeture de l'ancien flux. */
  startScan: async (candidate) => {
    const config = candidate ?? get().config
    if (!config) return
    closeScanSocket()
    set({ config, status: "starting", error: null, results: [] })
    try {
      const job = await scannerApi.start(config)
      set({ job, status: "running" })
      const socket = new WebSocket(scannerApi.websocketUrl(job.id))
      scanSocket = socket

      socket.onmessage = async (event) => {
        // Une ancienne socket ne peut pas publier dans le job qui l'a remplacée.
        if (scanSocket !== socket) return
        try {
          const parsed = scannerJobMessageSchema.safeParse(JSON.parse(String(event.data)))
          if (!parsed.success) {
            set({ error: "Message de progression invalide", status: "failed" })
            return
          }
          const nextJob = parsed.data as ScanJob
          if (nextJob.id !== job.id) return
          set({ job: nextJob, status: nextJob.status === "failed" ? "failed" : nextJob.status === "completed" || nextJob.status === "cancelled" ? "completed" : "running" })
          if (nextJob.status === "completed" || nextJob.status === "cancelled") {
            // Les messages de progression n'embarquent pas les résultats volumineux.
            const completed = await scannerApi.results(nextJob.id)
            if (scanSocket !== socket) return
            set({ job: completed, results: completed.results ?? [], status: "completed" })
            closeScanSocket()
          } else if (nextJob.status === "failed") {
            set({ error: nextJob.error ?? "Le scan a échoué", status: "failed" })
            closeScanSocket()
          }
        } catch (error) {
          if (scanSocket === socket) set({ error: error instanceof Error ? error.message : "Message de progression invalide", status: "failed" })
        }
      }
      socket.onerror = () => {
        if (scanSocket === socket) set({ error: "Connexion de progression interrompue" })
      }
      socket.onclose = () => {
        if (scanSocket === socket) scanSocket = null
      }
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Impossible de démarrer le scan", status: "failed" })
      throw error
    }
  },

  /** Demande l'annulation du job courant sans anticiper son résultat terminal. */
  cancelScan: async () => {
    const job = get().job
    if (!job) return
    set({ status: "cancelling", error: null })
    try {
      const updated = await scannerApi.cancel(job.id)
      set({ job: updated, status: updated.status === "cancelled" ? "completed" : "running" })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "Impossible d’annuler le scan", status: "failed" })
    }
  },
}))
