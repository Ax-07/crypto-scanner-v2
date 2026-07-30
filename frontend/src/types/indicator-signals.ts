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
  | "atr"
  | "adx"
  | "supertrend"
  | "donchian"
  | "keltner"

export type IndicatorComponentUnit =
  | "price"
  | "percent"
  | "ratio"
  | "index"
  | "volume"
  | "unitless"

export interface IndicatorComponent {
  value: number | null
  normalized_value: number | null
  unit: IndicatorComponentUnit
}

export type IndicatorComponents =
  | Record<
      | "middle_band"
      | "upper_band"
      | "lower_band"
      | "band_width"
      | "band_width_percent"
      | "band_position",
      IndicatorComponent
    >
  | Record<"true_range" | "atr" | "natr" | "natr_change", IndicatorComponent>
  | Record<"adx" | "plus_di" | "minus_di" | "dx", IndicatorComponent>
  | Record<
      "supertrend" | "upper_band" | "lower_band" | "atr" | "distance_ratio",
      IndicatorComponent
    >
  | Record<
      | "upper_channel"
      | "middle_channel"
      | "lower_channel"
      | "previous_upper_channel"
      | "previous_lower_channel"
      | "channel_width"
      | "channel_width_percent"
      | "channel_position",
      IndicatorComponent
    >
  | Record<
      | "middle_line"
      | "upper_channel"
      | "lower_channel"
      | "atr"
      | "channel_width"
      | "channel_width_percent"
      | "channel_position",
      IndicatorComponent
    >

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
  components?: IndicatorComponents | null
}

export type IndicatorSignals = Partial<Record<IndicatorName, IndicatorSignal>>

/**
 * Pendant la migration, un payload historique peut omettre `indicator_signals`.
 * `{}` signifie qu'un payload moderne n'a produit aucun signal, tandis qu'un
 * signal indisponible reste présent avec son propre `status`.
 */
