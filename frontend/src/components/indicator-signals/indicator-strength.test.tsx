import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { IndicatorStrength, getStrengthCategory } from "@/components/indicator-signals"

describe("IndicatorStrength", () => {
  it.each([
    [0, 0],
    [0.25, 25],
    [0.5, 50],
    [0.75, 75],
    [1, 100],
  ])("renders %s as an intensity of %s", (value, expected) => {
    render(<IndicatorStrength value={value} />)
    const progress = screen.getByRole("progressbar", {
      name: `Intensité technique : ${expected} sur 100`,
    })
    expect(progress).toHaveAttribute("aria-valuemin", "0")
    expect(progress).toHaveAttribute("aria-valuemax", "100")
    expect(progress).toHaveAttribute("aria-valuenow", String(expected))
    expect(screen.getByText(`Intensité ${expected}/100`)).toBeVisible()
  })

  it.each([
    [-1, 0],
    [2, 100],
    [Number.NaN, 0],
    [Number.POSITIVE_INFINITY, 0],
  ])("safely clamps %s to %s", (value, expected) => {
    render(<IndicatorStrength value={value} />)
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", String(expected))
  })

  it("supports compact and value-hidden modes while keeping an accessible label", () => {
    render(<IndicatorStrength value={0.75} compact showValue={false} className="test-strength" />)
    expect(screen.queryByText("Intensité 75/100")).not.toBeInTheDocument()
    expect(screen.getByRole("progressbar", {
      name: "Intensité technique : 75 sur 100",
    }).parentElement).toHaveClass("test-strength")
  })

  it("uses descriptive categories and never presents a financial promise", () => {
    expect([0, 25, 50, 75, 90].map(getStrengthCategory)).toEqual([
      "Très faible",
      "Faible",
      "Modérée",
      "Forte",
      "Très forte",
    ])
    const { container } = render(<IndicatorStrength value={0.9} />)
    expect(container).not.toHaveTextContent(/probabilité|réussite|gain garanti/i)
  })
})
