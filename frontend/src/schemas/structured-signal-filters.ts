import { z } from "zod"

const uniqueNonEmptyArray = <T extends z.ZodType>(item: T) =>
  z.array(item).min(1, "Sélectionnez au moins une valeur").refine(
    (values) => new Set(values).size === values.length,
    "Les valeurs doivent être uniques",
  )

const directionConditionSchema = z.object({
  field: z.literal("direction"),
  values: uniqueNonEmptyArray(z.enum(["bullish", "bearish", "neutral"])),
}).strict()

const statusConditionSchema = z.object({
  field: z.literal("status"),
  values: uniqueNonEmptyArray(
    z.enum(["available", "insufficient_data", "invalid_data", "disabled"]),
  ),
}).strict()

const signalConditionSchema = z.object({
  field: z.literal("signal"),
  values: uniqueNonEmptyArray(z.string().trim().min(1)),
}).strict()

const stateConditionSchema = z.object({
  field: z.literal("state"),
  values: uniqueNonEmptyArray(z.string().trim().min(1)),
}).strict()

export const structuredSignalFilterConditionSchema = z.discriminatedUnion("field", [
  directionConditionSchema,
  signalConditionSchema,
  stateConditionSchema,
  statusConditionSchema,
])

export const structuredIndicatorFilterSchema = z.object({
  match: z.enum(["all", "any"]),
  // Une liste vide neutralise explicitement le filtre et bloque le fallback legacy.
  conditions: z.array(structuredSignalFilterConditionSchema),
}).strict()

export const structuredSignalFiltersSchema = z.object({
  version: z.literal(1, "La version des filtres structurés doit être 1"),
  indicators: z.object({
    macd: structuredIndicatorFilterSchema.optional(),
    bollinger: structuredIndicatorFilterSchema.optional(),
    stochastic: structuredIndicatorFilterSchema.optional(),
  }).strict(),
}).strict()
