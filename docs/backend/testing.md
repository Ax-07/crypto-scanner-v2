# Tests et qualité

## Caractérisation des signaux — phase 1

Les fichiers `test_indicators_math.py`, `test_signal_classification.py`,
`test_divergences.py`, `test_phase1_data_quality.py` et
`test_phase1_contracts.py` couvrent les calculs numériques, classifications aux
bornes, tendances, croisements, divergences, confluence, qualité OHLCV, sélection
temporelle des clôtures et contrats Pydantic. Ces tests sont déterministes,
n'effectuent aucun appel réseau et utilisent des timestamps fixes ou une horloge
injectée.

## Organisation

Les tests utilisent `unittest` et `IsolatedAsyncioTestCase`, collectés par pytest :

- `test_domain.py` : validations de `ScanConfig`, bougies, limites OHLCV et CSV ;
- `test_market_data.py` : données invalides, retries et bougies clôturées ;
- `test_scanner_service.py` : indicateurs, filtres, confluence, cache, concurrence, tri et cycle de vie ;
- `test_market_stream.py` : payloads du WebSocket marché avec `FakeProExchange` ;
- `test_candle_repository.py` : migrations, pragmas, UPSERT, plages et trous ;
- `test_candle_sync.py` : pagination, reprise, retries, réparation et lecture scanner ;
- `test_candles_api.py` : lecture, validation, statut et export OHLCV ;
- `test_backfill.py` : catalogue, timeframes, simulation, pagination, reprise et arrêt ;
- `test_backfill_cli.py` : validation CLI et sauvegarde SQLite ;
- `test_backtest_coverage.py` : lecture déterministe destinée au futur backtest ;
- `test_api.py` : REST, annulation et WebSocket de progression avec scanners immédiat et bloquant ;
- `test_import_contracts.py` : point d'entrée ASGI, réexports, routes et OpenAPI.

Les doubles de test remplacent CCXT et `ScannerService`. La suite ne doit jamais contacter Binance : un nouveau test réseau doit injecter un faux exchange ou patcher la classe CCXT concernée.

## Commandes

Depuis `backend/`, environnement activé :

```powershell
python -m pytest -q
python -m pytest tests/test_scanner_service.py -q
python -m pytest -k confluence -q
python -m compileall -q app
python -m black --check app tests main.py indicators.py
python -m flake8 app tests main.py indicators.py
python -m mypy app tests main.py indicators.py
python -c "from main import app; print(app.title)"
```

`pyproject.toml` limite pytest à `tests`, configure Black à 100 caractères pour Python 3.11 et exclut `venv`. mypy contrôle `app` mais exclut actuellement `tests`; lui passer `tests` en ligne de commande ne remplace pas cette exclusion. Flake8 est configuré par le dépôt. Ruff et la couverture ne sont pas configurés.

Pour reformater après une modification :

```powershell
python -m black app tests main.py indicators.py
```

## Ajouter un indicateur

1. Tester la série pure, l'amorçage, les valeurs absentes et la détection du signal dans un test de domaine ou de scanner.
2. Tester les bornes et validations de ses paramètres dans `ScanConfig`.
3. Étendre un faux exchange avec juste assez de bougies déterministes.
4. Tester l'activation, la désactivation, le filtre et les champs de `ScanResult`.
5. S'il participe à la confluence, tester facteur, poids nul, renormalisation et grade.
6. S'il apparaît dans `/ws`, vérifier séparément `history` et `update`.

Les assertions doivent porter sur des valeurs calculées déterministes, sans délai réseau réel.
