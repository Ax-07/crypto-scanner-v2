# Fonctionnalité scanner

## Composition

`ScannerPage` délègue à `ScannerWorkspace`, qui relie le store aux trois blocs visibles : formulaire, progression/actions et tableau de résultats. Le tableau reçoit `job.config` plutôt que la configuration actuellement éditée afin que ses colonnes décrivent exactement le scan exécuté.

## Démarrage et progression

Au premier montage, la configuration par défaut est chargée si elle manque. Un lancement :

1. conserve la configuration validée dans le store ;
2. efface les anciens résultats ;
3. crée le job par HTTP ;
4. ouvre `/api/scanner/ws/{jobId}` ;
5. remplace le snapshot du job à chaque message ;
6. récupère le job avec ses résultats lorsque son état devient terminal.

Les messages d’un ancien job sont ignorés grâce à une comparaison d’instance et d’identifiant. Démarrer un nouveau scan ferme explicitement l’ancienne connexion.

## Annulation

`cancelScan` envoie `DELETE /api/scanner/jobs/{id}`. Le bouton passe à l’état `cancelling`; le WebSocket peut ensuite transmettre le snapshot final. Un job annulé peut avoir des résultats partiels, qui sont récupérés par le même endpoint que ceux d’un job terminé.

## Résultats

`ScannerResultsTable` construit ses colonnes à partir des indicateurs activés dans le snapshot de configuration du job. La première cellule couvre toutes les colonnes lorsqu’il n’y a aucun résultat ; le nombre est toujours calculé comme un entier défini afin de ne jamais transmettre `NaN` à `colSpan`.

Chaque ligne propose un lien vers :

```text
/market?symbol=<paire encodée>&timeframe=<timeframe du scan>
```

L’export CSV est une navigation directe vers l’URL produite par `scannerApi.exportUrl`. Elle utilise la même origine API que les appels JSON.

## Échecs à connaître

- Une erreur de configuration initiale met le store en `failed`.
- Une erreur POST est remontée au formulaire et au store.
- Un message WebSocket non JSON marque le scan comme échoué.
- Une coupure du socket de progression est signalée, sans reconnexion automatique actuellement.
- Une erreur backend terminal utilise `job.error` lorsqu’il est présent.

Le détail du cycle serveur est décrit dans la [documentation du flux scanner backend](../backend/scanner-flow.md) et son [contrat WebSocket](../backend/websockets.md#progression-du-scanner).
