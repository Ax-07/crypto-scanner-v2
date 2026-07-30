import { z } from "zod"

import { API_URL, ApiError, apiRequest } from "@/api/client"
import { indicatorSignalsSchema } from "@/schemas/indicator-signals"
import {
  portfolioEquityPageSchema,
  portfolioRunMetadataSchema,
  portfolioSimulationConfigSchema,
  portfolioSimulationPublicResultSchema,
  portfolioTradePageSchema,
} from "@/schemas/portfolio"
import type { BacktestConfig, BacktestJob, SignalObservation } from "@/types/backtest"
import type {
  PortfolioEquityPage,
  PortfolioRunMetadata,
  PortfolioTradePage,
} from "@/types/portfolio"

const progressSchema = z.object({
  processed: z.number(), total: z.number(), observations: z.number(),
  current_symbol: z.string().nullable(), phase: z.string(), percent: z.number(),
})
const summarySchema = z.object({
  observation_count: z.number(), accepted_count: z.number(), rejected_count: z.number(),
  censored_count: z.number(), warnings: z.array(z.string()),
  horizons: z.record(z.string(), z.record(z.string(), z.unknown())),
  segments: z.record(z.string(), z.unknown()), filter_funnel: z.array(z.object({
    stage: z.string(), input: z.number(), passed: z.number(), rejected: z.number(),
  })), provisional_supported: z.boolean(), trade_simulation_included: z.boolean(),
  portfolio_simulation: portfolioSimulationPublicResultSchema.optional(),
})
const configSchema = z.object({
  portfolio_simulation: portfolioSimulationConfigSchema.optional(),
}).passthrough()
export const backtestJobSchema = z.object({
  id: z.string(), status: z.enum(["pending", "running", "completed", "failed", "cancelled", "interrupted"]),
  config: configSchema, progress: progressSchema, summary: summarySchema.nullable(),
  correlations: z.record(z.string(), z.unknown()).nullable(),
  ablations: z.record(z.string(), z.unknown()).nullable(),
  warnings: z.array(z.string()), error: z.string().nullable(),
  created_at: z.string(), started_at: z.string().nullable(), completed_at: z.string().nullable(),
  dataset_version: z.string().default("unknown"),
  algorithm_version: z.string().default("signal-evaluation-v2"),
  checkpoint: z.record(z.string(), z.unknown()).nullable().default(null),
})

function parseJob(payload: unknown): BacktestJob {
  return backtestJobSchema.parse(payload) as BacktestJob
}

/**
 * Les champs historiques sont conservés pendant que le contrat structuré
 * additif est validé strictement.
 */
export const signalObservationSchema = z.object({
  indicator_signals: indicatorSignalsSchema.optional(),
}).passthrough()

export const signalObservationPageSchema = z.object({
  items: z.array(signalObservationSchema),
  total: z.number().int().nonnegative(),
}).passthrough()

export function parseSignalObservationPage(
  payload: unknown,
): { items: SignalObservation[]; total: number } {
  return signalObservationPageSchema.parse(payload) as {
    items: SignalObservation[]
    total: number
  }
}

export async function getPortfolioEquity(
  id: string,
  options: { mode?: "raw" | "sampled"; offset?: number; limit?: number; maxPoints?: number } = {},
): Promise<PortfolioEquityPage> {
  const params = new URLSearchParams()
  if (options.mode) params.set("mode", options.mode)
  if (options.mode === "sampled") {
    params.set("max_points", String(options.maxPoints ?? 1000))
  } else {
    params.set("offset", String(options.offset ?? 0))
    params.set("limit", String(options.limit ?? 100))
  }
  return portfolioEquityPageSchema.parse(
    await apiRequest<unknown>(`/api/backtests/${id}/equity?${params}`),
  )
}

export const backtestApi = {
  async start(config: BacktestConfig): Promise<BacktestJob> {
    return parseJob(await apiRequest<unknown>("/api/backtests", {
      method: "POST", body: JSON.stringify(config),
    }))
  },
  async get(id: string): Promise<BacktestJob> {
    return parseJob(await apiRequest<unknown>(`/api/backtests/${id}`))
  },
  async list(offset = 0, limit = 20): Promise<{ items: BacktestJob[]; total: number }> {
    const payload = await apiRequest<{ items: unknown[]; total: number }>(
      `/api/backtests?offset=${offset}&limit=${limit}`,
    )
    return { items: payload.items.map(parseJob), total: payload.total }
  },
  async resume(id: string): Promise<BacktestJob> {
    return parseJob(await apiRequest<unknown>(`/api/backtests/${id}/resume`, { method: "POST" }))
  },
  async cancel(id: string): Promise<BacktestJob> {
    return parseJob(await apiRequest<unknown>(`/api/backtests/${id}`, { method: "DELETE" }))
  },
  async observations(
    id: string,
    offset = 0,
    limit = 50,
  ): Promise<{ items: SignalObservation[]; total: number }> {
    return parseSignalObservationPage(
      await apiRequest<unknown>(
        `/api/backtests/${id}/observations?offset=${offset}&limit=${limit}`,
      ),
    )
  },
  async portfolio(id: string): Promise<PortfolioRunMetadata> {
    return portfolioRunMetadataSchema.parse(
      await apiRequest<unknown>(`/api/backtests/${id}/portfolio`),
    )
  },
  async trades(id: string, offset = 0, limit = 50): Promise<PortfolioTradePage> {
    return portfolioTradePageSchema.parse(
      await apiRequest<unknown>(
        `/api/backtests/${id}/trades?offset=${offset}&limit=${limit}`,
      ),
    )
  },
  equity: getPortfolioEquity,
  async downloadPortfolioExport(id: string, dataset: "trades" | "equity"): Promise<void> {
    const response = await fetch(
      `${API_URL}/api/backtests/${id}/${dataset}/export.csv`,
    )
    if (!response.ok) {
      const payload: unknown = await response.json().catch(() => null)
      const detail = payload && typeof payload === "object" && "detail" in payload
        ? payload.detail
        : null
      const message = detail && typeof detail === "object" && "message" in detail
        && typeof detail.message === "string"
        ? detail.message
        : `Export ${dataset} impossible`
      throw new ApiError(message, response.status)
    }
    const blob = await response.blob()
    const disposition = response.headers.get("Content-Disposition") ?? ""
    const match = /filename="?([^";]+)"?/i.exec(disposition)
    const filename = match?.[1] ?? `${id}-${dataset}-v1.csv`
    const url = URL.createObjectURL(blob)
    try {
      const anchor = document.createElement("a")
      anchor.href = url
      anchor.download = filename
      anchor.click()
    } finally {
      URL.revokeObjectURL(url)
    }
  },
  websocketUrl(id: string): string {
    const url = new URL(API_URL)
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
    url.pathname = `/api/backtests/${id}/ws`
    return url.toString()
  },
  exportUrl(id: string, dataset: string): string {
    return `${API_URL}/api/backtests/${id}/export.csv?dataset=${dataset}`
  },
  summaryUrl(id: string): string {
    return `${API_URL}/api/backtests/${id}/summary.json`
  },
}

export function portfolioErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return error instanceof Error ? error.message : "Détails du portefeuille indisponibles."
  }
  const messages: Record<string, string> = {
    portfolio_not_requested: "Ce backtest ne contient aucune simulation de portefeuille.",
    portfolio_job_not_completed: "La simulation sera disponible lorsque le backtest sera terminé.",
    portfolio_details_legacy_unavailable:
      "Le résumé est disponible, mais les détails de cette ancienne simulation n’ont pas été persistés.",
    portfolio_details_unavailable:
      "Les détails de la simulation sont actuellement indisponibles.",
    invalid_pagination: "La page demandée est invalide.",
  }
  return (error.code && messages[error.code]) || error.message
}
