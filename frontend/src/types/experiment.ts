export type CandidateSpec = {
  id: string
  family: "baseline" | "trend" | "redundancy" | "weights" | "thresholds" | "bollinger" | "divergence" | "liquidity" | "regime" | "timeframe"
  description?: string
  weights?: Record<string, number>
  rsi_threshold?: number
  min_confluence_score?: number
  excluded_factors?: string[]
  group_scoring?: boolean
  trend_policy?: string
}

export type ExperimentManifest = {
  id: string
  status: "pending" | "running" | "completed" | "failed" | "cancelled" | "interrupted"
  dataset_version: string
  algorithm_version: string
  candidate_count: number
  total_trials: number
  splits: Array<{ name: string; start: string; end: string; observation_count: number }>
  results: Array<{
    candidate_id: string
    family: string
    rank: number | null
    eligible: boolean
    rejection_reasons: string[]
    metrics: Record<string, Record<string, unknown>>
    walk_forward: Array<Record<string, unknown>>
    sensitivity: Record<string, unknown>
    oos_metrics: Record<string, unknown>
    final_test_metrics: Record<string, unknown>
    adjusted_p_value: number | null
    selection_reason: string | null
    selected: boolean
  }>
  warnings: string[]
  error: string | null
}

export type SignalProfile = {
  id: string
  name: string
  version: string
  status: "draft" | "candidate" | "shadow" | "production" | "retired"
  content_hash: string
  experiment_id: string | null
  dataset_version: string
  description: string
}

export type ShadowSummary = {
  total: number
  sampled: number
  divergent: number
  agreement_rate: number | null
  reasons: Record<string, number>
  future_outcomes_available: number
}
