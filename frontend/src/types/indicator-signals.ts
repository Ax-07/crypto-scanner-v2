export type IndicatorSignalStatus =
  | "available"
  | "insufficient_data"
  | "invalid_data"
  | "disabled"

export type IndicatorSignalDirection = "bullish" | "bearish" | "neutral"

export type IndicatorName =
  | "rsi"
  | "sma"
  | "ema"
  | "macd"
  | "bollinger"
  | "stochastic"

export interface IndicatorSignal {
  status: IndicatorSignalStatus
  direction: IndicatorSignalDirection
  signal: string | null
  state: string | null
  /**
   * Intensité technique du signal selon les règles de l'indicateur.
   * Ce n'est ni une probabilité de réussite ni une prévision de gain.
   */
  strength: number
  reason: string | null
  raw_value: number | null
}

export type IndicatorSignals = Partial<Record<IndicatorName, IndicatorSignal>>

/**
 * Pendant la migration, un payload historique peut omettre `indicator_signals`.
 * `{}` signifie qu'un payload moderne n'a produit aucun signal, tandis qu'un
 * signal indisponible reste présent avec son propre `status`.
 */
