# Tests frontend

La suite utilise Vitest, Testing Library, `jest-dom` et jsdom. La configuration partagée est dans `src/test/setup.ts`.

## Commandes

```bash
cd frontend
pnpm run test
pnpm run measure:history
pnpm exec vitest src/features/scanner/scan-config-schema.test.ts
pnpm exec vitest --watch
```

Le script officiel utilise `vitest run` et termine après un passage. Les commandes ciblées sont utiles pendant le développement, mais la suite complète doit être exécutée avant livraison.

Mesure locale de référence du 23 juillet 2026, Node/Vitest sur la machine de
développement, fusion d'une page de 2 001 points dont un doublon (médiane de
cinq exécutions) :

| Historique existant | Médiane |
|---:|---:|
| 10 000 | 1,53 ms |
| 50 000 | 7,00 ms |
| 100 000 | 14,76 ms |

Ces chiffres ne sont pas un seuil CI : ils caractérisent la fonction de fusion,
pas le coût de rendu de Lightweight Charts ni la mémoire du navigateur.

## Couverture actuelle

- création du routeur et chargement lazy des pages ;
- validation croisée de la configuration scanner ;
- parsing et tri des listes de périodes ;
- validation/normalisation des paramètres marché ;
- colonnes de résultats fondées sur `job.config` et navigation vers le marché ;
- déduplication du chargement de configuration ;
- validation runtime du WebSocket scanner et protection du job courant ;
- remplacement et nettoyage des WebSockets marché.
- fusion et déduplication des pages, garde de génération et compensation logique ;
- mesure de la fusion sur 10k, 50k et 100k bougies.

Les tests ne font pas d’appel réseau réel. Fetch, WebSocket et modules lourds doivent être simulés à la frontière, sans recopier l’implémentation interne.

## Stratégie

Préférer :

- un test unitaire pour une fonction pure de parsing ou validation ;
- un test de store pour une transition asynchrone et ses protections contre les courses ;
- un test Testing Library pour le comportement observable, les rôles et la navigation ;
- un test de contrat ciblé lorsqu’un payload backend change.

Éviter les assertions sur les classes CSS ou la structure exacte des composants Shadcn. Interroger l’écran par rôle, nom accessible ou texte métier.

## WebSockets

Une simulation de socket doit exposer les callbacks `onopen`, `onmessage`, `onerror`, `onclose` et tracer `close()`. Tester les événements tardifs après changement de symbole : ils ne doivent ni reconnecter l’ancien flux ni modifier le store.

## Critère de fin

```bash
pnpm run typecheck
pnpm run lint
pnpm run test
pnpm run build
```

Une correction d’avertissement React doit inclure un scénario qui rend réellement le composant ou la route concernée lorsqu’un test raisonnable peut empêcher la régression.
