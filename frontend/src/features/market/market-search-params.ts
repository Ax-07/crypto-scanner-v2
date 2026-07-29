import type { Timeframe } from "@/types/scanner"
import { parseMarketProfile } from "@/features/market/market-profile"

export const MARKET_TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w"] as const
export const DEFAULT_MARKET = { symbol: "BTC/USDC", timeframe: "1h" as Timeframe }

/** Réduit une valeur d'URL à l'union canonique des timeframes. */
export function isTimeframe(value: string | null): value is Timeframe {
  return MARKET_TIMEFRAMES.includes(value as Timeframe)
}

/** Accepte uniquement la forme canonique majuscule BASE/QUOTE. */
export function isSymbol(value: string | null): value is string {
  return Boolean(value && /^[A-Z0-9]+\/[A-Z0-9]+$/.test(value))
}

/** Lit les paramètres partageables et remplace toute valeur invalide par le marché par défaut. */
export function parseMarketSearch(params: URLSearchParams) {
  const rawSymbol = params.get("symbol")
  const rawTimeframe = params.get("timeframe")
  return {
    symbol: isSymbol(rawSymbol) ? rawSymbol : DEFAULT_MARKET.symbol,
    timeframe: isTimeframe(rawTimeframe) ? rawTimeframe : DEFAULT_MARKET.timeframe,
    profile: parseMarketProfile(params.get("profile")),
  }
}
