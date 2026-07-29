# Gestion des erreurs

| Catégorie | Détection et comportement | Transport / retry / impact |
|---|---|---|
| Validation `ScanConfig` | Pydantic, avant le handler | HTTP 422, aucun job créé, pas de retry. |
| Exchange inconnu | `create_exchange`, `UnknownExchangeError` | Non traduit : un job lancé passe à `failed`. La route `/markets` utilise toujours Binance. |
| Marché indisponible | appel `load_markets` | Scan global `failed`; journal avec trace, sans retry explicite à ce niveau. |
| Symbole marché invalide | `/ws` après `load_markets` | Message WebSocket `error`, trace, puis fermeture de l'exchange. |
| Timeframe invalide | domaine `timeframe_seconds` | Sur `/ws`, message `error`; un `ScanConfig` REST invalide répond 422. |
| Données OHLCV vides ou invalides | `market_data` / `analyze_symbol` | `None`, puis erreur isolée du symbole et compteur `errors`. |
| Historique RSI insuffisant | `analyze_symbol` | Erreur isolée `Données RSI insuffisantes`. |
| Rate limit / réseau | `fetch_ohlcv` | Retry exponentiel avec jitter, puis `None` et avertissement après épuisement. |
| Erreur exchange CCXT | `fetch_ohlcv` | Pas de retry, avertissement, puis erreur du symbole. |
| Job introuvable | routes scanner | HTTP 404 `Scan introuvable`; WebSocket de progression 4404. |
| Scan non terminé | résultats / export | HTTP 409 pour `pending`, `running` et aussi `failed`. |
| Annulation | `ScanManager` et `ScannerService` | `CancelledError` conservé jusqu'au manager, résultats partiels, état `cancelled`. |
| Erreur interne de symbole | `_analyze_guarded` | Trace avec symbole, compteur `errors`, autres paires poursuivies. |
| Erreur globale du scan | `_run_job` | Trace, état `failed`, texte dans `job.error`. |
| Déconnexion WebSocket | handlers | Absorbée ; le flux marché ferme l'exchange dans `finally`. |

## Isolation par symbole

Le sémaphore entoure chaque `analyze_symbol()`. Toute exception autre qu'une annulation est capturée et convertie en `AnalysisOutcome(ERROR)`. La boucle incrémente alors `processed` et `errors`, publie la progression et planifie le symbole suivant. Une paire défectueuse ne fait donc pas échouer le job.

Les rejets normaux de filtre utilisent `FILTERED`, sans message d'erreur ni trace. Cela distingue une paire techniquement non retenue d'une donnée impossible à analyser.

## Limites de traduction API

Il n'existe pas de handler FastAPI global pour `ScannerError` ou CCXT. Les erreurs de démarrage d'un job sont capturées par la tâche et deviennent `failed`, mais certaines erreurs de `/markets` remontent comme réponses serveur génériques. Consulter les logs pour leur diagnostic.
