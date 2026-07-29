# Client API et types

## Client HTTP

`src/api/client.ts` expose `apiRequest<T>`. Il préfixe chaque chemin avec `API_URL`, ajoute `Content-Type: application/json`, transmet les options Fetch — dont `AbortSignal` — puis transforme les réponses non réussies en `ApiError`.

```ts
const job = await apiRequest<ScanJob>("/api/scanner/jobs", {
  method: "POST",
  body: JSON.stringify(config),
  signal: controller.signal,
})
```

Une réponse 204 produit `undefined` au niveau d’exécution ; choisir un type compatible pour un futur endpoint sans contenu. Le générique TypeScript ne valide pas le JSON à l’exécution. Toute nouvelle réponse non maîtrisée doit être considérée comme `unknown` et validée si elle peut évoluer indépendamment du frontend.

## Endpoints scanner

`src/api/scanner.ts` centralise :

| Méthode | Endpoint |
| --- | --- |
| `getDefaultConfig` | `GET /api/scanner/config` |
| `start` | `POST /api/scanner/jobs` |
| `results` | `GET /api/scanner/jobs/{id}/results` |
| `cancel` | `DELETE /api/scanner/jobs/{id}` |
| `exportUrl` | `/api/scanner/jobs/{id}/export.csv` |
| `websocketUrl` | `/api/scanner/ws/{id}` avec protocole WS/WSS |
| `getMarkets` | `GET /api/scanner/markets?quote=...&market_type=...` |

Les composants ne doivent pas reconstruire ces URLs. Ajouter une méthode métier dans `scannerApi`, puis la consommer depuis une feature ou un store.

## Modèle d’erreur

```ts
try {
  await scannerApi.start(config)
} catch (error) {
  if (error instanceof ApiError && error.status === 422) {
    error.issues.forEach(({ loc, msg }) => console.error(loc, msg))
  }
}
```

`readIssues` et `readDetail` contrôlent la forme du payload avant lecture. Une chaîne `detail` devient le message ; une liste de validations est concaténée tout en restant disponible dans `issues`.

## Types canoniques

- `src/types/scanner.ts` définit `ScanConfig`, `ScanJob`, `ScanResult`, les statuts, signaux et timeframes.
- `src/types/market.ts` définit les bougies, indicateurs, marqueurs, snapshots et l’union discriminée `MarketMessage`.
- `src/types/indicator-signals.ts` définit le contrat structuré commun à `ScanResult`,
  `MarketSnapshot` et `SignalObservation`.

`IndicatorSignal` porte un statut strict, une direction, un événement et un état
nullables, une intensité technique `strength` bornée entre 0 et 1, une raison et
une valeur brute nullable. Les indicateurs reconnus sont `rsi`, `sma`, `ema`,
`macd`, `bollinger` et `stochastic`; leur dictionnaire peut être partiel.

Pendant la migration, `indicator_signals` est optionnel mais jamais nullable :
un champ absent désigne un ancien payload, `{}` un payload moderne sans signal
produit, et un signal présent avec `insufficient_data`, `invalid_data` ou
`disabled` décrit explicitement une indisponibilité. Le frontend ne reconstruit
jamais ces données depuis les anciens champs.

Le schéma commun rejette les clés d'indicateur et champs de signal inconnus ainsi
que les nombres non finis. Les enveloppes scanner/backtest restent additives afin
de préserver leurs champs historiques; les vues et messages marché connus sont
stricts. `strength` est une intensité technique, pas une probabilité de réussite
ni une prévision de gain.

Les trois stores conservent ces données et les interfaces scanner, marché et
backtest les affichent avec la bibliothèque commune. L'état réel, les champs
legacy et les conditions de dépréciation sont détaillés dans
[`structured-signals-migration-audit.md`](structured-signals-migration-audit.md).

Depuis la Phase 5.5, `backtestApi.observations(id, offset, limit)` transmet la
pagination native de `GET /api/backtests/{id}/observations`. Le store conserve la
page courante, le total, l'offset et ses états de chargement/erreur. Ouvrir le
détail d'une observation ne déclenche aucun appel réseau.

Le type `SignalObservation` expose aussi les champs backend utilisés par le détail :
`confluence_breakdown`, `filter_trace`, `source_open_time`, `calculation_mode` et
`schema_version`, optionnels côté frontend pour préserver les anciens résultats.
`accepted` reste un booléen d'acceptation par les filtres, pas une décision
d'entrée/sortie.

Utiliser l’union `message.type` pour réduire un message WebSocket. Éviter les copies locales partielles de ces contrats : elles dérivent rapidement du backend. Les exemples complets de payloads sont dans la [documentation WebSocket](websockets.md).

## Contrat des filtres structurés

`src/types/structured-signal-filters.ts` est la source TypeScript canonique de
la v1 et `src/schemas/structured-signal-filters.ts` sa validation Zod stricte.
`ScanConfig.structured_signal_filters` reste optionnel et nullable pour les
anciens payloads. Le schéma refuse versions, indicateurs, champs et clés
inconnus, listes de valeurs vides ou dupliquées, directions et statuts invalides.

`scannerApi.start` sérialise le champ dans le POST existant. Les snapshots de
jobs valident additivement ce sous-contrat ; l'absence du champ reste valide.
Aucun endpoint, appel réseau ou store supplémentaire n'est introduit.
Les exemples JSON et la politique de changement v1 sont regroupés dans le
[rapport de stabilisation backend](../backend/structured-signal-filters-v1-stability.md).

## Évolution du contrat

Lorsqu'un champ backend change, mettre à jour dans la même livraison le type canonique, le client ou store consommateur, la validation éventuelle, les exemples et les tests. Utiliser `unknown` à une frontière non fiable puis réduire sa forme ; éviter `any`, qui masque les écarts de contrat.

Les champs `null` représentent une valeur calculable mais absente, par exemple `rsi` ou `last_close_price`. `results?` est optionnel car il n'est ajouté qu'au snapshot de l'endpoint de résultats. Ne pas remplacer arbitrairement `null` par `undefined`, car le JSON backend et les conditions d'affichage les distinguent.

## Présentation des erreurs

- `ApiError` alimente les `FieldError` et l'`Alert` du scanner.
- Les erreurs WebSocket sont stockées dans les stores ; celles du scanner sont visibles dans une alerte.
- `RouteErrorPage` traite les erreurs levées pendant le routage.
- Sonner est installé globalement, mais aucun flux métier courant ne lui envoie encore de toast.
- Lightweight Charts est nettoyé au démontage ; une erreur de création inattendue remonte actuellement à la limite d'erreur de route, sans traitement spécialisé.
