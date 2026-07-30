import { z } from "zod"

const DECIMAL_PATTERN = /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/

export const finiteDecimalStringSchema = z.string().min(1).regex(
  DECIMAL_PATTERN,
  "Chaîne décimale canonique attendue",
)

const nonEmptyStringSchema = z.string().trim().min(1)
const timestampSchema = z.string().refine(
  (value) => (
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    && Number.isFinite(Date.parse(value))
  ),
  "Timestamp ISO avec fuseau attendu",
)
const countSchema = z.number().int().nonnegative()
const positiveDecimalStringSchema = finiteDecimalStringSchema.refine(
  (value) => !value.startsWith("-") && !/^0(?:\.0+)?$/.test(value),
  "Décimal strictement positif attendu",
)
const nonNegativeDecimalStringSchema = finiteDecimalStringSchema.refine(
  (value) => !value.startsWith("-"),
  "Décimal positif ou nul attendu",
)
const percentageDecimalStringSchema = positiveDecimalStringSchema.refine(
  (value) => Number(value) <= 100,
  "Pourcentage compris entre 0 et 100 attendu",
)
const rateDecimalStringSchema = finiteDecimalStringSchema.refine(
  (value) => !value.startsWith("-") && Number(value) < 1,
  "Ratio compris entre 0 inclus et 1 exclu attendu",
)
const unitRatioDecimalStringSchema = nonNegativeDecimalStringSchema.refine(
  (value) => Number(value) <= 1,
  "Ratio compris entre 0 et 1 attendu",
)

export const portfolioPositionSizingConfigSchema = z.object({
  mode: z.literal("percent_cash"),
  value: percentageDecimalStringSchema,
}).strict()

export const portfolioSimulationConfigSchema = z.object({
  version: z.literal(1),
  quote_asset: nonEmptyStringSchema,
  initial_capital: positiveDecimalStringSchema,
  position_sizing: portfolioPositionSizingConfigSchema,
  execution_policy: z.literal("next_open"),
  fee_rate: rateDecimalStringSchema,
  slippage_rate: rateDecimalStringSchema,
  end_of_test_policy: z.literal("force_close"),
}).strict()

export const portfolioSimulationSummarySchema = z.object({
  version: z.literal(1),
  quote_asset: nonEmptyStringSchema,
  initial_capital: positiveDecimalStringSchema,
  final_cash: nonNegativeDecimalStringSchema,
  final_equity: nonNegativeDecimalStringSchema,
  net_profit: finiteDecimalStringSchema,
  total_return_ratio: finiteDecimalStringSchema,
  realized_pnl: finiteDecimalStringSchema,
  unrealized_pnl: finiteDecimalStringSchema,
  total_fees: nonNegativeDecimalStringSchema,
  trade_count: countSchema,
  winning_trade_count: countSchema,
  losing_trade_count: countSchema,
  breakeven_trade_count: countSchema,
  win_rate: unitRatioDecimalStringSchema.nullable(),
  average_trade_return: finiteDecimalStringSchema.nullable(),
  max_drawdown_ratio: unitRatioDecimalStringSchema,
  exposure_ratio: unitRatioDecimalStringSchema,
  open_position_count: countSchema,
}).strict()

export const portfolioSimulationPublicResultSchema = z.object({
  version: z.literal(1),
  quote_asset: nonEmptyStringSchema,
  summary: portfolioSimulationSummarySchema,
  has_trades: z.boolean(),
  has_equity_curve: z.boolean(),
}).strict()

export const portfolioRunMetadataSchema = z.object({
  version: z.literal(1),
  schema_version: z.literal(1),
  engine_version: nonEmptyStringSchema,
  quote_asset: nonEmptyStringSchema,
  summary: portfolioSimulationSummarySchema,
  details_status: z.enum(["complete", "unavailable_legacy"]),
  order_count: countSchema,
  execution_count: countSchema,
  trade_count: countSchema,
  equity_point_count: countSchema,
  available_after_restart: z.boolean(),
}).strict()

export const portfolioTradeSchema = z.object({
  version: z.literal(1),
  sequence: countSchema,
  trade_id: nonEmptyStringSchema,
  position_id: nonEmptyStringSchema,
  symbol: nonEmptyStringSchema,
  quote_asset: nonEmptyStringSchema,
  entry_observation_id: nonEmptyStringSchema,
  exit_observation_id: nonEmptyStringSchema.nullable(),
  entry_time: timestampSchema,
  exit_time: timestampSchema,
  entry_price: positiveDecimalStringSchema,
  exit_price: positiveDecimalStringSchema,
  quantity: positiveDecimalStringSchema,
  entry_fee: nonNegativeDecimalStringSchema,
  exit_fee: nonNegativeDecimalStringSchema,
  gross_exit_proceeds: nonNegativeDecimalStringSchema,
  net_exit_proceeds: nonNegativeDecimalStringSchema,
  realized_pnl: finiteDecimalStringSchema,
  return_ratio: finiteDecimalStringSchema,
  duration_bars: countSchema,
  exit_reason: z.enum(["validation_lost", "end_of_test"]),
}).strict()

export const portfolioEquityPointSchema = z.object({
  version: z.literal(1),
  sequence: countSchema,
  timestamp: timestampSchema,
  cash: nonNegativeDecimalStringSchema,
  position_value: nonNegativeDecimalStringSchema,
  equity: nonNegativeDecimalStringSchema,
  realized_pnl_cumulative: finiteDecimalStringSchema,
  unrealized_pnl: finiteDecimalStringSchema,
  fees_cumulative: nonNegativeDecimalStringSchema,
  drawdown_ratio: unitRatioDecimalStringSchema,
}).strict()

export const portfolioTradePageSchema = z.object({
  items: z.array(portfolioTradeSchema),
  total: countSchema,
  offset: countSchema,
  limit: z.number().int().min(1).max(500),
  has_more: z.boolean(),
}).strict()

export const portfolioEquityPageSchema = z.object({
  items: z.array(portfolioEquityPointSchema),
  total: countSchema,
  offset: countSchema,
  limit: z.number().int().min(1).max(2000),
  has_more: z.boolean(),
  sampled: z.boolean(),
  source_point_count: countSchema,
}).strict()
