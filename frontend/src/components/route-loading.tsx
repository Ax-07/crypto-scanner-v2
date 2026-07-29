import { Skeleton } from "@/components/ui/skeleton"

export function RouteLoading() {
  return (
    <main
      className="mx-auto grid min-h-screen w-full max-w-[1600px] content-start gap-4 p-4 lg:p-6"
      aria-busy="true"
      aria-live="polite"
    >
      <span className="sr-only">Chargement de la page…</span>
      <Skeleton className="h-14 w-full" />
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    </main>
  )
}
