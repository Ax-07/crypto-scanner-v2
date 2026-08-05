# État actuel de `scanner_binance_v2` pour reprise IA

Généré le 5 août 2026 après audit du code, des tests, des artefacts et de la base
locale. Le rapport détaillé et les preuves sont dans
[`docs/audits/current-project-audit.md`](audits/current-project-audit.md).

## Métadonnées de reprise

- Branche : `main`.
- Commit audité initialement : `5d137a57462a53ee984052e9ae003352498279fa`.
- HEAD observé après publication externe de l'audit pendant la Phase 0 :
  `763ffa8b1c4cfc66433472a23ff65896aec7c5af`.
- HEAD au démarrage de la Phase 1 : `4b6676b2abb4fde0d65dd4baa28525e8ca01fd06` ;
  les changements Phase 0 avaient été commités extérieurement et le worktree était propre.
- Amont : `origin/main`, avance 0, retard 0 au début de l'audit.
- État initial : aucun fichier suivi modifié et aucun fichier non suivi.
- `frontend/src/lib/utils.ts` est requis par 27 composants. La Phase 0 a ajouté des négations
  ciblées au motif `.gitignore` `lib/` : le fichier est désormais versionnable et une copie
  frontend propre a été installée, compilée et testée avec succès.
- Git nécessite ici `-c safe.directory=...` à cause du propriétaire Windows ; ne pas modifier la
  configuration globale sans demande.
- Modifications de l'audit : uniquement ce fichier et
  `docs/audits/current-project-audit.md`.
- Ne pas lire/reproduire `frontend/.env`. Ne pas supprimer les caches, virtualenv, base ou
  artefacts ignorés sans demande explicite.

## Résumé du produit

Application locale d'analyse technique crypto, sans passage d'ordre réel :

- scanner asynchrone CCXT multi-paires ;
- dashboard Binance historique et temps réel ;
- stockage SQLite de bougies et jobs ;
- indicateurs, signaux structurés, événements et confluence ;
- backtest causal avec observations et outcomes futurs ;
- simulation facultative de portefeuille long-only ;
- expérimentations de profils et shadow ;
- pipeline ML causal, exports vérifiés et benchmark temporel.

Le backend est FastAPI/Pydantic/aiosqlite/pandas. Le frontend est React 19, TypeScript 6,
Vite 8, React Router, Zustand, React Hook Form, Zod, Shadcn/Radix et lightweight-charts.

## Architecture

```text
backend/
  app/
    api/            REST scanner, bougies, historique, backtests, expériences
    core/           settings, chemins, logs, exceptions
    database/       connexion SQLite, migrations 1 à 9
    domain/         candles, indicateurs, décision, analyses, portefeuille
    models/         contrats Pydantic publics
    repositories/   persistance SQLite
    services/       scanner, marché, backtest, portfolio, expériences
    ml/             dataset, preprocessing, évaluations, exports et CLI
    cli/            backfill/sync/backup/réparation
  tests/
  artifacts/        datasets et benchmarks ML suivis
frontend/
  src/
    app/            router/providers/layout
    api/            REST/WebSocket + validation Zod
    stores/         Zustand scanner/marché/backtest
    features/       scanner, marché, backtests, expériences
    components/     graphique, signaux, primitives UI
    types/          miroirs TypeScript
docs/
```

Points d'entrée : `backend/main.py` exporte l'application créée par
`backend/app/main.py:create_app`; `frontend/src/main.tsx` monte la SPA.

## Routes REST et WebSocket

### REST

- `GET /health`, `GET /api/health`.
- Scanner sous `/api/scanner` : config, marchés, jobs, résultats, CSV, annulation.
- Bougies sous `/api/market/candles` : état, fenêtre, pagination et CSV.
- Historique sous `/api/market/history` : couverture globale/par symbole et runs.
- Backtests sous `/api/backtests` : création, liste, capacités, lecture, reprise, annulation,
  summary, observations, outcomes, correlations, segments, funnel, divergences, ablations,
  exports.
- Portefeuille : metadata, trades/equity paginés, CSV trades/equity.
- Expériences/profils/shadow sous `/api/experiments`, `/api/signal-profiles`, `/api/shadow`.
- Fallback SPA sur `/` et `/{frontend_path:path}` si le build est disponible.

### WebSocket

- `/api/scanner/ws/{job_id}` : progression/résultats scanner.
- `/api/backtests/{job_id}/ws` : progression backtest.
- `/ws?symbol=...&timeframe=...&include_history=...&profile=...` : marché live, messages
  `history`, `update`, `error`.

## Modèles et contrats importants

`ScanConfig` est la configuration technique commune. Elle contient timeframe, exchange/type/
quote, limites OHLCV, RSI, SMA/EMA, MACD, Bollinger, Stochastique, filtres/confluence et les
extensions optionnelles ATR, ADX, Supertrend, Donchian et Keltner.

`IndicatorSignalModel` expose status, direction, signal, state, strength, reason, raw_value et
des `components` additifs. Les composants portent valeur brute, valeur normalisée et unité.

`BacktestConfig` contient symboles, dates UTC, `signal_config`,
`signal_profile_id="inline"`, horizons, replay/entry/gap policies, frais/slippage, statut du
snapshot et bloc portefeuille optionnel. `SignalObservation` contient la décision technique,
signaux, événements, profil/fingerprint, OHLCV source, qualité et provenance.
`ForwardOutcome` contient la cible future par horizon. `BacktestSummary` ne doit pas être confondu
avec une performance de portefeuille.

Le frontend valide strictement certaines frontières avec Zod mais utilise aussi `passthrough` et
des casts. Toujours modifier Python, TypeScript, Zod, fixtures et documentation ensemble lors
d'une évolution de contrat.

## SQLite et persistance

`backend/app/database/schema.py` définit neuf migrations :

1. bougies ;
2. marchés, sync, backfill et gaps ;
3-4. bornes historiques ;
5. jobs/observations/outcomes backtest ;
6. expériences, profils, promotions, shadow ;
7. checkpoints, artifacts, lifecycle ;
8. run/ordres/exécutions/trades/equity portefeuille.
9. revendication atomique des identités de sources ML v2.

La copie locale ignorée `backend/data/scanner_crypto.sqlite3` est intègre, en version 8, avec
143 325 bougies, 283 symboles, 8 timeframes, 8 jobs terminés, 4 711 observations et 22 619
outcomes au moment de l'audit. Tous les jobs locaux sont `signal_profile_id=inline`; il n'existe
pas de backtest source `ml-dataset-v2` local.

`DATABASE_PATH` choisit la base. Les écritures métier passent par les repositories. Ne jamais
supposer que la base ignorée est disponible dans un clone frais.

## Scanner

`ScannerService` charge/filtre les marchés CCXT, récupère les OHLCV, retire la bougie ouverte,
calcule le bundle, applique filtres et confluence, puis trie les résultats. `ScanManager` gère les
tâches. Le scanner ne stocke pas une position et ne passe pas d'ordre. Les structured signal
filters v1 ciblent MACD, Bollinger et Stochastique avec fallback legacy local.

## Historique OHLCV

`CandleRepository` est la source SQLite. `CandleSyncService`, `CandleBackfillService` et
`MarketHistoryService` gèrent synchronisation/couverture/fenêtres. CLI :

```powershell
python -m app.cli.backfill_candles
python -m app.cli.sync_candles
python -m app.cli.repair_history_metadata
python -m app.cli.backup_database
```

Le backtest lit SQLite uniquement et demande `closed_only=True`; il ne contacte pas l'exchange.

## Indicateurs, signaux et confluence

Indicateurs historiques : RSI, SMA/EMA, MACD, Bollinger, Stochastique. Extensions disponibles :
ATR/NATR, ADX/DMI, Supertrend, Donchian, Keltner. Les extensions sont désactivées par défaut dans
`ScanConfig`; le profil dataset v2 les active explicitement.

`domain/indicator_bundle.py` centralise calculs/signaux/événements.
`domain/backtesting.py:evaluate_information_set` est la décision canonique du replay ;
`domain/signal_evaluation.py:evaluate_signal_snapshot` est la façade commune. Les extensions
n'ajoutent pas de filtre/confluence et ne changent pas `accepted`, outcomes ou trades par défaut.

## Marché, graphique et marqueurs

Le service marché produit une vue confirmed sur bougies closes et une vue provisional incluant
la bougie en formation. Les marqueurs restent confirmed. Ils couvrent EMA, MACD, Supertrend,
RSI, Stochastique, Bollinger, Donchian, Keltner, ADX/DMI et ATR/NATR.

Le store fusionne/déduplique bougies, séries et marqueurs. Le graphique applique visibilité,
normalisation d'anciens marqueurs et empilement. `minimumSimultaneousMarkers` accepte 1 à 5 et
filtre les événements ayant le même timestamp. ATR exige visibilité signaux et volatilité.

## Backtest réel

Flux :

1. `POST /api/backtests` valide le config ; `BacktestManager` crée un UUID et persiste le job.
2. `BacktestEngine` charge warmup, fenêtre et futur nécessaire depuis SQLite.
3. Chaque fenêtre est tronquée causalement à la décision.
4. `evaluate_signal_snapshot` produit l'observation avec le profil transmis.
5. `calculate_forward_outcomes` calcule h horizons, entrée signal close/next open, frais,
   slippage, MFE/MAE et censure.
6. Repository persiste observation/outcomes et checkpoint.
7. `build_analytics` produit summary/correlations/segments/funnel/divergences/ablations.
8. Si demandé, le portefeuille simule ensuite à partir des observations et des bougies, jamais
   des outcomes, puis persiste son résultat.
9. REST/WS et exports exposent les résultats.

Modes replay : `every_bar`, `state_changes`, `filtered_signals`. Provisional est refusé, faute de
révisions intrabar historiques. Les gaps peuvent rejeter, sauter les observations affectées ou
être tolérés avec warning.

## Portefeuille

Simulation v1 facultative, mono-symbole, long-only, cash + une position, Decimal, sizing en
pourcentage du cash, frais/slippage, entrée signal close ou next open, politique de fin de test.
Elle est distincte des outcomes indépendants. Le bloc absent conserve le payload historique.
Trades/equity sont paginés et exportables ; la persistance est atomique par lots. Pas de short,
levier, stop-loss, take-profit ou portefeuille multi-actifs.

## Profils et fingerprints

### Identité de profil

`BacktestConfig.signal_profile_id` vaut `inline` par défaut, est normalisé et transmis à chaque
observation comme `profile_id`. Le config public omet uniquement `inline`; un identifiant explicite
reste visible. `signal_profile` dans l'observation contient le `ScanConfig` réellement utilisé.

Attention : le moteur ne résout pas `signal_profile_id` dans le repository des profils. Le caller
doit fournir simultanément le bon `signal_config` et le bon identifiant.

### Trois identités à ne pas confondre

- `profile_fingerprint` : SHA-256 du `ScanConfig` canonique, identité technique de l'observation ;
- `config_fingerprint` : fingerprint du backtest/portefeuille, créé seulement si
  `portfolio_simulation` existe ;
- `dataset_version` du backtest : hash de symbole + bornes + nombre de bougies, donc identité de
  fenêtre faible, pas hash du contenu OHLCV.

Les tests prouvent que l'ajout du portefeuille ne change pas `profile_fingerprint` et produit un
`config_fingerprint` séparé.

## Pipeline ML v1

État : infrastructure implémentée ; premier modèle logistique rejeté ; production interdite ;
test terminal consommé.

Flux : `BacktestRepository.ml_source_rows` joint observations confirmed et outcome h6 ;
`MLDatasetBuilder` filtre et construit les lignes ; `MLDatasetExporter` écrit JSONL/manifeste ;
`MLDatasetLoader` vérifie hash/ordre/métadonnées ; preprocessing, split chronologique purgé,
walk-forward, dummy/logistique et final evaluator produisent le benchmark.

Contrats : dataset/manifeste 1, `causal-features-v1`, label `direction-natr-h6-v1`, horizon 6.
Le label compare le rendement futur au seuil `NATR / 100 * multiplier`. Les features refusent
les données futures/réservées et les nombres non finis. Fit du preprocessing uniquement sur train.

Artefact principal : 713 lignes BTC/USDC 1h, hash JSONL
`sha256:a94660d07503b9494ac646ad948d0738d7b6a6941b1893c40a3a671484e4b2a4`.
Benchmark rejeté :
`sha256:dab10c9e3de2e160fd25b8259dc37e444190f8dc4d925d33bea87b0407f109dc`.

## Pipeline ML v2

### Déjà présent

- `ML_DATASET_PROFILE_V2_ID = "ml-dataset-v2"` ;
- `build_ml_dataset_profile_v2(timeframe, quote, exchange_id, market_type)` active ATR, ADX, Supertrend, Donchian,
  Keltner en conservant les defaults historiques ;
- schéma de caractéristiques `causal-features-v2` ;
- composants continus/normalisés aplatis dans les features ;
- CLI export accepte `--feature-schema-version causal-features-v2` ;
- builder/exporter exigent job terminé, profil/config canonique, horizon 6, même fingerprint
  SHA-256 et au moins une ligne ; loader compatible v2.
- `MLV2SourceService` construit, retrouve, reprend ou crée le source canonique ;
- `python -m app.ml.cli.prepare_ml_v2_source` expose `--dry-run`, `--wait` et `--json` ;
- l'identité logique `ml-v2-source-identity-v1` couvre le config complet et la version moteur ;
- la migration 9 et une transaction `BEGIN IMMEDIATE` empêchent deux revendications identiques ;
- la couverture locale vérifie warmup, fenêtre, futur h6, timeframes MA, bougies closes et gaps ;
- l'intégration SQLite temporaire valide backtest, export v2, loader, réutilisation et hash stable.

### Encore manquant

- fingerprint fort du contenu OHLCV et manifest suffisant pour reconstruire le source ;
- artefact dataset v2 ;
- politique d'évaluation v2 séparée, nouvelle période terminale, benchmark v2 ;
- UI ML ou support `signal_profile_id` dans le formulaire backtest.

Le chemin de préparation du source v2 est implémenté, mais le v2 reste **partiellement
implémenté**, pas un pipeline expérimental achevé. Ne pas modifier
les policies v1 ni réutiliser le test terminal v1.

## Exports

- scanner : CSV ; bougies : CSV ;
- backtest : summary JSON, observations CSV, trades/equity CSV ;
- expériences : JSON/CSV ;
- ML dataset : JSONL canonique + manifest JSON + SHA-256 ;
- ML benchmark : JSON canonique immuable.

L'export benchmark refuse un contenu divergent sous le même nom. L'export dataset remplace
atomiquement le fichier cible ; utiliser un nouveau nom/version pour chaque dataset.

## Frontend

Routes : scanner, marché, backtests, expériences. Stores : scanner job/socket, marché
historique/live, backtest jobs/observations/portfolio. Le backtest affiche observations,
confluence, signaux, résumé portfolio, equity et trades. Il n'existe pas d'interface ML.

Écart de contrat connu : le type/formulaire backtest frontend n'expose pas
`signal_profile_id`. Les API Zod backtest utilisent `passthrough`, donc le champ backend peut
traverser en lecture sans être correctement typé ni créable depuis l'UI.

## Commandes de développement et qualité

Depuis `backend/` :

```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --reload
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m compileall -q app tests
.\venv\Scripts\python.exe -m black --check app tests scripts main.py indicators.py
.\venv\Scripts\python.exe -m flake8 app tests scripts main.py indicators.py
.\venv\Scripts\python.exe -m mypy app
```

Depuis `frontend/` :

```powershell
pnpm install --frozen-lockfile
pnpm run dev
pnpm run typecheck
pnpm run lint
pnpm run test
pnpm run build
```

ML :

```powershell
python -m app.ml.cli.export_ml_dataset <job_id> --feature-schema-version causal-features-v1
python -m app.ml.cli.export_ml_benchmark <manifest> ...
python -m app.ml.cli.prepare_ml_v2_source BTC/USDC --timeframe 1h --start <ISO> --end <ISO> --dry-run --json
```

Pour v2, préparer d'abord le source avec la commande dédiée, puis exporter le job retourné avec
`--feature-schema-version causal-features-v2`. Voir
[`backend/docs/ml/ml-pipeline-v2.md`](../backend/docs/ml/ml-pipeline-v2.md).

## Résultats de validation du 5 août 2026 après Phase 0

- Backend : 1074 passés, 0 échec, 1 ignoré, 27 subtests passés, 2 warnings.
- Frontend : 311 passés, 0 échec dans 48 fichiers.
- Total : 1385 passés, 0 échec, 1 ignoré, plus 27 subtests.
- compileall : succès.
- mypy : succès, 114 fichiers.
- Flake8 : succès.
- Black : succès sur 195 fichiers avec `--no-cache --workers 1`; le cache local faisait expirer
  les invocations précédentes.
- TypeScript : succès.
- ESLint : succès, zéro warning.
- Build Vite : succès, 2066 modules.
- Installation pnpm propre : succès avec lockfile figé, 335 paquets, sans réutiliser le
  `node_modules` principal ; typecheck, build et 311 tests réussis dans la copie temporaire.

## Résultats de validation du 5 août 2026 après Phase 1

- Backend : 1090 passés, 0 échec, 1 ignoré, 27 subtests, 2 warnings pandas historiques.
- Tests finaux ciblés source/CLI/migrations : 25 passés.
- compileall : succès ; Black : 199 fichiers ; Flake8 : succès ; mypy : 116 fichiers.
- Frontend inchangé : 311 tests dans 48 fichiers ; TypeScript, ESLint et build Vite réussis.
- Preuve manuelle temporaire : `created`, puis `reused`, puis `would-reuse` en dry-run ; un seul
  job et hash SQLite inchangé pendant le dry-run.
- Deux exports de 10 lignes ont les mêmes octets et le même SHA-256 :
  `sha256:665ee28a59826c17d74118cdd80f34083c8ac3b0c5c0bbe8f2998c11c90c26a4` ;
  les deux sont acceptés par `MLDatasetLoader`.
- La base et les exports de preuve étaient temporaires et ont été supprimés après contrôle.

## Résultats de validation du 5 août 2026 après Phase 2

- Backend : 1118 passés, 0 échec, 1 ignoré, 27 subtests et les 2 warnings pandas historiques.
- Frontend inchangé : 311 tests dans 48 fichiers ; TypeScript, ESLint et build Vite (2066
  modules) réussis.
- compileall, Black (204 fichiers), Flake8, mypy (120 fichiers) et `git diff --check` réussis.
- Preuve SQLite temporaire : `created`, `reused`, ancien manifeste `stale`, nouveau manifeste
  `reproducible`, mutation hors périmètre `reused`, concurrence `created + reused`, ancien job
  conservé et un seul nouveau job par mutation.
- Fingerprints agrégés de la preuve : ancien
  `sha256:edd7424e0c2ba13229597e6f5f231afe3fd44e953cbd0eedd142738f282a9838`, nouveau
  `sha256:8477a62307b9e0d98b691f012dbe75496a3ed82b5f392b891e325caa3decaf75`.
- Deux exports inchangés étaient byte-identiques. La base et les artefacts étaient dans un
  répertoire temporaire automatiquement supprimé ; la base locale réelle n'a pas été modifiée.

## Problèmes connus

1. Pas d'artefact v2 persistant publié ni de modèle/benchmark v2.
2. Aucun dataset, entraînement ou benchmark ML v2 réel n'a encore été lancé ; la Phase 2 fournit
   seulement la provenance forte et sa vérification locale.
3. Deux warnings pandas de perte de nanosecondes dans `market_data.py`.
4. Contrats Python/TS/Zod partiellement dupliqués ; marché sans modèle Pydantic public.

Corrections Phase 0 : fixture v2 canonique, test frontend aligné sur les 11 indicateurs
implémentés, style Python vert et helper Shadcn versionnable. Aucun contrat métier n'a été relâché.

## Dette et risques

Préserver : causalité confirmed, fit train-only, purge temporelle, séparation outcome/trade,
policies et test terminal v1 figés, omission publique de `inline`, séparation des fingerprints,
compatibilité des anciens payloads et neutralité des extensions d'indicateurs.

Ne pas conclure qu'un ajout existe parce qu'une roadmap ou un test l'attend. Vérifier domaine,
builder, service, contrat frontend et flux réel.

## Où modifier quoi

- Routes/lifespan : `backend/app/main.py`, `backend/app/api/`.
- Config scanner/indicateurs : `backend/app/core/settings.py`.
- Calcul/signaux/événements : `backend/app/domain/indicators/`, `indicator_bundle.py`.
- Décision canonique : `backend/app/domain/backtesting.py`, `signal_evaluation.py`.
- Backtest : `models/backtest.py`, `services/backtest_engine.py`, `backtest_manager.py`,
  `repositories/backtest_repository.py`.
- Portefeuille : `domain/portfolio/`, `services/portfolio_replay.py`, repository/modèles portfolio.
- SQLite : `database/schema.py` puis ajouter une migration, jamais éditer une table existante en
  place sans compatibilité.
- Profil/source ML v2 : `ml/domain/ml_dataset_profile.py`, `ml/services/ml_v2_source.py`,
  `ml/cli/prepare_ml_v2_source.py`, `ml/services/ml_dataset_builder.py`.
- Contrat/features/labels ML : `ml/models/ml_dataset.py`, `ml/domain/ml_dataset.py`.
- Export/load ML : `ml/services/ml_dataset_{exporter,loader}.py` et CLI.
- Évaluation : preprocessing, feature policy, temporal split, walk-forward/final/benchmark.
- Frontend contrats/API : `src/types`, `src/api`, schémas Zod.
- Graphique/marqueurs : `src/components/dashboard/trading-chart.tsx`,
  `src/features/market/market-history.ts`, `src/stores/market-store.ts`.
- UI backtest : `src/pages/backtests-page.tsx`, `src/features/backtests`, backtest store/API.

## Comment poursuivre le pipeline ML v2

1. Phases 0 et 1 terminées : conserver la baseline et le service source canonique.
2. Phase 2 terminée dans le worktree : fingerprint `ohlcv-content-sha256-v1`, agrégat
   `ohlcv-input-aggregate-sha256-v1`, migration 10, manifeste de schéma 2 et CLI
   `app.ml.cli.verify_ml_v2_source`.
3. Générer ensuite un artefact v2 réel sur une fenêtre suffisamment longue et l'auditer.
4. Auditer features, données manquantes, distributions, régimes et causalité avant l'entraînement.
5. Définir une policy v2 séparée ; ne pas modifier `ML_FEATURE_POLICIES_V1`.
6. Réserver avant sélection une nouvelle période terminale postérieure au test consommé v1.
7. Figer candidats/critères, sélectionner seulement sur développement, ouvrir le test une fois et
   exporter un benchmark v2 immuable avec décision acceptée/rejetée.

## Ce qui n'a pas été vérifié

Réseau Binance/CCXT et sockets réelles, rendu navigateur manuel, reconstruction intégrale du
benchmark v1, source/export v2 persistant sur la base locale réelle, performance économique/ML
indépendante, secrets `.env` et état d'un environnement externe à cette copie locale. La Phase 1
a vérifié le parcours source/export v2 sur SQLite temporaire et Black sur les 199 fichiers.
