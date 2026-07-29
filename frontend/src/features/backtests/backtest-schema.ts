import { z } from "zod"

export const backtestFormSchema = z.object({
  symbols: z.string().trim().min(1, "Ajoutez au moins un symbole"),
  start: z.string().min(1, "Date de début requise"),
  end: z.string().min(1, "Date de fin requise"),
  timeframe: z.enum(["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w"]),
  horizons: z.string().regex(/^\s*\d+(\s*,\s*\d+)*\s*$/, "Exemple : 1, 3, 6, 12"),
  replay_mode: z.enum(["every_bar", "state_changes", "filtered_signals"]),
  entry_policy: z.enum(["signal_close", "next_open"]),
  gap_policy: z.enum(["reject_range", "skip_affected", "allow_with_warning"]),
  fee_bps: z.number().min(0).max(1000),
  slippage_bps: z.number().min(0).max(1000),
  use_rsi: z.boolean(),
  rsi_threshold: z.number().min(0).max(100),
  use_ma: z.boolean(),
  min_trend_score: z.number().int().min(0).max(20),
  use_confluence_score: z.boolean(),
  min_confluence_score: z.number().min(0).max(100),
}).superRefine((value, context) => {
  if (new Date(value.start) >= new Date(value.end)) {
    context.addIssue({ code: "custom", path: ["end"], message: "La fin doit suivre le début" })
  }
})

export type BacktestFormValues = z.infer<typeof backtestFormSchema>

export function parseHorizons(value: string): number[] {
  return [...new Set(value.split(",").map(Number))].sort((left, right) => left - right)
}
