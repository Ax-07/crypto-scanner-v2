# Frontend React

La route `/backtests/experiments` utilise React Hook Form, Zod et les composants
`Field`. Elle affiche l’estimation du nombre de candidats, les splits, effectifs,
rejets et exports; elle ne promeut aucun profil automatiquement.

Documentation du dashboard React 19 de `scanner_crypto`. Le frontend utilise TypeScript, Vite, React Router, Zustand, React Hook Form, Zod, Shadcn UI et Lightweight Charts. Les dépendances sont exclusivement gérées avec **pnpm** ; `frontend/pnpm-lock.yaml` est le lockfile de référence.

Il permet de configurer et suivre des jobs de scan via FastAPI, d'explorer leurs résultats, puis d'ouvrir un marché temps réel alimenté par WebSocket. Il ne calcule pas les indicateurs : il présente les données et orchestre les interactions navigateur.

## Prérequis et environnement

- Node.js `^20.19.0` ou `>=22.12.0` ;
- pnpm 10 (`pnpm@10.15.1` déclaré) ;
- backend FastAPI accessible.

`VITE_API_URL` configure l'origine HTTP (`http://localhost:8000` par défaut dans le client). `VITE_WS_URL` peut surcharger l'origine du flux marché. Voir [Démarrage local](getting-started.md) pour les valeurs et précautions.

Le marché utilise aussi `VITE_MARKET_INITIAL_CANDLE_LIMIT` (2000),
`VITE_MARKET_HISTORY_PAGE_LIMIT` (2000),
`VITE_MARKET_PREFETCH_THRESHOLD_BARS` (100) et, facultativement,
`VITE_MARKET_MAX_CANDLES_IN_MEMORY` (0, donc sans limite).

## Architecture et flux

```text
Navigateur → React Router → AppLayout
                         ├─ ScannerPage → React Hook Form → API REST
                         │                            └──→ WebSocket job → Zustand
                         └─ MarketPage ← paramètres URL
                                      └──→ WebSocket marché → Zustand → graphique
```

Les pages orchestrent les features. React Hook Form conserve la configuration en cours d'édition ; Zustand conserve le job appliqué et les données de flux ; l'URL conserve le symbole et le timeframe partageables.

## Routes

| URL | Rôle |
| --- | --- |
| `/` | Redirection vers `/scanner` |
| `/scanner` | Configuration, progression et résultats |
| `/market?symbol=BTC%2FUSDC&timeframe=1h` | Marché temps réel |
| `*` | Page 404 |

## Parcours recommandé

1. [Démarrage local](getting-started.md)
2. [Architecture](architecture.md)
3. [Routage et paramètres d’URL](routing.md)
4. [État global Zustand](state-management.md)
5. [Formulaire et validation](forms-and-validation.md)
6. [Client API et types](api-and-types.md)
7. [Fonctionnalité scanner](scanner-feature.md)
8. [Fonctionnalité marché](market-feature.md)
9. [WebSockets](websockets.md)
10. [UI et accessibilité](ui-and-accessibility.md)
11. [Tests](testing.md)
12. [Build et déploiement](build-and-deployment.md)
13. [Dépannage](troubleshooting.md)

Le contrat serveur détaillé reste documenté dans la [documentation backend](../backend/README.md), notamment les [WebSockets](../backend/websockets.md).

## Commandes essentielles

```bash
cd frontend
pnpm install
pnpm run dev
pnpm run typecheck
pnpm run lint
pnpm run test
pnpm run build
pnpm run measure:history
```

## Carte rapide du code

| Répertoire | Responsabilité |
| --- | --- |
| `src/app/` | Routeur, providers et layout partagé |
| `src/pages/` | Assemblage des écrans routés |
| `src/features/` | Logique et composants propres au scanner et au marché |
| `src/api/` | Transport HTTP et endpoints métier |
| `src/stores/` | État global des flux asynchrones |
| `src/types/` | Contrats TypeScript du domaine |
| `src/components/ui/` | Primitives Shadcn réutilisables |
| `src/components/dashboard/` | Visualisations et contrôles du marché |

## Règles de contribution

- Utiliser `pnpm`, jamais npm ou yarn.
- Traiter les réponses réseau comme `unknown` à leur entrée et conserver les types canoniques dans `src/types/`.
- Garder les paramètres partageables dans l’URL, pas dans Zustand.
- Garder les sockets hors de l’état sérialisable.
- Ajouter un test ciblé pour toute modification du parsing, de la validation ou du cycle de vie d’un flux.
- Exécuter les quatre contrôles avant livraison : typecheck, lint, tests et build.

## Limites connues

- Le socket de progression scanner ne se reconnecte pas automatiquement.
- Les stores sont éphémères : un rechargement perd le job et les préférences.
- Le déploiement doit fournir un fallback SPA et relayer les upgrades WebSocket.
