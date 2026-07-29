import { describe, expect, it } from "vitest"
import { parsePeriodList, scanConfigSchema } from "@/features/scanner/scan-config-schema"
import type { ScanConfig } from "@/types/scanner"

const valid: ScanConfig = {
  exchange_id: "binance", market_type: "spot", quote: "USDC", exclude_stable_pairs: true, max_pairs: null,
  timeframe: "4h", min_ohlcv_bars: 200, max_concurrency: 6, max_retries: 3, retry_delay_seconds: 1.5,
  use_rsi: true, rsi_period: 14, rsi_threshold: 35,
  use_ma: true, use_sma: true, use_ema: true, sma_periods: [20, 50], ema_periods: [20, 50], ma_timeframes: ["1w", "1d", "4h"], min_trend_score: 2,
  use_macd: true, macd_fast_period: 12, macd_slow_period: 26, macd_signal_period: 9,
  use_bollinger: true, bollinger_period: 20, bollinger_std_dev: 2,
  use_stochastic: true, stochastic_k_period: 14, stochastic_d_period: 3, stochastic_oversold: 20, stochastic_overbought: 80,
  use_confluence_score: true, min_confluence_score: 60, confluence_weights: { rsi: 20, trend: 25, macd: 20, bollinger: 20, stochastic: 15 },
  filter_macd_signal: null, filter_bb_position: null, filter_stoch_signal: null,
}

describe("scanConfigSchema", () => {
  it("accepte et normalise une configuration valide", () => expect(scanConfigSchema.parse({ ...valid, quote: " usdc " }).quote).toBe("USDC"))
  it("refuse une période MACD rapide supérieure à la lente", () => expect(scanConfigSchema.safeParse({ ...valid, macd_fast_period: 30 }).success).toBe(false))
  it("refuse des seuils stochastiques inversés", () => expect(scanConfigSchema.safeParse({ ...valid, stochastic_oversold: 90 }).success).toBe(false))
  it("impose SMA ou EMA lorsque les moyennes sont actives", () => expect(scanConfigSchema.safeParse({ ...valid, use_sma: false, use_ema: false }).success).toBe(false))
  it("limite le score de tendance aux timeframes", () => expect(scanConfigSchema.safeParse({ ...valid, min_trend_score: 4 }).success).toBe(false))
  it("impose un poids positif actif pour la confluence", () => expect(scanConfigSchema.safeParse({ ...valid, confluence_weights: { rsi: 0, trend: 0, macd: 0, bollinger: 0, stochastic: 0 } }).success).toBe(false))
  it("accepte une ancienne configuration sans contrat structuré", () => expect(scanConfigSchema.safeParse(valid).success).toBe(true))
  it("accepte la coexistence ancien/nouveau", () => expect(scanConfigSchema.safeParse({
    ...valid,
    filter_macd_signal: ["bearish"],
    structured_signal_filters: {
      version: 1,
      indicators: {
        macd: { match: "all", conditions: [{ field: "direction", values: ["bullish"] }] },
      },
    },
  }).success).toBe(true))
  it("rejette une version structurée inconnue", () => expect(scanConfigSchema.safeParse({
    ...valid,
    structured_signal_filters: { version: 2, indicators: {} },
  }).success).toBe(false))
})

describe("parsePeriodList", () => {
  it("trie les périodes valides", () => expect(parsePeriodList("50, 20, 100")).toEqual([20, 50, 100]))
  it("refuse les doublons et les fragments invalides", () => { expect(parsePeriodList("20,20")).toBeNull(); expect(parsePeriodList("20, x")).toBeNull() })
})
