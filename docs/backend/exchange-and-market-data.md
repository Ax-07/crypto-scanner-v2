# Exchanges et données de marché

## Deux clients CCXT

Le scanner REST utilise `ccxt.async_support`. `create_exchange()` résout dynamiquement `exchange_id`, active `enableRateLimit`, fixe un timeout de 30 000 ms et transmet `options.defaultType`. Le WebSocket `/ws` utilise exclusivement `ccxt.pro.binance` avec `enableRateLimit` et `newUpdates`. Les deux chemins écrivent les OHLCV brutes dans SQLite.

Les deux chemins ferment leur exchange dans `finally`. `GET /api/scanner/markets` fait de même après la liste.

## Filtrage des marchés

Après `load_markets()`, un marché est conservé si :

- `active` n'est pas explicitement `false` ;
- `type` correspond exactement à `spot`, `swap` ou `future` ;
- `quote` correspond à la quote normalisée ;
- sa base n'est pas stable si `exclude_stable_pairs=true`.

Bases exclues : `USDT`, `USDC`, `BUSD`, `DAI`, `TUSD`, `USDP`, `FDUSD`, `EURC`. Les symboles sont triés avant `max_pairs`. Le scanner ne réécrit pas les symboles retournés par CCXT. Le flux marché retire les espaces et met le symbole demandé en majuscules avant de le chercher dans `exchange.markets`.

## Récupération OHLCV et retries

Le scanner demande d'abord l'historique à `CandleSyncService`, qui relit SQLite
si les données sont suffisantes et fraîches. Sinon, il pagine explicitement
`fetch_ohlcv()` avec `since`, UPSERT les pages et relit SQLite. La conversion en
DataFrame reste la frontière vers les indicateurs. Une réponse vide ou
entièrement invalide devient une erreur isolée du symbole.

- `RateLimitExceeded` et `NetworkError` sont récupérables ;
- le nombre total maximal de tentatives vaut `max_retries + 1` ;
- le délai commence à `retry_delay_seconds`, double après chaque échec et est plafonné à 30 secondes ;
- chaque attente est multipliée par un jitter uniforme entre 0,9 et 1,1 ;
- une `ExchangeError` est considérée définitive et n'est pas retentée.

Le rate limiting natif de CCXT reste activé. Une erreur sur une paire est transformée en issue interne et n'arrête pas le scan global.

## Validation des lignes

Les six colonnes attendues sont `timestamp`, `open`, `high`, `low`, `close`, `volume`. Timestamp et OHLC non numériques, infinis ou absents font rejeter la ligne. Un volume invalide devient `0.0`.

La limite demandée n'est pas simplement `min_ohlcv_bars` : elle couvre le plus grand besoin des indicateurs actifs, ajoute une marge de 10, puis le scanner demande encore une ligne pour pouvoir exclure la bougie ouverte.

## Timestamps et bougies clôturées

- CCXT fournit les timestamps en millisecondes Unix.
- Le domaine conserve une colonne `timestamp` en millisecondes et une colonne `time` en datetime UTC.
- Les payloads du graphique convertissent `time` en secondes Unix, format attendu côté graphique.

Pour un timeframe de durée `D`, une bougie n'est clôturée que si `timestamp + D <= maintenant`. Les timeframes acceptés vont de `1m` à `1w` et leur durée est explicitement mappée.

Le scanner exclut la bougie ouverte pour produire des filtres reproductibles. Le flux temps réel la conserve volontairement : une mise à jour de même timestamp remplace la dernière bougie ; un timestamp supérieur confirme la précédente, calcule ses nouveaux marqueurs, puis ajoute la nouvelle bougie ouverte.

Calculer un signal de scan sur une bougie ouverte l'exposerait à disparaître avant la clôture. Cette distinction est donc volontaire.
