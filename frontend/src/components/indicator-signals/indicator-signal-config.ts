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
  "atr",
  "adx",
  "supertrend",
  "donchian",
  "keltner",
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
  atr: {
    label: "ATR / NATR",
    description: "Amplitude et évolution de la volatilité",
  },
  adx: {
    label: "ADX / DMI",
    description: "Direction et intensité de la tendance",
  },
  supertrend: {
    label: "Supertrend",
    description: "Régime directionnel fondé sur l'ATR",
  },
  donchian: {
    label: "Canaux de Donchian",
    description: "Bornes roulantes et cassures causales",
  },
  keltner: {
    label: "Canaux de Keltner",
    description: "Canal de volatilité fondé sur EMA et ATR",
  },
}

export const INDICATOR_LABELS: Record<IndicatorName, string> = Object.fromEntries(
  INDICATOR_ORDER.map((indicator) => [indicator, INDICATOR_CONFIG[indicator].label]),
) as Record<IndicatorName, string>
