# Backfill historique OHLCV

## Portée

Le backfill remplit la base SQLite avec les bougies brutes disponibles pour les
marchés que Binance expose encore via CCXT. « Historique complet » signifie ici
la période comprise entre la première bougie réellement retournée pour chaque
couple `symbol/timeframe` et la borne actuelle ou `--to-date`.

Par défaut, l'univers contient tous les marchés actifs :

```text
type = spot
quote = USDC
symbole CCXT BASE/USDC
```

Les filtres du scanner (`max_pairs`, exclusion des bases stables, signaux,
volume) ne sont jamais appliqués. `--include-inactive` ajoute les marchés
inactifs encore présents dans le catalogue courant. Un marché totalement retiré
de Binance et absent du catalogue CCXT ne peut pas être découvert
automatiquement.

## Sécurité : simulation par défaut

Sans `--execute`, la commande charge uniquement le catalogue, calcule
l'intersection des timeframes, lit la couverture SQLite et affiche une
estimation du travail. Elle n'appelle jamais `fetch_ohlcv` et ne modifie aucune
bougie.

```powershell
cd backend
python -m app.cli.backfill_candles --quote USDC --symbols all --timeframes all
```

Exécution réelle :

```powershell
python -m app.cli.backfill_candles `
  --exchange binance --market-type spot --quote USDC `
  --symbols all --timeframes all --from earliest --resume --execute
```

Sélection réduite :

```powershell
python -m app.cli.backfill_candles `
  --quote USDC --symbols all --timeframes 15m 1h 4h 1d `
  --from earliest --resume --execute
```

Une paire précise :

```powershell
python -m app.cli.backfill_candles `
  --symbol BTC/USDC --timeframes 1m 5m 1h `
  --from earliest --resume --execute
```

Réparation :

```powershell
python -m app.cli.backfill_candles `
  --quote USDC --symbols all --timeframes all `
  --resume --repair-gaps --execute
```

Synchronisation incrémentale :

```powershell
python -m app.cli.sync_candles `
  --quote USDC --timeframes all --execute
```

## Timeframes et ordre

La source canonique est `Timeframe` dans `app.core.settings`, exposée sous
`PROJECT_TIMEFRAMES`. `all` prend l'intersection avec `exchange.timeframes` et
`fetchOHLCV`. `1M` est volontairement exclu. Les cibles sont ordonnées par
symbole alphabétique, puis du timeframe le plus long au plus court afin
d'obtenir rapidement une couverture utile et peu volumineuse.

## Première bougie et pagination

La première recherche demande `since=0`. Si l'exchange retourne une borne
récente, le service sonde au maximum seize fenêtres antérieures. La première
bougie réellement retournée devient `earliest_available_time`; aucune bougie
artificielle n'est créée.

Chaque page est validée, dédupliquée, triée, bornée, UPSERT dans une transaction
courte, puis son checkpoint est écrit. Un timestamp qui ne progresse pas ou une
page répétée produit une erreur de cible. Une page vide termine la cible. Les
retries réseau/rate-limit réutilisent le backoff annulable de
`CandleSyncService`.

Les pages sont traitées par une file bornée et un nombre faible de workers
(`2` par défaut). Une seule instance CCXT avec rate limiter est partagée. Il
n'existe ni tâche par bougie ni commit par bougie.

## Reprise, restart et arrêt

`--resume` compare `next_since` avec la dernière bougie réellement présente,
puis reprend avec le chevauchement configuré. SQLite UPSERT rend cette
réinsertion idempotente.

`--restart` supprime uniquement le checkpoint de chaque cible sélectionnée et
reparcourt sa plage. Les bougies ne sont pas supprimées : elles sont corrigées
par UPSERT. Aucune option ne supprime la base entière.

`Ctrl+C`, `SIGINT`, `SIGTERM` et `CancelledError` annulent les workers. La page
déjà validée reste commitée, la cible passe à `interrupted`, l'exchange est
fermé et la commande de reprise est affichée.

## Catalogue, trous et état

La migration 2 ajoute :

- `markets` : catalogue courant et historique d'activité ;
- `candle_sync_state` : checkpoint par cible ;
- `backfill_runs` : exécutions globales ;
- `candle_gaps` : trous internes encore ouverts.

Après le téléchargement, les écarts internes sont détectés dans la plage
demandée. `--repair-gaps` demande uniquement les plages manquantes, puis vérifie
à nouveau la continuité. Un trou non servi par Binance reste ouvert. Aucun
remplissage synthétique n'est effectué.

API en lecture seule :

```text
GET /api/market/history/coverage
GET /api/market/history/coverage/BTC%2FUSDC
GET /api/market/history/runs
GET /api/market/history/runs/{run_id}
```

## Préparation du backtesting

`CandleRepository.get_candles_for_backtest()` lit exclusivement SQLite avec une
plage `[start_time, end_time)`, un tri chronologique et `closed_only=true` par
défaut. `validate_backtest_coverage()` retourne bornes disponibles, compte
attendu, trous et complétude. Une lecture incomplète lève
`BacktestCoverageError`. Aucun indicateur, signal ou moteur de stratégie n'est
implémenté.

## Rapports, disque et sauvegarde

`--report-path reports/backfill-usdc.json` écrit un rapport JSON sans chemin
personnel ni secret. Il contient compteurs, bornes globales, durée, trous,
erreurs et commande de reprise.

Le volume peut être très important : plusieurs années de données `1m` sur de
nombreuses paires peuvent représenter des dizaines ou centaines de millions de
lignes et plusieurs dizaines de gigaoctets. La commande affiche la taille
actuelle et l'espace disponible, mais ne prétend pas fournir une estimation
finale précise.

Sauvegarde cohérente, y compris avec WAL actif :

```powershell
python -m app.cli.backup_database `
  --output backups/scanner_crypto-2026-07-23.sqlite3
```

Cette commande utilise l'API SQLite backup ; ne pas copier seulement le fichier
principal pendant une écriture.
