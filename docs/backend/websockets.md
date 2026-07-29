# WebSockets

## Snapshots de signaux

Le flux marché accepte un paramètre JSON `profile` validé comme
`MarketIndicatorConfig`. Chaque message fournit `confirmed` et, lorsqu'une
bougie est ouverte, `provisional`. Les anciens champs restent une façade dérivée
pendant la migration.

## Progression du scanner

URL : `ws://127.0.0.1:8000/api/scanner/ws/{job_id}`.

Un job existant est accepté, puis son snapshot courant est envoyé immédiatement. Chaque changement publié par `ScanManager` déclenche ensuite un message : passage à `running`, progression après un symbole et état final. Il n'existe ni intervalle fixe ni message de heartbeat.

Le payload est celui de `ScanJob.public_payload()` sans `results` :

```json
{
  "id": "a1b2c3d4e5f6478899aabbccddeeff00",
  "status": "running",
  "config": {"exchange_id": "binance", "market_type": "spot", "quote": "USDC"},
  "progress": {"processed": 12, "total": 50, "successful": 3, "filtered": 8, "errors": 1, "percent": 24.0},
  "error": null,
  "created_at": "2026-07-22T10:00:00Z",
  "started_at": "2026-07-22T10:00:00.010000Z",
  "completed_at": null,
  "result_count": 3
}
```

Ici encore, `config` est abrégé pour montrer le format du message ; le serveur envoie tous ses champs. Après le premier message `completed`, `failed` ou `cancelled`, le handler retourne et la connexion se termine normalement. Une déconnexion client est silencieusement absorbée.

Si le job n'existe pas, le serveur ferme avant acceptation avec le code 4404 et la raison `Scan introuvable`. Le même code est utilisé si le job disparaît avant une émission.

## Marché temps réel

URL : `ws://127.0.0.1:8000/ws?symbol=BTC/USDC&timeframe=1h`. Les paramètres sont facultatifs et reprennent `BINANCE_SYMBOL` et `BINANCE_TIMEFRAME`. `include_history=false` désactive uniquement le message initial `history` ; sa valeur par défaut reste `true`. La socket est acceptée, le symbole est nettoyé et mis en majuscules, puis le timeframe et le marché Binance sont validés.

### Message `history`

Il est envoyé une fois après `load_markets()`, synchronisation incrémentale et
relecture de SQLite. Un fallback réseau reste disponible si le stockage local
échoue. Les temps de bougie et de point sont des secondes Unix.

```json
{
  "type": "history",
  "symbol": "BTC/USDC",
  "timeframe": "1h",
  "candles": [{"time": 1784710800, "open": 64000.0, "high": 64500.0, "low": 63800.0, "close": 64300.0, "volume": 125.4}],
  "indicators": {
    "rsi_14": [{"time": 1784710800, "value": 48.2}],
    "sma_20": [{"time": 1784710800, "value": 63950.0}],
    "sma_50": [],
    "ema_20": [{"time": 1784710800, "value": 64010.0}],
    "ema_50": [],
    "macd": [],
    "macd_signal": [],
    "macd_histogram": [],
    "bollinger_upper": [],
    "bollinger_middle": [],
    "bollinger_lower": [],
    "stochastic_k": [],
    "stochastic_d": []
  },
  "markers": [],
  "snapshot": {
    "price": 64300.0,
    "rsi": 48.2,
    "trend": "bullish",
    "macd": "neutral",
    "bollinger": "neutral",
    "stochastic": "neutral",
    "confluence": {
      "score": 51.25,
      "grade": "D",
      "breakdown": {"rsi": 6.0, "trend": 25.0, "macd": 8.0, "bollinger": 7.0, "stochastic": 5.25},
      "effective_weights": {"rsi": 20.0, "trend": 25.0, "macd": 20.0, "bollinger": 20.0, "stochastic": 15.0}
    }
  }
}
```

Les listes sont limitées à `DISPLAY_LIMIT`. L'exemple raccourcit volontairement l'historique ; son score applique les facteurs documentés dans [confluence.md](confluence.md).

### Message `update`

Chaque retour non vide de `watch_ohlcv` envoie la dernière bougie, les derniers points disponibles de chaque série, les nouveaux marqueurs éventuels et le snapshot recalculé.

```json
{
  "type": "update",
  "candle": {"time": 1784714400, "open": 64300.0, "high": 64600.0, "low": 64200.0, "close": 64550.0, "volume": 82.1},
  "indicators": {"rsi_14": {"time": 1784714400, "value": 51.7}},
  "markers": [{"time": 1784710800, "position": "belowBar", "shape": "circle", "color": "#38bdf8", "text": "MACD haussier", "category": "signal"}],
  "snapshot": {
    "price": 64550.0,
    "rsi": 51.7,
    "trend": "bullish",
    "macd": "bullish",
    "bollinger": "neutral",
    "stochastic": "neutral",
    "confluence": {
      "score": 57.25,
      "grade": "D",
      "breakdown": {"rsi": 0.0, "trend": 25.0, "macd": 20.0, "bollinger": 7.0, "stochastic": 5.25},
      "effective_weights": {"rsi": 20.0, "trend": 25.0, "macd": 20.0, "bollinger": 20.0, "stochastic": 15.0}
    }
  }
}
```

Si le timestamp est identique, la bougie ouverte est remplacée et `markers`
reste vide. Sa persistance est limitée en fréquence. Si le timestamp augmente,
la précédente vient de clôturer : son état final est immédiatement persisté,
les croisements du dernier index et les divergences nouvellement confirmées sont
alors émis avant l'ajout et la persistance de la nouvelle bougie.

### Marqueurs

Les marqueurs de signal possèdent `time`, `position`, `shape`, `color`, `text`, `category`. Les divergences ajoutent `source`, `divergence_type`, `first_time`, `first_price`, `second_price`, `first_indicator`, `second_indicator` :

```json
{
  "time": 1784710800,
  "position": "belowBar",
  "shape": "arrowUp",
  "color": "#a78bfa",
  "text": "RSI div. haussière",
  "category": "divergence",
  "source": "RSI",
  "divergence_type": "regular_bullish",
  "first_time": 1784631600,
  "first_price": 63000.0,
  "second_price": 62500.0,
  "first_indicator": 24.0,
  "second_indicator": 29.0
}
```

### Message `error` et fermeture

Une exception applicative est journalisée puis, si possible, envoyée :

```json
{"type": "error", "message": "ValueError: Symbole Binance inconnu : TEST/USDC"}
```

La fonction quitte ensuite et ferme toujours l'exchange. Une `WebSocketDisconnect` est seulement journalisée. Aucun code de fermeture applicatif spécifique n'est envoyé par ce flux.
