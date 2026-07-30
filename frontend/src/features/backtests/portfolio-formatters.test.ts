import { describe, expect, it } from "vitest"

import {
  formatDecimalAmount,
  formatDecimalRatio,
  formatSignedAmount,
  parseDecimalForDisplay,
} from "@/features/backtests/portfolio-formatters"

describe("formatters portfolio fr-FR", () => {
  it("formate montants, signes, ratios et unités explicites", () => {
    expect(formatDecimalAmount("10000", "USDC")).toContain("10")
    expect(formatDecimalAmount("-12.5", "EUR")).toContain("EUR")
    expect(formatSignedAmount("2.5", "USDC")).toMatch(/^\+/)
    expect(formatDecimalRatio("0.001")).toContain("0,1")
    expect(formatDecimalRatio("-0.1")).toContain("-10")
    expect(formatDecimalAmount("0", "BTC")).toContain("BTC")
  })

  it("gère petites, grandes et valeurs non affichables", () => {
    expect(formatDecimalAmount("0.00000001")).not.toContain("NaN")
    expect(formatDecimalAmount("999999999999")).not.toContain("Infinity")
    expect(formatDecimalAmount(null)).toBe("—")
    expect(parseDecimalForDisplay("1e999")).toBeNull()
  })
})
