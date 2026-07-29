# Architecture

## Vue d’ensemble

```text
main.tsx
└── AppProviders
    └── App
        └── RouterProvider
            └── AppLayout
                ├── AppSidebar
                └── Outlet
                    ├── ScannerPage → ScannerWorkspace → store scanner → API + WS job
                    └── MarketPage  → URL → socket marché → store marché → graphique
```

`main.tsx` installe les providers transverses et React Strict Mode. `App.tsx` ne fait qu’exposer le routeur. Le layout fournit la navigation commune ; les pages assemblent les blocs métier sans réimplémenter le transport réseau.

## Frontières de responsabilité

- `src/app/router.tsx` décrit les routes, le chargement différé et les écrans de secours.
- `src/pages/` lit le contexte de navigation et compose les features.
- `src/features/scanner/` gère le formulaire, son schéma, la progression et les résultats.
- `src/features/market/` valide l’URL, sélectionne un marché et pilote le socket.
- `src/stores/` centralise les transitions de flux qui doivent survivre ou être partagées entre composants.
- `src/api/` centralise l’origine serveur, les erreurs HTTP et les URLs métier.
- `src/types/` est la source de vérité TypeScript pour les payloads scanner et marché.

## Arborescence

```text
frontend/
├── src/
│   ├── app/                 # routeur, providers, layout
│   ├── pages/               # écrans associés aux routes
│   ├── features/            # scanner et marché
│   ├── components/ui/       # primitives Shadcn
│   ├── components/dashboard/# composants métier du graphique
│   ├── api/                 # HTTP et URLs métier
│   ├── stores/              # état global Zustand
│   ├── hooks/               # hook responsive partagé
│   ├── types/               # contrats canoniques
│   └── lib/                 # utilitaires génériques, dont cn
├── components.json          # configuration Shadcn
├── vite.config.ts           # plugins, alias et proxy de développement
└── package.json             # scripts et dépendances pnpm
```

## Flux scanner

```text
GET configuration → édition locale RHF/Zod → POST job
→ snapshot du job → WebSocket de progression
→ état terminal → GET résultats → tableau/export
```

La configuration en cours d’édition reste locale au formulaire. Le store ne reçoit une nouvelle configuration qu’au lancement. Le socket de progression est une variable privée du module et non une donnée Zustand.

## Flux marché

```text
URL validée (symbol, timeframe) → useMarketSocket
→ history complet → store → setData du graphique
→ update incrémental → store → update du graphique
```

Le symbole et le timeframe ne sont pas dupliqués dans le store. Cette règle garantit qu’un lien copié ou un retour navigateur reconstruit le même marché.

## Règles d’architecture

Pour ajouter une feature, placer le contrat partagé dans `src/types`, le transport dans `src/api`, l’état transversal dans un store seulement s’il dépasse la durée de vie d’un composant, puis exposer une page mince. Une donnée dérivable ne doit pas être copiée dans plusieurs couches.

Les composants de `src/components/ui` sont des primitives. La logique métier appartient aux features ou aux composants `dashboard`, jamais aux primitives générées.

Les dépendances circulent des pages vers les features, puis vers les API/stores/types. Une primitive UI ne dépend pas d'une feature. Les appels HTTP restent centralisés dans `src/api`; les hooks ou stores pilotent leurs effets de bord. Les paramètres navigables restent dans React Router, l'édition temporaire dans React Hook Form et l'état partagé dans Zustand.
