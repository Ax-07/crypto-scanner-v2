import * as React from "react"

import { cn } from "@/lib/utils"

export function Field({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("grid gap-2", className)} {...props} />
}

export function FieldGroup({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("grid gap-4", className)} {...props} />
}

export function FieldLabel({ className, ...props }: React.ComponentProps<"label">) {
  return <label className={cn("text-sm font-medium", className)} {...props} />
}

export function FieldDescription({ className, ...props }: React.ComponentProps<"p">) {
  return <p className={cn("text-xs text-muted-foreground", className)} {...props} />
}

export function FieldError({ errors, className, ...props }: React.ComponentProps<"p"> & { errors?: Array<{ message?: string }> }) {
  const message = errors?.map((error) => error.message).filter(Boolean).join(" · ")
  if (!message) return null
  return <p role="alert" className={cn("text-sm text-destructive", className)} {...props}>{message}</p>
}

export function FieldSet({ className, ...props }: React.ComponentProps<"fieldset">) {
  return <fieldset className={cn("grid gap-4", className)} {...props} />
}

export function FieldLegend({ className, ...props }: React.ComponentProps<"legend">) {
  return <legend className={cn("mb-3 text-base font-semibold", className)} {...props} />
}
