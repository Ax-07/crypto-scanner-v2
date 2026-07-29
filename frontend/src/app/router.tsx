/**
 * Configuration principale des routes du frontend.
 * Les pages lazy partagent AppLayout, un écran d'erreur et un fallback d'hydratation.
 */
import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";

import { AppLayout } from "@/app/layouts/app-layout";
import { RouteLoading } from "@/components/route-loading";
import { RouteErrorPage } from "@/pages/route-error-page";

/** Arbre de routes exporté séparément pour permettre les tests avec un routeur mémoire. */
export const appRoutes: RouteObject[] = [
  {
    element: <AppLayout />,
    errorElement: <RouteErrorPage />,
    HydrateFallback: RouteLoading,
    children: [
      { index: true, element: <Navigate to="/scanner" replace /> },
      { path: "scanner", lazy: async () => ({ Component: (await import("@/pages/scanner-page")).ScannerPage }) },
      { path: "market", lazy: async () => ({ Component: (await import("@/pages/market-page")).MarketPage }) },
      { path: "backtests", lazy: async () => ({ Component: (await import("@/pages/backtests-page")).BacktestsPage }) },
      { path: "backtests/experiments", lazy: async () => ({ Component: (await import("@/pages/experiments-page")).ExperimentsPage }) },
      { path: "*", lazy: async () => ({ Component: (await import("@/pages/not-found-page")).NotFoundPage }) },
    ],
  },
];

/** Routeur navigateur unique de l'application. */
export const router = createBrowserRouter(appRoutes);
