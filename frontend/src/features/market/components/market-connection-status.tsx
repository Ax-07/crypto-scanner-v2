import {
  AlertCircle,
  CircleCheck,
  LoaderCircle,
  Radio,
  WifiOff,
} from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { useMarketStore } from "@/stores/market-store"
import type { ConnectionStatus } from "@/types/market"

const statusConfig: Record<ConnectionStatus, {
  label: string
  description: string
  icon: typeof Radio
  variant: "success" | "warning" | "destructive" | "outline"
}> = {
  connecting: {
    label: "Connexion…",
    description: "Connexion ou reconnexion automatique au flux en cours.",
    icon: LoaderCircle,
    variant: "warning",
  },
  connected: {
    label: "Temps réel connecté",
    description: "Les données du marché sont actualisées en direct.",
    icon: CircleCheck,
    variant: "success",
  },
  disconnected: {
    label: "Déconnecté",
    description: "Les dernières données restent affichées. La reconnexion est automatique.",
    icon: WifiOff,
    variant: "outline",
  },
  error: {
    label: "Erreur de connexion",
    description: "Le flux temps réel est momentanément indisponible.",
    icon: AlertCircle,
    variant: "destructive",
  },
}

export function MarketConnectionStatus() {
  const status = useMarketStore((state) => state.status)
  const error = useMarketStore((state) => state.connectionError)
  const config = statusConfig[status]
  const Icon = config.icon

  return (
    <div className="min-w-0 space-y-2">
      <div
        aria-live="polite"
        aria-atomic="true"
        className="flex min-w-0 flex-wrap items-center gap-2"
      >
        <Badge variant={config.variant} className="max-w-full whitespace-normal">
          <Icon
            aria-hidden="true"
            className={cn("size-3.5 shrink-0", status === "connecting" && "animate-spin")}
          />
          {config.label}
        </Badge>
        <span className="min-w-0 text-xs text-muted-foreground">{config.description}</span>
      </div>
      {status === "error" || error ? (
        <Alert className="border-destructive/40 bg-destructive/5">
          <AlertTitle className="flex items-center gap-2 text-destructive">
            <AlertCircle aria-hidden="true" className="size-4" />
            Flux temps réel indisponible
          </AlertTitle>
          <AlertDescription className="space-y-1">
            <p>Les dernières données reçues restent affichées et peuvent être figées.</p>
            {error ? <p className="break-words">Détail : {error}</p> : null}
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}
