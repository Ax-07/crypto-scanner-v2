import { Link, createSearchParams } from "react-router-dom";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ScanConfig, ScanResult } from "@/types/scanner";
import { marketProfileFromScan, serializeMarketProfile } from "@/features/market/market-profile";

/** Affiche des colonnes dérivées de la configuration figée du job exécuté. */
export function ScannerResultsTable({ results, config }: { results: ScanResult[]; config: ScanConfig | null }) {
  // Deux colonnes sont fixes ; filter(Boolean).length produit toujours un entier fini.
  const columnCount =
    2 +
    [
      config?.use_rsi,
      config?.use_ma,
      config?.use_macd,
      config?.use_bollinger,
      config?.use_stochastic,
      config?.use_confluence_score,
    ].filter(Boolean).length;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Opportunités</CardTitle>
        <CardDescription>Les colonnes correspondent à la configuration figée du job.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Symbole</TableHead>
                <TableHead>Prix</TableHead>
                {config?.use_rsi && <TableHead>RSI</TableHead>}
                {config?.use_ma && <TableHead>Tendance</TableHead>}
                {config?.use_macd && <TableHead>MACD</TableHead>}
                {config?.use_bollinger && <TableHead>Bollinger</TableHead>}
                {config?.use_stochastic && <TableHead>Stochastique</TableHead>}
                {config?.use_confluence_score && <TableHead>Confluence</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {results.map((result) => (
                <TableRow key={result.symbol}>
                  <TableCell>
                    <Link
                      className="font-medium text-primary underline-offset-4 hover:underline"
                      to={{
                        pathname: "/market",
                        search: createSearchParams({
                          symbol: result.symbol,
                          timeframe: result.timeframe,
                          ...(config ? { profile: serializeMarketProfile(marketProfileFromScan(config)) } : {}),
                        }).toString(),
                      }}
                    >
                      {result.symbol}
                    </Link>
                  </TableCell>
                  <TableCell>{formatPrice(result.last_close_price)}</TableCell>
                  {config?.use_rsi && <TableCell>{format(result.rsi)}</TableCell>}
                  {config?.use_ma && (
                    <TableCell>
                      <details>
                        <summary>
                          {result.trend_score ?? "—"} haussier(s) · net {result.trend_net_score ?? "—"}
                        </summary>
                        {Object.entries(result.trend_states ?? {}).map(([timeframe, state]) => (
                          <div key={timeframe} className="text-xs">
                            {timeframe} : {label(state)}
                          </div>
                        ))}
                      </details>
                    </TableCell>
                  )}
                  {config?.use_macd && <TableCell>{label(result.macd_signal_type)}</TableCell>}
                  {config?.use_bollinger && <TableCell>{label(result.bb_position)}</TableCell>}
                  {config?.use_stochastic && <TableCell>{label(result.stoch_signal)}</TableCell>}
                  {config?.use_confluence_score && (
                    <TableCell>
                      <details>
                        <summary>
                          {format(result.confluence_score)} {result.confluence_grade ?? ""}
                        </summary>
                        {Object.entries(result.confluence_details ?? {}).map(([name, detail]) => (
                          <div key={name} className="text-xs">
                            {name}: {detail.status === "available" ? format(detail.contribution) : "Indisponible"}
                          </div>
                        ))}
                      </details>
                    </TableCell>
                  )}
                </TableRow>
              ))}
              {!results.length && (
                <TableRow>
                  <TableCell colSpan={columnCount} className="h-24 text-center text-muted-foreground">
                    Aucun résultat pour le moment.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
const labels: Record<string, string> = {
  bullish: "Haussier",
  bearish: "Baissier",
  neutral: "Neutre",
  unavailable: "Indisponible",
  oversold: "Survente",
  overbought: "Surachat",
  near_oversold: "Proche survente",
  near_overbought: "Proche surachat",
  bullish_cross: "Croisement haussier",
  bearish_cross: "Croisement baissier",
};
/** Traduit un signal connu et affiche un tiret pour une valeur absente. */
const label = (value: string | null) => (value ? (labels[value] ?? value) : "—");
/** Formate une métrique sur deux décimales, ou un tiret si elle est absente. */
const format = (value: number | null) => (value == null ? "—" : value.toFixed(2));
/** Préserve jusqu'à huit chiffres significatifs, y compris pour les actifs de faible prix. */
const formatPrice = (value: number | null) =>
  value == null ? "—" : value.toLocaleString("fr-FR", { maximumSignificantDigits: 8 });
