import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it } from "vitest"

import { MarketConnectionStatus } from "@/features/market/components/market-connection-status"
import { useMarketStore } from "@/stores/market-store"
import type { ConnectionStatus } from "@/types/market"

describe("MarketConnectionStatus", () => {
  beforeEach(() => useMarketStore.setState({
    status: "disconnected",
    connectionError: null,
  }))

  it.each([
    ["connecting", "Connexion…"],
    ["connected", "Temps réel connecté"],
    ["disconnected", "Déconnecté"],
    ["error", "Erreur de connexion"],
  ] as const)("affiche l’état %s avec un libellé textuel", (status, label) => {
    useMarketStore.setState({ status: status as ConnectionStatus })
    render(<MarketConnectionStatus />)
    expect(screen.getByText(label)).toBeVisible()
  })

  it("annonce la reconnexion automatique sans inventer de compteur", () => {
    render(<MarketConnectionStatus />)
    expect(screen.getByText(/reconnexion est automatique/i)).toBeVisible()
    expect(screen.queryByText(/tentative \d/i)).not.toBeInTheDocument()
  })

  it("affiche une erreur compréhensible et précise que les données restent visibles", () => {
    useMarketStore.setState({
      status: "error",
      connectionError: "Message WebSocket invalide",
      snapshot: { confirmed: { price: 42 } },
    })
    render(<MarketConnectionStatus />)
    expect(screen.getByRole("alert")).toHaveTextContent("Flux temps réel indisponible")
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Les dernières données reçues restent affichées et peuvent être figées.",
    )
    expect(screen.getByRole("alert")).toHaveTextContent("Message WebSocket invalide")
    expect(useMarketStore.getState().snapshot.confirmed?.price).toBe(42)
  })
})
