import { describe, expect, it } from "vitest"

import { backtestFormSchema, parseHorizons } from "@/features/backtests/backtest-schema"

const valid = {
  symbols: "BTC/USDC, ETH/USDC",
  start: "2026-01-01T00:00",
  end: "2026-02-01T00:00",
  timeframe: "4h",
  horizons: "1, 3, 6",
  replay_mode: "every_bar",
  entry_policy: "next_open",
  gap_policy: "reject_range",
  fee_bps: 10,
  slippage_bps: 5,
  use_rsi: true,
  rsi_threshold: 35,
  use_ma: true,
  min_trend_score: 2,
  use_confluence_score: true,
  min_confluence_score: 60,
}

describe("backtestFormSchema", () => {
  it("valide une configuration complète et ordonne les horizons", () => {
    expect(backtestFormSchema.safeParse(valid).success).toBe(true)
    expect(parseHorizons("6, 1, 3, 3")).toEqual([1, 3, 6])
  })

  it("refuse une plage inversée et des horizons ambigus", () => {
    expect(backtestFormSchema.safeParse({ ...valid, end: valid.start }).success).toBe(false)
    expect(backtestFormSchema.safeParse({ ...valid, horizons: "1;3" }).success).toBe(false)
  })
})
