import { useEffect } from "react";
import { Controller, useForm, useWatch, type Control, type FieldPathByValue, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { ApiError } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { formatTechnicalLabel } from "@/components/indicator-signals";
import { parsePeriodList, scanConfigSchema, TIMEFRAMES } from "@/features/scanner/scan-config-schema";
import {
  migrateLegacySignalFilters,
  setStructuredFilterMatch,
  toggleStructuredFilterValue,
} from "@/features/scanner/structured-signal-filter-migration";
import type { ScanConfig } from "@/types/scanner";
import type {
  StructuredSignalFilterField,
  StructuredSignalFilterIndicator,
} from "@/types/structured-signal-filters";

type Props = { config: ScanConfig; busy: boolean; onSubmit: (config: ScanConfig) => Promise<void> };

/** Édite une copie locale de ScanConfig et ne publie qu'une valeur validée par Zod. */
export function ScannerConfigForm({ config, busy, onSubmit }: Props) {
  const form = useForm<ScanConfig>({
    resolver: zodResolver(scanConfigSchema) as Resolver<ScanConfig>,
    defaultValues: migrateLegacySignalFilters(config),
    mode: "onChange",
  });
  useEffect(() => form.reset(migrateLegacySignalFilters(config)), [config, form]);
  const values = useWatch({ control: form.control }) as ScanConfig;
  const active = [
    values.use_rsi && "RSI",
    values.use_ma && "Tendance",
    values.use_macd && "MACD",
    values.use_bollinger && "Bollinger",
    values.use_stochastic && "Stochastique",
  ].filter(Boolean);
  const activeWeight =
    (values.use_rsi ? values.confluence_weights.rsi : 0) +
    (values.use_ma ? values.confluence_weights.trend : 0) +
    (values.use_macd ? values.confluence_weights.macd : 0) +
    (values.use_bollinger ? values.confluence_weights.bollinger : 0) +
    (values.use_stochastic ? values.confluence_weights.stochastic : 0);

  const submit = form.handleSubmit(async (candidate) => {
    try {
      await onSubmit(candidate);
      form.reset(candidate);
    } catch (error) {
      // Les chemins FastAPI « body.champ » sont rebranchés sur React Hook Form.
      if (error instanceof ApiError)
        error.issues.forEach((item) => {
          const name = item.loc.filter((part) => part !== "body").join(".");
          if (name in candidate) form.setError(name as keyof ScanConfig, { message: item.msg });
        });
      form.setError("root", { message: error instanceof Error ? error.message : "Configuration refusée" });
    }
  });

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      {form.formState.errors.root ? <FieldError errors={[form.formState.errors.root]} /> : null}
      <Card>
        <CardHeader>
          <CardTitle>Marché</CardTitle>
        </CardHeader>
        <CardContent>
          <FieldGroup className="md:grid-cols-3">
            <TextField control={form.control} name="exchange_id" label="Exchange" disabled={busy} />
            <TextField
              control={form.control}
              name="quote"
              label="Devise de cotation"
              disabled={busy}
              description="Exemple : USDC"
            />
            <Field>
              <FieldLabel htmlFor="market_type">Type de marché</FieldLabel>
              <select
                id="market_type"
                className="h-9 rounded-md border bg-background px-3"
                disabled={busy}
                {...form.register("market_type")}
              >
                <option value="spot">Spot</option>
                <option value="swap">Swap</option>
                <option value="future">Future</option>
              </select>
            </Field>
            <BooleanField
              control={form.control}
              name="exclude_stable_pairs"
              label="Exclure les paires stables"
              disabled={busy}
            />
          </FieldGroup>
        </CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Données</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="timeframe">Timeframe</FieldLabel>
                <select
                  id="timeframe"
                  className="h-9 rounded-md border bg-background px-3"
                  disabled={busy}
                  {...form.register("timeframe")}
                >
                  {TIMEFRAMES.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
              </Field>
              <NullableNumberField
                control={form.control}
                name="max_pairs"
                label="Nombre maximal de paires"
                disabled={busy}
              />
              <NumberField control={form.control} name="min_ohlcv_bars" label="Bougies minimum" disabled={busy} />
            </FieldGroup>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Performance</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldGroup>
              <NumberField control={form.control} name="max_concurrency" label="Analyses simultanées" disabled={busy} />
              <NumberField control={form.control} name="max_retries" label="Tentatives" disabled={busy} />
              <NumberField
                control={form.control}
                name="retry_delay_seconds"
                label="Délai initial de retry"
                disabled={busy}
                step={0.1}
              />
            </FieldGroup>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <IndicatorCard title="RSI" control={form.control} enabledName="use_rsi" busy={busy}>
          <NumberField control={form.control} name="rsi_period" label="Période" disabled={busy || !values.use_rsi} />
          <NumberField
            control={form.control}
            name="rsi_threshold"
            label="Seuil maximum"
            disabled={busy || !values.use_rsi}
          />
        </IndicatorCard>
        <IndicatorCard title="Moyennes mobiles" control={form.control} enabledName="use_ma" busy={busy}>
          <div className="flex gap-5">
            <BooleanField control={form.control} name="use_sma" label="SMA" disabled={busy || !values.use_ma} />
            <BooleanField control={form.control} name="use_ema" label="EMA" disabled={busy || !values.use_ma} />
          </div>
          <PeriodField
            control={form.control}
            name="sma_periods"
            label="Périodes SMA"
            disabled={busy || !values.use_ma || !values.use_sma}
          />
          <PeriodField
            control={form.control}
            name="ema_periods"
            label="Périodes EMA"
            disabled={busy || !values.use_ma || !values.use_ema}
          />
          <FieldSet>
            <FieldLegend>Timeframes de tendance</FieldLegend>
            <div className="flex flex-wrap gap-3">
              {TIMEFRAMES.map((timeframe) => (
                <Controller
                  key={timeframe}
                  name="ma_timeframes"
                  control={form.control}
                  render={({ field }) => (
                    <label className="flex items-center gap-2 text-sm">
                      <Checkbox
                        disabled={busy || !values.use_ma}
                        checked={field.value.includes(timeframe)}
                        onCheckedChange={() => field.onChange(toggle(field.value, timeframe))}
                      />
                      {timeframe}
                    </label>
                  )}
                />
              ))}
            </div>
          </FieldSet>
          <NumberField
            control={form.control}
            name="min_trend_score"
            label="Score de tendance minimum"
            disabled={busy || !values.use_ma}
          />
        </IndicatorCard>
        <IndicatorCard title="MACD" control={form.control} enabledName="use_macd" busy={busy}>
          <div className="grid grid-cols-3 gap-3">
            <NumberField
              control={form.control}
              name="macd_fast_period"
              label="Rapide"
              disabled={busy || !values.use_macd}
            />
            <NumberField
              control={form.control}
              name="macd_slow_period"
              label="Lente"
              disabled={busy || !values.use_macd}
            />
            <NumberField
              control={form.control}
              name="macd_signal_period"
              label="Signal"
              disabled={busy || !values.use_macd}
            />
          </div>
        </IndicatorCard>
        <IndicatorCard title="Bandes de Bollinger" control={form.control} enabledName="use_bollinger" busy={busy}>
          <NumberField
            control={form.control}
            name="bollinger_period"
            label="Période"
            disabled={busy || !values.use_bollinger}
          />
          <NumberField
            control={form.control}
            name="bollinger_std_dev"
            label="Écarts-types"
            disabled={busy || !values.use_bollinger}
            step={0.1}
          />
        </IndicatorCard>
        <IndicatorCard title="Stochastique" control={form.control} enabledName="use_stochastic" busy={busy}>
          <div className="grid grid-cols-2 gap-3">
            <NumberField
              control={form.control}
              name="stochastic_k_period"
              label="Période K"
              disabled={busy || !values.use_stochastic}
            />
            <NumberField
              control={form.control}
              name="stochastic_d_period"
              label="Période D"
              disabled={busy || !values.use_stochastic}
            />
            <NumberField
              control={form.control}
              name="stochastic_oversold"
              label="Survente"
              disabled={busy || !values.use_stochastic}
            />
            <NumberField
              control={form.control}
              name="stochastic_overbought"
              label="Surachat"
              disabled={busy || !values.use_stochastic}
            />
          </div>
        </IndicatorCard>
        <IndicatorCard title="Confluence" control={form.control} enabledName="use_confluence_score" busy={busy}>
          <NumberField
            control={form.control}
            name="min_confluence_score"
            label="Score minimum"
            disabled={busy || !values.use_confluence_score}
          />
          <div className="flex flex-wrap gap-2">
            {active.map((name) => (
              <Badge key={String(name)} variant="secondary">
                {name}
              </Badge>
            ))}
          </div>
          <FieldDescription>Total des poids actifs : {activeWeight}</FieldDescription>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {(["rsi", "trend", "macd", "bollinger", "stochastic"] as const).map((name) => (
              <NumberField
                key={name}
                control={form.control}
                name={`confluence_weights.${name}`}
                label={`Poids ${name}`}
                disabled={busy || !values.use_confluence_score}
              />
            ))}
          </div>
        </IndicatorCard>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Filtres avancés</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <FieldDescription>
            Les nouveaux filtres utilisent les signaux structurés. Les anciens filtres restent
            acceptés pour les configurations existantes.
          </FieldDescription>
          <div className="grid gap-5 lg:grid-cols-3">
            <StructuredSignalField
              control={form.control}
              indicator="macd"
              label="MACD"
              options={[
                { field: "direction", value: "bullish", label: "Direction haussière" },
                { field: "direction", value: "bearish", label: "Direction baissière" },
                { field: "direction", value: "neutral", label: "Direction neutre" },
              ]}
              disabled={busy || !values.use_macd}
            />
            <StructuredSignalField
              control={form.control}
              indicator="bollinger"
              label="Bollinger"
              options={[
                ...["oversold", "near_oversold", "neutral", "near_overbought", "overbought"].map(
                  (value) => ({
                    field: "state" as const,
                    value,
                    label: formatTechnicalLabel(value),
                  }),
                ),
                ...[
                  "lower_band_breakout",
                  "lower_band_reentry",
                  "upper_band_breakout",
                  "upper_band_reentry",
                ].map((value) => ({
                  field: "signal" as const,
                  value,
                  label: formatTechnicalLabel(value),
                })),
              ]}
              disabled={busy || !values.use_bollinger}
            />
            <StructuredSignalField
              control={form.control}
              indicator="stochastic"
              label="Stochastique"
              options={[
                ...["bullish_cross", "bearish_cross", "oversold", "overbought", "neutral"].map(
                  (value) => ({
                    field: "signal" as const,
                    value,
                    label: `Événement / classe : ${formatTechnicalLabel(value)}`,
                  }),
                ),
                ...["oversold", "neutral", "overbought"].map((value) => ({
                  field: "state" as const,
                  value,
                  label: `État actuel : ${formatTechnicalLabel(value)}`,
                })),
              ]}
              disabled={busy || !values.use_stochastic}
            />
          </div>
        </CardContent>
      </Card>
      <div className="sticky bottom-3 flex flex-wrap justify-end gap-2 rounded-lg border bg-background/95 p-3 backdrop-blur">
        <Button
          type="button"
          variant="outline"
          disabled={!form.formState.isDirty || form.formState.isSubmitting}
          onClick={() => form.reset(migrateLegacySignalFilters(config))}
        >
          Annuler les modifications
        </Button>
        <Button type="submit" disabled={busy || form.formState.isSubmitting || !form.formState.isValid}>
          {form.formState.isSubmitting ? "Lancement…" : "Appliquer et lancer"}
        </Button>
      </div>
    </form>
  );
}

type NumberName = FieldPathByValue<ScanConfig, number>;
function NumberField({
  control,
  name,
  label,
  disabled,
  step = 1,
}: {
  control: Control<ScanConfig>;
  name: NumberName;
  label: string;
  disabled: boolean;
  step?: number;
}) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid}>
          <FieldLabel htmlFor={field.name}>{label}</FieldLabel>
          <Input
            id={field.name}
            type="number"
            step={step}
            disabled={disabled}
            aria-invalid={fieldState.invalid}
            value={Number(field.value)}
            onChange={(event) => field.onChange(event.target.value === "" ? Number.NaN : event.target.valueAsNumber)}
          />
          <FieldError errors={[fieldState.error ?? {}]} />
        </Field>
      )}
    />
  );
}
function NullableNumberField({
  control,
  name,
  label,
  disabled,
}: {
  control: Control<ScanConfig>;
  name: "max_pairs";
  label: string;
  disabled: boolean;
}) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field, fieldState }) => (
        <Field>
          <FieldLabel htmlFor={field.name}>{label}</FieldLabel>
          <Input
            id={field.name}
            type="number"
            min={1}
            disabled={disabled}
            aria-invalid={fieldState.invalid}
            value={field.value ?? ""}
            onChange={(event) => field.onChange(event.target.value === "" ? null : event.target.valueAsNumber)}
          />
          <FieldError errors={[fieldState.error ?? {}]} />
        </Field>
      )}
    />
  );
}
function TextField({
  control,
  name,
  label,
  disabled,
  description,
}: {
  control: Control<ScanConfig>;
  name: "quote" | "exchange_id";
  label: string;
  disabled: boolean;
  description?: string;
}) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field, fieldState }) => (
        <Field>
          <FieldLabel htmlFor={field.name}>{label}</FieldLabel>
          <Input {...field} id={field.name} disabled={disabled} aria-invalid={fieldState.invalid} />
          <FieldDescription>{description}</FieldDescription>
          <FieldError errors={[fieldState.error ?? {}]} />
        </Field>
      )}
    />
  );
}
function BooleanField({
  control,
  name,
  label,
  disabled,
}: {
  control: Control<ScanConfig>;
  name: FieldPathByValue<ScanConfig, boolean>;
  label: string;
  disabled: boolean;
}) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field, fieldState }) => (
        <Field className="flex grid-cols-[auto_1fr] items-center gap-2">
          <Switch
            id={field.name}
            checked={field.value}
            disabled={disabled}
            onCheckedChange={field.onChange}
            aria-invalid={fieldState.invalid}
          />
          <FieldLabel htmlFor={field.name}>{label}</FieldLabel>
          <FieldError className="col-span-2" errors={[fieldState.error ?? {}]} />
        </Field>
      )}
    />
  );
}
function IndicatorCard({
  title,
  control,
  enabledName,
  busy,
  children,
}: {
  title: string;
  control: Control<ScanConfig>;
  enabledName: FieldPathByValue<ScanConfig, boolean>;
  busy: boolean;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>{title}</CardTitle>
        <BooleanField control={control} name={enabledName} label="Activer" disabled={busy} />
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
    </Card>
  );
}
function PeriodField({
  control,
  name,
  label,
  disabled,
}: {
  control: Control<ScanConfig>;
  name: "sma_periods" | "ema_periods";
  label: string;
  disabled: boolean;
}) {
  return (
    <Controller
      name={name}
      control={control}
      render={({ field, fieldState }) => (
        <Field>
          <FieldLabel htmlFor={field.name}>{label}</FieldLabel>
          <Input
            id={field.name}
            disabled={disabled}
            defaultValue={field.value.join(", ")}
            onBlur={(event) => {
              const parsed = parsePeriodList(event.target.value);
              if (parsed) field.onChange(parsed);
            }}
            aria-invalid={fieldState.invalid}
          />
          <FieldDescription>Valeurs uniques entre 2 et 1000, séparées par des virgules.</FieldDescription>
          <FieldError errors={[fieldState.error ?? {}]} />
        </Field>
      )}
    />
  );
}
type StructuredOption = {
  field: StructuredSignalFilterField;
  value: string;
  label: string;
};

function StructuredSignalField({
  control,
  indicator,
  label,
  options,
  disabled,
}: {
  control: Control<ScanConfig>;
  indicator: StructuredSignalFilterIndicator;
  label: string;
  options: StructuredOption[];
  disabled: boolean;
}) {
  return (
    <Controller
      name="structured_signal_filters"
      control={control}
      render={({ field, fieldState }) => {
        const group = field.value?.indicators[indicator];
        const isSelected = (option: StructuredOption) =>
          group?.conditions
            .find((condition) => condition.field === option.field)
            ?.values.map(String)
            .includes(option.value) ?? false;
        return (
          <FieldSet>
            <FieldLegend>{label}</FieldLegend>
            <Field>
              <FieldLabel htmlFor={`${indicator}-filter-match`}>Correspondance</FieldLabel>
              <select
                id={`${indicator}-filter-match`}
                className="h-9 rounded-md border bg-background px-3"
                disabled={disabled}
                value={group?.match ?? "any"}
                onChange={(event) =>
                  field.onChange(
                    setStructuredFilterMatch(
                      field.value,
                      indicator,
                      event.target.value === "all" ? "all" : "any",
                    ),
                  )
                }
              >
                <option value="any">Au moins une condition</option>
                <option value="all">Toutes les conditions</option>
              </select>
            </Field>
            <div className="grid gap-2">
              {options.map((option) => (
                <label
                  key={`${option.field}-${option.value}`}
                  className="flex items-center gap-2 text-sm"
                >
                  <Checkbox
                    disabled={disabled}
                    checked={isSelected(option)}
                    onCheckedChange={() =>
                      field.onChange(
                        toggleStructuredFilterValue(
                          field.value,
                          indicator,
                          option.field,
                          option.value,
                        ),
                      )
                    }
                  />
                  {option.label}
                </label>
              ))}
            </div>
            <FieldDescription>Aucune sélection accepte toutes les valeurs.</FieldDescription>
            <FieldError errors={[fieldState.error ?? {}]} />
          </FieldSet>
        );
      }}
    />
  );
}
function toggle<T>(items: T[], item: T): T[] {
  return items.includes(item) ? items.filter((value) => value !== item) : [...items, item];
}
