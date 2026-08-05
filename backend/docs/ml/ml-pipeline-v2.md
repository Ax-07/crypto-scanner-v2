# Source backtest canonique du pipeline ML v2

## Périmètre

Les Phases 1 et 2 fournissent le chemin officiel qui prépare puis prouve le backtest nécessaire à
un export `causal-features-v2`. Elles ne lancent ni entraînement, ni benchmark v2, ni
téléchargement réseau.

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
- `input_data_fingerprint` prouve le contenu exact de tous les flux OHLCV consommés ;
- `config_fingerprint` reste réservé au portefeuille et vaut `null` pour le source v2 ;
- `dataset_version` reste le marqueur historique faible (symbole, bornes et compte), uniquement
  pour compatibilité. Il n'est jamais utilisé comme preuve ML v2.

Le replay ne voit que les bougies closes disponibles au temps de décision. Les features v2 sont
extraites de l'observation causale ; le futur h6 sert uniquement au label. Pour les mêmes bougies,
configurations et versions, deux exports ont les mêmes lignes et le même SHA-256 de données.

## Encodage OHLCV fort

`ohlcv-content-sha256-v1` alimente SHA-256 incrémentalement, sans grande sérialisation
intermédiaire. Le domaine est préfixé par `scanner-binance:ohlcv-stream\0`. Les textes UTF-8 sont
précédés de leur longueur `uint32` big-endian ; timestamps, comptes et bornes sont des `int64`
big-endian en millisecondes Unix ; les nombres OHLCV sont des IEEE-754 binary64 big-endian.
`-0.0` est normalisé en `+0.0`, NaN et les infinis sont refusés. Les bougies doivent être
strictement croissantes et uniques.

Le hash d'un flux couvre version, rôle, exchange, marché, symbole, timeframe, `closed_only`,
fenêtre demandée, warmup, futur, compte, bornes effectives, puis pour chaque bougie :
`open_time`, OHLCV, `close_time` optionnel et `is_closed`. Le flux principal couvre le warmup,
la fenêtre de décision et les sept bougies actuellement chargées pour l'outcome h6. Les flux
`trend:<timeframe>` couvrent leur warmup MA et toutes les bougies effectivement remises au moteur.

`ohlcv-input-aggregate-sha256-v1` trie les flux par
`(role, exchange, market, symbol, timeframe)` et hache son domaine, sa version, le
`source_identity`, chaque hash de flux et toutes ses métadonnées de plan. La fenêtre demandée
exprime le besoin canonique ; les bornes effectives décrivent les premières et dernières bougies
réellement obtenues.

Le service calcule le fingerprint attendu avec le même chargeur que le moteur. Le moteur recharge
une seule fois ces objets, recalcule le fingerprint avant tout résultat, le compare strictement,
puis confirme la provenance persistée. Une modification entre ces deux lectures fait échouer le
job explicitement. Une modification postérieure au chargement ne change pas les objets immuables
déjà consommés.

## Persistance, réutilisation et migration 10

La migration 10 ajoute la colonne nullable `ml_v2_source_claims.input_data_fingerprint` et la
table `ml_v2_source_inputs`. Cette table conserve par job l'identité logique, les versions, le
fingerprint agrégé, l'inventaire JSON complet, la création et la confirmation moteur. Les jobs et
claims issus du schéma 9 restent intacts avec une provenance forte absente ; aucun hash ne leur est
attribué rétroactivement.

Un job terminé n'est réutilisé que si sa provenance est reconnue, confirmée, égale aux données
candidates et si le builder v2 le juge exportable. Sans fingerprint fort, ou après divergence, il
devient historique non réutilisable : un nouveau job est créé, le claim est remplacé sous
`BEGIN IMMEDIATE`, et l'ancien job, ses observations et outcomes sont conservés. Une bougie hors
du plan n'affecte pas le hash. La transaction conditionnelle et le verrou par
`(base, source_identity)` empêchent deux générations pour une même mutation.

## Manifeste reproductible et vérification

Le manifeste reproductible porte `manifest_schema_version=2`, le `BacktestConfig` complet,
`source_identity`, profil et fingerprint, version du moteur, statut source, fingerprint agrégé,
inventaire de chaque flux, versions builder/exporter/loader/features/labels, ordre des lignes et
règles d'exclusion. Le JSONL et le manifeste utilisent un JSON canonique trié, compact et terminé
par une nouvelle ligne. À options et nom de fichier identiques, deux exports sont byte-identiques.
Les manifests de schéma 1 restent chargeables ; un ancien export `causal-features-v2` sous ce
contrat est lisible mais explicitement non vérifiable comme manifeste reproductible de Phase 2.

Depuis `backend/`, la vérification locale sans écriture ni réseau est :

```powershell
.\venv\Scripts\python.exe -m app.ml.cli.verify_ml_v2_source `
  artifacts/ml-v2/source.manifest.json `
  --database-path data/scanner_crypto.sqlite3 `
  --json
```

Le résultat est `reproducible`, `absent`, `incompatible`, `stale` ou `incomplete`. Les divergences
indiquent hashes agrégés attendu/calculé, rôle, timeframe, hashes de flux, comptes, bornes et type
(`contenu`, `plage_ou_nombre`, `gap`, `metadonnees`, `flux_absent`). Code 0 : reproductible ; 2 :
entrée invalide ou divergence ; 1 : erreur inattendue ; 130 : interruption. Le manifeste ne
contient pas les bougies brutes : il reconstruit la demande et vérifie une base candidate, mais ne
constitue pas une archive autonome.

## Limites reportées à la Phase 3

Aucun dataset v2 réel n'est généré ou publié, aucun modèle n'est entraîné, aucun benchmark ou
nouvelle période terminale n'est défini. La vérification exige une base SQLite candidate contenant
les bougies et, pour l'état `reproducible`, le job source confirmé référencé par le manifeste.
