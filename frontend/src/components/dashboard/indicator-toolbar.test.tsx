import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it } from "vitest"

import { IndicatorToolbar } from "@/components/dashboard/indicator-toolbar"
import { useMarketStore } from "@/stores/market-store"

describe("IndicatorToolbar", () => {
  beforeEach(() => useMarketStore.setState({
    visibility: {
      ema: true,
      sma: false,
      bollinger: true,
      rsi: true,
      macd: true,
      stochastic: true,
      signals: true,
      divergences: true,
    },
  }))

  it("conserve le pilotage des séries du graphique", () => {
    render(<IndicatorToolbar />)
    const ema = screen.getByRole("switch", { name: "EMA 20/50" })
    const sma = screen.getByRole("switch", { name: "SMA 20/50" })
    expect(ema).toBeChecked()
    expect(sma).not.toBeChecked()
    fireEvent.click(sma)
    expect(useMarketStore.getState().visibility.sma).toBe(true)
    expect(screen.getByRole("switch", { name: "SMA 20/50" })).toBeChecked()
  })
})
