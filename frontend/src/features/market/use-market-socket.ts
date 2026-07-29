/**
 * Cycle de vie du WebSocket marché.
 * Les générations de connexion empêchent tout flux remplacé de publier dans le store.
 */
import { useEffect } from "react"

import { marketApi, marketMessageSchema } from "@/api/market"
import { serializeMarketProfile } from "@/features/market/market-profile"
import { useMarketStore } from "@/stores/market-store"
import type { MarketIndicatorConfig } from "@/types/market"
import type { Timeframe } from "@/types/scanner"

const BASE_WS_URL = (import.meta.env.VITE_WS_URL as string | undefined)?.replace(/\/$/, "")
  ?? (import.meta.env.VITE_API_URL as string | undefined)?.replace(/^http/, "ws").replace(/\/$/, "")
  ?? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`

/**
 * Maintient le flux du marché courant et invalide les callbacks des anciennes connexions.
 * La reconnexion utilise un backoff borné et s'arrête au démontage ou au changement d'URL.
 */
export function useMarketSocket(
  symbol: string,
  timeframe: Timeframe,
  enabled = true,
  includeHistory = false,
  profile?: MarketIndicatorConfig,
) {
  const profilePayload = profile ? serializeMarketProfile(profile) : null
  useEffect(() => {
    if (!enabled) return
    let socket: WebSocket | null = null
    let reconnectTimer: number | null = null
    let reconnectDelay = 2_000
    let generation = 0
    let active = true
    const selectionKey = `${symbol}|${timeframe}`
    const reconciliationControllers = new Set<AbortController>()

    const connect = () => {
      if (!active) return
      // La génération protège le store des messages et fermetures arrivés en retard.
      const currentGeneration = ++generation
      useMarketStore.getState().setConnection("connecting")
      const params = new URLSearchParams({
        symbol,
        timeframe,
        include_history: String(includeHistory),
      })
      if (profilePayload) params.set("profile", profilePayload)
      socket = new WebSocket(`${BASE_WS_URL}/ws?${params}`)
      const currentSocket = socket

      currentSocket.onopen = () => {
        if (!active || currentGeneration !== generation) return
        reconnectDelay = 2_000
        useMarketStore.getState().setConnection("connected")
        const state = useMarketStore.getState()
        if (state.selectionKey === selectionKey && state.latestLoadedTime !== null) {
          const controller = new AbortController()
          reconciliationControllers.add(controller)
          marketApi.getCandles({
            symbol,
            timeframe,
            after: Math.max(0, state.latestLoadedTime - 1),
            limit: 500,
            profile,
            signal: controller.signal,
          }).then((response) => {
            useMarketStore.getState().mergeRecentHistory(
              response,
              state.historyRequestGeneration,
            )
          }).catch(() => undefined).finally(() => {
            reconciliationControllers.delete(controller)
          })
        }
      }
      currentSocket.onmessage = (event) => {
        if (!active || currentGeneration !== generation || socket !== currentSocket) return
        try {
          const parsed = marketMessageSchema.safeParse(JSON.parse(String(event.data)))
          if (!parsed.success) {
            useMarketStore.getState().setConnection(
              "error",
              "Message WebSocket invalide : contrat de marché non respecté",
            )
            return
          }
          const message = parsed.data
          if (message.type === "history") {
            if (message.symbol === symbol && message.timeframe === timeframe) {
              const state = useMarketStore.getState()
              state.applyHistory(message, selectionKey)
              // Si SQLite était vide au premier GET, le bootstrap du socket vient
              // de la synchroniser. Relire REST fournit couverture et pagination.
              if (includeHistory) {
                const controller = new AbortController()
                reconciliationControllers.add(controller)
                marketApi.getCandles({
                  symbol,
                  timeframe,
                  limit: 2_000,
                  profile,
                  signal: controller.signal,
                }).then((response) => {
                  useMarketStore.getState().initializeHistory(
                    response,
                    state.historyRequestGeneration,
                  )
                }).catch(() => undefined).finally(() => {
                  reconciliationControllers.delete(controller)
                })
              }
            }
          } else if (message.type === "update") {
            useMarketStore.getState().applyUpdate(message, selectionKey)
          } else useMarketStore.getState().setConnection("error", message.message)
        } catch {
          useMarketStore.getState().setConnection("error", "Message WebSocket invalide")
        }
      }
      currentSocket.onerror = () => {
        if (active && currentGeneration === generation) useMarketStore.getState().setConnection("error", "Erreur WebSocket")
      }
      currentSocket.onclose = () => {
        if (!active || currentGeneration !== generation) return
        useMarketStore.getState().setConnection("disconnected")
        reconnectTimer = window.setTimeout(connect, reconnectDelay)
        reconnectDelay = Math.min(Math.round(reconnectDelay * 1.5), 15_000)
      }
    }
    connect()
    return () => {
      // Invalider avant close empêche onclose de programmer une reconnexion obsolète.
      active = false
      generation += 1
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
      reconciliationControllers.forEach((controller) => controller.abort())
      socket?.close()
    }
  }, [symbol, timeframe, enabled, includeHistory, profile, profilePayload])
}
