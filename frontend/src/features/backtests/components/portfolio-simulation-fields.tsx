import type { UseFormReturn } from "react-hook-form"

import { Badge } from "@/components/ui/badge"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import type { BacktestFormValues } from "@/features/backtests/backtest-schema"
import { deriveQuoteAsset } from "@/features/backtests/portfolio-utils"

export function PortfolioSimulationFields({
  form,
  disabled,
}: {
  form: UseFormReturn<BacktestFormValues>
  disabled: boolean
}) {
  const enabled = form.watch("portfolio_simulation_enabled")
  const errors = form.formState.errors.portfolio_simulation
  const setEnabled = (checked: boolean) => {
    form.setValue("portfolio_simulation_enabled", checked, { shouldValidate: true })
    if (!checked) return
    const quote = deriveQuoteAsset(form.getValues("symbols"))
    if (quote) {
      form.setValue("portfolio_simulation.quote_asset", quote, { shouldValidate: true })
    }
    form.setValue("replay_mode", "every_bar", { shouldValidate: true })
  }

  return (
    <section className="space-y-4 rounded-lg border p-4" aria-labelledby="portfolio-config-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h2 id="portfolio-config-title" className="font-semibold">
            Simulation de portefeuille
          </h2>
          <p className="text-sm text-muted-foreground">
            Simule l’évolution d’un capital fictif à partir des observations acceptées.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <FieldLabel htmlFor="portfolio_simulation_enabled">Activer</FieldLabel>
          <Switch
            id="portfolio_simulation_enabled"
            aria-label="Activer la simulation de portefeuille"
            checked={enabled}
            disabled={disabled}
            onCheckedChange={setEnabled}
          />
        </div>
      </div>

      {enabled ? (
        <>
          <FieldGroup className="md:grid-cols-2 xl:grid-cols-5">
            <PortfolioField
              form={form}
              name="quote_asset"
              label="Actif de cotation"
              description="Unité explicite du capital, modifiable."
              disabled={disabled}
              error={errors?.quote_asset}
            />
            <PortfolioField
              form={form}
              name="initial_capital"
              label="Capital initial"
              description="Montant fictif strictement positif."
              disabled={disabled}
              error={errors?.initial_capital}
              inputMode="decimal"
            />
            <PortfolioField
              form={form}
              name="position_size_percent"
              label="Taille de position (%)"
              description="Part du cash disponible, de 0 à 100 %."
              disabled={disabled}
              error={errors?.position_size_percent}
              inputMode="decimal"
            />
            <PortfolioField
              form={form}
              name="fee_percent"
              label="Frais par côté (%)"
              description="0,1 % est envoyé comme ratio 0.001."
              disabled={disabled}
              error={errors?.fee_percent}
              inputMode="decimal"
            />
            <PortfolioField
              form={form}
              name="slippage_percent"
              label="Slippage (%)"
              description="Appliqué défavorablement à l’achat et à la vente."
              disabled={disabled}
              error={errors?.slippage_percent}
              inputMode="decimal"
            />
          </FieldGroup>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">Exécution : ouverture suivante</Badge>
            <Badge variant="outline">Fin : clôture forcée</Badge>
            <Badge variant="outline">Spot long uniquement · une position maximum</Badge>
          </div>
          <div className="space-y-1 text-xs text-muted-foreground">
            <p>
              Les observations acceptées ne sont pas directement des ordres d’achat. Le moteur
              ouvre et ferme une position selon sa stratégie de transition.
            </p>
            <p>Les ordres sont exécutés à l’ouverture de la bougie suivante.</p>
          </div>
        </>
      ) : null}
    </section>
  )
}

type PortfolioFieldName =
  | "quote_asset"
  | "initial_capital"
  | "position_size_percent"
  | "fee_percent"
  | "slippage_percent"

function PortfolioField({
  form,
  name,
  label,
  description,
  disabled,
  error,
  inputMode,
}: {
  form: UseFormReturn<BacktestFormValues>
  name: PortfolioFieldName
  label: string
  description: string
  disabled: boolean
  error?: { message?: string }
  inputMode?: "decimal"
}) {
  const id = `portfolio_simulation_${name}`
  return (
    <Field data-invalid={Boolean(error)}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input
        id={id}
        disabled={disabled}
        inputMode={inputMode}
        aria-invalid={Boolean(error)}
        aria-describedby={`${id}-description`}
        {...form.register(`portfolio_simulation.${name}`)}
      />
      <FieldDescription id={`${id}-description`}>{description}</FieldDescription>
      <FieldError errors={[error ?? {}]} />
    </Field>
  )
}
