import { z } from "zod"

import type {
  IndicatorSignal,
  IndicatorSignalDirection,
  IndicatorSignals,
  IndicatorSignalStatus,
  IndicatorComponent,
} from "@/types/indicator-signals"

export const indicatorSignalStatusSchema: z.ZodType<IndicatorSignalStatus> = z.enum([
  "available",
  "insufficient_data",
  "invalid_data",
  "disabled",
])

export const indicatorSignalDirectionSchema: z.ZodType<IndicatorSignalDirection> = z.enum([
  "bullish",
  "bearish",
  "neutral",
])

export const indicatorNameSchema = z.enum([
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
])

export const indicatorComponentSchema: z.ZodType<IndicatorComponent> = z.strictObject({
  value: z.number().finite().nullable(),
  normalized_value: z.number().finite().nullable(),
  unit: z.enum(["price", "percent", "ratio", "index", "volume", "unitless"]),
})

const atrComponentsSchema = z.strictObject({
  true_range: indicatorComponentSchema,
  atr: indicatorComponentSchema,
  natr: indicatorComponentSchema,
  natr_change: indicatorComponentSchema,
})
const adxComponentsSchema = z.strictObject({
  adx: indicatorComponentSchema,
  plus_di: indicatorComponentSchema,
  minus_di: indicatorComponentSchema,
  dx: indicatorComponentSchema,
})
const supertrendComponentsSchema = z.strictObject({
  supertrend: indicatorComponentSchema,
  upper_band: indicatorComponentSchema,
  lower_band: indicatorComponentSchema,
  atr: indicatorComponentSchema,
  distance_ratio: indicatorComponentSchema,
})
const bollingerComponentsSchema = z.strictObject({
  middle_band: indicatorComponentSchema,
  upper_band: indicatorComponentSchema,
  lower_band: indicatorComponentSchema,
  band_width: indicatorComponentSchema,
  band_width_percent: indicatorComponentSchema,
  band_position: indicatorComponentSchema,
})
const donchianComponentsSchema = z.strictObject({
  upper_channel: indicatorComponentSchema,
  middle_channel: indicatorComponentSchema,
  lower_channel: indicatorComponentSchema,
  previous_upper_channel: indicatorComponentSchema,
  previous_lower_channel: indicatorComponentSchema,
  channel_width: indicatorComponentSchema,
  channel_width_percent: indicatorComponentSchema,
  channel_position: indicatorComponentSchema,
})
const keltnerComponentsSchema = z.strictObject({
  middle_line: indicatorComponentSchema,
  upper_channel: indicatorComponentSchema,
  lower_channel: indicatorComponentSchema,
  atr: indicatorComponentSchema,
  channel_width: indicatorComponentSchema,
  channel_width_percent: indicatorComponentSchema,
  channel_position: indicatorComponentSchema,
})

/** Les champs inconnus sont rejetés afin de détecter une dérive du contrat public. */
export const indicatorSignalSchema: z.ZodType<IndicatorSignal> = z.strictObject({
  status: indicatorSignalStatusSchema,
  direction: indicatorSignalDirectionSchema,
  signal: z.string().nullable(),
  state: z.string().nullable(),
  strength: z.number().finite().min(0).max(1),
  reason: z.string().nullable(),
  raw_value: z.number().finite().nullable(),
  components: z.union([
    atrComponentsSchema,
    adxComponentsSchema,
    supertrendComponentsSchema,
    bollingerComponentsSchema,
    donchianComponentsSchema,
    keltnerComponentsSchema,
  ]).nullable().optional(),
})

/**
 * Un sous-ensemble des six indicateurs est valide. L'objet strict distingue un
 * indicateur absent d'un signal présent avec un statut non disponible.
 */
export const indicatorSignalsSchema: z.ZodType<IndicatorSignals> = z.strictObject({
  rsi: indicatorSignalSchema.optional(),
  sma: indicatorSignalSchema.optional(),
  ema: indicatorSignalSchema.optional(),
  macd: indicatorSignalSchema.optional(),
  bollinger: indicatorSignalSchema.optional(),
  stochastic: indicatorSignalSchema.optional(),
  atr: indicatorSignalSchema.optional(),
  adx: indicatorSignalSchema.optional(),
  supertrend: indicatorSignalSchema.optional(),
  donchian: indicatorSignalSchema.optional(),
  keltner: indicatorSignalSchema.optional(),
})

export function parseIndicatorSignals(value: unknown): IndicatorSignals | undefined {
  if (value === undefined) return undefined
  return indicatorSignalsSchema.parse(value)
}
