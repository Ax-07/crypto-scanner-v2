import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import {
  IndicatorDirectionBadge,
  IndicatorStatusBadge,
} from "@/components/indicator-signals"

describe("IndicatorStatusBadge", () => {
  it.each([
    ["available", "Disponible"],
    ["insufficient_data", "Données insuffisantes"],
    ["invalid_data", "Données invalides"],
    ["disabled", "Désactivé"],
  ] as const)("renders the %s status with text, icon and accessible name", (status, label) => {
    render(<IndicatorStatusBadge status={status} />)
    expect(screen.getByText(label)).toBeVisible()
    expect(screen.getByLabelText(`Statut : ${label}`)).toBeInTheDocument()
    expect(screen.getByTestId(`status-icon-${status}`)).toHaveAttribute("aria-hidden", "true")
  })

  it("supports compact rendering and a custom class", () => {
    render(<IndicatorStatusBadge status="available" compact className="test-status" />)
    expect(screen.getByLabelText("Statut : Disponible")).toHaveClass("test-status")
    expect(screen.getByText("Disponible")).toBeVisible()
  })
})

describe("IndicatorDirectionBadge", () => {
  it.each([
    ["bullish", "Haussier"],
    ["bearish", "Baissier"],
    ["neutral", "Neutre"],
  ] as const)("renders the %s direction with text, icon and accessible name", (direction, label) => {
    render(<IndicatorDirectionBadge direction={direction} />)
    expect(screen.getByText(label)).toBeVisible()
    expect(screen.getByLabelText(`Direction technique : ${label}`)).toBeInTheDocument()
    expect(screen.getByTestId(`direction-icon-${direction}`)).toHaveAttribute("aria-hidden", "true")
  })

  it("supports compact rendering and a custom class without financial recommendations", () => {
    const { container } = render(
      <IndicatorDirectionBadge direction="bullish" compact className="test-direction" />,
    )
    expect(screen.getByLabelText("Direction technique : Haussier")).toHaveClass("test-direction")
    expect(container).not.toHaveTextContent(/acheter|vendre|gain|recommandation/i)
  })
})
