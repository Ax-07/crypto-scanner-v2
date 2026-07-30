import type { PortfolioSimulationConfig } from "@/types/portfolio"

export interface PortfolioFormValues {
  portfolio_simulation_enabled: boolean
  portfolio_simulation: {
    quote_asset: string
    initial_capital: string
    position_size_percent: string
    fee_percent: string
    slippage_percent: string
  }
}

export const DEFAULT_PORTFOLIO_FORM_VALUES: PortfolioFormValues = {
  portfolio_simulation_enabled: false,
  portfolio_simulation: {
    quote_asset: "USDC",
    initial_capital: "10000",
    position_size_percent: "100",
    fee_percent: "0,1",
    slippage_percent: "0",
  },
}

function normalizedDecimal(value: string): string | null {
  const compact = value.trim().replace(/\s+/g, "").replace(",", ".")
  if (!/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(compact)) return null
  const [integer, fraction] = compact.split(".")
  const cleanFraction = fraction?.replace(/0+$/, "")
  return cleanFraction ? `${integer}.${cleanFraction}` : integer
}

export function percentageInputToRatioString(value: string): string | null {
  const normalized = normalizedDecimal(value)
  if (normalized === null) return null
  const [integer, fraction = ""] = normalized.split(".")
  const digits = `${integer}${fraction}`.replace(/^0+(?=\d)/, "")
  const scale = fraction.length + 2
  const padded = digits.padStart(scale + 1, "0")
  const whole = padded.slice(0, -scale)
  const decimals = padded.slice(-scale).replace(/0+$/, "")
  return decimals ? `${whole}.${decimals}` : whole
}

export function ratioStringToPercentageInput(value: string): string | null {
  const normalized = normalizedDecimal(value)
  if (normalized === null) return null
  const [integer, fraction = ""] = normalized.split(".")
  const digits = `${integer}${fraction}`
  const scale = fraction.length - 2
  const padded = scale > 0
    ? digits.padStart(scale + 1, "0")
    : `${digits}${"0".repeat(-scale)}`
  const whole = scale > 0 ? padded.slice(0, -scale) : padded
  const decimals = scale > 0 ? padded.slice(-scale).replace(/0+$/, "") : ""
  const cleanWhole = whole.replace(/^0+(?=\d)/, "") || "0"
  return decimals ? `${cleanWhole}.${decimals}` : cleanWhole
}

export function deriveQuoteAsset(symbols: string): string | null {
  const items = symbols.split(",").map((item) => item.trim()).filter(Boolean)
  if (items.length !== 1 || !items[0].includes("/")) return null
  const quote = items[0].split("/").pop()?.trim().toUpperCase()
  return quote || null
}

export function buildPortfolioSimulationPayload(
  values: PortfolioFormValues,
): PortfolioSimulationConfig | undefined {
  if (!values.portfolio_simulation_enabled) return undefined
  const feeRate = percentageInputToRatioString(values.portfolio_simulation.fee_percent)
  const slippageRate = percentageInputToRatioString(values.portfolio_simulation.slippage_percent)
  if (feeRate === null || slippageRate === null) {
    throw new Error("Pourcentage de portefeuille invalide")
  }
  const initialCapital = normalizedDecimal(values.portfolio_simulation.initial_capital)
  const positionSize = normalizedDecimal(values.portfolio_simulation.position_size_percent)
  if (initialCapital === null || positionSize === null) {
    throw new Error("Montant de portefeuille invalide")
  }
  return {
    version: 1,
    quote_asset: values.portfolio_simulation.quote_asset.trim().toUpperCase(),
    initial_capital: initialCapital,
    position_sizing: { mode: "percent_cash", value: positionSize },
    execution_policy: "next_open",
    fee_rate: feeRate,
    slippage_rate: slippageRate,
    end_of_test_policy: "force_close",
  }
}
