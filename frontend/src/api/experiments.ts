import { z } from "zod"

import { API_URL, apiRequest } from "@/api/client"
import type { CandidateSpec, ExperimentManifest, ShadowSummary, SignalProfile } from "@/types/experiment"

const manifestSchema = z.object({
  id: z.string(),
  status: z.enum(["pending", "running", "completed", "failed", "cancelled", "interrupted"]),
  dataset_version: z.string(), algorithm_version: z.string(),
  candidate_count: z.number(), total_trials: z.number(),
  splits: z.array(z.object({
    name: z.string(), start: z.string(), end: z.string(), observation_count: z.number(),
  })),
  results: z.array(z.object({
    candidate_id: z.string(), family: z.string(), rank: z.number().nullable(),
    eligible: z.boolean(), rejection_reasons: z.array(z.string()),
    metrics: z.record(z.string(), z.record(z.string(), z.unknown())),
    walk_forward: z.array(z.record(z.string(), z.unknown())),
    sensitivity: z.record(z.string(), z.unknown()),
    oos_metrics: z.record(z.string(), z.unknown()).default({}),
    final_test_metrics: z.record(z.string(), z.unknown()).default({}),
    adjusted_p_value: z.number().nullable().default(null),
    selection_reason: z.string().nullable().default(null),
    selected: z.boolean(),
  })),
  warnings: z.array(z.string()), error: z.string().nullable(),
}).passthrough()

export const experimentApi = {
  async start(payload: {
    source_backtest_id: string
    candidates: CandidateSpec[]
    selection_horizon: number
    split: { embargo_bars: number }
    minimum_global: number
  }): Promise<ExperimentManifest> {
    return manifestSchema.parse(await apiRequest("/api/experiments/jobs", {
      method: "POST", body: JSON.stringify(payload),
    })) as ExperimentManifest
  },
  async get(id: string): Promise<ExperimentManifest> {
    return manifestSchema.parse(await apiRequest(`/api/experiments/jobs/${id}`)) as ExperimentManifest
  },
  async cancel(id: string): Promise<void> {
    await apiRequest(`/api/experiments/jobs/${id}`, { method: "DELETE" })
  },
  async profiles(): Promise<SignalProfile[]> {
    return apiRequest<SignalProfile[]>("/api/signal-profiles")
  },
  async enableShadow(id: string, comment: string): Promise<void> {
    await apiRequest(`/api/signal-profiles/${id}/shadow`, {
      method: "POST", body: JSON.stringify({ comment, confirm: true }),
    })
  },
  async promote(id: string, experimentId: string, comment: string): Promise<void> {
    await apiRequest(`/api/signal-profiles/${id}/promote`, {
      method: "POST", body: JSON.stringify({ experiment_id: experimentId, comment, confirm: true }),
    })
  },
  async shadowSummary(): Promise<ShadowSummary> {
    return apiRequest<ShadowSummary>("/api/shadow/summary")
  },
  exportUrl(id: string, dataset: string): string {
    return `${API_URL}/api/experiments/jobs/${id}/export?dataset=${dataset}`
  },
}
