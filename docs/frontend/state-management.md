# État global avec Zustand

Les stores scanner et marché restent séparés. L'URL porte le symbole et le
timeframe partageables ; Zustand porte les données éphémères et les états
asynchrones.

## Store marché

`useMarketStore` contient les bougies, indicateurs, marqueurs, couverture,
bornes chargées, pagination, snapshot, connexion et visibilité. `selectionKey`
et `historyRequestGeneration` ne dupliquent pas la sélection métier : ils
servent uniquement à ignorer une réponse tardive d'un ancien marché.

Actions principales :

- `resetMarket` nettoie la sélection et crée une nouvelle génération ;
- `initializeHistory`, `prependHistory` et `mergeRecentHistory` fusionnent les
  lots REST sans doublon ;
- `applyHistory` fusionne le snapshot WebSocket compatible ;
- `applyUpdate` remplace ou ajoute incrémentalement le tick courant ;
- `setHistoryError` et `setConnection` gardent les erreurs REST et WS séparées.

`historyVersion` déclenche `setData` pour un lot. `historyPrependCount` contient
le nombre réellement ajouté à gauche et sert à restaurer la plage logique.
`updateVersion` déclenche `update` pour un tick sans retrier tout l'historique.

Les marqueurs sont dédupliqués par temps, texte, catégorie, source et type de
divergence, sans limite globale arbitraire. Les préférences de visibilité
survivent au changement de marché.
