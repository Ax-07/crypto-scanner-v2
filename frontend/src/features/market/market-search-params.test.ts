import { describe, expect, it } from "vitest"
import { DEFAULT_MARKET, parseMarketSearch } from "@/features/market/market-search-params"

describe("parseMarketSearch", () => {
  it("conserve une paire et un timeframe valides", () => {
    expect(parseMarketSearch(new URLSearchParams("symbol=ETH%2FUSDC&timeframe=4h"))).toMatchObject({ symbol: "ETH/USDC", timeframe: "4h", profile: { origin: "default" } })
  })
  it("remplace les valeurs absentes ou invalides", () => {
    expect(parseMarketSearch(new URLSearchParams("symbol=bad&timeframe=10m"))).toMatchObject({ ...DEFAULT_MARKET, profile: { origin: "default" } })
  })
})
