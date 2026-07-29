import { z } from "zod"

import { API_URL, apiRequest } from "@/api/client"
import { indicatorSignalsSchema } from "@/schemas/indicator-signals"
import { structuredSignalFiltersSchema } from "@/schemas/structured-signal-filters"
import type { MarketType, ScanConfig, ScanJob } from "@/types/scanner"

/**
 * Cette frontière est volontairement additive : les champs historiques du
 * résultat sont préservés, mais le nouveau contrat public est validé.
 */
export const scanResultSchema = z.object({
  indicator_signals: indicatorSignalsSchema.optional(),
}).passthrough()

export const scannerConfigEnvelopeSchema = z.object({
  structured_signal_filters: structuredSignalFiltersSchema.nullable().optional(),
}).passthrough()

/** Contrat runtime des snapshots diffusés par le WebSocket scanner. */
export const scannerJobMessageSchema = z.object({
  id: z.string().min(1),
  status: z.enum(["pending", "running", "completed", "failed", "cancelled"]),
  config: scannerConfigEnvelopeSchema,
  progress: z.object({
    processed: z.number().int().nonnegative(),
    total: z.number().int().nonnegative(),
    successful: z.number().int().nonnegative(),
    filtered: z.number().int().nonnegative(),
    errors: z.number().int().nonnegative(),
    percent: z.number().min(0).max(100),
  }),
  result_count: z.number().int().nonnegative().optional(),
  error: z.string().nullable().optional(),
  created_at: z.string().optional(),
  started_at: z.string().nullable().optional(),
  completed_at: z.string().nullable().optional(),
  results: z.array(scanResultSchema).optional(),
}).passthrough()

export function parseScannerJob(payload: unknown): ScanJob {
  return scannerJobMessageSchema.parse(payload) as ScanJob
}

export const scannerApi = {
  /** Charge la configuration scanner calculée par le backend. */
  getDefaultConfig: (signal?: AbortSignal) =>
    apiRequest<unknown>("/api/scanner/config", { signal })
      .then((payload) => scannerConfigEnvelopeSchema.parse(payload) as ScanConfig),
  /** Crée un job avec une configuration déjà validée côté formulaire. */
  start: (config: ScanConfig) =>
    apiRequest<unknown>("/api/scanner/jobs", {
      method: "POST",
      body: JSON.stringify(config),
    }).then(parseScannerJob),
  /** Récupère le snapshot terminal accompagné de ses résultats. */
  results: (jobId: string) =>
    apiRequest<unknown>(`/api/scanner/jobs/${jobId}/results`).then(parseScannerJob),
  /** Demande l'annulation coopérative d'un job. */
  cancel: (jobId: string) =>
    apiRequest<unknown>(`/api/scanner/jobs/${jobId}`, { method: "DELETE" }).then(parseScannerJob),
  /** Produit une URL navigable directement pour le téléchargement CSV. */
  exportUrl: (jobId: string) => `${API_URL}/api/scanner/jobs/${jobId}/export.csv`,
  /** Dérive l'origine WS/WSS de l'origine HTTP configurée. */
  websocketUrl: (jobId: string) => {
    const url = new URL(API_URL)
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
    url.pathname = `/api/scanner/ws/${jobId}`
    return url.toString()
  },
  /** Liste les paires disponibles pour la quote et le type de marché demandés. */
  getMarkets: (quote = "USDC", marketType: MarketType = "spot", signal?: AbortSignal) =>
    apiRequest<string[]>(`/api/scanner/markets?${new URLSearchParams({ quote, market_type: marketType })}`, { signal }),
}
