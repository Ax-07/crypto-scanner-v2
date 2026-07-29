# Routage et paramètres d’URL

Le routeur est créé dans `src/app/router.tsx` avec `createBrowserRouter`. Toutes les pages vivent sous `AppLayout`.

| Route | Comportement |
| --- | --- |
| `/` | Redirection avec remplacement vers `/scanner` |
| `/scanner` | Configuration, progression et résultats |
| `/market?symbol=BTC%2FUSDC&timeframe=1h` | Marché temps réel partageable |
| `*` | Page 404 |

Les pages sont chargées à la demande avec la propriété `lazy`. `RouteLoading` est fourni comme `HydrateFallback`, ce qui évite un rendu vide et l’avertissement React Router pendant l’hydratation initiale. `RouteErrorPage` traite les erreurs de route.

## Contrat de l’URL marché

`parseMarketSearch` accepte un symbole en majuscules au format `BASE/QUOTE` et un timeframe présent dans `MARKET_TIMEFRAMES`. Une valeur absente ou invalide revient à `BTC/USDC` et `1h`.

```ts
const market = parseMarketSearch(
  new URLSearchParams("symbol=ETH%2FUSDC&timeframe=15m"),
)
// { symbol: "ETH/USDC", timeframe: "15m" }
```

`MarketPage` remplace ensuite les paramètres invalides par leur forme normalisée. Le symbole n’est pas corrigé silencieusement vers les majuscules : `btc/usdc` est invalide et revient au marché par défaut.

## Ajouter une route

1. Créer un composant nommé exporté dans `src/pages/`.
2. Ajouter une entrée lazy dans les enfants de `appRoutes`.
3. Ajouter la navigation dans `AppSidebar` si la page est destinée au menu.
4. Mettre à jour le titre du layout si nécessaire.
5. Tester le module lazy, la navigation directe et la page inconnue.

En production, le serveur statique doit appliquer un fallback SPA vers `index.html` pour `/scanner`, `/market` et toute nouvelle route.
