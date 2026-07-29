# Configuration

## Variables d'environnement

Toutes sont optionnelles et lues au chargement du processus. Les valeurs par défaut apparaissent ci-dessous.

| Variable | Type / défaut | Effet et précautions |
|---|---|---|
| `CORS_ORIGINS` | liste CSV / `http://localhost:5173,http://127.0.0.1:5173` | Origines autorisées ; les entrées vides sont ignorées. |
| `LOG_LEVEL` | chaîne / `INFO` | Niveau `logging` ; une valeur inconnue retombe sur `INFO`. |
| `LOG_DIR` | chemin / `logs` | Dossier créé au démarrage, contenant `scanner.log`. |
| `JOB_TTL_SECONDS` | entier / `3600` | TTL des jobs terminés, borné à 60 secondes minimum. |
| `MAX_RETAINED_JOBS` | entier / `100` | Capacité mémoire, bornée à 1 ; purge lors d'une nouvelle création. |
| `DATABASE_PATH` | chemin / `data/scanner_crypto.sqlite3` | Base SQLite, résolue depuis `backend/`. |
| `CANDLE_STORAGE_ENABLED` | booléen / `true` | Active la persistance OHLCV locale. |
| `CANDLE_SYNC_ENABLED` | booléen / `true` | Autorise la synchronisation CCXT si l'historique manque. |
| `CANDLE_DEFAULT_LIMIT` | entier / `500` | Nombre REST de bougies par défaut. |
| `CANDLE_MAX_API_LIMIT` | entier / `5000` | Borne des lectures REST et CSV. |
| `CANDLE_INDICATOR_WARMUP_BARS` | entier / `500` | Bougies antérieures chargées uniquement pour calculer les indicateurs d'une page REST. |
| `CANDLE_GAP_REPAIR_ENABLED` | booléen / `true` | Autorise la réparation des trous internes. |
| `CANDLE_SYNC_PAGE_LIMIT` | entier / `1000` | Taille demandée par page CCXT. |
| `CANDLE_SYNC_MAX_PAGES` | entier / `100` | Garde-fou contre une pagination infinie. |
| `CANDLE_OPEN_WRITE_INTERVAL_SECONDS` | flottant / `5` | Limitation des écritures de la bougie ouverte. |
| `BACKFILL_DEFAULT_EXCHANGE` | texte / `binance` | Exchange CLI par défaut. |
| `BACKFILL_DEFAULT_MARKET_TYPE` | texte / `spot` | Type de marché CLI par défaut. |
| `BACKFILL_DEFAULT_QUOTE` | texte / `USDC` | Quote découverte par défaut. |
| `BACKFILL_DEFAULT_TIMEFRAMES` | liste CSV / timeframes projet | Sélection par défaut validée au démarrage. |
| `BACKFILL_PAGE_LIMIT` | entier / `1000` | Taille de page historique. |
| `BACKFILL_MAX_CONCURRENCY` | entier / `2` | Workers bornés partageant l'exchange. |
| `BACKFILL_MAX_RETRIES` | entier / `5` | Retries réseau/rate-limit. |
| `BACKFILL_RETRY_DELAY_SECONDS` | flottant / `2` | Backoff initial. |
| `BACKFILL_PROGRESS_INTERVAL_SECONDS` | flottant / `5` | Intervalle cible de progression synthétique. |
| `BACKFILL_OVERLAP_CANDLES` | entier / `2` | Chevauchement lors d'une reprise. |
| `BACKFILL_REPAIR_GAPS` | booléen / `true` | Politique disponible pour la réparation. |
| `BINANCE_SYMBOL` | chaîne / `BTC/USDC` | Symbole par défaut de `/ws` et affiché par `/health`. |
| `BINANCE_TIMEFRAME` | chaîne / `1h` | Timeframe par défaut du flux ; validé à la connexion. |
| `CALCULATION_LIMIT` | entier / `500` | Taille de l'historique de calcul ; relevée au maximum de cette valeur, `DISPLAY_LIMIT` et 100. |
| `DISPLAY_LIMIT` | entier / `500` | Nombre maximal de bougies et points historiques visibles. |
| `DIVERGENCE_LEFT` | entier / `3` | Nombre de voisins à gauche d'un pivot strict. |
| `DIVERGENCE_RIGHT` | entier / `3` | Nombre de voisins à droite et délai de confirmation. |
| `DIVERGENCE_MIN_BARS` | entier / `5` | Distance minimale entre deux pivots. |
| `DIVERGENCE_MAX_BARS` | entier / `60` | Distance maximale entre deux pivots. |
| `DIVERGENCE_PRICE_MIN_CHANGE` | flottant / `0.001` | Variation relative minimale du prix, soit 0,1 % par défaut. |
| `INCLUDE_HIDDEN_DIVERGENCES` | booléen texte / `true` | Vrai uniquement si la valeur, en minuscules, est exactement `true`. |

Exemple sûr :

```dotenv
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
LOG_LEVEL=INFO
LOG_DIR=logs
JOB_TTL_SECONDS=3600
MAX_RETAINED_JOBS=100
BINANCE_SYMBOL=BTC/USDC
BINANCE_TIMEFRAME=1h
CALCULATION_LIMIT=500
DISPLAY_LIMIT=500
DIVERGENCE_LEFT=3
DIVERGENCE_RIGHT=3
DIVERGENCE_MIN_BARS=5
DIVERGENCE_MAX_BARS=60
DIVERGENCE_PRICE_MIN_CHANGE=0.001
INCLUDE_HIDDEN_DIVERGENCES=true
```

Les entiers et flottants invalides empêchent l'import ou la création de la configuration. Aucune variable ne contient de secret.

## `ScanConfig`

### Exchange et marché

| Champ | Type / défaut | Validation et comportement |
|---|---|---|
| `exchange_id` | `str` / `binance` | Espaces retirés, minuscules, non vide ; doit nommer une classe CCXT au démarrage. |
| `market_type` | `spot`, `swap`, `future` / `spot` | Correspondance exacte avec `market.type`. |
| `quote` | `str` / `USDC` | Espaces retirés, majuscules, alphanumérique non vide. |
| `exclude_stable_pairs` | `bool` / `true` | Exclut les bases stables répertoriées. |
| `max_pairs` | `int` ou `null` / `null` | 1 à 2000 ; limite appliquée après tri alphabétique. |

### OHLCV, concurrence et retries

| Champ | Type / défaut | Bornes / unité |
|---|---|---|
| `timeframe` | enum / `4h` | `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`. |
| `min_ohlcv_bars` | `int` / `200` | 60 à 1500 bougies ; la limite effective est le maximum des besoins actifs, avec marge 10. |
| `max_concurrency` | `int` / `6` | 1 à 20 analyses simultanées. |
| `max_retries` | `int` / `3` | 0 à 8 retries, donc jusqu'à `max_retries + 1` tentatives. |
| `retry_delay_seconds` | `float` / `1.5` | 0,1 à 30 secondes, délai initial du backoff. |

### RSI

`use_rsi` vaut `true`. `rsi_period` vaut 14 et reste entre 2 et 100. `rsi_threshold` vaut 35 et reste entre 0 et 100. Si le RSI est actif, une valeur absente produit une erreur de symbole et `rsi >= rsi_threshold` filtre la paire. Désactivé, le champ `rsi` du résultat vaut `null` et le filtre RSI ne s'applique pas.

### Moyennes mobiles

`use_ma`, `use_sma` et `use_ema` valent `true`. Au moins une famille doit rester active lorsque `use_ma` est vrai. `sma_periods` et `ema_periods` valent `[20, 50]` ; chaque liste doit être non vide, sans doublon, comprise entre 2 et 1000, puis est triée. `ma_timeframes` vaut `["1w", "1d", "4h"]` et interdit les doublons.

`min_trend_score` vaut 2, reste entre 0 et 20 et ne peut dépasser le nombre de `ma_timeframes`. Une tendance manquante ne marque aucun point. Avec `use_ma=false`, les timeframes MA ne sont pas interrogés, `trend_score` vaut `null` dans le résultat, et les dictionnaires MA sont vides.

### MACD, Bollinger et Stochastique

| Groupe | Activation et paramètres |
|---|---|
| MACD | `use_macd=true`; périodes fast 12 (2–100), slow 26 (3–200), signal 9 (2–100). Fast doit être strictement inférieur à slow. |
| Bollinger | `use_bollinger=true`; période 20 (2–200), `bollinger_std_dev=2.0` strictement positif et ≤ 10. |
| Stochastique | `use_stochastic=true`; K 14 (2–200), D 3 (2–50), oversold 20 et overbought 80, tous deux entre 0 et 100 ; oversold doit être inférieur à overbought. |

Désactiver un groupe évite son calcul et laisse ses champs `ScanResult` à `null`. Les filtres associés sont alors ignorés.

### Confluence et filtres

`use_confluence_score=true`, `min_confluence_score=60` entre 0 et 100. Les poids par défaut sont RSI 20, tendance 25, MACD 20, Bollinger 20 et Stochastique 15. Les clés inconnues, poids négatifs, infinis et `NaN` sont refusés. La confluence active exige au moins un indicateur actif de poids positif.

`filter_macd_signal`, `filter_bb_position` et `filter_stoch_signal` valent `null`. Une liste non vide n'accepte que les valeurs de son enum et est dédupliquée en conservant l'ordre. Une liste vide se comporte comme l'absence de filtre.

Valeurs possibles :

- MACD : `bullish`, `bearish`, `neutral` ;
- Bollinger : `oversold`, `near_oversold`, `neutral`, `near_overbought`, `overbought` ;
- Stochastique : `oversold`, `overbought`, `bullish_cross`, `bearish_cross`, `neutral`.

## Exemples JSON

Minimal — tous les autres champs prennent leur valeur par défaut :

```json
{
  "max_pairs": 25
}
```

Complet :

```json
{
  "exchange_id": "binance",
  "market_type": "spot",
  "quote": "USDC",
  "exclude_stable_pairs": true,
  "max_pairs": 100,
  "timeframe": "4h",
  "min_ohlcv_bars": 200,
  "max_concurrency": 6,
  "max_retries": 3,
  "retry_delay_seconds": 1.5,
  "use_rsi": true,
  "rsi_period": 14,
  "rsi_threshold": 35,
  "use_ma": true,
  "use_sma": true,
  "use_ema": true,
  "sma_periods": [20, 50],
  "ema_periods": [20, 50],
  "ma_timeframes": ["4h", "1d", "1w"],
  "min_trend_score": 2,
  "use_macd": true,
  "macd_fast_period": 12,
  "macd_slow_period": 26,
  "macd_signal_period": 9,
  "use_bollinger": true,
  "bollinger_period": 20,
  "bollinger_std_dev": 2.0,
  "use_stochastic": true,
  "stochastic_k_period": 14,
  "stochastic_d_period": 3,
  "stochastic_oversold": 20,
  "stochastic_overbought": 80,
  "use_confluence_score": true,
  "min_confluence_score": 60,
  "confluence_weights": {"rsi": 20, "trend": 25, "macd": 20, "bollinger": 20, "stochastic": 15},
  "filter_macd_signal": ["bullish"],
  "filter_bb_position": null,
  "filter_stoch_signal": ["oversold", "bullish_cross"]
}
```

La réponse exacte des valeurs par défaut est disponible via `GET /api/scanner/config`. Voir [l'API](api-reference.md) et [la confluence](confluence.md).
