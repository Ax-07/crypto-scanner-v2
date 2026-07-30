import { z } from "zod"

import type { MarketIndicatorConfig } from "@/types/market"
import type { ScanConfig } from "@/types/scanner"
import {
  adxConfigSchema,
  atrConfigSchema,
  donchianConfigSchema,
  keltnerConfigSchema,
  supertrendConfigSchema,
} from "@/features/scanner/scan-config-schema"

export const marketProfileSchema = z.object({
  rsi_period: z.number().int().min(2).max(100),
  rsi_threshold: z.number().min(0).max(100),
  use_rsi: z.boolean(),
  use_ma: z.boolean(),
  use_sma: z.boolean(),
  use_ema: z.boolean(),
  sma_periods: z.array(z.number().int().min(2).max(1000)).min(1),
  ema_periods: z.array(z.number().int().min(2).max(1000)).min(1),
  macd_fast_period: z.number().int().min(2).max(100),
  macd_slow_period: z.number().int().min(3).max(200),
  macd_signal_period: z.number().int().min(2).max(100),
  use_macd: z.boolean(),
  bollinger_period: z.number().int().min(2).max(200),
  bollinger_std_dev: z.number().positive().max(10),
  use_bollinger: z.boolean(),
  stochastic_k_period: z.number().int().min(2).max(200),
  stochastic_d_period: z.number().int().min(2).max(50),
  stochastic_oversold: z.number().min(0).max(100),
  stochastic_overbought: z.number().min(0).max(100),
  use_stochastic: z.boolean(),
  atr: atrConfigSchema.nullable().optional(),
  adx: adxConfigSchema.nullable().optional(),
  supertrend: supertrendConfigSchema.nullable().optional(),
  donchian: donchianConfigSchema.nullable().optional(),
  keltner: keltnerConfigSchema.nullable().optional(),
  use_confluence_score: z.boolean(),
  confluence_weights: z.record(z.string(), z.number().nonnegative()),
  origin: z.enum(["default", "scan", "custom"]),
}).superRefine((profile, context) => {
  if (profile.macd_fast_period >= profile.macd_slow_period) {
    context.addIssue({ code: "custom", path: ["macd_fast_period"], message: "MACD rapide doit être inférieur au lent" })
  }
  if (profile.stochastic_oversold >= profile.stochastic_overbought) {
    context.addIssue({ code: "custom", path: ["stochastic_oversold"], message: "Seuils stochastiques incohérents" })
  }
})

export const DEFAULT_MARKET_PROFILE: MarketIndicatorConfig = {
  rsi_period: 14, rsi_threshold: 35, use_rsi: true,
  use_ma: true, use_sma: true, use_ema: true, sma_periods: [20, 50], ema_periods: [20, 50],
  macd_fast_period: 12, macd_slow_period: 26, macd_signal_period: 9, use_macd: true,
  bollinger_period: 20, bollinger_std_dev: 2, use_bollinger: true,
  stochastic_k_period: 14, stochastic_d_period: 3,
  stochastic_oversold: 20, stochastic_overbought: 80, use_stochastic: true,
  use_confluence_score: true,
  confluence_weights: { rsi: 20, trend: 25, macd: 20, bollinger: 20, stochastic: 15 },
  origin: "default",
}

export function marketProfileFromScan(config: ScanConfig): MarketIndicatorConfig {
  const scanValues = {
    rsi_period: config.rsi_period,
    rsi_threshold: config.rsi_threshold,
    use_rsi: config.use_rsi,
    use_ma: config.use_ma,
    use_sma: config.use_sma,
    use_ema: config.use_ema,
    sma_periods: config.sma_periods,
    ema_periods: config.ema_periods,
    macd_fast_period: config.macd_fast_period,
    macd_slow_period: config.macd_slow_period,
    macd_signal_period: config.macd_signal_period,
    use_macd: config.use_macd,
    bollinger_period: config.bollinger_period,
    bollinger_std_dev: config.bollinger_std_dev,
    use_bollinger: config.use_bollinger,
    stochastic_k_period: config.stochastic_k_period,
    stochastic_d_period: config.stochastic_d_period,
    stochastic_oversold: config.stochastic_oversold,
    stochastic_overbought: config.stochastic_overbought,
    use_stochastic: config.use_stochastic,
    atr: config.atr,
    adx: config.adx,
    supertrend: config.supertrend,
    donchian: config.donchian,
    keltner: config.keltner,
    use_confluence_score: config.use_confluence_score,
    confluence_weights: config.confluence_weights,
    origin: "scan",
  }
  return marketProfileSchema.parse({
    ...DEFAULT_MARKET_PROFILE,
    ...Object.fromEntries(
      Object.entries(scanValues).filter(([, value]) => value !== undefined),
    ),
    origin: "scan",
  })
}

export function serializeMarketProfile(profile: MarketIndicatorConfig) {
  return JSON.stringify(profile)
}

export function parseMarketProfile(value: string | null): MarketIndicatorConfig {
  if (!value) return DEFAULT_MARKET_PROFILE
  try {
    return marketProfileSchema.parse(JSON.parse(value))
  } catch {
    return DEFAULT_MARKET_PROFILE
  }
}
