import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"
import { ScannerResultsTable } from "@/features/scanner/components/scanner-results-table"
import type { ScanConfig, ScanResult } from "@/types/scanner"

const config = { use_rsi: true, use_ma: false, use_macd: false, use_bollinger: false, use_stochastic: false, use_confluence_score: false } as ScanConfig
const result = { symbol: "ETH/USDC", timeframe: "4h", last_close_price: 1234, rsi: 42 } as ScanResult

describe("ScannerResultsTable", () => {
  it("utilise deux colonnes pour l’état vide sans configuration", () => {
    render(<MemoryRouter><ScannerResultsTable config={null} results={[]} /></MemoryRouter>)
    expect(screen.getByText("Aucun résultat pour le moment.")).toHaveAttribute("colspan", "2")
  })

  it("utilise les colonnes du job et lie le symbole au marché", () => {
    render(<MemoryRouter><ScannerResultsTable config={config} results={[result]} /></MemoryRouter>)
    expect(screen.getByRole("columnheader", { name: "RSI" })).toBeInTheDocument()
    expect(screen.queryByRole("columnheader", { name: "MACD" })).not.toBeInTheDocument()
    const href = screen.getByRole("link", { name: "ETH/USDC" }).getAttribute("href")
    expect(href).toContain("/market?symbol=ETH%2FUSDC&timeframe=4h")
    expect(href).toContain("profile=")
  })
})
