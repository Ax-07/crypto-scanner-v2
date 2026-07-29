# Documentation du backend

Le backend expose le scanner technique asynchrone, deux flux WebSocket et le build React. Il valide chaque scan avec Pydantic, synchronise les bougies CCXT dans SQLite, calcule les indicateurs dans un domaine indépendant et conserve les jobs en mémoire.

## Pile technique

- Python 3.11 dans l'environnement actuel ;
- FastAPI, Uvicorn et Pydantic ;
- `ccxt.async_support` pour les scans et `ccxt.pro` pour le marché temps réel ;
- `aiosqlite` pour le stockage OHLCV local durable ;
- pandas et NumPy pour les séries ;
- pytest, Black, Flake8 et mypy pour la qualité.

## Flux principal

```text
Frontend React
├── REST → routes FastAPI → ScanManager → ScannerService
│                                      ├── CCXT / données OHLCV
│                                      ├── indicateurs
│                                      └── ScanResult
├── WS /api/scanner/ws/{job_id} → snapshots du ScanManager
└── WS /ws → flux Binance CCXT Pro → bougies, indicateurs et marqueurs
```

`ScanManager` porte le cycle de vie d'un job. `ScannerService` analyse les symboles avec une concurrence bornée. Le domaine calcule les indicateurs sans connaître FastAPI ni CCXT.

## Parcours documentaire

- [Architecture](architecture.md)
- [Démarrage](getting-started.md)
- [Configuration](configuration.md)
- [Référence REST et modèles](api-reference.md)
- [Flux complet d'un scan](scanner-flow.md)
- [Exchanges et données de marché](exchange-and-market-data.md)
- [Stockage SQLite des bougies](ohlcv-storage.md)
- [Historique du graphique chargé à la demande](on-demand-market-history.md)
- [Backfill historique et CLI](historical-backfill.md)
- [Indicateurs et tendance](indicators.md)
- [Score de confluence](confluence.md)
- [Jobs, progression et annulation](jobs-and-progress.md)
- [WebSockets](websockets.md)
- [Gestion des erreurs](error-handling.md)
- [Tests et qualité](testing.md)
- [Déploiement](deployment.md)
- [Dépannage](troubleshooting.md)

## Démarrage express

Prérequis : Python 3.11 ou une version compatible avec les dépendances, et Node.js/pnpm pour reconstruire le frontend.

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

```powershell
cd backend
python -m pytest -q
```

Les sondes sont `GET http://127.0.0.1:8000/api/health` et `GET http://127.0.0.1:8000/health`.

## Limites générales

- Les bougies OHLCV sont persistées ; les jobs et résultats ne sont ni persistés ni partagés entre processus.
- Un redémarrage les supprime et déconnecte les WebSockets.
- Un seul worker Uvicorn doit être utilisé pour conserver la cohérence REST/WebSocket des jobs.
- Le streaming `/ws` dépend de `ccxt.pro` et de la disponibilité de `watch_ohlcv` sur Binance.
- Le backend public ne configure aucune authentification ni clé d'exchange.

Les signaux produits sont des informations techniques et ne constituent pas un conseil financier.
