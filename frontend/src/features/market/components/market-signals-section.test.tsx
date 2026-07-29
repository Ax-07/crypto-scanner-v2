import { act, fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it } from "vitest"

import { MarketSignalsSection } from "@/features/market/components/market-signals-section"
import { useMarketStore } from "@/stores/market-store"

describe("MarketSignalsSection", () => {
  beforeEach(() => useMarketStore.setState({
    snapshot: {
      confirmed: { price: 100, indicator_signals: {} },
      provisional: { price: 101, indicator_signals: {}, is_forming: true },
    },
  }))

  it("sélectionne le confirmé initialement et garde les deux snapshots dans le DOM", () => {
    render(<MarketSignalsSection symbol="BTC/USDC" timeframe="1h" />)
    expect(screen.getByRole("tab", { name: "Confirmés" })).toHaveAttribute(
      "aria-selected", "true",
    )
    expect(screen.getByRole("heading", { name: "Signaux confirmés" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Signaux provisoires" })).toBeInTheDocument()
  })

  it("permet la navigation clavier sans écrire le choix dans Zustand", () => {
    render(<MarketSignalsSection symbol="BTC/USDC" timeframe="1h" />)
    const before = useMarketStore.getState().snapshot
    const confirmedTab = screen.getByRole("tab", { name: "Confirmés" })
    fireEvent.keyDown(confirmedTab, { key: "ArrowRight" })
    expect(screen.getByRole("tab", { name: "Provisoires" })).toHaveAttribute(
      "aria-selected", "true",
    )
    expect(useMarketStore.getState().snapshot).toBe(before)
  })

  it("se met à jour depuis les sélecteurs fins du store", () => {
    render(<MarketSignalsSection symbol="BTC/USDC" timeframe="1h" />)
    expect(screen.getByText("100")).toBeInTheDocument()
    act(() => useMarketStore.setState((state) => ({
        snapshot: {
          ...state.snapshot,
          confirmed: { price: 102, indicator_signals: {} },
        },
      })))
    expect(screen.getByText("102")).toBeInTheDocument()
  })
})
