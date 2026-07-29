import type {
  IndicatorSignalDirection,
  IndicatorSignalStatus,
} from "@/types/indicator-signals"

export type StructuredSignalFilterVersion = 1
export type StructuredSignalFilterIndicator = "macd" | "bollinger" | "stochastic"
export type StructuredSignalFilterField = "direction" | "signal" | "state" | "status"
export type StructuredSignalFilterMatch = "all" | "any"

export type StructuredDirectionCondition = {
  field: "direction"
  values: IndicatorSignalDirection[]
}

export type StructuredStatusCondition = {
  field: "status"
  values: IndicatorSignalStatus[]
}

export type StructuredTextCondition = {
  field: "signal" | "state"
  values: string[]
}

export type StructuredSignalFilterCondition =
  | StructuredDirectionCondition
  | StructuredStatusCondition
  | StructuredTextCondition

export type StructuredIndicatorFilter = {
  match: StructuredSignalFilterMatch
  conditions: StructuredSignalFilterCondition[]
}

export type StructuredSignalFilters = {
  version: StructuredSignalFilterVersion
  indicators: Partial<
    Record<StructuredSignalFilterIndicator, StructuredIndicatorFilter>
  >
}
