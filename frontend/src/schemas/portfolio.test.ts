import { describe, expect, it } from "vitest"

import {
  finiteDecimalStringSchema,
  portfolioEquityPageSchema,
  portfolioEquityPointSchema,
  portfolioRunMetadataSchema,
  portfolioSimulationConfigSchema,
  portfolioSimulationSummarySchema,
  portfolioTradePageSchema,
  portfolioTradeSchema,
} from "@/schemas/portfolio"
import {
  portfolioEquityPage,
  portfolioMetadata,
  portfolioPublicResult,
  portfolioTradePage,
} from "@/test/backtest-fixtures"

describe("schémas portfolio v1", () => {
  const config = {
    version: 1,
    quote_asset: "USDC",
    initial_capital: "10000",
    position_sizing: { mode: "percent_cash", value: "100" },
    execution_policy: "next_open",
    fee_rate: "0.001",
    slippage_rate: "0",
    end_of_test_policy: "force_close",
  }

  it("valide les contrats canoniques sans convertir les décimaux", () => {
    expect(portfolioSimulationConfigSchema.parse(config).initial_capital).toBe("10000")
    expect(portfolioSimulationSummarySchema.parse(portfolioPublicResult.summary).win_rate).toBe("1")
    expect(portfolioRunMetadataSchema.parse(portfolioMetadata)).toEqual(portfolioMetadata)
    expect(portfolioTradeSchema.parse(portfolioTradePage.items[0]).realized_pnl).toBe("98.9")
    expect(portfolioEquityPointSchema.parse(portfolioEquityPage.items[0]).equity).toBe("10000")
    expect(portfolioTradePageSchema.parse(portfolioTradePage).total).toBe(1)
    expect(portfolioEquityPageSchema.parse(portfolioEquityPage).sampled).toBe(true)
  })

  it.each(["", "NaN", "Infinity", "-Infinity", "abc", "1e3", ".5"])(
    "rejette le décimal invalide %s",
    (value) => expect(finiteDecimalStringSchema.safeParse(value).success).toBe(false),
  )

  it("rejette versions, enums, timestamps, compteurs et clés inconnus", () => {
    expect(portfolioSimulationConfigSchema.safeParse({ ...config, version: 2 }).success).toBe(false)
    expect(portfolioSimulationConfigSchema.safeParse({
      ...config,
      execution_policy: "signal_close",
    }).success).toBe(false)
    expect(portfolioTradeSchema.safeParse({
      ...portfolioTradePage.items[0],
      entry_time: "hier",
    }).success).toBe(false)
    expect(portfolioTradeSchema.safeParse({
      ...portfolioTradePage.items[0],
      duration_bars: -1,
    }).success).toBe(false)
    expect(portfolioRunMetadataSchema.safeParse({ ...portfolioMetadata, extra: true }).success)
      .toBe(false)
  })

  it("préserve les champs nullables prévus", () => {
    expect(portfolioSimulationSummarySchema.parse({
      ...portfolioPublicResult.summary,
      win_rate: null,
      average_trade_return: null,
    }).win_rate).toBeNull()
    expect(portfolioTradeSchema.parse(portfolioTradePage.items[0]).exit_observation_id).toBeNull()
  })
})
