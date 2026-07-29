import { useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch, type Resolver } from "react-hook-form";

import { experimentApi } from "@/api/experiments";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  candidateEstimate,
  experimentFormSchema,
  type ExperimentFormValues,
} from "@/features/experiments/experiment-schema";
import type { CandidateSpec, ExperimentManifest, ShadowSummary, SignalProfile } from "@/types/experiment";

const defaults: ExperimentFormValues = {
  sourceBacktestId: "",
  horizon: 24,
  embargo: 24,
  minimumGlobal: 30,
  includeTrend: true,
  includeRedundancy: true,
  includeThresholds: true,
};

export function ExperimentsPage() {
  const [manifest, setManifest] = useState<ExperimentManifest | null>(null);
  const [profiles, setProfiles] = useState<SignalProfile[]>([]);
  const [shadow, setShadow] = useState<ShadowSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const form = useForm<ExperimentFormValues>({
    resolver: zodResolver(experimentFormSchema) as Resolver<ExperimentFormValues>,
    defaultValues: defaults,
    mode: "onChange",
  });
  const values = useWatch({ control: form.control });
  const estimate = useMemo(() => candidateEstimate(values), [values]);
  const running = manifest?.status === "pending" || manifest?.status === "running";
  const refreshGovernance = () =>
    Promise.all([experimentApi.profiles().then(setProfiles), experimentApi.shadowSummary().then(setShadow)]).catch(
      () => undefined,
    );

  useEffect(() => {
    void refreshGovernance();
  }, [manifest?.status]);

  useEffect(() => {
    if (!running || !manifest) return;
    const timer = window.setInterval(() => {
      experimentApi
        .get(manifest.id)
        .then(setManifest)
        .catch((reason: unknown) => {
          setError(reason instanceof Error ? reason.message : "Lecture impossible");
        });
    }, 750);
    return () => window.clearInterval(timer);
  }, [manifest, running]);

  const submit = form.handleSubmit(async (input) => {
    setError(null);
    try {
      setManifest(
        await experimentApi.start({
          source_backtest_id: input.sourceBacktestId,
          candidates: candidatesFor(input),
          selection_horizon: input.horizon,
          split: { embargo_bars: input.embargo },
          minimum_global: input.minimumGlobal,
        }),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Lancement impossible");
    }
  });

  return (
    <div className="flex w-full flex-col gap-5">
      <div>
        <h1 className="text-2xl font-bold">Expériences de signaux</h1>
        <p className="text-muted-foreground">
          Comparez une recherche bornée à baseline-v1, sans modifier la production.
        </p>
      </div>
      <form onSubmit={submit} noValidate>
        <Card>
          <CardHeader>
            <CardTitle>Protocole hors échantillon</CardTitle>
            <CardDescription>Le test final reste exclu de l’objectif de classement.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <FieldGroup className="md:grid-cols-4">
              <TextField form={form} name="sourceBacktestId" label="Backtest source terminé" />
              <NumberField form={form} name="horizon" label="Horizon (bougies)" />
              <NumberField form={form} name="embargo" label="Embargo (bougies)" />
              <NumberField form={form} name="minimumGlobal" label="Échantillon minimum" />
            </FieldGroup>
            <div className="grid gap-3 md:grid-cols-3">
              <Toggle form={form} name="includeTrend" label="Politiques de tendance" />
              <Toggle form={form} name="includeRedundancy" label="Redondance des facteurs" />
              <Toggle form={form} name="includeThresholds" label="Seuils voisins" />
            </div>
            <div className="flex items-center justify-between rounded-md border p-3">
              <span>
                <strong>{estimate}</strong> candidats estimés (maximum API : 128)
              </span>
              <div className="flex gap-2">
                {running && manifest ? (
                  <Button type="button" variant="outline" onClick={() => void experimentApi.cancel(manifest.id)}>
                    Annuler
                  </Button>
                ) : null}
                <Button type="submit" disabled={!form.formState.isValid || running}>
                  Lancer
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </form>
      {error ? (
        <Alert className="border-destructive">
          <AlertTitle>Expérience interrompue</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {manifest ? <ExperimentResults manifest={manifest} /> : null}
      <GovernancePanel profiles={profiles} shadow={shadow} onAction={refreshGovernance} />
    </div>
  );
}

function candidatesFor(values: ExperimentFormValues): CandidateSpec[] {
  const items: CandidateSpec[] = [
    {
      id: "baseline-v1",
      family: "baseline",
      description: "Profil canonique immuable",
      weights: { rsi: 20, trend: 25, macd: 20, bollinger: 20, stochastic: 15 },
      rsi_threshold: 35,
      min_confluence_score: 60,
    },
  ];
  if (values.includeTrend) {
    items.push(
      { id: "trend-strict", family: "trend", trend_policy: "strict_consensus" },
      { id: "trend-majority", family: "trend", trend_policy: "mtf_majority" },
      { id: "trend-weighted", family: "trend", trend_policy: "mtf_weighted" },
    );
  }
  if (values.includeRedundancy) {
    items.push(
      { id: "without-rsi", family: "redundancy", excluded_factors: ["rsi"] },
      { id: "without-stochastic", family: "redundancy", excluded_factors: ["stochastic"] },
      { id: "factor-groups", family: "redundancy", group_scoring: true },
    );
  }
  if (values.includeThresholds) {
    for (const threshold of [32, 35, 38, 40]) {
      items.push({ id: `rsi-${threshold}`, family: "thresholds", rsi_threshold: threshold, min_confluence_score: 60 });
    }
  }
  return items;
}

type Form = ReturnType<typeof useForm<ExperimentFormValues>>;
function TextField({ form, name, label }: { form: Form; name: "sourceBacktestId"; label: string }) {
  const error = form.formState.errors[name];
  return (
    <Field data-invalid={Boolean(error)}>
      <FieldLabel htmlFor={name}>{label}</FieldLabel>
      <Input id={name} {...form.register(name)} />
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
  name: "horizon" | "embargo" | "minimumGlobal";
  label: string;
}) {
  const error = form.formState.errors[name];
  return (
    <Field data-invalid={Boolean(error)}>
      <FieldLabel htmlFor={name}>{label}</FieldLabel>
      <Input id={name} type="number" {...form.register(name, { valueAsNumber: true })} />
      <FieldError errors={[error ?? {}]} />
    </Field>
  );
}
function Toggle({
  form,
  name,
  label,
}: {
  form: Form;
  name: "includeTrend" | "includeRedundancy" | "includeThresholds";
  label: string;
}) {
  return (
    <Field className="flex-row items-center justify-between rounded-md border p-3">
      <FieldLabel htmlFor={name}>{label}</FieldLabel>
      <Switch id={name} checked={form.watch(name)} onCheckedChange={(checked) => form.setValue(name, checked)} />
    </Field>
  );
}
function ExperimentResults({ manifest }: { manifest: ExperimentManifest }) {
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex justify-between">
            <CardTitle>Résultats</CardTitle>
            <Badge>{manifest.status}</Badge>
          </div>
          <CardDescription>
            {manifest.total_trials} essais · {manifest.dataset_version.slice(0, 24)}…
          </CardDescription>
        </CardHeader>
      </Card>
      {manifest.warnings.map((warning) => (
        <Alert key={warning}>
          <AlertTitle>Garde-fou statistique</AlertTitle>
          <AlertDescription>{warning}</AlertDescription>
        </Alert>
      ))}
      {manifest.results.length ? (
        <Card>
          <CardContent className="overflow-x-auto pt-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Rang</TableHead>
                  <TableHead>Candidat</TableHead>
                  <TableHead>Famille</TableHead>
                  <TableHead>Train N</TableHead>
                  <TableHead>Validation N</TableHead>
                  <TableHead>Test N</TableHead>
                  <TableHead>Décision</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {manifest.results.map((item) => (
                  <TableRow key={item.candidate_id}>
                    <TableCell>{item.rank ?? "—"}</TableCell>
                    <TableCell>{item.candidate_id}</TableCell>
                    <TableCell>{item.family}</TableCell>
                    <TableCell>{metric(item, "train", "signal_count")}</TableCell>
                    <TableCell>{metric(item, "validation", "signal_count")}</TableCell>
                    <TableCell>{metric(item, "test", "signal_count")}</TableCell>
                    <TableCell>
                      <Badge variant={item.eligible ? "default" : "secondary"}>
                        {item.eligible ? "éligible" : item.rejection_reasons.join(", ")}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
      {manifest.results.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Validation walk-forward et test final</CardTitle>
            <CardDescription>
              Le classement utilise la validation; OOS et test final restent visibles séparément.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Candidat</TableHead>
                  <TableHead>WF OOS N</TableHead>
                  <TableHead>WF OOS médiane</TableHead>
                  <TableHead>Test final N</TableHead>
                  <TableHead>Test final médiane</TableHead>
                  <TableHead>BH ajusté</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {manifest.results.map((item) => (
                  <TableRow key={item.candidate_id}>
                    <TableCell>{item.candidate_id}</TableCell>
                    <TableCell>{objectMetric(item.oos_metrics, "signal_count")}</TableCell>
                    <TableCell>{percentMetric(item.oos_metrics, "net_median")}</TableCell>
                    <TableCell>{objectMetric(item.final_test_metrics, "signal_count")}</TableCell>
                    <TableCell>{percentMetric(item.final_test_metrics, "net_median")}</TableCell>
                    <TableCell>{item.adjusted_p_value?.toFixed(4) ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
      {manifest.status === "completed" ? (
        <Card>
          <CardHeader>
            <CardTitle>Exports reproductibles</CardTitle>
          </CardHeader>
          <CardContent className="flex gap-2">
            {["manifest", "candidates", "folds", "sensitivity"].map((dataset) => (
              <Button asChild variant="outline" key={dataset}>
                <a href={experimentApi.exportUrl(manifest.id, dataset)}>{dataset}</a>
              </Button>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
function GovernancePanel({
  profiles,
  shadow,
  onAction,
}: {
  profiles: SignalProfile[];
  shadow: ShadowSummary | null;
  onAction: () => Promise<unknown>;
}) {
  const act = async (kind: "shadow" | "promote", profile: SignalProfile) => {
    const comment = window.prompt(`Commentaire explicite pour ${kind} ${profile.id}`);
    if (!comment || comment.trim().length < 3) return;
    if (kind === "shadow") await experimentApi.enableShadow(profile.id, comment);
    else if (profile.experiment_id) await experimentApi.promote(profile.id, profile.experiment_id, comment);
    await onAction();
  };
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Profils versionnés</CardTitle>
          <CardDescription>Le hash de contenu reste immuable; le statut suit un historique séparé.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {profiles.map((profile) => (
            <div key={profile.id} className="flex flex-wrap items-center gap-2 rounded-md border p-3">
              <span className="font-medium">{profile.name}</span>
              <Badge>{profile.status}</Badge>
              <code className="text-xs text-muted-foreground">{profile.content_hash.slice(0, 20)}…</code>
              <span className="grow" />
              {profile.status === "candidate" ? (
                <Button size="sm" variant="outline" onClick={() => void act("shadow", profile)}>
                  Passer shadow
                </Button>
              ) : null}
              {profile.status === "shadow" ? (
                <Button size="sm" onClick={() => void act("promote", profile)}>
                  Promouvoir
                </Button>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Comparaison shadow</CardTitle>
          <CardDescription>Aucun résultat shadow ne modifie les décisions de production.</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3">
          <MetricSmall label="Comparaisons" value={shadow?.total} />
          <MetricSmall label="Divergences" value={shadow?.divergent} />
          <MetricSmall
            label="Accord"
            value={shadow?.agreement_rate == null ? undefined : `${(shadow.agreement_rate * 100).toFixed(1)} %`}
          />
          <MetricSmall label="Outcomes disponibles" value={shadow?.future_outcomes_available} />
        </CardContent>
      </Card>
    </div>
  );
}
function MetricSmall({ label, value }: { label: string; value: number | string | undefined }) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-xl font-semibold">{value ?? "—"}</div>
    </div>
  );
}
function metric(item: ExperimentManifest["results"][number], split: string, name: string): string {
  const value = item.metrics[split]?.[name];
  return typeof value === "number" ? String(value) : "—";
}
function objectMetric(values: Record<string, unknown>, name: string): string {
  const value = values[name];
  return typeof value === "number" ? String(value) : "—";
}
function percentMetric(values: Record<string, unknown>, name: string): string {
  const value = values[name];
  return typeof value === "number" ? `${(value * 100).toFixed(2)} %` : "—";
}
