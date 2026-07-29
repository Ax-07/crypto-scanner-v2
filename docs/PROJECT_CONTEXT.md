# Contexte technique — scanner_crypto

Photographie vérifiée le 24 juillet 2026. Pour le contexte IA autonome le plus complet, utiliser `CURRENT_APP_STATE_FOR_AI.md`. Pour les preuves/statuts, utiliser `PHASES_IMPLEMENTATION_AUDIT.md`.

## Résumé et état

Application locale FastAPI + React d’analyse de marchés crypto : stockage OHLCV SQLite, scanner technique, marché Binance live, backtest causal et expériences bornées. Aucun passage d’ordres.

L’état Git est indéterminable : `.git/` existe mais est vide. Branche, commit, modifications suivies/non suivies et historique ne peuvent pas être fournis.

| Phase | État |
|---|---|
| 1 — calculs/contrats/qualité | `partial` : très largement implémentée et testée, couverture invalide/NaN non exhaustive par famille |
| 2 — cohérence scanner/live/frontend | `partial` : confirmed/provisional, profils et Zod opérationnels ; assemblage encore dupliqué et tendance live mono-TF |
| 3 — replay/backtest | `partial` : causal/persistant ; statistiques, divergence replay, provisional et reprise incomplets |
| 4 — expérimentation | `partial` : splits/profils/promotion présents ; vrai walk-forward, familles avancées et shadow automatique absents |

## Stack

Backend : Python 3.11.5, FastAPI, Pydantic, pandas, NumPy, ccxt/ccxt.pro, aiosqlite, pytest, Black, Flake8, mypy.

Frontend : Node 24.12.0, pnpm 10.15.1, React 19, React Router 7, TypeScript 6, Vite 8, RHF, Zod, Zustand, Lightweight Charts, Tailwind/Shadcn/Radix.

## Architecture

```text
backend/app/
├── api/            routes REST/WS
├── cli/            sync/backfill/backup/réparation
├── core/           configuration et erreurs
├── database/       SQLite + migrations
├── domain/         calculs purs candles/indicators/backtesting/experiments
├── models/         Pydantic
├── repositories/   persistance
└── services/       orchestration scanner/live/jobs

frontend/src/
├── api/            clients + Zod runtime
├── app/            routeur/layout
├── components/     UI et graphique
├── features/       scanner/marché/backtests/expériences
├── pages/
├── stores/         Zustand
└── types/
```

Points d’entrée : `backend/main.py` → `app.main:app`; `frontend/src/main.tsx`.

## Fonctionnalités

Scanner : jobs mémoire, CCXT configurable, SQLite prioritaire, indicateurs activables, filtres, confluence explicable, progression/annulation/export.

Marché : pagination SQLite, navigation date, CCXT Pro Binance, reconnexion, indicateurs et marqueurs, confirmed/provisional, profil URL.

Backtest : replay confirmed close-only, trois modes, trois politiques de trous, observations/outcomes, frais/slippage/MFE/MAE, analytics, persistance, API/WS/UI/exports. Pas de portefeuille ni reprise de job.

Expériences : backtest source, fingerprint, splits/embargo/folds, candidats bornés, métriques train/validation/test, profils et promotion. Shadow = stockage manuel seulement.

## Stockage et migrations

Chemin par défaut : `backend/data/scanner_crypto.sqlite3`. Schéma applicatif version 6 via `schema_migrations`; `PRAGMA user_version` n’est pas utilisé.

Tables : candles, markets, sync/gaps/bounds/backfill, backtest jobs/observations/outcomes, experiment jobs, signal profiles, promotion decisions, shadow comparisons.

État local vérifié : intégrité ok, migrations 1..6, 102 886 bougies, 468 observations, 1 404 outcomes, 2 expériences, 2 profils.

## Routes frontend

- `/scanner`
- `/market`
- `/backtests`
- `/backtests/experiments`

## Routes backend

Groupes réels :

- `/api/scanner/config`, `/markets`, `/jobs*`, WebSocket scanner ;
- `/api/market/candles*`, `/api/market/history*`, WebSocket `/ws` ;
- `/api/backtests*`, WebSocket de job ;
- `/api/experiments/jobs*` ;
- `/api/signal-profiles*` ;
- `/api/shadow/comparisons`.

La liste exhaustive est dans `CURRENT_APP_STATE_FOR_AI.md` et a été comparée à OpenAPI.

## Modèles et contrats

Scanner : `ScanConfig`, `MarketIndicatorConfig`, `ScanJob`, `ScanResult`.

Backtest : `BacktestConfig`, `BacktestJob`, `SignalObservation`, `ForwardOutcome`, `BacktestSummary`.

Recherche : `ExperimentConfig`, `ExperimentManifest`, `CandidateSpec/Result`, `SignalProfileVersion`, `PromotionDecision`, `ShadowComparison`.

Les contrats TS sont dans `frontend/src/types`; les messages WS marché/scanner/backtest sont validés par Zod. Les champs racine legacy des snapshots restent présents pour compatibilité.

## Configuration

Backend : `DATABASE_PATH`, CORS/TTL/rétention, `CANDLE_*`, `BACKFILL_*`, `SHADOW_MODE_ENABLED`. Le scanner possède sa configuration métier par job.

Frontend : `VITE_API_URL`, `VITE_WS_URL`, `VITE_MARKET_MAX_CANDLES_IN_MEMORY`.

Valeurs par défaut signal : 4h, 200 barres, RSI 14/35, MA 20/50, MACD 12/26/9, Bollinger 20×2, Stoch 14/3 20/80, confluence min 60.

## Commandes

```powershell
cd backend
.\venv\Scripts\python.exe -m uvicorn main:app --reload
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m compileall -q app tests main.py indicators.py
.\venv\Scripts\python.exe -m black --check app tests main.py indicators.py
.\venv\Scripts\python.exe -m flake8 app tests main.py indicators.py
.\venv\Scripts\python.exe -m mypy app

cd ..\frontend
pnpm run dev
pnpm run typecheck
pnpm run lint
pnpm run test
pnpm run build
```

Backfill :

```powershell
cd backend
python -m app.cli.backfill_candles --quote USDC --symbols all --timeframes all
# ajouter --execute pour écrire/télécharger réellement
```

Les migrations s’appliquent automatiquement au démarrage avec le stockage activé.

## État qualité

Audit final :

- backend : 248 passed, 1 benchmark opt-in passé séparément, 22 subtests ;
- frontend : 52 passed dans 17 fichiers ;
- compileall, Black, Flake8, mypy, typecheck, lint et build : succès ;
- SQLite temporaire : création, migrations, insert/read, restart/read et suppression contrôlée : succès.

Deux warnings pandas signalent une perte de nanosecondes lors d’une conversion datetime. Aucun test ne requiert Binance.

## Dette et risques

- assemblage des signaux dupliqué scanner/live/replay ;
- jobs scanner en mémoire et backtests interrompus non repris ;
- divergences absentes du replay ;
- statistiques phase 3 incomplètes ;
- protocole walk-forward partiel ;
- familles avancées et shadow automatique absents ;
- profil frozen dont le statut JSON est muté ;
- requirements Python à versions minimales, avec dépendances desktop historiques ;
- pas d’UI profils/promotion/shadow, ni restauration/pagination backtest complète.

## Où modifier quoi

| Sujet | Emplacement |
|---|---|
| Formules/confluence/tendance | `backend/app/domain/indicators.py` |
| Scanner | `backend/app/services/scanner.py`, manager/API, frontend feature/store |
| Live/snapshots/marqueurs | `backend/app/services/market_stream.py`, market frontend |
| Replay/statistiques | `domain/backtesting.py`, engine/repository/API/page |
| Expériences/profils/shadow | `models/experiment.py`, `domain/experiments.py`, manager/repository/API/page |
| SQLite | `database/schema.py`, migrations, repositories |
| Contrats frontend | `frontend/src/types`, `api`, schemas feature |
| Routes | `app/main.py`, routers, `frontend/src/app/router.tsx` |
| Documentation | présent fichier, audit, état IA, signaux/backtesting/optimisation |
