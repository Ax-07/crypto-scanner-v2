import { performance } from "node:perf_hooks"
import { describe, expect, it } from "vitest"

import { mergeCandles } from "../src/features/market/market-history"
import type { Candle } from "../src/types/market"

function candle(time: number): Candle {
  return { time, open: 1, high: 1, low: 1, close: 1, volume: 1 }
}

describe("history merge measurements", () => {
  it("mesure 10k, 50k et 100k bougies avec une page de 2k", () => {
    for (const size of [10_000, 50_000, 100_000]) {
      const current = Array.from({ length: size }, (_, index) => candle(index + 2_000))
      const incoming = Array.from({ length: 2_001 }, (_, index) => candle(index))
      mergeCandles(current, incoming)
      const samples: number[] = []
      for (let run = 0; run < 5; run += 1) {
        const started = performance.now()
        const result = mergeCandles(current, incoming)
        samples.push(performance.now() - started)
        expect(result.candles).toHaveLength(size + 2_000)
      }
      samples.sort((left, right) => left - right)
      console.log(`${size}: médiane ${samples[2].toFixed(2)} ms`)
    }
  })
})
