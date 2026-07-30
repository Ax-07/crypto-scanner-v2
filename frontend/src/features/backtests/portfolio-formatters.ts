const amountFormatter = new Intl.NumberFormat("fr-FR", {
  maximumFractionDigits: 8,
})
const ratioFormatter = new Intl.NumberFormat("fr-FR", {
  style: "percent",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
})

export function parseDecimalForDisplay(value: string): number | null {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function formatDecimalAmount(
  value: string | null,
  quoteAsset?: string,
): string {
  if (value === null) return "—"
  const parsed = parseDecimalForDisplay(value)
  if (parsed === null) return "—"
  const formatted = amountFormatter.format(parsed)
  return quoteAsset ? `${formatted} ${quoteAsset}` : formatted
}

export function formatDecimalRatio(value: string | null): string {
  if (value === null) return "—"
  const parsed = parseDecimalForDisplay(value)
  return parsed === null ? "—" : ratioFormatter.format(parsed)
}

export function formatSignedAmount(value: string, quoteAsset: string): string {
  const parsed = parseDecimalForDisplay(value)
  if (parsed === null) return "—"
  const prefix = parsed > 0 ? "+" : ""
  return `${prefix}${formatDecimalAmount(value, quoteAsset)}`
}
