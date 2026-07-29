import { z } from "zod"

import type {
  IndicatorSignal,
  IndicatorSignalDirection,
  IndicatorSignals,
  IndicatorSignalStatus,
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
])

/** Les champs inconnus sont rejetés afin de détecter une dérive du contrat public. */
export const indicatorSignalSchema: z.ZodType<IndicatorSignal> = z.strictObject({
  status: indicatorSignalStatusSchema,
  direction: indicatorSignalDirectionSchema,
  signal: z.string().nullable(),
  state: z.string().nullable(),
  strength: z.number().finite().min(0).max(1),
  reason: z.string().nullable(),
  raw_value: z.number().finite().nullable(),
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
})

export function parseIndicatorSignals(value: unknown): IndicatorSignals | undefined {
  if (value === undefined) return undefined
  return indicatorSignalsSchema.parse(value)
}
