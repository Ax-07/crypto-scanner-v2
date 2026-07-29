import type {
  StructuredIndicatorFilter,
  StructuredSignalFilterCondition,
  StructuredSignalFilterField,
  StructuredSignalFilterIndicator,
  StructuredSignalFilters,
} from "@/types/structured-signal-filters"
import type { ScanConfig } from "@/types/scanner"

function condition(
  field: StructuredSignalFilterField,
  values: string[],
): StructuredSignalFilterCondition {
  if (field === "direction") {
    return { field, values: values as Array<"bullish" | "bearish" | "neutral"> }
  }
  if (field === "status") {
    return {
      field,
      values: values as Array<
        "available" | "insufficient_data" | "invalid_data" | "disabled"
      >,
    }
  }
  return { field, values }
}

function legacyGroup(
  field: StructuredSignalFilterField,
  values: string[] | null,
): StructuredIndicatorFilter | undefined {
  return values?.length
    ? { match: "any", conditions: [condition(field, values)] }
    : undefined
}

/** Convertit une configuration éditable sans altérer les snapshots de jobs historiques. */
export function migrateLegacySignalFilters(config: ScanConfig): ScanConfig {
  const existing = config.structured_signal_filters
  const indicators: StructuredSignalFilters["indicators"] = {
    ...existing?.indicators,
  }
  let changed = !existing
  const macd = legacyGroup("direction", config.filter_macd_signal)
  const bollinger = legacyGroup("state", config.filter_bb_position)
  // La classe historique complète est portée par `signal`, croisements prioritaires inclus.
  const stochastic = legacyGroup("signal", config.filter_stoch_signal)
  if (!indicators.macd && macd) {
    indicators.macd = macd
    changed = true
  }
  if (!indicators.bollinger && bollinger) {
    indicators.bollinger = bollinger
    changed = true
  }
  if (!indicators.stochastic && stochastic) {
    indicators.stochastic = stochastic
    changed = true
  }
  if (!changed) return config
  return {
    ...config,
    structured_signal_filters: { version: 1, indicators },
  }
}

export function toggleStructuredFilterValue(
  filters: StructuredSignalFilters | null | undefined,
  indicator: StructuredSignalFilterIndicator,
  field: StructuredSignalFilterField,
  value: string,
): StructuredSignalFilters {
  const current = filters ?? { version: 1, indicators: {} }
  const group = current.indicators[indicator] ?? { match: "any", conditions: [] }
  const existing = group.conditions.find((item) => item.field === field)
  const values = existing?.values.map(String) ?? []
  const nextValues = values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value]
  const remaining = group.conditions.filter((item) => item.field !== field)
  const conditions = nextValues.length
    ? [...remaining, condition(field, nextValues)]
    : remaining
  return {
    version: 1,
    indicators: {
      ...current.indicators,
      [indicator]: { ...group, conditions },
    },
  }
}

export function setStructuredFilterMatch(
  filters: StructuredSignalFilters | null | undefined,
  indicator: StructuredSignalFilterIndicator,
  match: "all" | "any",
): StructuredSignalFilters {
  const current = filters ?? { version: 1, indicators: {} }
  const group = current.indicators[indicator] ?? { match: "any", conditions: [] }
  return {
    version: 1,
    indicators: {
      ...current.indicators,
      [indicator]: { ...group, match },
    },
  }
}
