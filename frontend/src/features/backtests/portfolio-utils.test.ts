import { describe, expect, it } from "vitest"

import {
  buildPortfolioSimulationPayload,
  deriveQuoteAsset,
  percentageInputToRatioString,
  ratioStringToPercentageInput,
} from "@/features/backtests/portfolio-utils"

describe("conversion des pourcentages portfolio", () => {
  it.each([
    ["0", "0"],
    ["0,1", "0.001"],
    ["1", "0.01"],
    ["100", "1"],
    [" 0.05 ", "0.0005"],
  ])("convertit %s en %s", (input, expected) => {
    expect(percentageInputToRatioString(input)).toBe(expected)
  })

  it.each(["", "abc", "-1", "1e2", "1,2.3"])("refuse %s", (input) => {
    expect(percentageInputToRatioString(input)).toBeNull()
  })

  it("effectue la conversion inverse pour l’affichage", () => {
    expect(ratioStringToPercentageInput("0.001")).toBe("0.1")
    expect(ratioStringToPercentageInput("1")).toBe("100")
  })
})

describe("payload portfolio", () => {
  const values = {
    portfolio_simulation_enabled: true,
    portfolio_simulation: {
      quote_asset: " usdc ",
      initial_capital: "10 000",
      position_size_percent: "50",
      fee_percent: "0,1",
      slippage_percent: "0,05",
    },
  }

  it("retourne undefined lorsque la simulation est désactivée", () => {
    expect(buildPortfolioSimulationPayload({
      ...values,
      portfolio_simulation_enabled: false,
    })).toBeUndefined()
  })

  it("produit le bloc v1 exact sans muter le formulaire", () => {
    const before = structuredClone(values)
    expect(buildPortfolioSimulationPayload(values)).toEqual({
      version: 1,
      quote_asset: "USDC",
      initial_capital: "10000",
      position_sizing: { mode: "percent_cash", value: "50" },
      execution_policy: "next_open",
      fee_rate: "0.001",
      slippage_rate: "0.0005",
      end_of_test_policy: "force_close",
    })
    expect(values).toEqual(before)
  })

  it("dérive uniquement un quote asset non ambigu", () => {
    expect(deriveQuoteAsset("BTC/USDC")).toBe("USDC")
    expect(deriveQuoteAsset("BTC/USDC, ETH/USDC")).toBeNull()
    expect(deriveQuoteAsset("BTCUSDC")).toBeNull()
  })
})
