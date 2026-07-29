# Référence REST et modèles publics

## Expérimentation phase 4

- `POST /api/experiments/jobs`, `GET/DELETE /api/experiments/jobs/{id}`
- `GET /api/experiments/jobs/{id}/candidates`
- `GET /api/experiments/jobs/{id}/candidate/{candidate_id}`
- `GET /api/experiments/jobs/{id}/walk-forward|sensitivity|exports`
- `GET /api/experiments/jobs/{id}/export`
- `GET /api/signal-profiles[/{id}]`
- `POST /api/signal-profiles/{id}/promote`
- `POST /api/signal-profiles/{id}/retire`
- `POST/GET /api/shadow/comparisons`

Les jobs sont exécutés hors event loop, bornés à 128 candidats et persistés. Le
shadow ne calcule pas lui-même deux profils : son endpoint persiste des
comparaisons confirmed déjà produites.

Base locale : `http://127.0.0.1:8000`. FastAPI expose aussi `/docs`, `/redoc` et `/openapi.json`. Les erreurs de validation Pydantic utilisent le format FastAPI 422.

## Santé et configuration

### `GET /api/health`

Sonde minimale, sans paramètre. Réponse 200 :

```json
{"status": "ok"}
```

### `GET /health`

Sonde du flux marché. Réponse 200 avec les valeurs chargées au démarrage :

```json
{"status": "ok", "symbol": "BTC/USDC", "timeframe": "1h", "display_limit": 500}
```

### `GET /api/scanner/config`

Retourne 200 et la sérialisation complète d'un `ScanConfig` par défaut. Voir [configuration.md](configuration.md).

### `GET /api/scanner/markets`

Paramètres de requête : `quote` (`USDC` par défaut) et `market_type` (`spot`, `swap` ou `future`, `spot` par défaut). Le backend crée un exchange Binance par défaut, charge ses marchés, renvoie les symboles triés et le ferme. Réponse 200 :

```json
["ADA/USDC", "BTC/USDC", "ETH/USDC"]
```

Une valeur de requête invalide répond 422. Une erreur CCXT pendant le chargement des marchés n'est pas traduite par cette route et produit une erreur serveur.

```bash
curl "http://127.0.0.1:8000/api/scanner/markets?quote=USDC&market_type=spot"
```

## Historique de marché

### `GET /api/market/candles`

Lit SQLite. Avec `sync_if_missing=true`, une page historique absente est
récupérée par `ccxt.async_support.fetch_ohlcv`, persistée, puis relue. Sans ce
paramètre, aucun accès réseau automatique n'est effectué. `before` et `after` sont des curseurs
Unix en millisecondes, exclusifs et mutuellement exclusifs. Sans curseur, les
dernières bougies sont renvoyées en ordre chronologique. `limit` est borné par
`CANDLE_MAX_API_LIMIT`.

La réponse contient les bougies (`time` en secondes, `open_time` en
millisecondes et `is_closed`), les indicateurs et marqueurs demandés, ainsi que
`page` (`next_before`, `next_after`, `has_more_before`, `has_more_after`) et
`coverage`. Cette couverture distingue `local_earliest_time`,
`exchange_earliest_time` et `exchange_earliest_verified`. `has_more_before`
reste vrai tant que le début exchange n'est pas vérifié ou que sa première
bougie n'est pas encore présente localement. `history_last_error` expose le
dernier échec sans le considérer comme une preuve de début. Les anciens filtres `from_time`/`to_time`
restent disponibles mais ne se combinent pas aux curseurs.

### `GET /api/market/candles/window`

Charge directement une fenêtre autour de `anchor_time` avec `before_count` et
`after_count`, sans parcourir les pages intermédiaires. Les timestamps sont en
millisecondes et la somme des deux comptes respecte `CANDLE_MAX_API_LIMIT`.

### `GET /api/market/candles/status`

Expose notamment `local_earliest_time`, `exchange_earliest_time`,
`exchange_earliest_verified`, `has_more_before` et `last_error` pour une cible
`exchange_id + market_type + symbol + timeframe`.

## Jobs de scan

### `POST /api/scanner/jobs`

Valide un corps `ScanConfig`, crée un job et planifie sa tâche. Réponse 202 ; erreur 422 si la configuration est invalide.

```bash
curl -X POST http://127.0.0.1:8000/api/scanner/jobs \
  -H "Content-Type: application/json" \
  -d '{"max_pairs":25,"timeframe":"4h"}'
```

Réponse initiale typique, sans tableau `results` :

```json
{
  "id": "a1b2c3d4e5f6478899aabbccddeeff00",
  "status": "pending",
  "config": {"exchange_id": "binance", "market_type": "spot", "quote": "USDC"},
  "progress": {"processed": 0, "total": 0, "successful": 0, "filtered": 0, "errors": 0, "percent": 0.0},
  "error": null,
  "created_at": "2026-07-22T10:00:00Z",
  "started_at": null,
  "completed_at": null,
  "result_count": 0
}
```

Le véritable objet `config` contient tous les champs de `ScanConfig`, même si l'exemple l'abrège pour la lisibilité.

### `GET /api/scanner/jobs/{job_id}`

Retourne 200 avec l'état courant sans `results`, ou 404 `{"detail":"Scan introuvable"}`. Le payload conserve `result_count`, y compris pendant le scan.

### `GET /api/scanner/jobs/{job_id}/results`

Disponible uniquement pour `completed` et `cancelled`. Réponse 200 : payload du job avec `results`. Job absent : 404. État `pending`, `running` ou `failed` : 409 `{"detail":"Le scan n'est pas terminé"}`.

```bash
curl http://127.0.0.1:8000/api/scanner/jobs/JOB_ID/results
```

### `DELETE /api/scanner/jobs/{job_id}`

Annule et attend une tâche encore active, puis retourne 200 avec le job. Les résultats déjà produits sont conservés. Un job final reste inchangé. Job absent : 404.

### `GET /api/scanner/jobs/{job_id}/export.csv`

Mêmes préconditions que `/results`. Réponse 200 `text/csv; charset=utf-8`, en-tête `Content-Disposition: attachment; filename="scan-{id}.csv"`. Les dictionnaires sont des objets JSON dans leurs cellules. Job absent : 404 ; scan non terminé ou en échec : 409.

## Routes du frontend

`GET /` sert `frontend/dist/index.html`; sans build il répond 503 avec une aide JSON. `GET /{frontend_path:path}` sert un asset situé sous `dist` ou l'index SPA ; sans build il répond 404. Cette route attrape-tout apparaît dans OpenAPI et doit rester déclarée après les routes API.

## `ScanStatus`

| Valeur | Sens |
|---|---|
| `pending` | Job enregistré, tâche pas encore entrée dans `_run_job`. |
| `running` | Scanner démarré et `started_at` défini. |
| `completed` | Tous les symboles ont été traités. |
| `failed` | Erreur globale interceptée par le manager ; `error` contient son texte. |
| `cancelled` | Tâche annulée ; les résultats partiels disponibles sont conservés. |

Transitions ordinaires : `pending → running → completed`; alternatives finales `failed` et `cancelled`.

## `ScanProgress`

`processed`, `total`, `successful`, `filtered` et `errors` sont des entiers. `percent` est ajouté au payload public et vaut `round(processed / total × 100, 2)`, ou 0 si `total=0`. Après chaque symbole traité par la boucle normale, l'invariant `processed = successful + filtered + errors` est maintenu. Une annulation peut arrêter les compteurs avant `total`.

## `ScanJob`

- `id` : UUID hexadécimal sans tirets ;
- `status` et `config` : état et configuration validée ;
- `progress` : compteurs et `percent` ajouté à la sérialisation publique ;
- `result_count` : longueur de la collection interne ;
- `error` : message de l'échec global ou `null` ;
- `created_at`, `started_at`, `completed_at` : datetimes UTC ISO 8601, les deux dernières étant nullables ;
- `results` : présent seulement sur `/results`, jamais sur le snapshot ordinaire.

## `ScanResult`

| Groupe | Champs |
|---|---|
| Identité | `symbol`, `timeframe` |
| Dernière bougie clôturée | `last_close_price`, `last_close_time` UTC |
| RSI | `rsi` |
| Tendance | `trend_score`, `trends` (`timeframe → bool/null`), `moving_averages` (`nom_période_timeframe → valeur`) |
| MACD | `macd`, `macd_signal`, `macd_histogram`, `macd_signal_type` |
| Bollinger | `bb_upper`, `bb_middle`, `bb_lower`, `bb_position` |
| Stochastique | `stoch_k`, `stoch_d`, `stoch_signal` |
| Confluence | `confluence_score`, `confluence_grade`, `confluence_breakdown`, `confluence_effective_weights` |

Les champs numériques sont `null` quand leur indicateur est désactivé ou non calculable. Les dictionnaires restent vides lorsque le calcul correspondant n'est pas actif. Une paire avec une donnée obligatoire insuffisante est normalement comptée en erreur plutôt que retournée.

Exemple de résultat :

```json
{
  "symbol": "BTC/USDC",
  "timeframe": "4h",
  "rsi": 28.4,
  "last_close_price": 64320.4,
  "last_close_time": "2026-07-22T08:00:00Z",
  "trend_score": 2,
  "trends": {"4h": true, "1d": true, "1w": false},
  "moving_averages": {"sma_20_4h": 64320.4, "sma_50_4h": 62980.8},
  "macd": 120.5,
  "macd_signal": 100.2,
  "macd_histogram": 20.3,
  "macd_signal_type": "bullish",
  "bb_upper": 66000.0,
  "bb_middle": 64000.0,
  "bb_lower": 62000.0,
  "bb_position": "neutral",
  "stoch_k": 18.2,
  "stoch_d": 16.8,
  "stoch_signal": "oversold",
  "confluence_score": 77.17,
  "confluence_grade": "B",
  "confluence_breakdown": {"rsi": 20.0, "trend": 16.67, "macd": 20.0, "bollinger": 7.0, "stochastic": 13.5},
  "confluence_effective_weights": {"rsi": 20.0, "trend": 25.0, "macd": 20.0, "bollinger": 20.0, "stochastic": 15.0}
}
```

Les valeurs illustrent un calcul cohérent avec les facteurs et poids par défaut. Pour les messages temps réel, consulter [websockets.md](websockets.md).

## Bougies locales

`GET /api/market/candles` lit SQLite en ordre chronologique. Les paramètres sont
`exchange_id`, `market_type`, `symbol`, `timeframe`, `limit`, `from_time`,
`to_time`, `closed_only` et `sync_if_missing`. Les bornes temporelles sont en
millisecondes et forment une plage `[from_time, to_time)`. Les bougies de la
réponse conservent le contrat graphique avec `time` en secondes.

`GET /api/market/candles/status` retourne `first_open_time`,
`last_open_time`, `last_closed_open_time`, `count`, `has_gaps` et
`missing_ranges`.

`GET /api/market/candles/export.csv` diffuse un CSV borné par
`CANDLE_MAX_API_LIMIT`. Il ne remplace pas l'export des résultats de scan.

Voir [le stockage OHLCV](ohlcv-storage.md) pour le schéma et la synchronisation.

## Couverture historique

Les endpoints en lecture seule `/api/market/history/coverage`,
`/coverage/{symbol}`, `/runs` et `/runs/{run_id}` exposent respectivement la
couverture locale et les exécutions persistantes. Les réponses ne contiennent
jamais le chemin absolu de SQLite. Les limites sont bornées à 2 000 entrées de
couverture et 200 runs.
