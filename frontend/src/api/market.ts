import { z } from "zod"

import { apiRequest } from "@/api/client"
import { marketProfileSchema, serializeMarketProfile } from "@/features/market/market-profile"
import { indicatorSignalsSchema } from "@/schemas/indicator-signals"
import type { CandlePageResponse, MarketIndicatorConfig } from "@/types/market"

const candleSchema = z.object({
  time: z.number().int(),
  open_time: z.number().int(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number(),
  is_closed: z.boolean(),
})
const pointSchema = z.object({
  time: z.number().int(),
  value: z.number(),
  color: z.string().optional(),
})
export const markerSchema = z.object({
  time: z.number().int(),
  position: z.enum(["aboveBar", "belowBar", "inBar"]),
  shape: z.enum(["circle", "square", "arrowUp", "arrowDown"]),
  color: z.string(),
  text: z.string(),
  category: z.enum(["signal", "divergence"]).optional(),
  source: z.enum(["RSI", "MACD"]).optional(),
  divergence_type: z.enum([
    "regular_bullish",
    "regular_bearish",
    "hidden_bullish",
    "hidden_bearish",
  ]).optional(),
  first_time: z.number().int().optional(),
  first_price: z.number().optional(),
  second_price: z.number().optional(),
  first_indicator: z.number().optional(),
  second_indicator: z.number().optional(),
})
const availabilitySchema = z.enum(["available", "insufficient_data", "invalid_data", "disabled"])
const factorDetailSchema = z.object({
  status: availabilitySchema,
  raw_value: z.unknown().optional(),
  signal: z.unknown().optional(),
  factor: z.number().nullable(),
  configured_weight: z.number(),
  effective_weight: z.number().nullable(),
  contribution: z.number().nullable(),
  reason: z.string().nullable(),
})
const confluenceSchema = z.object({
  score: z.number(),
  grade: z.enum(["F", "D", "C", "B", "A", "A+"]),
  breakdown: z.record(z.string(), z.number()).optional(),
  effective_weights: z.record(z.string(), z.number()).optional(),
  details: z.record(z.string(), factorDetailSchema).optional(),
})
const signalViewSchema = z.strictObject({
  price: z.number().nullable().optional(),
  timestamp: z.number().int().nullable().optional(),
  rsi: z.number().nullable().optional(),
  trend: z.enum(["bullish", "bearish", "neutral", "unavailable"]).optional(),
  macd: z.string().nullable().optional(),
  bollinger: z.string().nullable().optional(),
  stochastic: z.string().nullable().optional(),
  confluence: confluenceSchema.nullable().optional(),
  availability: z.record(z.string(), availabilitySchema).optional(),
  indicator_signals: indicatorSignalsSchema.optional(),
  is_forming: z.boolean().optional(),
})
export const snapshotSchema = signalViewSchema.safeExtend({
  confirmed: signalViewSchema.optional(),
  provisional: signalViewSchema.nullable().optional(),
  profile: marketProfileSchema.optional(),
})
export const marketMessageSchema = z.discriminatedUnion("type", [
  z.strictObject({
    type: z.literal("history"),
    symbol: z.string(),
    timeframe: z.string(),
    candles: z.array(candleSchema.omit({ open_time: true, is_closed: true }).extend({
      open_time: z.number().int().optional(),
      is_closed: z.boolean().optional(),
    })),
    indicators: z.record(z.string(), z.array(pointSchema)),
    markers: z.array(markerSchema),
    snapshot: snapshotSchema,
  }),
  z.strictObject({
    type: z.literal("update"),
    candle: candleSchema.omit({ open_time: true, is_closed: true }).extend({
      open_time: z.number().int().optional(),
      is_closed: z.boolean().optional(),
    }),
    indicators: z.record(z.string(), pointSchema),
    markers: z.array(markerSchema),
    snapshot: snapshotSchema,
  }),
  z.strictObject({ type: z.literal("error"), message: z.string() }),
])
const responseSchema = z.strictObject({
  exchange_id: z.string(),
  market_type: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  candles: z.array(candleSchema),
  indicators: z.record(z.string(), z.array(pointSchema)),
  markers: z.array(markerSchema),
  page: z.object({
    limit: z.number().int().positive(),
    count: z.number().int().nonnegative(),
    oldest_open_time: z.number().int().nullable(),
    newest_open_time: z.number().int().nullable(),
    next_before: z.number().int().nullable(),
    next_after: z.number().int().nullable(),
    has_more_before: z.boolean(),
    has_more_after: z.boolean(),
  }),
  coverage: z.object({
    earliest_open_time: z.number().int().nullable(),
    latest_open_time: z.number().int().nullable(),
    total_candles: z.number().int().nonnegative(),
    is_complete: z.boolean(),
    gap_count: z.number().int().nonnegative(),
    available_from: z.number().int().nullable(),
    available_to: z.number().int().nullable(),
    local_earliest_time: z.number().int().nullable(),
    exchange_earliest_time: z.number().int().nullable(),
    exchange_earliest_verified: z.boolean(),
    local_candle_count: z.number().int().nonnegative(),
    is_earliest_known: z.boolean(),
    is_recent_complete: z.boolean(),
    history_last_error: z.string().nullable(),
  }),
  source: z.object({
    read_from_sqlite: z.boolean(),
    downloaded_from_exchange: z.number().int().nonnegative(),
  }),
  anchor_time: z.number().int().nullable(),
  anchor_before_available: z.boolean(),
  snapshot: snapshotSchema.optional(),
  profile: marketProfileSchema.optional(),
})

export interface CandleQuery {
  symbol: string
  timeframe: string
  limit: number
  before?: number
  after?: number
  syncMissing?: boolean
  signal?: AbortSignal
  profile?: MarketIndicatorConfig
}

export const marketApi = {
  async getCandles(query: CandleQuery): Promise<CandlePageResponse> {
    const params = new URLSearchParams({
      exchange_id: "binance",
      market_type: "spot",
      symbol: query.symbol,
      timeframe: query.timeframe,
      limit: String(query.limit),
      closed_only: "false",
      include_indicators: "true",
      sync_if_missing: String(query.syncMissing ?? false),
    })
    if (query.before !== undefined) params.set("before", String(query.before))
    if (query.after !== undefined) params.set("after", String(query.after))
    if (query.profile) params.set("profile", serializeMarketProfile(query.profile))
    const payload = await apiRequest<unknown>(`/api/market/candles?${params}`, {
      signal: query.signal,
    })
    return responseSchema.parse(payload) as CandlePageResponse
  },

  async getCandleWindow(query: {
    symbol: string
    timeframe: string
    anchorTime: number
    beforeCount: number
    afterCount: number
    signal?: AbortSignal
    profile?: MarketIndicatorConfig
  }): Promise<CandlePageResponse> {
    const params = new URLSearchParams({
      exchange_id: "binance",
      market_type: "spot",
      symbol: query.symbol,
      timeframe: query.timeframe,
      anchor_time: String(query.anchorTime),
      before_count: String(query.beforeCount),
      after_count: String(query.afterCount),
      closed_only: "false",
      include_indicators: "true",
    })
    if (query.profile) params.set("profile", serializeMarketProfile(query.profile))
    const payload = await apiRequest<unknown>(
      `/api/market/candles/window?${params}`,
      { signal: query.signal },
    )
    return responseSchema.parse(payload) as CandlePageResponse
  },
}
