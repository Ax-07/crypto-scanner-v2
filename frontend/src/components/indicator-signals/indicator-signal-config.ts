import type { IndicatorName } from "@/types/indicator-signals"

export interface IndicatorDisplayConfig {
  label: string
  description: string
}

export const INDICATOR_ORDER = [
  "rsi",
  "sma",
  "ema",
  "macd",
  "bollinger",
  "stochastic",
] as const satisfies readonly IndicatorName[]

export const INDICATOR_CONFIG: Record<IndicatorName, IndicatorDisplayConfig> = {
  rsi: {
    label: "RSI",
    description: "Indice de force relative",
  },
  sma: {
    label: "SMA",
    description: "Moyenne mobile simple",
  },
  ema: {
    label: "EMA",
    description: "Moyenne mobile exponentielle",
  },
  macd: {
    label: "MACD",
    description: "Convergence et divergence des moyennes mobiles",
  },
  bollinger: {
    label: "Bollinger",
    description: "Bandes de volatilité de Bollinger",
  },
  stochastic: {
    label: "Stochastique",
    description: "Oscillateur stochastique",
  },
}

export const INDICATOR_LABELS: Record<IndicatorName, string> = Object.fromEntries(
  INDICATOR_ORDER.map((indicator) => [indicator, INDICATOR_CONFIG[indicator].label]),
) as Record<IndicatorName, string>
