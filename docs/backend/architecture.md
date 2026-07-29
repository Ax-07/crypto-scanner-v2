# Architecture du backend

## Structure et responsabilités

```text
backend/
├── main.py                 point d'entrée ASGI stable, réexporte app.main:app
├── indicators.py           réexports historiques des indicateurs
├── app/
│   ├── api/                transport REST et WebSocket des scans
│   ├── cli/                backfill, synchronisation et sauvegarde SQLite
│   ├── core/               environnement, ScanConfig, logging, exceptions
│   ├── database/           connexions courtes, schéma et migrations SQLite
│   ├── domain/             bougies, limites, indicateurs, issues internes
│   ├── exporters/          conversion CSV
│   ├── models/             contrats Pydantic publics
│   ├── repositories/       requêtes paramétrées sur les bougies
│   ├── services/           CCXT, scanner, jobs et marché temps réel
│   └── main.py             fabrique FastAPI et service du frontend
└── tests/                  tests sans accès réel à Binance
```

Les routes appellent les services. Les services peuvent dépendre du domaine, des modèles et de l'infrastructure CCXT. Le domaine ne dépend pas des routes ou de CCXT. `ScanConfig` est transmis explicitement à chaque `ScannerService`.

## Objets principaux

- `ScanConfig` valide l'intégralité d'une demande.
- `ScanManager` conserve les `ScanJob`, tâches, versions et `asyncio.Condition`.
- `ScannerService` charge les symboles, orchestre leur analyse et construit des `ScanResult`.
- `ExchangeProtocol` réduit la surface CCXT et permet les faux exchanges de test.
- `CandleRepository` persiste les OHLCV brutes et `CandleSyncService` orchestre CCXT.
- `MarketCatalogService` découvre les marchés et `CandleBackfillService`
  orchestre les longues exécutions avec `BackfillRepository`.
- `AnalysisOutcome` distingue succès, rejet par filtre et erreur d'un symbole.
- `websocket_market_data` orchestre un flux graphique indépendant des jobs.

## Cycle de vie FastAPI

`backend/main.py` garantit l'import historique `main:app`. `app.main.create_app()` crée FastAPI, configure le CORS, inclut les routeurs scanner et bougies, puis déclare les routes de santé, le WebSocket marché et le service React. Le `lifespan` configure les logs, crée le dossier SQLite, active WAL et applique les migrations. Aucune connexion CCXT n'est ouverte au démarrage.

`CORS_ORIGINS` devient la liste `allow_origins`. Les credentials, méthodes et en-têtes sont autorisés. Le logging écrit sur la console et dans `LOG_DIR/scanner.log` avec le niveau `LOG_LEVEL`.

## Frontend React

Si `frontend/dist/index.html` existe, `/` le sert. La route attrape-tout sert les assets situés sous `dist` et retourne l'index pour le routage SPA ; la résolution du chemin empêche de sortir du dossier. Sans build, `/` répond 503 avec les commandes de développement et les autres chemins répondent 404.

## Compatibilité

`backend/indicators.py` réexporte les fonctions de `app.domain.indicators`. Il ne contient aucune seconde implémentation. `backend/main.py` joue le même rôle pour l'application ASGI.

## Règles d'architecture

- Les routes ne contiennent pas les calculs du scanner.
- Les indicateurs n'accèdent pas directement à CCXT.
- SQLite conserve les OHLCV brutes ; les indicateurs calculés ne sont pas persistés.
- Un `ScanConfig` validé porte toute la configuration d'un scan.
- Les connexions d'exchange du scan et du streaming sont fermées dans `finally`.
- Le scanner n'utilise que des bougies clôturées ; le flux graphique expose aussi la bougie ouverte.
- Une erreur d'un symbole ne fait pas échouer les autres symboles.
- L'état des jobs est local au processus et la purge ne vise que des jobs terminés.

Voir aussi [le flux du scanner](scanner-flow.md) et [les jobs](jobs-and-progress.md).
