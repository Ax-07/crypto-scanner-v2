import { describe, expect, it } from "vitest"

import {
  DEFAULT_MARKET_PROFILE,
  parseMarketProfile,
  serializeMarketProfile,
} from "@/features/market/market-profile"
import { parseMarketSearch } from "@/features/market/market-search-params"

describe("market indicator profile", () => {
  it("keeps old URLs compatible with the default profile", () => {
    const parsed = parseMarketSearch(new URLSearchParams("symbol=ETH%2FUSDC&timeframe=4h"))
    expect(parsed.profile).toEqual(DEFAULT_MARKET_PROFILE)
    expect(parsed.profile.origin).toBe("default")
  })

  it("round-trips a reproducible custom profile through the URL", () => {
    const profile = { ...DEFAULT_MARKET_PROFILE, rsi_period: 7, origin: "custom" as const }
    const encoded = serializeMarketProfile(profile)
    expect(parseMarketProfile(encoded)).toEqual(profile)
    const params = new URLSearchParams({
      symbol: "BTC/USDC",
      timeframe: "1h",
      profile: encoded,
    })
    expect(parseMarketSearch(params).profile.rsi_period).toBe(7)
  })

  it("falls back safely when a shared profile is invalid", () => {
    expect(parseMarketProfile('{"macd_fast_period":99}')).toEqual(DEFAULT_MARKET_PROFILE)
  })
})
