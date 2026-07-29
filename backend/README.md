# Backend FastAPI

La documentation de référence se trouve dans
[`../docs/backend/README.md`](../docs/backend/README.md). Le présent fichier reste
un mémo concis placé à côté du point d'entrée.

Les bougies OHLCV sont conservées localement dans SQLite
(`data/scanner_crypto.sqlite3` par défaut), sans serveur externe. Le schéma, la
synchronisation incrémentale, les routes et la sauvegarde WAL sont décrits dans
[`../docs/backend/ohlcv-storage.md`](../docs/backend/ohlcv-storage.md).

Le backfill complet et la synchronisation incrémentale sont documentés dans
[`../docs/backend/historical-backfill.md`](../docs/backend/historical-backfill.md).

La pagination ciblée du graphique et le mode « aller à une date » sont documentés
dans [`../docs/backend/on-demand-market-history.md`](../docs/backend/on-demand-market-history.md).

Le point d'entrée ASGI stable est `main:app`; il réexporte l'application définie dans
`app.main`. Le frontend React compilé reste servi par FastAPI, avec fallback SPA.

Le fichier racine `indicators.py` est uniquement un module de compatibilité pour les
anciens imports publics. Toutes ses fonctions sont des réexports de `app.domain.indicators`.

## Architecture

```text
app/
├── api/                    scanner, bougies et WebSocket de progression
├── core/                   configuration applicative, ScanConfig, logging, erreurs
├── database/               connexions, schéma et migrations SQLite
├── domain/                 bougies, limites OHLCV, indicateurs et types d'analyse
├── exporters/              sérialisation CSV
├── models/                 contrats publics des jobs et résultats
├── repositories/           requêtes OHLCV paramétrées
├── services/               exchange async, données, scanner, jobs et streaming marché
└── main.py                 fabrique d'application, santé, routeurs et frontend
```

Flux du scanner :

```text
API
  → ScanManager
    → ScannerService
      → ExchangeService / market_data
      → Indicator Domain
      → ScanResult
    → Progress Publisher
  → WebSocket / Results / CSV
```

## Développement et vérifications

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload

python -m pytest -q
python -m black --check app tests main.py
python -m flake8 app tests main.py
python -m mypy app
python -m compileall app
python -c "from main import app; print(app.title)"
```

Les tests emploient exclusivement de faux exchanges et ne contactent pas Binance.

## Configuration

`ScanConfig` est créé pour chaque job et transmis explicitement au scanner. Il contient
l'exchange, le type de marché, la quote, les timeframes, les indicateurs, les filtres,
la concurrence et les retries. Il n'existe aucun état global mutable de scan dans
`app/`.

Variables applicatives :

- `CORS_ORIGINS` : origines séparées par des virgules ;
- `JOB_TTL_SECONDS` : durée de conservation d'un job terminé (défaut 3600) ;
- `MAX_RETAINED_JOBS` : nombre maximal de jobs en mémoire (défaut 100) ;
- `BINANCE_SYMBOL`, `BINANCE_TIMEFRAME`, `CALCULATION_LIMIT`, `DISPLAY_LIMIT` :
  valeurs par défaut du graphique temps réel ;
- variables `DIVERGENCE_*` : réglage des pivots et divergences du graphique.

Aucun secret ni clé API n'est stocké dans le code.

## API conservée

- `GET /api/health`, `GET /health`, `WS /ws`
- `GET /api/scanner/config`, `GET /api/scanner/markets`
- `POST /api/scanner/jobs`
- `GET|DELETE /api/scanner/jobs/{job_id}`
- `GET /api/scanner/jobs/{job_id}/results`
- `GET /api/scanner/jobs/{job_id}/export.csv`
- `WS /api/scanner/ws/{job_id}`

Le lancement retourne 202, un job absent 404 et des résultats prématurés 409. Les
payloads publics restent ceux consommés par les types TypeScript existants.

## Scanner, retries et bougies

Le scanner crée progressivement au plus `max_concurrency` analyses. Une erreur de paire
est isolée. CCXT async applique `max_retries`, un backoff exponentiel borné à 30 secondes
et un léger jitter aux erreurs réseau/rate-limit; une erreur exchange définitive n'est
pas retryée. L'exchange est fermé dans un `finally`.

Les timestamps bruts restent en millisecondes. Les dates métier sont UTC et le graphique
convertit explicitement en secondes. Une bougie participe au scan seulement si
`timestamp + durée_timeframe <= maintenant`. Les lignes dont timestamp/open/high/low/
close sont non numériques ou non finies sont rejetées.

La limite OHLCV est le maximum des besoins des seuls indicateurs actifs, avec marge. Un
cache limité à l'analyse d'un symbole évite les lectures identiques par timeframe.

## Confluence, annulation et rétention

La confluence ne retient que les indicateurs actifs, calculés et finis. Leurs poids sont
renormalisés à 100; sans facteur valide, le résultat vaut `None` et le filtre minimum ne
s'applique pas. Les grades restent A+, A, B, C, D et F.

Une annulation stoppe la planification, annule les tâches en attente, laisse remonter
`CancelledError`, ferme l'exchange et conserve les résultats partiels. Le manager publie
les changements par `asyncio.Condition`; le WebSocket envoie immédiatement le snapshot,
sans polling ni doublon, puis se ferme à l'état final.

Les jobs terminés sont gardés en mémoire seulement jusqu'au TTL et à la limite configurée.
La purge s'effectue lors de la création des jobs et ne retire jamais un job actif.

## Limites connues

La rétention est volontairement en mémoire : les jobs disparaissent au redémarrage et ne
sont pas partagés entre plusieurs processus Uvicorn. Le streaming `/ws` utilise CCXT Pro
et nécessite donc une version/licence qui expose `watch_ohlcv`.
