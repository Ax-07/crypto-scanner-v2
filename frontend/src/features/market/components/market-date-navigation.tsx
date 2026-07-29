import { zodResolver } from "@hookform/resolvers/zod"
import { CalendarDays, Loader2 } from "lucide-react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Field, FieldError, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"

const dateSchema = z.object({
  date: z.string().min(1, "Choisissez une date").refine(
    (value) => {
      const timestamp = Date.parse(`${value}T00:00:00Z`)
      return Number.isFinite(timestamp) && timestamp <= Date.now()
    },
    "La date doit être valide et ne pas être future",
  ),
})

type DateValues = z.infer<typeof dateSchema>

export function MarketDateNavigation({
  jumping,
  onJump,
}: {
  jumping: boolean
  onJump: (anchorTime: number) => void
}) {
  const form = useForm<DateValues>({
    resolver: zodResolver(dateSchema),
    defaultValues: { date: "" },
  })
  return <form
    className="flex items-end gap-2"
    onSubmit={form.handleSubmit(({ date }) => {
      onJump(Date.parse(`${date}T00:00:00Z`))
    })}
  >
    <Field data-invalid={Boolean(form.formState.errors.date)}>
      <FieldLabel htmlFor="market-anchor-date">Aller à une date</FieldLabel>
      <Input
        id="market-anchor-date"
        type="date"
        max={new Date().toISOString().slice(0, 10)}
        aria-invalid={Boolean(form.formState.errors.date)}
        {...form.register("date")}
      />
      <FieldError errors={[form.formState.errors.date ?? {}]} />
    </Field>
    <Button type="submit" size="sm" disabled={jumping}>
      {jumping ? <Loader2 className="animate-spin" /> : <CalendarDays />}
      Afficher
    </Button>
  </form>
}
