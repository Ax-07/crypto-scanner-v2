import type {
  IndicatorName,
  IndicatorSignalDirection,
  IndicatorSignalStatus,
} from "@/types/indicator-signals"

export const INDICATOR_STATUS_LABELS: Record<IndicatorSignalStatus, string> = {
  available: "Disponible",
  insufficient_data: "Données insuffisantes",
  invalid_data: "Données invalides",
  disabled: "Désactivé",
}

export const INDICATOR_DIRECTION_LABELS: Record<IndicatorSignalDirection, string> = {
  bullish: "Haussier",
  bearish: "Baissier",
  neutral: "Neutre",
}

const TECHNICAL_LABELS: Record<string, string> = {
  atr: "ATR utilisé",
  exit_oversold: "Sortie de survente",
  exit_overbought: "Sortie de surachat",
  bullish_cross: "Croisement haussier",
  bearish_cross: "Croisement baissier",
  bullish_alignment: "Alignement haussier",
  bearish_alignment: "Alignement baissier",
  price_above: "Prix au-dessus",
  price_below: "Prix en dessous",
  above_signal: "Au-dessus du signal",
  below_signal: "Sous le signal",
  above_zero: "Au-dessus de zéro",
  below_zero: "Sous zéro",
  lower_band_breakout: "Cassure de la bande basse",
  lower_band_reentry: "Réintégration de la bande basse",
  upper_band_breakout: "Cassure de la bande haute",
  upper_band_reentry: "Réintégration de la bande haute",
  near_oversold: "Proche de la survente",
  near_overbought: "Proche du surachat",
  overbought: "Surachat",
  oversold: "Survente",
  neutral: "Neutre",
  volatility_expansion: "Expansion de volatilité",
  volatility_contraction: "Contraction de volatilité",
  volatility_stable: "Volatilité stable",
  expanding: "En expansion",
  contracting: "En contraction",
  stable: "Stable",
  weak_trend: "Tendance faible",
  developing_trend: "Tendance en développement",
  strong_trend: "Tendance forte",
  trend_strengthening: "Renforcement de tendance",
  trend_weakening: "Affaiblissement de tendance",
  bullish_flip: "Bascule haussière",
  bearish_flip: "Bascule baissière",
  uptrend: "Tendance haussière",
  downtrend: "Tendance baissière",
  breakout_up: "Cassure haussière du canal",
  breakout_down: "Cassure baissière du canal",
  above_channel: "Prix au-dessus du canal",
  below_channel: "Prix sous le canal",
  inside_channel: "Prix à l’intérieur du canal",
  middle_band: "Bande centrale",
  upper_band: "Bande haute",
  lower_band: "Bande basse",
  band_width: "Largeur des bandes",
  band_width_percent: "Largeur normalisée",
  band_position: "Position du prix",
  upper_channel: "Borne haute",
  middle_channel: "Milieu du canal",
  lower_channel: "Borne basse",
  previous_upper_channel: "Borne haute précédente",
  previous_lower_channel: "Borne basse précédente",
  channel_width: "Largeur du canal",
  channel_width_percent: "Largeur normalisée",
  channel_position: "Position du prix",
  middle_line: "Ligne centrale",
}

function humanizeSnakeCase(value: string): string {
  const words = value.trim().replace(/[_-]+/g, " ").replace(/\s+/g, " ")
  if (!words) return "Valeur inconnue"
  return `${words.charAt(0).toLocaleUpperCase("fr-FR")}${words.slice(1).toLocaleLowerCase("fr-FR")}`
}

export function formatTechnicalLabel(value: string): string {
  const directLabel = TECHNICAL_LABELS[value]
  if (directLabel) return directLabel

  if (value.includes("/")) {
    return value
      .split("/")
      .map((part) => TECHNICAL_LABELS[part] ?? humanizeSnakeCase(part))
      .join(" / ")
  }

  return humanizeSnakeCase(value)
}

function priceFractionDigits(value: number): number {
  const absoluteValue = Math.abs(value)
  if (absoluteValue >= 1_000) return 2
  if (absoluteValue >= 1) return 4
  return 8
}

function maximumFractionDigits(indicator: IndicatorName, value: number): number {
  switch (indicator) {
    case "rsi":
    case "stochastic":
    case "adx":
      return 2
    case "atr":
      return 4
    case "macd":
      return Math.abs(value) >= 1 ? 4 : 8
    case "sma":
    case "ema":
    case "bollinger":
    case "supertrend":
    case "donchian":
    case "keltner":
      return priceFractionDigits(value)
  }
}

export function formatIndicatorRawValue(
  indicator: IndicatorName,
  value: number | null,
): string {
  if (value === null || !Number.isFinite(value)) return "—"

  const formatted = new Intl.NumberFormat("fr-FR", {
    maximumFractionDigits: maximumFractionDigits(indicator, value),
    useGrouping: true,
  }).format(value)
  return indicator === "atr" ? `${formatted} %` : formatted
}
