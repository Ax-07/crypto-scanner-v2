import { useEffect } from "react";

import { scannerApi } from "@/api/scanner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { ScannerConfigForm } from "@/features/scanner/components/scanner-config-form";
import { ScannerResultsTable } from "@/features/scanner/components/scanner-results-table";
import { useScannerStore } from "@/stores/scanner-store";

/** Relie le formulaire, la progression et les résultats au cycle de vie du store scanner. */
export function ScannerWorkspace() {
  const config = useScannerStore((state) => state.config);
  const job = useScannerStore((state) => state.job);
  const results = useScannerStore((state) => state.results);
  const status = useScannerStore((state) => state.status);
  const error = useScannerStore((state) => state.error);
  const loadConfig = useScannerStore((state) => state.loadConfig);
  const startScan = useScannerStore((state) => state.startScan);
  const cancelScan = useScannerStore((state) => state.cancelScan);

  useEffect(() => {
    if (!config) void loadConfig();
  }, [config, loadConfig]);
  const running = status === "starting" || status === "running" || status === "cancelling";

  return (
    <div className="space-y-4">
      {error && (
        <Alert className="border-destructive/50">
          <AlertTitle>Une erreur est survenue</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {job && (
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Progression du scan</CardTitle>
            <div className="flex gap-2">
              {job.status === "completed" && (
                <Button variant="secondary" asChild>
                  <a href={scannerApi.exportUrl(job.id)}>Exporter CSV</a>
                </Button>
              )}
              <Button
                variant="outline"
                disabled={!running || status === "cancelling"}
                onClick={() => void cancelScan()}
              >
                {status === "cancelling" ? "Annulation…" : "Arrêter"}
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            <Progress value={job.progress.percent} aria-label={`Progression ${job.progress.percent}%`} />
            <p className="text-sm text-muted-foreground">
              {job.progress.processed}/{job.progress.total} traitées · {job.progress.successful} résultats ·{" "}
              {job.progress.filtered} filtrées · {job.progress.errors} erreurs
            </p>
          </CardContent>
        </Card>
      )}
      {!config ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <ScannerConfigForm config={config} busy={running} onSubmit={startScan} />
      )}
      <ScannerResultsTable results={results} config={job?.config ?? null} />
    </div>
  );
}
