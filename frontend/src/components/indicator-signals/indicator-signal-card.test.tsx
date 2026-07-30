import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { IndicatorSignalCard } from "@/components/indicator-signals"
import type { IndicatorName, IndicatorSignal } from "@/types/indicator-signals"

const completeSignal: IndicatorSignal = {
  status: "available",
  direction: "bullish",
  signal: "exit_oversold",
  state: "near_oversold",
  strength: 0.75,
  reason: "Le RSI vient de sortir de la zone de survente",
  raw_value: 31.4,
}

describe("IndicatorSignalCard", () => {
  it("renders every field of a complete available signal", () => {
    render(<IndicatorSignalCard indicator="rsi" signal={completeSignal} />)
    const card = screen.getByRole("article", { name: "Signal RSI" })
    expect(within(card).getByText("RSI")).toBeVisible()
    expect(within(card).getByText("Disponible")).toBeVisible()
    expect(within(card).getByText("Haussier")).toBeVisible()
    expect(within(card).getByText("Sortie de survente")).toBeVisible()
    expect(within(card).getByText("Proche de la survente")).toBeVisible()
    expect(within(card).getByText("31,4")).toBeVisible()
    expect(within(card).getByText("Intensité 75/100")).toBeVisible()
    expect(within(card).getByText(/Le RSI vient de sortir/)).toBeVisible()
  })

  it("handles nullable fields without empty labels or null text", () => {
    const { container } = render(
      <IndicatorSignalCard
        indicator="rsi"
        signal={{ ...completeSignal, signal: null, state: null, reason: null, raw_value: null }}
      />,
    )
    expect(screen.getByText("indisponible")).toBeVisible()
    expect(container).not.toHaveTextContent("null")
    expect(container).not.toHaveTextContent(/État\s*:/)
    expect(container).not.toHaveTextContent(/Raison\s*:/)
  })

  it("does not present insufficient data as a computed neutral direction", () => {
    render(
      <IndicatorSignalCard
        indicator="macd"
        signal={{ ...completeSignal, status: "insufficient_data", direction: "neutral" }}
      />,
    )
    expect(screen.getByText("Historique insuffisant pour calculer ce signal.")).toBeVisible()
    expect(screen.queryByText("Neutre")).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Direction technique/)).not.toBeInTheDocument()
  })

  it("shows the diagnostic reason for invalid data", () => {
    render(
      <IndicatorSignalCard
        indicator="bollinger"
        signal={{
          ...completeSignal,
          status: "invalid_data",
          direction: "neutral",
          reason: "Bandes dégénérées",
        }}
      />,
    )
    expect(screen.getByText("Les données de cet indicateur ne peuvent pas être exploitées.")).toBeVisible()
    expect(screen.getByText(/Bandes dégénérées/)).toBeVisible()
  })

  it("does not emphasize a direction for a disabled indicator", () => {
    render(
      <IndicatorSignalCard
        indicator="ema"
        signal={{ ...completeSignal, status: "disabled", direction: "bearish" }}
      />,
    )
    expect(screen.getByText("Cet indicateur est désactivé.")).toBeVisible()
    expect(screen.queryByText("Baissier")).not.toBeInTheDocument()
  })

  it("keeps essential information accessible in compact mode", () => {
    render(<IndicatorSignalCard indicator="rsi" signal={completeSignal} compact />)
    const card = screen.getByRole("article", { name: "Signal RSI" })
    expect(within(card).getByText("RSI")).toBeVisible()
    expect(within(card).getByText("Haussier")).toBeVisible()
    expect(within(card).getByText("Sortie de survente")).toBeVisible()
    expect(within(card).getByRole("progressbar")).toHaveAccessibleName(
      "Intensité technique : 75 sur 100",
    )
    expect(within(card).queryByText(/Raison\s*:/)).not.toBeInTheDocument()
  })

  it("keeps a long reason entirely available in the DOM", () => {
    const reason = "Une explication technique longue ".repeat(20).trim()
    render(<IndicatorSignalCard indicator="rsi" signal={{ ...completeSignal, reason }} />)
    expect(screen.getByText(reason)).toBeVisible()
  })

  it.each([
    ["rsi", "RSI"],
    ["sma", "SMA"],
    ["ema", "EMA"],
    ["macd", "MACD"],
    ["bollinger", "Bollinger"],
    ["stochastic", "Stochastique"],
    ["atr", "ATR / NATR"],
    ["adx", "ADX / DMI"],
    ["supertrend", "Supertrend"],
    ["donchian", "Canaux de Donchian"],
    ["keltner", "Canaux de Keltner"],
  ] as const)("renders the %s indicator as %s", (indicator: IndicatorName, label) => {
    render(<IndicatorSignalCard indicator={indicator} signal={completeSignal} />)
    expect(screen.getByRole("article", { name: `Signal ${label}` })).toBeInTheDocument()
  })

  it("renders named multi-value components with their units", () => {
    render(
      <IndicatorSignalCard
        indicator="atr"
        signal={{
          ...completeSignal,
          direction: "neutral",
          raw_value: 1.25,
          components: {
            true_range: { value: 12, normalized_value: null, unit: "price" },
            atr: { value: 10, normalized_value: null, unit: "price" },
            natr: { value: 1.25, normalized_value: 0.0125, unit: "percent" },
            natr_change: { value: 0.2, normalized_value: null, unit: "percent" },
          },
        }}
      />,
    )
    const card = screen.getByRole("article", { name: "Signal ATR / NATR" })
    expect(within(card).getByText("True range")).toBeVisible()
    expect(within(card).getAllByText("1,25 %")).toHaveLength(2)
  })

  it("supports hiding a reason and applying a custom class", () => {
    render(
      <IndicatorSignalCard
        indicator="rsi"
        signal={completeSignal}
        showReason={false}
        className="test-card"
      />,
    )
    expect(screen.getByRole("article", { name: "Signal RSI" })).toHaveClass("test-card")
    expect(screen.queryByText(/Le RSI vient de sortir/)).not.toBeInTheDocument()
  })

  it("renders Donchian bounds, width, position, state and breakout in French", () => {
    const price = { value: 100, normalized_value: null, unit: "price" } as const
    render(
      <IndicatorSignalCard
        indicator="donchian"
        signal={{
          ...completeSignal,
          signal: "breakout_up",
          state: "above_channel",
          components: {
            upper_channel: price,
            middle_channel: price,
            lower_channel: price,
            previous_upper_channel: price,
            previous_lower_channel: price,
            channel_width: price,
            channel_width_percent: {
              value: 10,
              normalized_value: 0.1,
              unit: "percent",
            },
            channel_position: {
              value: 1.1,
              normalized_value: 1.1,
              unit: "ratio",
            },
          },
        }}
      />,
    )
    const card = screen.getByRole("article", { name: "Signal Canaux de Donchian" })
    expect(within(card).getByText("Cassure haussière du canal")).toBeVisible()
    expect(within(card).getByText("Prix au-dessus du canal")).toBeVisible()
    expect(within(card).getByText("Borne haute")).toBeVisible()
    expect(within(card).getByText("Largeur normalisée")).toBeVisible()
    expect(within(card).getByText("Position du prix")).toBeVisible()
  })
})
