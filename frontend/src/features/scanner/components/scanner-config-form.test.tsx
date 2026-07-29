import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeAll, describe, expect, it, vi } from "vitest"

import { ScannerConfigForm } from "@/features/scanner/components/scanner-config-form"
import { createScanConfig } from "@/test/scanner-fixtures"

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
})

describe("ScannerConfigForm structured filters", () => {
  it("charge une configuration historique et soumet le nouveau contrat avec le legacy", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <ScannerConfigForm
        config={createScanConfig({
          filter_stoch_signal: ["bullish_cross", "oversold"],
        })}
        busy={false}
        onSubmit={onSubmit}
      />,
    )

    expect(screen.getByLabelText("Événement / classe : Croisement haussier"))
      .toHaveAttribute("data-state", "checked")
    expect(screen.getByLabelText("Événement / classe : Survente"))
      .toHaveAttribute("data-state", "checked")

    await waitFor(() => expect(screen.getByRole("button", { name: "Appliquer et lancer" })).toBeEnabled())
    fireEvent.click(screen.getByRole("button", { name: "Appliquer et lancer" }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce())
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      filter_stoch_signal: ["bullish_cross", "oversold"],
      structured_signal_filters: {
        version: 1,
        indicators: {
          stochastic: {
            match: "any",
            conditions: [{
              field: "signal",
              values: ["bullish_cross", "oversold"],
            }],
          },
        },
      },
    })
  })

  it("configure un événement Bollinger et la logique all", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <ScannerConfigForm
        config={createScanConfig()}
        busy={false}
        onSubmit={onSubmit}
      />,
    )
    fireEvent.click(screen.getByLabelText("Réintégration de la bande basse"))
    fireEvent.change(screen.getByLabelText("Correspondance", { selector: "#bollinger-filter-match" }), {
      target: { value: "all" },
    })
    await waitFor(() => expect(screen.getByRole("button", { name: "Appliquer et lancer" })).toBeEnabled())
    fireEvent.click(screen.getByRole("button", { name: "Appliquer et lancer" }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce())
    expect(onSubmit.mock.calls[0][0].structured_signal_filters.indicators.bollinger)
      .toEqual({
        match: "all",
        conditions: [{ field: "signal", values: ["lower_band_reentry"] }],
      })
  })

  it("désactive les contrôles pendant un scan", () => {
    render(
      <ScannerConfigForm
        config={createScanConfig()}
        busy
        onSubmit={vi.fn()}
      />,
    )
    expect(screen.getByLabelText("Direction haussière")).toBeDisabled()
    expect(screen.getByRole("button", { name: "Appliquer et lancer" })).toBeDisabled()
  })
})
