import { z } from "zod"

const localizedUnsignedDecimal = z.string().trim().regex(
  /^(?:0|[1-9]\d*)(?:[.,]\d+)?$/,
  "Saisissez un nombre positif sans notation exponentielle",
)

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
  portfolio_simulation_enabled: z.boolean().default(false),
  portfolio_simulation: z.object({
    quote_asset: z.string(),
    initial_capital: localizedUnsignedDecimal,
    position_size_percent: localizedUnsignedDecimal,
    fee_percent: localizedUnsignedDecimal,
    slippage_percent: localizedUnsignedDecimal,
  }).default({
    quote_asset: "USDC",
    initial_capital: "10000",
    position_size_percent: "100",
    fee_percent: "0,1",
    slippage_percent: "0",
  }),
}).superRefine((value, context) => {
  if (new Date(value.start) >= new Date(value.end)) {
    context.addIssue({ code: "custom", path: ["end"], message: "La fin doit suivre le début" })
  }
  if (!value.portfolio_simulation_enabled) return
  const decimal = (input: string) => Number(input.trim().replace(",", "."))
  if (!value.portfolio_simulation.quote_asset.trim()) {
    context.addIssue({
      code: "custom",
      path: ["portfolio_simulation", "quote_asset"],
      message: "L’actif de cotation est requis.",
    })
  }
  if (decimal(value.portfolio_simulation.initial_capital) <= 0) {
    context.addIssue({
      code: "custom",
      path: ["portfolio_simulation", "initial_capital"],
      message: "Le capital initial doit être supérieur à zéro.",
    })
  }
  const sizing = decimal(value.portfolio_simulation.position_size_percent)
  if (sizing <= 0 || sizing > 100) {
    context.addIssue({
      code: "custom",
      path: ["portfolio_simulation", "position_size_percent"],
      message: "La taille de position doit être comprise entre 0 et 100 %.",
    })
  }
  for (const [field, label] of [
    ["fee_percent", "Les frais"],
    ["slippage_percent", "Le slippage"],
  ] as const) {
    const rate = decimal(value.portfolio_simulation[field])
    if (rate < 0 || rate >= 100) {
      context.addIssue({
        code: "custom",
        path: ["portfolio_simulation", field],
        message: `${label} doivent être compris entre 0 et 100 % exclus.`,
      })
    }
  }
  const symbols = value.symbols.split(",").map((item) => item.trim()).filter(Boolean)
  if (symbols.length !== 1) {
    context.addIssue({
      code: "custom",
      path: ["symbols"],
      message: "La simulation de portefeuille exige exactement un symbole.",
    })
  }
  if (value.replay_mode !== "every_bar") {
    context.addIssue({
      code: "custom",
      path: ["replay_mode"],
      message: "La simulation exige le mode every_bar.",
    })
  }
})

export type BacktestFormValues = z.infer<typeof backtestFormSchema>

export function parseHorizons(value: string): number[] {
  return [...new Set(value.split(",").map(Number))].sort((left, right) => left - right)
}
