import { z } from "zod"

export const experimentFormSchema = z.object({
  sourceBacktestId: z.string().min(8, "Identifiant de backtest requis"),
  horizon: z.number().int().min(1).max(10_000),
  embargo: z.number().int().min(1).max(10_000),
  minimumGlobal: z.number().int().min(1),
  includeTrend: z.boolean(),
  includeRedundancy: z.boolean(),
  includeThresholds: z.boolean(),
}).superRefine((value, context) => {
  if (value.embargo < value.horizon) {
    context.addIssue({ code: "custom", path: ["embargo"], message: "L’embargo doit couvrir l’horizon" })
  }
})

export type ExperimentFormValues = z.infer<typeof experimentFormSchema>

export function candidateEstimate(values: Partial<ExperimentFormValues>): number {
  return 1 + Number(values.includeTrend) * 3 + Number(values.includeRedundancy) * 3
    + Number(values.includeThresholds) * 4
}
