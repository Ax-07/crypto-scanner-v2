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
      return 2
    case "macd":
      return Math.abs(value) >= 1 ? 4 : 8
    case "sma":
    case "ema":
    case "bollinger":
      return priceFractionDigits(value)
  }
}

export function formatIndicatorRawValue(
  indicator: IndicatorName,
  value: number | null,
): string {
  if (value === null || !Number.isFinite(value)) return "—"

  return new Intl.NumberFormat("fr-FR", {
    maximumFractionDigits: maximumFractionDigits(indicator, value),
    useGrouping: true,
  }).format(value)
}
