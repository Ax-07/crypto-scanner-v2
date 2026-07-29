# Stockage local des bougies OHLCV

## Rôle et emplacement

SQLite est la source de vérité locale des bougies brutes. Les CSV restent des
exports. Une base unique contient tous les exchanges, types de marché, symboles
et timeframes. Aucun serveur de base de données n'est requis.

Le chemin par défaut est `backend/data/scanner_crypto.sqlite3`. Un
`DATABASE_PATH` relatif est toujours résolu depuis `backend/`, même si Uvicorn
est lancé depuis un autre dossier. Le dossier parent est créé au démarrage.

Les timestamps `open_time`, `close_time` et `updated_at` sont des timestamps
Unix UTC en millisecondes, convention native de CCXT. L'API du graphique
continue à convertir `open_time` en secondes.

## Schéma et migrations

La migration version 1 crée `candles`. La migration version 2 ajoute le
catalogue, les checkpoints, les runs et les trous du backfill. La migration 3
avait introduit une première borne historique locale. La migration 4 la
remplace par des métadonnées exchange explicites et réinitialise les anciennes
preuves ambiguës sans supprimer les bougies. Voir
[historical-backfill.md](historical-backfill.md).

```sql
CREATE TABLE candles (
    exchange_id TEXT NOT NULL,
    market_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open_time INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    close_time INTEGER,
    is_closed INTEGER NOT NULL DEFAULT 1 CHECK (is_closed IN (0, 1)),
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (exchange_id, market_type, symbol, timeframe, open_time)
);
```

L'index `idx_candles_market_time` porte sur
`(exchange_id, market_type, symbol, timeframe, open_time DESC)`. La table
`schema_migrations` conserve les versions appliquées. Les migrations sont
idempotentes et exécutées dans le lifespan FastAPI.

Chaque connexion courte active `foreign_keys`, `synchronous=NORMAL` et un
`busy_timeout` de 5 secondes. L'initialisation active aussi WAL. Aucune
transaction globale ne reste ouverte.

La table `candle_history_bounds`, ciblée par
`(exchange_id, market_type, symbol, timeframe)`, contient :

- `exchange_earliest_time`, nullable tant que Binance n'a pas répondu à une
  vérification REST fiable ;
- `exchange_earliest_verified`, distinct de la présence de bougies locales ;
- `has_more_before`, vrai tant que SQLite n'a pas rejoint la borne vérifiée ;
- `last_error`, qui conserve un incident sans valider la borne.

`local_earliest_time` n'est pas persisté dans cette table : il est toujours
recalculé depuis `MIN(candles.open_time)`, afin de ne jamais le confondre avec
le début réel de cotation.

## UPSERT et bougie ouverte

Les insertions sont groupées dans une transaction `BEGIN IMMEDIATE` et utilisent
`ON CONFLICT ... DO UPDATE`. La clé primaire empêche tout doublon. Une nouvelle
version de la même bougie remplace OHLCV, `close_time`, `is_closed` et
`updated_at`, ce qui couvre une bougie ouverte qui évolue et une correction
ultérieure de l'exchange.

Une bougie est clôturée si `open_time + durée_timeframe <= heure_courante`. Les
timeframes actuellement exposés ont tous une durée fixe de `1m` à `1w`; aucun
timeframe mensuel n'est proposé. Le scanner demande uniquement les bougies
clôturées.

Le flux WebSocket persiste une nouvelle bougie immédiatement. À l'apparition
d'un timestamp supérieur, il persiste l'état final de la précédente en
`is_closed=true`, puis la nouvelle bougie. Les variations d'une bougie ouverte
sont limitées par `CANDLE_OPEN_WRITE_INTERVAL_SECONDS`. Une erreur SQLite est
journalisée mais ne coupe pas à elle seule le flux envoyé au navigateur.

## Synchronisation et reprise

`CandleSyncService.ensure_history()` suit ce flux :

1. compter et contrôler la fraîcheur des bougies SQLite ;
2. retourner immédiatement l'historique local s'il suffit ;
3. reprendre depuis la dernière bougie connue, incluse ;
4. paginer explicitement CCXT avec `since` ;
5. valider, trier, dédupliquer et UPSERT chaque page ;
6. vérifier que le dernier timestamp progresse ;
7. relire l'historique depuis SQLite.

Le chevauchement de la dernière bougie met à jour la bougie ouverte, capture les
corrections et évite un trou autour d'une clôture. Une page vide termine
normalement la pagination. Les erreurs réseau et de rate limit utilisent un
backoff exponentiel annulable. Une pagination immobile ou la limite de pages
produit une erreur métier explicite. Un arrêt après une page validée ne perd pas
cette page : l'exécution suivante reprend depuis la dernière clé connue.

Les trous sont détectés uniquement entre deux timestamps déjà connus. Le code ne
considère donc pas le début de cotation comme un trou, ignore le futur et ne
fabrique aucune bougie vide. La réparation interroge CCXT sur les plages
détectées, avec un nombre de plages borné par exécution.

Pour une page plus ancienne, le service calcule la plage précédant
`local_earliest_time`, appelle `fetch_ohlcv` avec un `since` en millisecondes,
filtre strictement la réponse sur la plage demandée, puis effectue les UPSERT.
Le début exchange est vérifié séparément par une réponse REST réussie et non
vide partant de `since=0`. Une page vide, une erreur réseau, un rate limit ou
une pagination immobile ne passe jamais `exchange_earliest_verified` à vrai.

Les anciennes métadonnées peuvent être réinitialisées sans toucher aux bougies :

```powershell
python -m app.cli.repair_history_metadata

python -m app.cli.repair_history_metadata `
  --exchange-id binance --market-type spot `
  --symbol ETH/USDC --timeframe 1h
```

## Scanner et graphique

Le scanner conserve son cache mémoire `(symbol, timeframe)` pendant un job, mais
sa première lecture passe par `ensure_history()`. Les indicateurs continuent à
recevoir les mêmes DataFrames pandas et restent dans le domaine existant. Les
timeframes de tendance sont stockés séparément.

Le WebSocket `/ws` synchronise puis relit son historique récent depuis SQLite.
Le navigateur fusionne ce payload sans supprimer les pages anciennes déjà
chargées. CCXT Pro et `watch_ohlcv` restent responsables uniquement des updates
temps réel ; l'historique profond utilise `ccxt.async_support.fetch_ohlcv`.

## API

- `GET /api/market/candles` : lecture chronologique ; pagination temporelle
  `before`/`after`, filtres historiques `from_time`/`to_time`,
  `closed_only`, `include_indicators` et `sync_if_missing`.
- `GET /api/market/candles/status` : première et dernière bougie, dernière
  clôturée, compte et au plus 20 trous.
- `GET /api/market/candles/export.csv` : export borné lu depuis SQLite.

Les plages suivent la convention `[from_time, to_time)`. `limit` ne peut pas
dépasser `CANDLE_MAX_API_LIMIT`. Les symboles et timeframes sont validés. Aucun
chemin local n'est exposé.

`before` et `after` sont exclusifs et mutuellement exclusifs. La pagination vers
le passé utilise l'index composé, `ORDER BY open_time DESC LIMIT ?`, puis inverse
la page en mémoire ; aucun `OFFSET` ni parcours complet n'est utilisé. La réponse
contient `page` (`next_before`, `has_more_before`) et `coverage` (bornes, total,
complétude et trous).

Avec `include_indicators=true`, le backend réutilise les calculs du flux marché.
Il charge `CANDLE_INDICATOR_WARMUP_BARS` bougies antérieures, ne renvoie que les
points de la page et fusionne les marqueurs côté navigateur. L'EMA initialisée
sur cette fenêtre reste une approximation de l'EMA calculée depuis la première
bougie absolue ; aucun indicateur n'est écrit dans la table brute.

## Configuration

| Variable | Défaut | Effet |
|---|---:|---|
| `DATABASE_PATH` | `data/scanner_crypto.sqlite3` | Fichier SQLite, relatif à `backend/`. |
| `CANDLE_STORAGE_ENABLED` | `true` | Initialise et utilise le stockage. |
| `CANDLE_SYNC_ENABLED` | `true` | Autorise le complément réseau. |
| `CANDLE_DEFAULT_LIMIT` | `500` | Limite REST par défaut. |
| `CANDLE_MAX_API_LIMIT` | `5000` | Borne REST/CSV. |
| `CANDLE_INDICATOR_WARMUP_BARS` | `500` | Préchauffage des indicateurs paginés. |
| `CANDLE_GAP_REPAIR_ENABLED` | `true` | Autorise la réparation de trous. |
| `CANDLE_SYNC_PAGE_LIMIT` | `1000` | Taille maximale demandée par page. |
| `CANDLE_SYNC_MAX_PAGES` | `100` | Garde-fou de pagination. |
| `CANDLE_OPEN_WRITE_INTERVAL_SECONDS` | `5` | Fréquence maximale des UPSERT ouverts. |

## Sauvegarde et limites

Après un arrêt propre, sauvegarder consiste principalement à copier
`scanner_crypto.sqlite3`. Avec WAL actif, ne pas copier uniquement le fichier
principal pendant une écriture : arrêter proprement l'application ou utiliser
l'API de backup SQLite afin d'inclure un état cohérent du WAL.

Limites actuelles :

- pas d'agrégation de timeframes depuis `1m` ;
- pas d'import CSV automatique ;
- pas de timeframe mensuel dans le contrat public actuel ;
- réparation limitée aux trous internes observables ;
- l'historique OHLCV est persistant, mais les jobs et résultats de scan restent
  en mémoire et imposent toujours un seul worker.

Le backfill CLI possède son propre état persistant et peut durer au-delà d'une
session, mais il n'est jamais lancé par FastAPI.
