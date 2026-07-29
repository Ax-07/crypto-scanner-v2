/**
 * Validation locale de ScanConfig et parsing des listes de périodes.
 * Le backend reste l'autorité finale du contrat.
 */
import { z } from "zod"
import { structuredSignalFiltersSchema } from "@/schemas/structured-signal-filters"

export const TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w"] as const
const periodList = z.array(z.number().int().min(2).max(1000)).min(1).refine((items) => new Set(items).size === items.length, "Les périodes doivent être uniques")

/** Contrat frontend de ScanConfig, aligné sur les contraintes utiles du modèle Pydantic. */
export const scanConfigSchema = z.object({
  exchange_id: z.string().trim().min(1).transform((value) => value.toLowerCase()),
  market_type: z.enum(["spot", "swap", "future"]),
  quote: z.string().trim().regex(/^[A-Za-z0-9]+$/, "Saisissez une devise valide").transform((value) => value.toUpperCase()),
  exclude_stable_pairs: z.boolean(),
  max_pairs: z.number().int().min(1).max(2000).nullable(),
  timeframe: z.enum(TIMEFRAMES),
  min_ohlcv_bars: z.number().int().min(60).max(1500),
  max_concurrency: z.number().int().min(1).max(20),
  max_retries: z.number().int().min(0).max(8),
  retry_delay_seconds: z.number().min(0.1).max(30),
  use_rsi: z.boolean(), rsi_period: z.number().int().min(2).max(100), rsi_threshold: z.number().min(0).max(100),
  use_ma: z.boolean(), use_sma: z.boolean(), use_ema: z.boolean(), sma_periods: periodList, ema_periods: periodList,
  ma_timeframes: z.array(z.enum(TIMEFRAMES)).min(1).refine((items) => new Set(items).size === items.length, "Les timeframes doivent être uniques"),
  min_trend_score: z.number().int().min(0).max(20),
  use_macd: z.boolean(), macd_fast_period: z.number().int().min(2).max(100), macd_slow_period: z.number().int().min(3).max(200), macd_signal_period: z.number().int().min(2).max(100),
  use_bollinger: z.boolean(), bollinger_period: z.number().int().min(2).max(200), bollinger_std_dev: z.number().gt(0).max(10),
  use_stochastic: z.boolean(), stochastic_k_period: z.number().int().min(2).max(200), stochastic_d_period: z.number().int().min(2).max(50), stochastic_oversold: z.number().min(0).max(100), stochastic_overbought: z.number().min(0).max(100),
  use_confluence_score: z.boolean(), min_confluence_score: z.number().min(0).max(100),
  confluence_weights: z.object({ rsi: z.number().nonnegative(), trend: z.number().nonnegative(), macd: z.number().nonnegative(), bollinger: z.number().nonnegative(), stochastic: z.number().nonnegative() }),
  filter_macd_signal: z.array(z.enum(["bullish", "bearish", "neutral"])).nullable(),
  filter_bb_position: z.array(z.enum(["oversold", "near_oversold", "neutral", "near_overbought", "overbought"])).nullable(),
  filter_stoch_signal: z.array(z.enum(["oversold", "overbought", "bullish_cross", "bearish_cross", "neutral"])).nullable(),
  structured_signal_filters: structuredSignalFiltersSchema.nullable().optional(),
}).superRefine((config, context) => {
  const issue = (path: Array<string | number>, message: string) => context.addIssue({ code: "custom", path, message })
  // Ces relations entre champs reflètent les refus Pydantic les plus utiles à anticiper.
  if (config.macd_fast_period >= config.macd_slow_period) issue(["macd_fast_period"], "La période rapide doit être inférieure à la période lente")
  if (config.stochastic_oversold >= config.stochastic_overbought) issue(["stochastic_oversold"], "Le seuil de survente doit être inférieur au seuil de surachat")
  if (config.use_ma && !config.use_sma && !config.use_ema) issue(["use_sma"], "Activez au moins SMA ou EMA")
  if (config.min_trend_score > config.ma_timeframes.length) issue(["min_trend_score"], "Le score ne peut pas dépasser le nombre de timeframes")
  const activeWeights = [config.use_rsi && config.confluence_weights.rsi, config.use_ma && config.confluence_weights.trend, config.use_macd && config.confluence_weights.macd, config.use_bollinger && config.confluence_weights.bollinger, config.use_stochastic && config.confluence_weights.stochastic]
  if (config.use_confluence_score && !activeWeights.some((weight) => Number(weight) > 0)) issue(["confluence_weights"], "Un indicateur actif doit avoir un poids positif")
})

/** Convertit une saisie « 20, 50 » en périodes uniques et triées, ou null si elle est invalide. */
export function parsePeriodList(value: string): number[] | null {
  const tokens = value.split(",").map((item) => item.trim())
  if (!tokens.length || tokens.some((item) => !/^\d+$/.test(item))) return null
  const numbers = tokens.map(Number)
  if (numbers.some((item) => item < 2 || item > 1000) || new Set(numbers).size !== numbers.length) return null
  return numbers.sort((a, b) => a - b)
}
