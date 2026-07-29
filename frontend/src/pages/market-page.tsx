import { useEffect, useMemo } from "react";
import { Activity } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { IndicatorToolbar } from "@/components/dashboard/indicator-toolbar";
import { MarketMetrics } from "@/components/dashboard/market-metrics";
import { TradingChart } from "@/components/dashboard/trading-chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MarketConnectionStatus } from "@/features/market/components/market-connection-status";
import { MarketSignalsSection } from "@/features/market/components/market-signals-section";
import { MarketToolbar } from "@/features/market/components/market-toolbar";
import { parseMarketSearch } from "@/features/market/market-search-params";
import { serializeMarketProfile } from "@/features/market/market-profile";
import { useMarketHistory } from "@/features/market/use-market-history";
import { useMarketSocket } from "@/features/market/use-market-socket";
import { useMarketStore } from "@/stores/market-store";

export function MarketPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const market = useMemo(() => parseMarketSearch(searchParams), [searchParams]);
  const { symbol, timeframe, profile } = market;
  const history = useMarketHistory(symbol, timeframe, profile);
  const socketReady = useMarketStore(
    (state) => state.historyInitialized && state.selectionKey === `${symbol}|${timeframe}`,
  );
  const count = useMarketStore((state) => state.loadedCandleCount);
  useMarketSocket(symbol, timeframe, socketReady, count === 0, profile);

  const coverage = useMarketStore((state) => state.coverage);
  const memoryLimit = useMarketStore((state) => state.memoryLimit);
  const hasMore = useMarketStore((state) => state.hasMoreBefore);
  const hasMoreAfter = useMarketStore((state) => state.hasMoreAfter);
  const mode = useMarketStore((state) => state.mode);
  const historyLoading = useMarketStore((state) => state.historyLoading);
  const loadingBefore = useMarketStore((state) => state.loadingBefore);
  const loadingAfter = useMarketStore((state) => state.loadingAfter);
  const jumpingToDate = useMarketStore((state) => state.jumpingToDate);
  const earliestLoadedTime = useMarketStore((state) => state.earliestLoadedTime);
  const latestLoadedTime = useMarketStore((state) => state.latestLoadedTime);
  const downloaded = useMarketStore((state) => state.downloadedFromExchange);
  const historyError = useMarketStore((state) => state.historyError);
  const snapshot = useMarketStore((state) => state.snapshot);
  const issueChartCommand = useMarketStore((state) => state.issueChartCommand);

  useEffect(() => {
    if (searchParams.get("symbol") !== symbol || searchParams.get("timeframe") !== timeframe) {
      setSearchParams(
        {
          symbol,
          timeframe,
          ...(searchParams.get("profile") ? { profile: serializeMarketProfile(profile) } : {}),
        },
        { replace: true },
      );
    }
  }, [symbol, timeframe, profile, searchParams, setSearchParams]);

  return (
    <div className="flex w-full flex-col gap-4">
      <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
        <div>
          <h1 className="text-2xl font-bold">Marché en temps réel</h1>
          <p className="text-muted-foreground">Historique SQLite progressif et mises à jour Binance en direct.</p>
        </div>
        <MarketToolbar
          {...market}
          onChange={(next) =>
            setSearchParams({
              ...next,
              profile: serializeMarketProfile(profile),
            })
          }
          onLoadMore={() => void history.loadMore()}
          onLoadMoreAfter={() => void history.loadMoreAfter()}
          onGoBeginning={() => void history.goToBeginning()}
          onJumpToDate={(anchorTime) => void history.jumpToDate(anchorTime)}
          onReturnToLive={() => void history.returnToLive()}
          onChartCommand={issueChartCommand}
          mode={mode}
          historyLoading={historyLoading}
          loadingBefore={loadingBefore}
          loadingAfter={loadingAfter}
          jumpingToDate={jumpingToDate}
          loadingAll={history.loadingAll}
          hasMoreBefore={hasMore}
          hasMoreAfter={hasMoreAfter}
        />
      </div>
      <MarketConnectionStatus />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border px-3 py-2 text-xs text-muted-foreground">
        <span>{count.toLocaleString("fr-FR")} bougies chargées</span>
        <span>{coverage?.total_candles.toLocaleString("fr-FR") ?? "—"} disponibles</span>
        <span>Couverture {coverage?.is_complete ? "complète" : "partielle"}</span>
        <span>{coverage?.gap_count ?? 0} trou(s)</span>
        <span>Mode {mode === "live" ? "direct" : "historique"}</span>
        <span>Profil {profile.origin === "scan" ? "du scan" : profile.origin}</span>
        <span>
          Exchange Binance · {symbol} · {timeframe}
        </span>
        <span>
          RSI {profile.rsi_period} · MACD {profile.macd_fast_period}/{profile.macd_slow_period}/
          {profile.macd_signal_period}
        </span>
        {snapshot.confirmed?.timestamp ? (
          <span>
            Dernière clôture utilisée : {new Date(snapshot.confirmed.timestamp * 1_000).toLocaleString("fr-FR")}
          </span>
        ) : null}
        {earliestLoadedTime !== null && latestLoadedTime !== null ? (
          <span>
            Période : {new Date(earliestLoadedTime).toLocaleDateString("fr-FR")}
            {" → "}
            {new Date(latestLoadedTime).toLocaleDateString("fr-FR")}
          </span>
        ) : null}
        {downloaded > 0 ? <span>{downloaded.toLocaleString("fr-FR")} téléchargée(s)</span> : null}
        {memoryLimit ? <span>Limite mémoire active : {memoryLimit.toLocaleString("fr-FR")}</span> : null}
        {historyError ? (
          <button className="text-destructive underline" onClick={history.retry}>
            {historyError} · Réessayer
          </button>
        ) : null}
      </div>
      <MarketMetrics />
      <IndicatorToolbar />
      <Card className="overflow-hidden">
        <CardHeader className="border-b py-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Activity className="size-4 text-primary" />
            Graphique de marché · {market.symbol} · {market.timeframe}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <TradingChart onLoadMore={history.loadMore} />
        </CardContent>
      </Card>
      <MarketSignalsSection symbol={symbol} timeframe={timeframe} />
    </div>
  );
}
