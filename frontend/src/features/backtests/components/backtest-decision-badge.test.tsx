import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { BacktestDecisionBadge } from "@/features/backtests/components/backtest-decision-badge"

describe("BacktestDecisionBadge", () => {
  it.each([
    [true, "Signal accepté"],
    [false, "Signal rejeté"],
  ])("affiche la décision backend %s avec texte et icône", (accepted, label) => {
    const { container } = render(<BacktestDecisionBadge accepted={accepted} />)
    expect(screen.getByText(label)).toBeVisible()
    expect(screen.getByLabelText(`Décision du moteur : ${label}`)).toBeVisible()
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true")
  })

  it("ne déduit pas une entrée ou une performance", () => {
    render(<BacktestDecisionBadge accepted />)
    expect(screen.queryByText(/entrée|sortie|gain|perte/i)).not.toBeInTheDocument()
  })
})
