# Historique du graphique chargé à la demande

Le graphique marché utilise SQLite comme cache durable. L’ouverture charge uniquement
la tranche récente configurée, puis le WebSocket continue d’alimenter la bougie active.
Aucun backfill global n’est lancé automatiquement.

## Navigation

- Un déplacement vers la gauche appelle `GET /api/market/candles` avec le curseur
  `before`. Si la page est déjà complète dans SQLite, aucun appel exchange n’est fait.
  Sinon, seule la plage nécessaire est téléchargée, persistée puis relue.
- En mode historique, `after` charge la page suivante sans utiliser `OFFSET`.
- `GET /api/market/candles/window` reçoit `anchor_time`, `before_count` et
  `after_count`. Il charge directement la fenêtre entourant la date UTC demandée.
- Le bouton « Revenir au live » recharge la tranche récente et réactive le suivi du
  temps réel. Les messages WebSocket reçus pendant le mode historique sont conservés
  comme état live, sans modifier la fenêtre affichée.
- « Aller au début » est la seule action de l’interface qui enchaîne volontairement
  les pages jusqu’à la première bougie réellement disponible.

Les réponses exposent les curseurs `next_before`/`next_after`, les indicateurs de
pagination, la couverture locale et `source.downloaded_from_exchange`. La borne
historique réelle est mémorisée par cible `(exchange, marché, symbole, timeframe)` afin
de ne pas redemander des pages antérieures inexistantes.

## Bornes locales et exchange

Les métadonnées distinguent volontairement :

- `local_earliest_time`, calculé avec `MIN(open_time)` dans SQLite ;
- `exchange_earliest_time`, obtenu par une requête REST CCXT
  `fetch_ohlcv(..., since=0)` réussie et non vide ;
- `exchange_earliest_verified`, qui indique que cette vérification a abouti ;
- `has_more_before`, qui reste vrai tant que la borne exchange n’est pas vérifiée ou
  que SQLite ne contient pas encore cette première bougie ;
- `last_error`, informatif, qui ne transforme jamais une panne en preuve de début.

Une page vide, une erreur réseau, un rate limit ou une pagination bloquée ne valide
jamais la borne. Les requêtes historiques utilisent `ccxt.async_support`; CCXT Pro et
`watch_ohlcv` restent réservés au flux temps réel.

La migration SQLite 4 réinitialise les anciennes bornes ambiguës sans supprimer les
bougies. Une réparation manuelle générique est également disponible :

```powershell
# Toutes les cibles précédemment déclarées vérifiées
python -m app.cli.repair_history_metadata

# Une cible exacte
python -m app.cli.repair_history_metadata `
  --exchange-id binance --market-type spot `
  --symbol ETH/USDC --timeframe 1h

# Absolument toutes les lignes de métadonnées
python -m app.cli.repair_history_metadata --all
```

La réinitialisation applique `exchange_earliest_time=NULL`,
`exchange_earliest_verified=0`, `has_more_before=1` et `last_error=NULL`.

## Configuration

Backend :

- `CANDLE_DEFAULT_LIMIT` : taille REST par défaut ;
- `CANDLE_MAX_API_LIMIT` : limite de sécurité ;
- `MARKET_HISTORY_WINDOW_BEFORE` / `MARKET_HISTORY_WINDOW_AFTER` : demi-fenêtres
  utilisées autour d’une date ;
- `CANDLE_SYNC_PAGE_LIMIT`, `CANDLE_SYNC_MAX_PAGES` : pagination CCXT bornée.

Frontend :

- `VITE_MARKET_INITIAL_CANDLE_LIMIT` : tranche récente (500 à 2000 conseillé) ;
- `VITE_MARKET_HISTORY_PAGE_LIMIT` : taille d’une page plus ancienne/récente ;
- `VITE_MARKET_HISTORY_WINDOW_BEFORE` / `VITE_MARKET_HISTORY_WINDOW_AFTER` :
  taille de la fenêtre autour d’une date ;
- `VITE_MARKET_MAX_CANDLES_IN_MEMORY=0` conserve toutes les bougies chargées.

Les indicateurs sont recalculés par le moteur Python existant avec la marge
`CANDLE_INDICATOR_WARMUP_BARS`. Les tests remplacent systématiquement l’exchange par
un faux et n’effectuent aucun appel Binance réel.
