import { z } from "zod"

import { API_URL, apiRequest } from "@/api/client"
import { indicatorSignalsSchema } from "@/schemas/indicator-signals"
import type { BacktestConfig, BacktestJob, SignalObservation } from "@/types/backtest"

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
})
export const backtestJobSchema = z.object({
  id: z.string(), status: z.enum(["pending", "running", "completed", "failed", "cancelled", "interrupted"]),
  config: z.unknown(), progress: progressSchema, summary: summarySchema.nullable(),
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
