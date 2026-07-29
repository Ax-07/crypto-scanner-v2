import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, type Resolver } from "react-hook-form";

import { backtestApi } from "@/api/backtests";
import { scannerApi } from "@/api/scanner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { backtestFormSchema, parseHorizons, type BacktestFormValues } from "@/features/backtests/backtest-schema";
import { BacktestObservationsTable } from "@/features/backtests/components/backtest-observations-table";
import { useBacktestStore } from "@/stores/backtest-store";
import type { BacktestConfig, BacktestJob, BacktestSummary } from "@/types/backtest";
import type { ScanConfig } from "@/types/scanner";

const now = new Date();
const monthAgo = new Date(now.getTime() - 30 * 86_400_000);
const localValue = (date: Date) =>
  new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
const defaults: BacktestFormValues = {
  symbols: "BTC/USDC",
  start: localValue(monthAgo),
  end: localValue(now),
  timeframe: "4h",
  horizons: "1, 3, 6, 12, 24",
  replay_mode: "every_bar",
  entry_policy: "signal_close",
  gap_policy: "reject_range",
  fee_bps: 0,
  slippage_bps: 0,
  use_rsi: true,
  rsi_threshold: 35,
  use_ma: true,
  min_trend_score: 2,
  use_confluence_score: true,
  min_confluence_score: 60,
};

export function BacktestsPage() {
  const [profile, setProfile] = useState<ScanConfig | null>(null);
  const [history, setHistory] = useState<BacktestJob[]>([]);
  const job = useBacktestStore((state) => state.job);
  const busy = useBacktestStore((state) => state.busy);
  const error = useBacktestStore((state) => state.error);
  const start = useBacktestStore((state) => state.start);
  const cancel = useBacktestStore((state) => state.cancel);
  const load = useBacktestStore((state) => state.load);
  const resume = useBacktestStore((state) => state.resume);
  
  const form = useForm<BacktestFormValues>({
    resolver: zodResolver(backtestFormSchema) as Resolver<BacktestFormValues>,
    defaultValues: defaults,
    mode: "onChange",
  });
  
  useEffect(() => {
    const controller = new AbortController();
    scannerApi
      .getDefaultConfig(controller.signal)
      .then(setProfile)
      .catch(() => undefined);
    backtestApi
      .list()
      .then((page) => setHistory(page.items))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);
  
  const submit = form.handleSubmit(async (values) => {
    if (!profile) return;
  
    const signalConfig: ScanConfig = {
      ...profile,
      timeframe: values.timeframe,
      use_rsi: values.use_rsi,
      rsi_threshold: values.rsi_threshold,
      use_ma: values.use_ma,
      min_trend_score: values.min_trend_score,
      use_confluence_score: values.use_confluence_score,
      min_confluence_score: values.min_confluence_score,
    };
  
    const config: BacktestConfig = {
      symbols: values.symbols
        .split(",")
        .map((item) => item.trim().toUpperCase())
        .filter(Boolean),
      start: new Date(values.start).toISOString(),
      end: new Date(values.end).toISOString(),
      signal_config: signalConfig,
      horizons: parseHorizons(values.horizons),
      replay_mode: values.replay_mode,
      entry_policy: values.entry_policy,
      gap_policy: values.gap_policy,
      fee_bps: values.fee_bps,
      slippage_bps: values.slippage_bps,
      snapshot_status: "confirmed",
    };
    await start(config);
  });
  return (
    <div className="flex w-full flex-col gap-5">
      <div>
        <h1 className="text-2xl font-bold">Backtests</h1>
        <p className="text-muted-foreground">
          Exécutez un backtest sur des symboles et horizons choisis, avec les paramètres du scanner. Les résultats sont persistants et reproductibles.
        </p>
      </div>
      <form onSubmit={submit} noValidate>
        <Card>
          <CardHeader>
            <CardTitle>Configuration du backtest</CardTitle>
            <CardDescription>Les paramètres techniques reprennent le profil canonique du scanner.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <FieldGroup className="md:grid-cols-3">
              <TextField form={form} name="symbols" label="Symboles (séparés par des virgules)" />
              <TextField form={form} name="start" label="Début UTC" type="datetime-local" />
              <TextField form={form} name="end" label="Fin UTC" type="datetime-local" />
              <SelectField
                form={form}
                name="timeframe"
                label="Timeframe"
                options={["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w"]}
              />
              <TextField form={form} name="horizons" label="Horizons (bougies)" />
              <SelectField
                form={form}
                name="replay_mode"
                label="Mode de rejeu"
                options={["every_bar", "state_changes", "filtered_signals"]}
              />
              <SelectField
                form={form}
                name="entry_policy"
                label="Politique d'entrée"
                options={["signal_close", "next_open"]}
              />
              <SelectField
                form={form}
                name="gap_policy"
                label="Trous de données"
                options={["reject_range", "skip_affected", "allow_with_warning"]}
              />
              <NumberField form={form} name="fee_bps" label="Frais (bps)" />
              <NumberField form={form} name="slippage_bps" label="Slippage (bps)" />
            </FieldGroup>
            <div className="grid gap-4 md:grid-cols-3">
              <ToggleCard form={form} name="use_rsi" title="RSI">
                <NumberField form={form} name="rsi_threshold" label="Seuil RSI" />
              </ToggleCard>
              <ToggleCard form={form} name="use_ma" title="Tendance">
                <NumberField form={form} name="min_trend_score" label="Score minimum" />
              </ToggleCard>
              <ToggleCard form={form} name="use_confluence_score" title="Confluence">
                <NumberField form={form} name="min_confluence_score" label="Score minimum" />
              </ToggleCard>
            </div>
            <div className="flex justify-end gap-2">
              {busy ? (
                <Button type="button" variant="outline" onClick={() => void cancel()}>
                  Annuler
                </Button>
              ) : null}
              <Button type="submit" disabled={!profile || busy || !form.formState.isValid}>
                {busy ? "Exécution…" : "Lancer le backtest"}
              </Button>
            </div>
          </CardContent>
        </Card>
      </form>
      {error ? (
        <Alert className="border-destructive">
          <AlertTitle>Backtest interrompu</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {history.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Historique persistant</CardTitle>
            <CardDescription>
              Rouvrez un résultat après redémarrage ou reprenez un calcul interrompu depuis son checkpoint.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Création</TableHead>
                  <TableHead>Statut</TableHead>
                  <TableHead>Progression</TableHead>
                  <TableHead>Dataset</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{new Date(item.created_at).toLocaleString()}</TableCell>
                    <TableCell>
                      <Badge>{item.status}</Badge>
                    </TableCell>
                    <TableCell>{item.progress.percent} %</TableCell>
                    <TableCell className="max-w-48 truncate">{item.dataset_version}</TableCell>
                    <TableCell>
                      <Button type="button" size="sm" variant="outline" onClick={() => void load(item.id)}>
                        Ouvrir
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
      {job?.status === "interrupted" && job.checkpoint ? (
        <div className="flex justify-end">
          <Button type="button" onClick={() => void resume()}>
            Reprendre depuis le checkpoint
          </Button>
        </div>
      ) : null}
      {job ? <Results job={job} /> : null}
    </div>
  );
}

type Form = ReturnType<typeof useForm<BacktestFormValues>>;
function TextField({
  form,
  name,
  label,
  type = "text",
}: {
  form: Form;
  name: "symbols" | "start" | "end" | "horizons";
  label: string;
  type?: string;
}) {
  const error = form.formState.errors[name];
  return (
    <Field data-invalid={Boolean(error)}>
      <FieldLabel htmlFor={name}>{label}</FieldLabel>
      <Input id={name} type={type} aria-invalid={Boolean(error)} {...form.register(name)} />
      <FieldError errors={[error ?? {}]} />
    </Field>
  );
}
function NumberField({
  form,
  name,
  label,
}: {
  form: Form;
  name: "fee_bps" | "slippage_bps" | "rsi_threshold" | "min_trend_score" | "min_confluence_score";
  label: string;
}) {
  const error = form.formState.errors[name];
  return (
    <Field>
      <FieldLabel htmlFor={name}>{label}</FieldLabel>
      <Input id={name} type="number" step="any" {...form.register(name, { valueAsNumber: true })} />
      <FieldError errors={[error ?? {}]} />
    </Field>
  );
}
function SelectField({
  form,
  name,
  label,
  options,
}: {
  form: Form;
  name: "timeframe" | "replay_mode" | "entry_policy" | "gap_policy";
  label: string;
  options: string[];
}) {
  return (
    <Field>
      <FieldLabel htmlFor={name}>{label}</FieldLabel>
      <select id={name} className="h-9 rounded-md border bg-background px-3" {...form.register(name)}>
        {options.map((option) => (
          <option key={option}>{option}</option>
        ))}
      </select>
    </Field>
  );
}
function ToggleCard({
  form,
  name,
  title,
  children,
}: {
  form: Form;
  name: "use_rsi" | "use_ma" | "use_confluence_score";
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-3 rounded-lg border p-4">
      <div className="flex items-center justify-between">
        <FieldLabel htmlFor={name}>{title}</FieldLabel>
        <Switch
          id={name}
          checked={form.watch(name)}
          onCheckedChange={(value) => form.setValue(name, value, { shouldValidate: true })}
        />
      </div>
      {children}
    </div>
  );
}
function Results({ job }: { job: BacktestJob }) {
  const summary = job.summary;
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Progression</CardTitle>
            <Badge>{job.status}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          <Progress value={job.progress.percent} />
          <div className="flex justify-between text-sm text-muted-foreground">
            <span>
              {job.progress.phase} · {job.progress.current_symbol ?? "analyse globale"}
            </span>
            <span>
              {job.progress.processed}/{job.progress.total} ({job.progress.percent} %)
            </span>
          </div>
        </CardContent>
      </Card>
      {summary ? (
        <>
          <div className="grid gap-3 sm:grid-cols-4">
            <Metric title="Observations" value={summary.observation_count} />
            <Metric title="Acceptées" value={summary.accepted_count} />
            <Metric title="Rejetées" value={summary.rejected_count} />
            <Metric title="Censurées" value={summary.censored_count} />
          </div>
          {summary.warnings.length ? (
            <Alert>
              <AlertTitle>Avertissements de qualité</AlertTitle>
              <AlertDescription>{summary.warnings.join(" · ")}</AlertDescription>
            </Alert>
          ) : null}
          <div className="grid gap-5 xl:grid-cols-2">
            <HorizonTable summary={summary} />
            <Funnel summary={summary} />
          </div>
          <ResearchPanels correlations={job.correlations} ablations={job.ablations} />
          <Card>
            <CardHeader>
              <CardTitle>Exports reproductibles</CardTitle>
              <CardDescription>
                L’export des observations inclut les signaux structurés au format JSON.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              <Button asChild variant="outline">
                <a href={backtestApi.summaryUrl(job.id)}>Résumé JSON</a>
              </Button>
              {["observations", "outcomes", "correlations", "ablations"].map((dataset) => (
                <Button key={dataset} asChild variant="outline">
                  <a href={backtestApi.exportUrl(job.id, dataset)}>{dataset}.csv</a>
                </Button>
              ))}
            </CardContent>
          </Card>
        </>
      ) : null}
      <BacktestObservationsTable job={job} />
    </div>
  );
}
function Metric({ title, value }: { title: string; value: number }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-2xl">{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}
function HorizonTable({ summary }: { summary: BacktestSummary }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Rendements nets par horizon</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Bougies</TableHead>
              <TableHead>N</TableHead>
              <TableHead>Moyenne</TableHead>
              <TableHead>Positifs</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {Object.entries(summary.horizons).map(([horizon, stats]) => (
              <TableRow key={horizon}>
                <TableCell>{horizon}</TableCell>
                <TableCell>{number(stats.count) ?? 0}</TableCell>
                <TableCell>{formatPercent(number(stats.mean))}</TableCell>
                <TableCell>{formatPercent(number(stats.positive_rate))}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
function Funnel({ summary }: { summary: BacktestSummary }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Funnel des filtres</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {summary.filter_funnel.map((item) => (
          <div key={item.stage}>
            <div className="flex justify-between text-sm">
              <span>{item.stage}</span>
              <span>
                {item.passed}/{item.input}
              </span>
            </div>
            <Progress value={item.input ? (item.passed / item.input) * 100 : 0} />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
function ResearchPanels({
  correlations,
  ablations,
}: {
  correlations: Record<string, unknown> | null;
  ablations: Record<string, unknown> | null;
}) {
  const horizons = record(correlations?.by_horizon);
  const firstHorizon = Object.keys(horizons)[0];
  const pearson = record(record(horizons[firstHorizon])?.pearson);
  const outcome = record(pearson.outcome);
  const availability = record(correlations?.availability);
  return (
    <div className="grid gap-5 xl:grid-cols-3">
      <Card>
        <CardHeader>
          <CardTitle>Corrélations Pearson</CardTitle>
          <CardDescription>Horizon {firstHorizon ?? "—"} · effectifs pairwise dans l'export.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {Object.entries(outcome).map(([name, value]) => (
            <div key={name} className="grid grid-cols-[1fr_auto] gap-3 border-b py-1 text-sm">
              <span>{name}</span>
              <span>{number(value)?.toFixed(3) ?? "n/d"}</span>
            </div>
          )) || "Aucune corrélation calculable"}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Disponibilité</CardTitle>
          <CardDescription>Les valeurs absentes ne sont jamais imputées à zéro.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {Object.entries(availability).map(([name, counts]) => (
            <div key={name} className="text-sm">
              <span className="font-medium">{name}</span>
              <div className="text-muted-foreground">
                {Object.entries(record(counts))
                  .map(([status, count]) => `${status}: ${String(count)}`)
                  .join(" · ")}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Ablations</CardTitle>
          <CardDescription>Facteurs et groupes, sans modification de production.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {Object.entries(ablations ?? {}).map(([name, value]) => {
            const item = record(value);
            return (
              <div key={name} className="grid grid-cols-[1fr_auto] gap-3 border-b py-1 text-sm">
                <span>{name}</span>
                <span>
                  {String(item.accepted_count ?? "—")} ({signed(number(item.delta_vs_baseline))})
                </span>
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}
function number(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}
function signed(value: number | undefined): string {
  return value === undefined ? "—" : value > 0 ? `+${value}` : String(value);
}
function formatPercent(value: number | undefined) {
  return value === undefined ? "—" : `${(value * 100).toFixed(2)} %`;
}
