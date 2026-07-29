import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it } from "vitest"

import { MarketMetrics } from "@/components/dashboard/market-metrics"
import { useMarketStore } from "@/stores/market-store"

describe("MarketMetrics", () => {
  beforeEach(() => useMarketStore.setState({ markers: [], snapshot: {} }))

  it("shows confirmed values, provisional values and unavailable factors", () => {
    useMarketStore.setState({
      snapshot: {
        confirmed: {
          rsi: 34.2,
          trend: "neutral",
          macd: null,
          availability: { rsi: "available", trend: "available", macd: "insufficient_data" },
          confluence: {
            score: 62,
            grade: "C",
            details: {
              rsi: {
                status: "available",
                factor: 0.75,
                configured_weight: 20,
                effective_weight: 100,
                contribution: 75,
                reason: null,
              },
              macd: {
                status: "insufficient_data",
                factor: null,
                configured_weight: 20,
                effective_weight: null,
                contribution: null,
                reason: "insufficient_data",
              },
            },
          },
        },
        provisional: { rsi: 38.7, trend: "bullish", is_forming: true },
      },
    })
    render(<MarketMetrics />)
    expect(screen.getByText("34,2")).toBeInTheDocument()
    expect(screen.getByText("En formation : 38,7")).toBeInTheDocument()
    expect(screen.getAllByText("Données insuffisantes").length).toBeGreaterThan(0)
    expect(screen.getByText("Détail du score de confluence")).toBeInTheDocument()
    expect(screen.getByText("Score technique, pas une probabilité de réussite.")).toBeInTheDocument()
  })
})
