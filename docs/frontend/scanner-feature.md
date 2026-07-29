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

`ScannerResultsTable` construit ses colonnes historiques à partir des indicateurs
activés dans le snapshot de configuration du job et ajoute toujours la colonne
non triable `Signaux`. La première cellule couvre toutes les colonnes lorsqu’il
n’y a aucun résultat ; le nombre est toujours calculé comme un entier défini afin
de ne jamais transmettre `NaN` à `colSpan`.

Chaque ligne propose un lien vers :

```text
/market?symbol=<paire encodée>&timeframe=<timeframe du scan>
```

L’export CSV est une navigation directe vers l’URL produite par `scannerApi.exportUrl`. Elle utilise la même origine API que les appels JSON.

### Signaux structurés

Chaque ligne possède son propre `Sheet` Shadcn/Radix, piloté par un état React
local. La cellule affiche un résumé descriptif compact : nombre disponible,
nombre indisponible et décompte des directions effectivement calculées. Le bouton
« Voir les signaux » est nommé avec le symbole et le timeframe pour les lecteurs
d'écran.

Le panneau réutilise `IndicatorSignalsPanel` pour les cartes détaillées et affiche
le score/grade de confluence sous le libellé distinct « Contexte historique ». Il
rappelle que l'intensité technique n'est pas une probabilité de gain. Le champ
absent d'un ancien payload et l'objet moderne vide possèdent des messages
différents. Un dictionnaire partiel n'est pas complété artificiellement et les
statuts indisponibles restent ceux du backend.

Sur mobile, le panneau utilise toute la largeur et son contenu défile
verticalement ; sur desktop, il devient un panneau latéral large. Le scroll
horizontal historique de la table reste actif. L'ouverture n'écrit ni dans
Zustand ni dans l'URL et n'interfère pas avec le lien marché.

## Échecs à connaître

- Une erreur de configuration initiale met le store en `failed`.
- Une erreur POST est remontée au formulaire et au store.
- Un message WebSocket non JSON marque le scan comme échoué.
- Une coupure du socket de progression est signalée, sans reconnexion automatique actuellement.
- Une erreur backend terminal utilise `job.error` lorsqu’il est présent.

Le détail du cycle serveur est décrit dans la [documentation du flux scanner backend](../backend/scanner-flow.md) et son [contrat WebSocket](../backend/websockets.md#progression-du-scanner).
