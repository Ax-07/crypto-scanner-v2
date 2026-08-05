# Source backtest canonique du pipeline ML v2

## Périmètre

La Phase 1 fournit le chemin officiel qui prépare le backtest nécessaire à un export
`causal-features-v2`. Elle ne lance ni entraînement, ni benchmark v2, ni téléchargement réseau.
Elle ne transforme pas non plus le faible `dataset_version` du moteur en hash du contenu OHLCV :
ce renforcement reste réservé à la Phase 2.

Trois objets restent distincts :

1. le profil de signaux `ml-dataset-v2`, construit par
   `build_ml_dataset_profile_v2(...)` ;
2. le backtest source, qui persiste les observations et outcomes causaux ;
3. le dataset JSONL exporté avec le schéma `causal-features-v2`.

## Commande officielle

Depuis `backend/` :

```powershell
.\venv\Scripts\python.exe -m app.ml.cli.prepare_ml_v2_source `
  BTC/USDC `
  --timeframe 1h `
  --start 2025-01-01T00:00:00Z `
  --end 2025-07-01T00:00:00Z `
  --database-path data/scanner_crypto.sqlite3 `
  --json
```

Paramètres de source autorisés : symbole, timeframe, début, fin, exchange, type de marché,
quote et chemin SQLite. `--dry-run` prévisualise sans initialiser, migrer ou modifier la base.
`--wait` attend aussi un job compatible déjà exécuté par un autre processus. Un job créé ou
repris par cette CLI est toujours attendu : quitter le processus annulerait autrement la tâche
asynchrone locale.

Les dates sont ISO-8601, avec fuseau, et la fin est exclusive. Le symbole suit `BASE/QUOTE`.

La CLI n'expose volontairement aucune option pour remplacer :

- `signal_profile_id="ml-dataset-v2"` ;
- le `ScanConfig` retourné par le constructeur officiel ;
- `snapshot_status="confirmed"` ;
- `replay_mode="every_bar"` ;
- `horizons=[6]` ;
- `entry_policy="signal_close"` ;
- `gap_policy="reject_range"` ;
- l'absence de simulation portefeuille.

## Prévisualisation et sorties

```powershell
.\venv\Scripts\python.exe -m app.ml.cli.prepare_ml_v2_source `
  BTC/USDC --timeframe 1h `
  --start 2025-01-01T00:00:00Z --end 2025-07-01T00:00:00Z `
  --database-path data/scanner_crypto.sqlite3 --dry-run --json
```

La sortie humaine et `--json` proviennent du même `MLV2SourceResult`. Elle contient l'action,
la raison, le job, son statut, le profil, le schéma de features, la fenêtre, l'horizon, les
fingerprints, le diagnostic de couverture et `can_export`.

Exemple abrégé :

```json
{
  "action": "created",
  "can_export": true,
  "feature_schema_version": "causal-features-v2",
  "job_id": "<uuid>",
  "signal_profile_id": "ml-dataset-v2",
  "status": "completed"
}
```

Actions possibles : `created`, `reused`, `resumed`, `already-running`, et en prévisualisation
`would-create`, `would-reuse`, `would-resume`.

Codes de sortie : 0 pour une résolution réussie, 1 pour un job terminal en échec ou une erreur
inattendue, 2 pour une entrée invalide ou un historique insuffisant, 130 pour une interruption.
L'erreur persistée du job est affichée lorsqu'elle existe.

## Identité logique et concurrence

L'identité `ml-v2-source-identity-v1` est le SHA-256 d'un JSON canonique (`sort_keys`, séparateurs
stables) contenant :

- `SIGNAL_EVALUATION_VERSION` ;
- le `BacktestConfig` complet validé, donc symbole, exchange, marché, quote, timeframe, fenêtre,
  profil technique, politiques de replay/décision/gap/entrée, horizons, snapshot, coûts et
  portefeuille absent.

Ainsi, toute propriété susceptible de modifier observations, labels ou provenance produit une
autre identité. L'ordre accidentel des clés JSON n'intervient pas.

La migration SQLite 9 ajoute `ml_v2_source_claims`, qui associe une identité unique à un job et
à sa version d'algorithme. `BEGIN IMMEDIATE`, la clé primaire et la mise à jour conditionnelle du
job remplacé garantissent une seule revendication logique, y compris entre processus. Un verrou
asynchrone est ajouté à la granularité `(chemin de base, identité)` dans le processus ; il ne
bloque pas les backtests différents. Les jobs historiques ne sont pas modifiés. Un job historique
canonique peut être adopté atomiquement lors de sa première résolution.

Le JSON seul permettait une comparaison canonique, mais pas d'empêcher deux inserts concurrents ;
c'est la raison de la migration.

## Politique par état

- `completed` : réutilisé seulement si le builder v2 confirme au moins une ligne exportable,
  avec observations confirmed, outcome h6, profil et fingerprint valides ;
- `pending` ou `running` : retourné sans doublon (`already-running`) ;
- `interrupted` : repris uniquement avec un checkpoint durable de la version moteur courante ;
- `failed` ou `cancelled` : jamais repris silencieusement, un nouveau job remplace la
  revendication ;
- terminé sans observation, sans outcome h6 ou sans ligne v2 exploitable : nouveau job ;
- version moteur, fenêtre, timeframe, profil ou configuration différente : autre identité ou
  remplacement explicite si une revendication incohérente est détectée.

Les anciens jobs restent consultables. La CLI ne change jamais directement un statut ni un
checkpoint ; elle passe par `BacktestManager`.

## Contrôle local de l'historique

Avant création ou reprise, le service contrôle sans réseau :

- les 200 bougies de warmup principal requises actuellement par le profil ;
- toute la fenêtre de décision ;
- les 7 bougies chargées après la fin par le moteur pour produire l'outcome h6 ;
- les 60 bougies de warmup pour chaque timeframe MA supérieur ;
- les bougies closes et les gaps internes.

Le diagnostic structuré indique fenêtre demandée, bornes disponibles, compte attendu/obtenu et
gaps. Il recommande la CLI de backfill, mais ne la lance jamais.

## Export après préparation

Lorsque `can_export=true` :

```powershell
.\venv\Scripts\python.exe -m app.ml.cli.export_ml_dataset <JOB_ID> `
  --feature-schema-version causal-features-v2 `
  --database-path data/scanner_crypto.sqlite3 `
  --output-directory artifacts/ml-v2
```

Le builder vérifie à nouveau le job terminé, le profil canonique (y compris exchange et marché),
l'horizon 6 et la provenance de chaque observation. L'exporteur écrit un JSONL déterministe et
un manifeste avec SHA-256 ; le loader revérifie octets, ordre et métadonnées.

## Fingerprints et garanties

- `profile_fingerprint` est le SHA-256 du `ScanConfig` canonique et reste porté par chaque
  observation ;
- `source_identity` identifie le contrat complet du source et la version moteur ;
- `config_fingerprint` reste réservé au portefeuille et vaut `null` pour le source v2 ;
- `dataset_version` actuel ne hash que symbole, bornes et nombre de bougies chargées.

Le replay ne voit que les bougies closes disponibles au temps de décision. Les features v2 sont
extraites de l'observation causale ; le futur h6 sert uniquement au label. Pour les mêmes bougies,
configurations et versions, deux exports ont les mêmes lignes et le même SHA-256 de données.

## Limites reportées à la Phase 2

L'identité logique ne prouve pas que deux contenus OHLCV ayant les mêmes bornes et le même nombre
de lignes sont identiques. La Phase 2 devra définir un fingerprint fort du contenu OHLCV et sa
politique d'invalidation. Aucun modèle, benchmark v2 ou nouvelle période terminale n'est défini
par la Phase 1.
