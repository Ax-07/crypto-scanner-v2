import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { MarketSignalSnapshot } from "@/features/market/components/market-signal-snapshot"
import type {
  IndicatorName,
  IndicatorSignal,
  IndicatorSignalStatus,
} from "@/types/indicator-signals"
import type { SignalView } from "@/types/market"

const signal: IndicatorSignal = {
  status: "available",
  direction: "bullish",
  signal: "bullish_cross",
  state: "above_signal",
  strength: 0.75,
  reason: "Signal calculé par le backend",
  raw_value: 31.4,
}

const sixSignals = Object.fromEntries(
  ["rsi", "sma", "ema", "macd", "bollinger", "stochastic"].map(
    (name) => [name, signal],
  ),
) as Record<IndicatorName, IndicatorSignal>

const complete: SignalView = {
  price: 64_321.5,
  timestamp: 1_785_225_600,
  confluence: { score: 74, grade: "B" },
  indicator_signals: sixSignals,
}

describe("MarketSignalSnapshot confirmé", () => {
  it("affiche le contexte, la confluence et les six indicateurs dans l’ordre canonique", () => {
    render(
      <MarketSignalSnapshot
        kind="confirmed"
        snapshot={complete}
        symbol="BTC/USDC"
        timeframe="4h"
      />,
    )
    expect(screen.getByRole("heading", { name: "Signaux confirmés" })).toBeVisible()
    expect(screen.getByText("Confirmé")).toBeVisible()
    expect(screen.getByText("BTC/USDC")).toBeVisible()
    expect(screen.getByText("4h")).toBeVisible()
    expect(screen.getByText("74/100 · Grade B")).toBeVisible()
    const cards = screen.getAllByRole("article")
    expect(cards).toHaveLength(6)
    expect(cards.map((card) => within(card).getByText(
      /^(RSI|SMA|EMA|MACD|Bollinger|Stochastique)$/,
    ).textContent)).toEqual([
      "RSI", "SMA", "EMA", "MACD", "Bollinger", "Stochastique",
    ])
    expect(screen.getByText(/facteur « Tendance »/)).toBeVisible()
    expect(screen.getByText(
      /L’intensité représente la force technique.*ne représente pas une probabilité de gain/i,
    )).toBeVisible()
    expect(screen.queryByText(/taux de réussite|confiance|fiabilité|chance de gain/i))
      .not.toBeInTheDocument()
  })

  it("distingue un champ absent d’un objet vide", () => {
    const { rerender } = render(
      <MarketSignalSnapshot
        kind="confirmed"
        snapshot={{ price: 1 }}
        symbol="ETH/USDC"
        timeframe="1h"
      />,
    )
    expect(screen.getByText(/ne sont pas disponibles pour ce snapshot/)).toBeVisible()
    rerender(
      <MarketSignalSnapshot
        kind="confirmed"
        snapshot={{ price: 1, indicator_signals: {} }}
        symbol="ETH/USDC"
        timeframe="1h"
      />,
    )
    expect(screen.getByText(/n’a été produit pour ce snapshot/)).toBeVisible()
  })

  it("rend uniquement un dictionnaire partiel et transmet les indisponibilités", () => {
    const statuses: IndicatorSignalStatus[] = [
      "insufficient_data", "invalid_data", "disabled",
    ]
    render(
      <MarketSignalSnapshot
        kind="confirmed"
        snapshot={{
          indicator_signals: {
            rsi: { ...signal, status: statuses[0], direction: "neutral" },
            macd: { ...signal, status: statuses[1], direction: "neutral" },
            stochastic: { ...signal, status: statuses[2], direction: "neutral" },
          },
        }}
        symbol="BTC/USDC"
        timeframe="1h"
      />,
    )
    expect(screen.getAllByRole("article")).toHaveLength(3)
    expect(screen.getByText("Données insuffisantes")).toBeVisible()
    expect(screen.getByText("Données invalides")).toBeVisible()
    expect(screen.getByText("Désactivé")).toBeVisible()
    expect(screen.queryByRole("article", { name: "Signal SMA" })).not.toBeInTheDocument()
  })

  it("gère indépendamment l’absence de snapshot confirmé", () => {
    render(
      <MarketSignalSnapshot
        kind="confirmed"
        snapshot={undefined}
        symbol="BTC/USDC"
        timeframe="1h"
      />,
    )
    expect(screen.getByText("Aucun snapshot confirmé reçu pour le moment.")).toBeVisible()
  })
})

describe("MarketSignalSnapshot provisoire", () => {
  it("identifie la bougie ouverte sans la présenter comme finale", () => {
    render(
      <MarketSignalSnapshot
        kind="provisional"
        snapshot={complete}
        symbol="BTC/USDC"
        timeframe="4h"
      />,
    )
    expect(screen.getByRole("heading", { name: "Signaux provisoires" })).toBeVisible()
    expect(screen.getByText("Provisoire")).toBeVisible()
    expect(screen.getByText(/peuvent changer avant sa clôture/)).toBeVisible()
    expect(screen.queryByText(/validation finale/i)).not.toBeInTheDocument()
  })

  it("réagit à une mise à jour de prix et de signal", () => {
    const { rerender } = render(
      <MarketSignalSnapshot
        kind="provisional"
        snapshot={{ price: 10, indicator_signals: { rsi: signal } }}
        symbol="BTC/USDC"
        timeframe="1h"
      />,
    )
    expect(screen.getByText("10")).toBeVisible()
    expect(screen.getByText("Haussier")).toBeVisible()
    rerender(
      <MarketSignalSnapshot
        kind="provisional"
        snapshot={{
          price: 11,
          indicator_signals: {
            rsi: { ...signal, direction: "bearish", signal: "bearish_cross" },
          },
        }}
        symbol="BTC/USDC"
        timeframe="1h"
      />,
    )
    expect(screen.getByText("11")).toBeVisible()
    expect(screen.getByText("Baissier")).toBeVisible()
    expect(screen.queryByText("Haussier")).not.toBeInTheDocument()
  })

  it("gère l’absence indépendante du provisoire", () => {
    render(
      <MarketSignalSnapshot
        kind="provisional"
        snapshot={null}
        symbol="BTC/USDC"
        timeframe="1h"
      />,
    )
    expect(screen.getByText("Aucun snapshot provisoire disponible.")).toBeVisible()
  })
})
