import { describe, expect, it } from "vitest"
import type { Logical } from "lightweight-charts"

import {
  shiftedLogicalRange,
  shouldPrefetchHistory,
} from "@/components/dashboard/trading-chart"

describe("trading chart viewport", () => {
  it("compense la plage logique avec le nombre réellement préfixé", () => {
    expect(shiftedLogicalRange({ from: 20 as Logical, to: 120 as Logical }, 2_000))
      .toEqual({ from: 2_020, to: 2_120 })
    expect(shiftedLogicalRange({ from: 20 as Logical, to: 120 as Logical }, 0))
      .toEqual({ from: 20, to: 120 })
  })

  it("précharge au seuil uniquement quand une page peut partir", () => {
    const range = { from: 100 as Logical, to: 200 as Logical }
    expect(shouldPrefetchHistory(range, 100, true, true, false)).toBe(true)
    expect(shouldPrefetchHistory(range, 99, true, true, false)).toBe(false)
    expect(shouldPrefetchHistory(range, 100, true, true, true)).toBe(false)
    expect(shouldPrefetchHistory(range, 100, true, false, false)).toBe(false)
  })
})
