import { isValidElement } from "react"
import { matchRoutes, Navigate, type RouteObject } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { appRoutes } from "@/app/router"

function leaf(path: string): RouteObject {
  const matches = matchRoutes(appRoutes, path)
  if (!matches?.length) throw new Error(`Route absente : ${path}`)
  return matches.at(-1)!.route
}

describe("appRoutes", () => {
  it("fournit un fallback pendant le chargement initial", () => {
    expect(appRoutes[0].HydrateFallback).toBeTypeOf("function")
  })

  it("redirige la racine vers le scanner", () => {
    const element = leaf("/").element
    expect(isValidElement(element)).toBe(true)
    expect(isValidElement(element) && element.type).toBe(Navigate)
    expect(isValidElement<{ to: string }>(element) && element.props.to).toBe("/scanner")
  })

  it.each([
    ["/scanner", "ScannerPage"],
    ["/market", "MarketPage"],
    ["/backtests", "BacktestsPage"],
    ["/chemin-inconnu", "NotFoundPage"],
  ])("charge le module lazy de %s", async (path, componentName) => {
    const route = leaf(path)
    expect(route.lazy).toBeTypeOf("function")
    const loaded = await (route.lazy as () => Promise<{ Component: { name: string } }>)()
    expect(loaded.Component.name).toBe(componentName)
  })
})
