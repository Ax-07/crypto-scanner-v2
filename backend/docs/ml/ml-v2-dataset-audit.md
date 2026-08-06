# Premier dataset ML v2 réel — audit de développement

## Statut et périmètre

Conclusion calculée : `accepted_with_reservations`.

Ce dataset est accepté uniquement comme base pour définir le protocole expérimental de la
Phase 4. Aucun modèle n'a été entraîné, aucun benchmark ML v2 n'a été exécuté et aucune période
terminale de test n'a été choisie ou consommée.

## Choix de la fenêtre

- exchange/marché : `binance spot` ;
- symbole/timeframe : `BTC/USDC 4h` ;
- début inclusif : `2020-04-01T00:00:00Z` ;
- fin exclusive : `2022-09-28T00:00:00Z`.

`BTC/USDC 1h` n'a que 4 780 bougies dans la base et ne peut pas atteindre 5 000 lignes après
warmup. Le flux `4h` contient 15 742 bougies depuis décembre 2018, mais un trou commun aux
timeframes commence le 29 septembre 2022 et se termine en mars 2023. La fenêtre retenue est le
plus grand segment contrôlable avant ce trou après exclusion d'un gap situé dans le warmup de
février 2020. Elle couvre le choc de 2020, la hausse 2020-2021, des phases latérales et le repli
2022. Ses 5 460 décisions dépassent le minimum de 5 000, mais pas les 10 000 recommandées : cette
limite est une réserve explicite.

## Source canonique

- job : `ebf1e0328c4346d69b02a0d1de802303` ; statut : `completed` ;
- profil/horizon : `ml-dataset-v2`, h6 ; entry policy : `signal_close` ;
- frais/slippage : zéro ; portefeuille : absent ;
- source identity : `sha256:b864504e19dfe40070942469d3849241d585cf4a1a54ad48c633efdb9c3952df` ;
- profile fingerprint : `sha256:858e94686f66c838356598b6b3beeb9f330e8f17177863c44ff6180c2777564c` ;
- input fingerprint : `sha256:7e162fa7341ece55c141affd6dcb142f499e5e2bcb528f7ad1fbbdced4bd5f85`.

| rôle | timeframe | bougies | warmup | futur | fingerprint |
|---|---:|---:|---:|---:|---|
| primary | 4h | 5 667 | 200 | 7 | `sha256:538f049650b79176c491b17234be422cb193cc3bc20ddd651a30a282a8d6139d` |
| trend:1d | 1d | 972 | 60 | 0 | `sha256:bd2a15066c07c4bce330ca42824349b573f046218e6183b813ce76dff453c6da` |
| trend:1w | 1w | 190 | 60 | 0 | `sha256:3c11c08ac1c1f1296253737b3cb9b055235d909ddff997d64761b5f8a44b3cba` |

Une limite externe a interrompu la première commande après 3 325 décisions. La CLI appelle
désormais la récupération officielle du manager et a repris le même job depuis son checkpoint
jusqu'à `completed`, sans doublon ni modification manuelle de statut.

## Artefacts et hashes

Répertoire : `artifacts/ml-v2/btc-usdc-4h-20200401-20220928-causal-v2-7e162fa7/`.

| fichier | octets | SHA-256 | Git |
|---|---:|---|---|
| `dataset.jsonl` | 220 393 468 | `d1d673c4fe96486891aa689de58dde3ac2f181b2459387def4214d109cadf205` | local, ignoré |
| `dataset.manifest.json` | 38 335 | `1ccfe4dfb0a9b1dda8fab0971dc6cdba6f37ce73b2ebef9fc3bf257c3358ecc2` | suivable |
| `dataset-audit.json` | 1 157 042 | `9267d1471621808344c1d737ab405247f1af94bc6eefbe5ca0d9f03c19b4e79b` | suivable |
| `dataset-audit.md` | 20 915 | `7e6dd26b2ee3381e94098a6c92e55f51ce4a29197b5ae20334454395b9182168` | suivable |
| `history-inventory.json` | 6 476 | `ab340d76234b81866f21afcdf9c629bbd92c554f528a551d4d0ebc3740b60f4d` | suivable |

Deux exports indépendants ont produit des JSONL et manifests identiques octet par octet. Deux
audits successifs ont produit les mêmes hashes. La base et les sauvegardes restent ignorées.

## Commandes exactes

Depuis `backend/` :

```powershell
.\venv\Scripts\python.exe -m app.ml.cli.inspect_ml_v2_history BTC/USDC `
  --database-path data/scanner_crypto.sqlite3 --output-json `
  artifacts/ml-v2/btc-usdc-4h-20200401-20220928-causal-v2-7e162fa7/history-inventory.json

.\venv\Scripts\python.exe -m app.ml.cli.prepare_ml_v2_source BTC/USDC `
  --timeframe 4h --start 2020-04-01T00:00:00Z --end 2022-09-28T00:00:00Z `
  --database-path data/scanner_crypto.sqlite3 --json

.\venv\Scripts\python.exe -m app.ml.cli.export_ml_dataset `
  ebf1e0328c4346d69b02a0d1de802303 --feature-schema-version causal-features-v2 `
  --database-path data/scanner_crypto.sqlite3 --output-directory `
  artifacts/ml-v2/btc-usdc-4h-20200401-20220928-causal-v2-7e162fa7 --file-stem dataset

.\venv\Scripts\python.exe -m app.ml.cli.verify_ml_v2_source `
  artifacts/ml-v2/btc-usdc-4h-20200401-20220928-causal-v2-7e162fa7/dataset.manifest.json `
  --database-path data/scanner_crypto.sqlite3 --json

.\venv\Scripts\python.exe -m app.ml.cli.audit_ml_v2_dataset `
  artifacts/ml-v2/btc-usdc-4h-20200401-20220928-causal-v2-7e162fa7/dataset.manifest.json `
  --database-path data/scanner_crypto.sqlite3 --output-json `
  artifacts/ml-v2/btc-usdc-4h-20200401-20220928-causal-v2-7e162fa7/dataset-audit.json `
  --output-markdown `
  artifacts/ml-v2/btc-usdc-4h-20200401-20220928-causal-v2-7e162fa7/dataset-audit.md --json
```

Codes d'audit : 0 accepté, 2 rejeté, 3 accepté avec réserves, 1 erreur inattendue,
130 interruption.

## Funnel, labels et structure

Le funnel est réconcilié : 5 460 observations confirmées, 5 460 outcomes h6 et 5 460 lignes
finales ; zéro censurée, invalide, NATR absent ou rejet contractuel.

| label | lignes | pourcentage |
|---|---:|---:|
| DOWN | 1 145 | 20,9707 % |
| NEUTRAL | 3 005 | 55,0366 % |
| UP | 1 310 | 23,9927 % |

Les trois classes existent chaque année. Les plus longues séquences sont 16 DOWN, 22 NEUTRAL
et 20 UP. Le dataset contient 675 features déclarées, aucun doublon d'observation ou timestamp,
aucun nombre non fini et aucun champ futur interdit.

## Features, extrêmes, régimes et stabilité

- 195 features constantes, principalement unités, disponibilités et invariants de qualité ;
- 54 quasi constantes, principalement événements/divergences rares ;
- 1 490 paires avec `abs(Pearson)` ou `abs(Spearman) >= 0.98`, dont les duplications explicites
  du prix et des couples valeur/valeur normalisée ;
- au plus 100 exemples extrêmes conservés, selon les quantiles empiriques 0,1 % et 99,9 % ;
- trois terciles NATR faible/moyen/fort de 1 820 lignes chacun ;
- 49 alertes de différence de moyenne normalisée entre années, dominées par les niveaux de prix
  et bandes techniques entre 2020 et 2021.

Ces constats sont des alertes. Aucune feature ni ligne n'a été supprimée, clippée, winsorisée,
rééquilibrée, transformée ou sélectionnée.

## Audit causal et fuite

Seize observations couvrant bornes, quartiles temporels, années, classes et extrêmes NATR ont été
recalculées depuis les OHLCV bruts tronqués à chaque décision. Features, outcome h6, NATR et labels
correspondent sans divergence.

Les tests contrôlés confirment qu'une mutation après h6 ne change ni feature ni label, qu'une
mutation dans h6 peut changer le label sans changer les features et qu'une mutation à la décision
peut changer les features et le fingerprint.

Leak audit : `no_leak_detected_by_defined_checks`. Cette formulation est limitée aux contrôles
définis et ne démontre pas l'impossibilité absolue de toute fuite future concevable.

## Conclusion et Phase 4

`accepted_with_reservations` est calculé parce qu'aucun contrôle bloquant n'échoue, mais que la
taille est sous 10 000 et que constantes, redondances et dérives devront être traitées dans un
protocole appris exclusivement sur les partitions de développement.

La Phase 4 devra figer les partitions chronologiques, les règles de preprocessing appris et la
période terminale avant tout entraînement. Ce rapport ne recommande aucun modèle ou stratégie et
ne constitue pas une preuve d'aptitude au trading.
