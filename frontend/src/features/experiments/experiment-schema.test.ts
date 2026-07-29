import { describe, expect, it } from "vitest"

import { candidateEstimate, experimentFormSchema } from "./experiment-schema"

const base = {
  sourceBacktestId: "abcdefgh", horizon: 24, embargo: 24, minimumGlobal: 30,
  includeTrend: true, includeRedundancy: true, includeThresholds: true,
}

describe("experiment form", () => {
  it("estimates the bounded search before launch", () => {
    expect(candidateEstimate(base)).toBe(11)
  })

  it("rejects an embargo shorter than the selected horizon", () => {
    expect(experimentFormSchema.safeParse({ ...base, embargo: 23 }).success).toBe(false)
  })
})
