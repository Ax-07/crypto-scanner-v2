# Audit courant de `scanner_binance_v2`

Date de l'audit : 5 août 2026 (Europe/Paris).

## 1. Conclusion exécutive

Le dépôt contient une application FastAPI/React fonctionnelle pour scanner des marchés,
visualiser l'historique et le temps réel, rejouer des signaux, simuler facultativement un
portefeuille et construire des datasets ML causaux. Le pipeline backtest est relié de bout en
bout et persiste observations, outcomes, analyses et résultats de portefeuille. Le pipeline ML
v1 est implémenté, exporté et évalué ; son infrastructure est exploitable mais son premier modèle
est explicitement rejeté. Le pipeline ML v2 a davantage avancé que l'ancienne documentation :
le profil canonique `ml-dataset-v2`, le schéma `causal-features-v2`, les composants continus et
les contrôles de provenance existent. La Phase 1 ajoute désormais la commande et le service
reproductibles permettant de préparer ce source. Aucun job source v2 n'a été ajouté à la base
locale réelle et aucun artefact dataset/benchmark v2 n'a été publié.

Lors de l'audit initial, une régression backend et une régression frontend faisaient échouer les
suites complètes et Flake8/Black signalaient des défauts de style. La Phase 0 datée du 5 août
2026, documentée ci-dessous, a corrigé ces défauts sans modifier de contrat ou comportement
métier. La baseline courante est verte et sa reproductibilité frontend a été validée dans une
copie temporaire propre.

Conventions du rapport : **Fait** signifie vérifié dans le code, la base, un artefact ou par une
commande ; **Déduction** signifie conséquence raisonnable de plusieurs faits ; **Hypothèse**
signifie non confirmée faute d'exécution réelle ; **Recommandation** n'est pas un état existant.

## 2. Métadonnées Git et protection du travail local

| Élément                                     | Valeur vérifiée                                                                                                         |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Branche                                     | `main`                                                                                                                  |
| Commit                                      | `5d137a57462a53ee984052e9ae003352498279fa`                                                                              |
| Sujet HEAD                                  | `Add continuous normalized components for various indicators and improve tests`                                         |
| Amont                                       | `origin/main`, avance 0, retard 0                                                                                       |
| État initial des fichiers suivis/non suivis | propre                                                                                                                  |
| État ignoré observé                         | virtualenv/caches, `backend/data`, logs, `frontend/.env`, `node_modules`, `dist`, `src/lib`, `*.tsbuildinfo`, `.vscode` |

Git refusait initialement le dépôt comme propriété douteuse Windows. Toutes les lectures Git ont
utilisé `git -c safe.directory=C:/Users/xavie/OneDrive/Bureau/scanner_binance_v2 ...` ; aucune
configuration globale n'a été modifiée. Aucun commit, push, reset, suppression ou écrasement de
travail local n'a été effectué.

## 3. Périmètre et méthode

L'inventaire porte sur 444 fichiers suivis : 207 sous `backend`, 158 sous `frontend`, 76 sous
`docs` et 3 fichiers racine. Ont été inspectés : arborescence suivie et ignorée, historique Git,
configurations Python/Node, points d'entrée, routes, modèles, services, repositories, domaine,
schéma/migrations SQLite, tests, CLI, artefacts ML, documentation backend/frontend/audits et base
locale. Les environnements installés n'ont été examinés que pour leurs versions et pour exécuter
les commandes.

Les documents prioritaires ont été lus intégralement :

- `docs/CURRENT_APP_STATE_FOR_AI.md` (ancien document de 85 702 octets) ;
- `backend/docs/ml/ml-pipeline-v1.md` (37 922 octets).

Les autres Markdown ont été inventoriés et recherchés transversalement pour les contrats ML,
datasets, backtests, signaux, profils, observations, labels, fingerprints, exports, audits et
historique. Les fichiers structurants réellement ouverts ou recherchés sont listés en section 23.

## 4. Commandes exécutées et résultats

### 4.1 Environnement

- Python système et virtualenv : 3.11.5.
- pytest 9.1.1 ; Black 26.5.1 ; Flake8 7.3.0 ; mypy 2.3.0.
- Node 24.12.0 ; pnpm 10.15.1, conforme à `packageManager`.

### 4.2 Backend

| Commande depuis `backend/`                                                           | Résultat                                                                     |
| ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| `.\venv\Scripts\python.exe -m pytest -q`                                             | échec : **1 failed, 1073 passed, 1 skipped**, 27 subtests passed, 2 warnings |
| `.\venv\Scripts\python.exe -m compileall -q app tests`                               | succès                                                                       |
| `.\venv\Scripts\python.exe -m black --check app tests scripts main.py indicators.py` | expiration à 300 s ; au moins 5 fichiers à reformater                        |
| `.\venv\Scripts\python.exe -m black --check app`                                     | expiration à 180 s ; 3 fichiers applicatifs à reformater                     |
| `.\venv\Scripts\python.exe -m flake8 app tests scripts main.py indicators.py`        | échec : 1 erreur `W292`                                                      |
| `.\venv\Scripts\python.exe -m mypy app`                                              | succès : 114 fichiers, aucune erreur                                         |

Échec Pytest exact :
`tests/ml/services/test_ml_dataset_loader.py::test_loader_accepts_v2_export`. La fixture produit
des lignes v2 avec `profile_id="inline"`, puis `MLDatasetExporter._validate_v2_provenance`
exige `ml-dataset-v2`. Le garde-fou de production est cohérent avec les autres tests v2 ; le test
d'acceptation/sa fixture n'a pas été aligné.

Black a nommé `app/api/candles.py`, `app/ml/domain/ml_preprocessing.py`,
`app/services/market_stream.py`, `tests/test_indicator_bundle.py` et
`tests/test_structured_signal_filters_v1_contract.py`. Flake8 confirme
`tests/test_indicator_bundle.py:185:71: W292 no newline at end of file`. Les deux expirations de
Black sont aussi une limite de vérification : la liste exhaustive des fichiers à reformater n'a
pas été obtenue.

Les deux warnings Pytest viennent de `app/services/market_data.py:96`, où pandas avertit que
`to_pydatetime()` abandonne des nanosecondes.

### 4.3 Frontend

| Commande depuis `frontend/`                | Résultat                                                                          |
| ------------------------------------------ | --------------------------------------------------------------------------------- |
| `pnpm install --frozen-lockfile --offline` | non réalisée : pnpm demandait interactivement de supprimer/recréer `node_modules` |
| `pnpm run typecheck`                       | succès                                                                            |
| `pnpm run lint`                            | succès, zéro warning                                                              |
| `pnpm run test`                            | échec : **1 failed, 310 passed** dans 48 fichiers                                 |
| `pnpm run build`                           | succès : 2066 modules transformés                                                 |

Échec Vitest exact :
`src/components/indicator-signals/indicator-signal-formatters.test.ts` attend dans
`INDICATOR_ORDER` `relative_volume`, `cmf` et `obv`, absents de l'implémentation. Le test et le
code ne représentent donc pas le même périmètre d'indicateurs. Aucune dépendance n'a été
installée ou mise à jour ; les validations ont utilisé `node_modules` déjà présent.

Total des suites exécutées : **1 383 tests passés, 2 échoués, 1 ignoré**, plus 27 subtests backend
passés.

### 4.4 Phase 0 — restauration de la baseline, 5 août 2026

Les résultats des sections 4.2 et 4.3 décrivent l'audit initial. Après correction :

| Contrôle | Résultat final |
|---|---|
| Pytest complet | **1074 passed, 1 skipped**, 27 subtests, 2 warnings pandas |
| Test ML v2 ciblé | 1 passed |
| Tests loader/exporter/builder/profil ML | 63 passed |
| compileall `app tests` | succès |
| Black complet | succès, 195 fichiers inchangés, 10,2 s avec `--no-cache --workers 1` |
| Flake8 | succès |
| mypy | succès, 114 fichiers |
| Vitest ciblé | 15 passed |
| Vitest complet | **311 passed** dans 48 fichiers |
| TypeScript | succès |
| ESLint | succès, zéro warning |
| Build Vite | succès, 2066 modules |

Causes et corrections :

- `.gitignore` utilisait le motif générique `lib/`, qui ignorait par accident
  `frontend/src/lib/utils.ts`. Deux négations ciblées rendent ce helper Shadcn versionnable sans
  réintroduire dépendances, builds, caches ou données locales. Les 27 imports `@/lib/utils`
  utilisent le fichier réel existant.
- La fixture loader v2 gardait les valeurs historiques `profile_id="inline"` et
  `sha256:profile`. Le seul cas d'acceptation v2 fournit désormais `ml-dataset-v2` et un SHA-256
  valide, puis vérifie profil et fingerprint dans le manifeste et les lignes chargées. Les tests
  existants continuent de refuser `inline`, fingerprints invalides ou mixtes ; v1 est inchangé.
- Le test frontend anticipait Relative Volume, CMF et OBV alors que l'implémentation canonique
  s'arrête à Keltner. Les six attentes prématurées ont été retirées ; le test continue de figer
  exactement l'ordre et les labels des 11 indicateurs réellement supportés.
- Black a appliqué uniquement des changements de présentation aux cinq fichiers signalés et a
  ajouté le saut de ligne final manquant. Le blocage provenait du cache Black local : le contrôle
  sans cache et avec un worker couvre les 195 fichiers en 10,2 secondes.

Preuve propre : une archive `git archive HEAD` a été extraite dans `%TEMP%`, puis les changements
Phase 0 versionnables ont été superposés explicitement. `frontend/src/lib/utils.ts` y était présent
(SHA-256 `7C8C3DFC0CDD370D44932828EB067EF771C8FE7996693221D5D4B90AF6D54F2D`). Une installation
`pnpm install --frozen-lockfile` distincte a installé 335 paquets sans modifier le lockfile, puis
typecheck, build et 311 tests ont réussi. La copie temporaire a été supprimée. La première tentative
`--offline` avait échoué uniquement parce que le tarball `@hookform/resolvers@5.4.0` manquait du
store ; la relance autorisée a finalement réutilisé les 335 paquets et n'en a téléchargé aucun.

Fichiers Phase 0 : `.gitignore`, `frontend/src/lib/utils.ts`, le test formatter frontend, la
fixture loader ML, les cinq fichiers formatés, et les deux documents d'état. Aucun lockfile,
algorithme, modèle de production, migration ou contrat public n'a changé.

Pendant la mission, un commit externe a fait passer `HEAD` de `5d137a5` à `763ffa8` (`Add current
project audit for scanner_binance_v2`) et a publié les documents d'audit précédemment indexés.
L'agent n'a exécuté ni commit ni push ; les changements Phase 0 restent non commités.

## 5. Architecture actuelle

Le backend est une application FastAPI créée par `app.main.create_app`, exportée par
`backend/main.py`. Le lifespan initialise `Database`, repositories et managers, applique les
migrations, marque les jobs abandonnés et ferme les ressources. Le domaine technique est séparé
des adaptateurs FastAPI/CCXT/SQLite. La persistance utilise SQLite et neuf migrations depuis la
Phase 1.

Le frontend est une SPA React 19/Vite 8. React Router charge les pages par feature, Zustand
conserve scanner/marché/backtests, React Hook Form et Zod valident les formulaires, Shadcn/Radix
fournissent les primitives, et `lightweight-charts` affiche le marché et l'equity.

## 6. Backend : routes et flux

### REST et WebSocket

- santé : `/health`, `/api/health` ;
- scanner : config, marchés, création/lecture/résultats/export/annulation sous `/api/scanner`,
  plus `/api/scanner/ws/{job_id}` ;
- bougies : état, export, fenêtre et pagination sous `/api/market/candles` ;
- historique : couverture et runs sous `/api/market/history` ;
- backtests : création/liste/capacités/reprise/annulation, summary, observations, outcomes,
  correlations, segments, funnel, divergences, ablations et exports sous `/api/backtests`, plus
  `/api/backtests/{job_id}/ws` ;
- portefeuille : metadata, trades/equity paginés et CSV sous le même préfixe ;
- expérimentations/profils/shadow : `/api/experiments`, `/api/signal-profiles`, `/api/shadow` ;
- marché live : `/ws?symbol=...&timeframe=...&include_history=...&profile=...` ;
- fallback SPA : `/` et `/{frontend_path:path}` lorsque le build existe.

Preuves : décorateurs dans `app/api/{scanner,candles,history,backtests,experiments}.py`, inclusion
dans `app/main.py`, socket marché dans `app/services/market_stream.py:websocket_market_data`.

### Scanner et données OHLCV

`ScannerService` charge les marchés via CCXT, récupère les OHLCV, retire la bougie ouverte avec
`market_data.get_closed_candles`, calcule indicateurs/signaux/filtres/confluence et renvoie des
`ScanResult`. `ScanManager` gère les tâches et snapshots. `CandleSyncService`,
`CandleBackfillService`, `MarketHistoryService` et les CLI `backfill_candles`, `sync_candles`,
`repair_history_metadata`, `backup_database` couvrent l'historique local.

La base locale ignorée `backend/data/scanner_crypto.sqlite3` a passé `PRAGMA integrity_check`,
est en schéma 8 et contient 143 325 bougies, 283 symboles et 8 timeframes. Ses bornes brutes sont
1544400000000 à 1785790800000 ms. Elle contient 853 bornes d'historique, aucun gap déclaré et
aucun run de backfill. Ces nombres décrivent seulement cette copie locale au 5 août.

### Indicateurs et signaux

Les indicateurs historiques RSI, SMA/EMA, MACD, Bollinger et Stochastique coexistent avec ATR/
NATR, ADX/DMI, Supertrend, Donchian et Keltner optionnels. `indicator_bundle` centralise calculs,
signaux et événements. `evaluate_information_set` dans `domain/backtesting.py` constitue la
décision canonique du replay ; `evaluate_signal_snapshot` est sa façade. Les extensions ajoutent
des `components` normalisés sans participer par défaut aux filtres, à `accepted` ou à la
confluence historique. Les structured filters v1 ne ciblent que MACD/Bollinger/Stochastique.

## 7. Frontend et cohérence des contrats

Routes : `/scanner`, `/market`, `/backtests`, `/backtests/experiments`, fallback 404, avec
redirection racine vers scanner (`src/app/router.tsx`). Trois stores Zustand gèrent les jobs et
la socket scanner, l'historique/live marché, et les jobs/observations/portefeuille backtest.

Le graphique fusionne les bougies, indicateurs et marqueurs par temps. Les marqueurs sont
normalisés, dédupliqués puis empilés ; `minimumSimultaneousMarkers` (1 à 5) filtre l'affichage des
groupes simultanés. La visibilité est contrôlée par familles, dont le double verrou signaux +
volatilité pour ATR. Les formulaires scanner, navigation historique et backtest utilisent RHF.

Les frontières scanner, marché et backtest utilisent Zod pour leurs parties critiques. Il reste
des `passthrough()` et des casts : le frontend ne valide donc pas exhaustivement tous les champs
du backend. Écart confirmé : `BacktestConfig.signal_profile_id` existe côté Python mais pas dans
le type `frontend/src/types/backtest.ts`, le schéma Zod du formulaire ni l'UI. Une création v2
canonique n'est donc pas disponible dans l'interface. Il n'existe pas de page ML dédiée ; la page
Expériences concerne les profils/évaluations historiques, pas l'export ML v1/v2.

## 8. Pipeline backtest réel, étape par étape

1. **Création** — `POST /api/backtests` valide `BacktestConfig` et
   `BacktestManager.create_job` crée un UUID aléatoire, persiste le job et démarre une tâche.
2. **Profil** — aucun resolver de registre n'est appelé. `signal_config` est fourni inline ;
   `signal_profile_id` est un identifiant/provenance transmis séparément. Les profils
   d'expériences stockés ne sont pas automatiquement résolus ici.
3. **OHLCV** — `BacktestEngine._load_primary/_load_trends` lit uniquement SQLite par
   `SQLiteHistoricalRepository`; warmup, fenêtre de décision et futur nécessaire aux outcomes
   sont chargés. Les bougies sont `closed_only=True`.
4. **Signaux** — pour chaque index, le moteur tronque les fenêtres à l'information disponible et
   appelle `evaluate_signal_snapshot(... profile=signal_config,
profile_id=config.signal_profile_id)`.
5. **Entrées/sorties indépendantes** — `calculate_forward_outcomes` applique horizon,
   `signal_close`/`next_open`, frais, slippage, censure et gap policy. Ce ne sont pas des trades.
6. **Persistance** — `BacktestRepository.add_observation/add_outcomes` fait des upserts SQLite ;
   checkpoints permettent une reprise idempotente sous la même version d'algorithme.
7. **Analyses** — `build_analytics` produit summary, correlations, segments, funnel, divergences,
   cooccurrences et ablations, persistés dans job/artifacts.
8. **Portefeuille optionnel** — seulement avec `portfolio_simulation`, un symbole et
   `every_bar`. `build_portfolio_simulation_steps` transforme observations + bougies,
   `simulate_portfolio` gère long-only/cash/ordres/exécutions/trades/equity, puis
   `PortfolioRepository.replace_simulation_result` persiste atomiquement les cinq tables.
9. **Exports** — JSON summary, CSV observations, trades et equity, plus liens exposés par API.

Limites : mode provisional explicitement refusé car les révisions intrabar ne sont pas stockées ;
le job ID n'est pas déterministe ; le moteur ne résout pas `signal_profile_id` vers une config ;
le portefeuille v1 est mono-symbole, long-only, sans levier/short/SL/TP.

## 9. Profils et fingerprints

### `signal_profile_id`

**Fait vérifié.** `BacktestConfig.signal_profile_id: str = "inline"` existe, est trimé et refuse
la chaîne vide. `BacktestEngine.run` le transmet à `evaluate_signal_snapshot`; l'observation le
stocke dans `profile_id`. `BacktestJob.public_payload` omet uniquement la valeur historique
`inline` et expose les identifiants explicites. Le repository persiste le config JSON et le
payload complet de l'observation. Preuves : `models/backtest.py`, `services/backtest_engine.py`,
`domain/backtesting.py`, tests `test_replay_propagates_profile_id_and_keeps_profile_fingerprint_separate`
et `test_signal_profile_id_is_normalized_and_exposed_only_when_explicit`.

### Séparation des fingerprints

**Fait vérifié.** `profile_fingerprint` est le SHA-256 du `ScanConfig` canonique calculé dans
`evaluate_information_set`; il identifie le calcul technique et est identique avec/sans
portefeuille. `config_fingerprint` est construit par `backtest_config_fingerprint` seulement si
le bloc portefeuille existe, stocké dans checkpoint/run portefeuille et omis du payload legacy.
Le test du moteur compare explicitement les deux scénarios. Ils ne sont pas confondus.

**Limite importante.** `dataset_version` du backtest est le SHA-256 de
`symbol:first_open_time:last_open_time:nombre_de_bougies`. Il ne hache pas les valeurs OHLCV,
l'exchange, le market type ou le timeframe. Il constitue un marqueur de fenêtre, pas une preuve
forte d'identité du contenu historique.

### Persistance publique du profil

Les profils explicites sont présents dans config/job, observations (`profile_id`,
`profile_fingerprint`, `signal_profile`) et manifests ML (`profile_ids`,
`profile_fingerprints`). Le profil inline est omis seulement du config public du job ; il reste
explicitement `profile_id="inline"` dans les observations et artefacts ML v1. Cette nuance est
compatible avec l'historique mais doit être documentée.

## 10. Pipeline ML v1

Le flux réel est relié : `BacktestRepository.ml_source_rows` joint observations confirmed et
outcome h6 ; `MLDatasetBuilder` filtre censures/invalides/NATR manquant et construit
`MLDatasetRow`; `MLDatasetExporter` écrit JSONL canonique + manifeste + SHA-256 ;
`MLDatasetLoader` revérifie hash, ordre, unicité et métadonnées ; prétraitement, split
chronologique, purge, walk-forward, baseline logistique/dummy et évaluation finale alimentent
`MLBenchmarkBuilder/Exporter`.

Contrats : dataset/manifeste v1, features `causal-features-v1`, label
`direction-natr-h6-v1`, horizon fixé à 6. Le label vaut UP/DOWN au-delà de
`NATR/100 * multiplier`, sinon NEUTRAL. Le dictionnaire `features` interdit les noms futurs et
les nombres non finis. Les préprocesseurs sont ajustés sur train ; les splits purgent toute cible
dont `exit_time` chevauche la partition suivante.

Artefacts suivis vérifiés : dataset BTC/USDC 1h de 713 lignes, SHA-256
`a94660d07503b9494ac646ad948d0738d7b6a6941b1893c40a3a671484e4b2a4` ; second export vide
au hash SHA-256 de fichier vide ; deux benchmarks byte-identiques au SHA-256
`dab10c9e3de2e160fd25b8259dc37e444190f8dc4d925d33bea87b0407f109dc`. Le benchmark marque
le modèle rejeté et le test terminal consommé. Aucun modèle de production ni endpoint
d'inférence n'existe.

## 11. Pipeline ML v2

### Phase 1 — source canonique

- `build_ml_v2_source_config` impose le profil officiel, confirmed/every-bar, horizon 6,
  signal-close, gap strict et absence de portefeuille ;
- `MLV2SourceService` sépare construction, recherche, politique d'état, couverture et manager ;
- `python -m app.ml.cli.prepare_ml_v2_source` fournit sorties humaine/JSON, `--dry-run` sans
  écriture et `--wait` pour un runner externe ;
- l'identité `ml-v2-source-identity-v1` hash le config complet canonique et la version moteur ;
- la migration 9 ajoute `ml_v2_source_claims` ; `BEGIN IMMEDIATE` et la clé unique arbitrent les
  créations concurrentes sans verrou global ;
- un job completed n'est réutilisé qu'après validation réelle par le builder v2 ; pending/running
  n'est pas dupliqué ; interrupted est repris avec checkpoint compatible ; failed/cancelled ou
  incomplet est remplacé sans suppression historique ;
- la couverture contrôle warmup principal et MA, fenêtre, futur h6, bougies closes et gaps, sans
  réseau ni backfill automatique ;
- un test SQLite déterministe exécute le vrai moteur, vérifie observations/outcomes, construit et
  charge `causal-features-v2`, réutilise le job et compare deux exports identiques.

Le profil accepte désormais explicitement exchange et type de marché ; le builder les reprend
pour comparer le profil officiel sans rendre les paramètres techniques configurables.

### Limites conservées

- aucun job n'a été créé dans `backend/data/scanner_crypto.sqlite3` pendant la Phase 1 ;
- aucun JSONL/manifeste/benchmark v2 n'est publié dans le dépôt ;
- `dataset_version` reste un fingerprint faible de fenêtre, pas un hash des octets OHLCV ;
- aucune période terminale, politique d'entraînement ou décision de modèle v2 n'est définie ;
- le frontend reste inchangé et n'expose pas le profil système.

La documentation opératoire complète est
[`backend/docs/ml/ml-pipeline-v2.md`](../../backend/docs/ml/ml-pipeline-v2.md).

## 12. Exports

Le scanner et les bougies exposent CSV ; le backtest expose summary JSON, observations CSV,
trades CSV et equity CSV ; les expérimentations ont JSON/CSV ; ML écrit JSONL + manifeste et
benchmark JSON canonique. Les exports portfolio sont versionnés. Le benchmark ML refuse
l'écrasement divergent et réutilise un contenu identique ; l'export dataset remplace ses chemins
cibles après écriture temporaire atomique, donc son nom n'est pas immuable à lui seul.

## 13. État de la persistance locale

Schéma 8, 22 tables applicatives. Comptes notables : 8 jobs backtest terminés, 4 711
observations, 22 619 outcomes, 42 artifacts, 7 checkpoints, 1 run portefeuille et 145 points
equity ; 2 expérimentations et 2 profils. Aucun ordre, exécution ou trade portefeuille n'est
présent dans cette copie. Ces données sont ignorées par Git et ne garantissent pas l'état d'un
autre environnement.

## 14. Comparaison documentation/code

| Document/groupe                      | Classement                                                | Écart principal                                                                                                                                                                                          |
| ------------------------------------ | --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ancien `CURRENT_APP_STATE_FOR_AI.md` | obsolète et partiellement contradictoire                  | mauvais commit, anciens comptes de tests, annonce encore des phases futures terminées, six indicateurs alors que les contrats sont enrichis, ignore les contrats/profils v2 et les régressions actuelles |
| `backend/docs/ml/ml-pipeline-v1.md`  | à jour pour le benchmark v1, partiellement à jour pour v2 | décrit fidèlement l'artefact v1, mais son inventaire code omet `ml_dataset_profile.py` et présente certains travaux v2 comme futurs alors que profil/schéma/garde-fous existent                          |
| docs backtest/portefeuille           | globalement à jour                                        | architecture et compatibilité v1 conformes ; pas de procédure source ML v2                                                                                                                               |
| docs indicateurs/marqueurs           | partiellement à jour                                      | phases 8.2/8.3 conformes ; roadmap volume entre en conflit avec le test frontend qui attend déjà trois indicateurs non implémentés                                                                       |
| docs frontend                        | partiellement à jour                                      | architecture valide ; anciens chiffres de tests et absence de `signal_profile_id`/ML v2 non signalée                                                                                                     |
| audits historiques                   | preuves historiques, pas état courant                     | utiles pour décisions passées, ne doivent pas servir de validation actuelle                                                                                                                              |

Fonctionnalités présentes mais insuffisamment documentées : schéma v2, profil canonique v2,
garde-fous de provenance v2 et distinction exacte `profile_fingerprint/config_fingerprint`.
Fonctionnalité documentée comme prochaine : politique/profil dataset v2 ; le profil et le schéma
sont désormais présents, mais pas le dataset ou l'expérience.

## 15. Problèmes confirmés et statut après Phase 0

1. Fixture loader v2 incompatible avec les nouveaux garde-fous : **corrigée**.
2. Test frontend anticipant trois indicateurs volume non implémentés : **corrigé**.
3. Flake8 `W292` et Black non conforme : **corrigés ; contrôles verts**.
4. Aucun chemin de création canonique du backtest source ML v2.
5. Aucun job/dataset/benchmark v2 réel dans la copie auditée.
6. `dataset_version` n'est pas un fingerprint du contenu OHLCV.
7. Le frontend ne transporte pas `signal_profile_id` et ne peut créer le source v2.
8. Le fichier d'état IA antérieur mélangeait historique et état courant et était nettement
   obsolète.
9. Reproductibilité frontend cassée par `lib/` : **corrigée et vérifiée dans une copie propre**.

## 16. Dette technique et risques de régression

- Contrats publics partiellement dupliqués Python/TypeScript/Zod sans génération automatique.
- Le helper frontend requis est désormais versionnable ; veiller à conserver les négations
  ciblées de `.gitignore`.
- Payload marché dictionnaire sans modèle Pydantic dédié.
- Defaults des dépendances Python bornés par minima, sauf deux paquets ML figés.
- Backtests/profils d'expériences sont deux mécanismes voisins non résolus automatiquement.
- Manifeste dataset insuffisant pour reconstruire seul le source.
- Export dataset écrasable sous le même nom.
- Tests et implémentation peuvent diverger quand un catalogue d'indicateurs est préparé avant le
  calcul effectif.
- Risques causaux : réintroduire une bougie ouverte/future, ajuster prétraitement sur validation,
  réutiliser le test terminal v1, mélanger outcome/trade, ou modifier les politiques v1 en ajoutant
  une policy v2.
- Risques de compatibilité : exposer `inline` au niveau job, rendre les champs additifs obligatoires,
  ou confondre fingerprint technique et portefeuille.

## 17. Fonctionnalités incomplètes

ML v2 de bout en bout ; création/recherche d'un source canonique ; fingerprint fort des données ;
manifest de reproduction complet ; dataset v2 réel ; split et politique v2 ; nouveau test terminal ;
benchmark v2 ; UI/commande d'orchestration. La roadmap volume (relative volume, CMF, OBV, VWAP)
reste non implémentée malgré une attente prématurée dans un test frontend.

## 18. Priorités recommandées

Priorité 0 : **terminée**. Priorité 1 : rendre la création du source ML v2 explicite,
déterministe et testée. Priorité 2 : renforcer les métadonnées
et l'identité OHLCV. Priorité 3 : produire/valider un vrai dataset v2 avant tout entraînement.
Priorité 4 : définir à l'avance le protocole expérimental v2 et une nouvelle période terminale.

## 19. Faits, déductions et hypothèses non confirmées

**Faits** : tous les résultats de commandes, contrats, routes, tables, hashes et absences décrits
ci-dessus. **Déduction** : un export v2 devrait fonctionner après création d'un job canonique et
correction de la fixture, car repository, builder et exporter sont reliés et largement testés.
**Hypothèse non confirmée** : la base locale contient assez d'historique continu pour le profil
v2 et toutes ses périodes de warmup. Aucun backtest v2 réel n'a été lancé pour le prouver.
**Hypothèse non confirmée** : les deux manifests/benchmarks v1 se reproduisent depuis une base
fraîche ; leurs hashes ont été vérifiés, pas leur reconstruction intégrale pendant cet audit.

## 20. Plan de reprise recommandé

### Phase 0 — Restaurer la baseline — terminée le 5 août 2026

Objectif : corriger la règle `lib/`/suivre `frontend/src/lib/utils.ts`, aligner les deux
fixtures/tests en échec et appliquer le formatage minimal. Fichiers probables : `.gitignore`,
`frontend/src/lib/utils.ts`, `tests/ml/services/test_ml_dataset_loader.py`, test/config frontend
des indicateurs, les fichiers signalés par Black/Flake8. Dépendance : aucune. Tests : installation
dans un clone propre, suites complètes et cinq
outils qualité. Acceptation obtenue : 0 échec, 0 warning lint/Flake8, Black terminé avec code 0 et
copie frontend propre validée. Risque résiduel :
choisir à tort d'implémenter les indicateurs volume alors que la roadmap les laisse futurs. Pas de
migration ; une clarification de contrat frontend peut être nécessaire.

### Phase 1 — Backtest source canonique ML v2 — terminée le 5 août 2026

La commande `app.ml.cli.prepare_ml_v2_source`, le service `MLV2SourceService` et la migration 9
réalisent la construction canonique, la recherche, la reprise sûre, la couverture locale et
l'arbitrage concurrent. Le profil reste fermé, le frontend et les routes sont inchangés.

Validation finale : 1090 tests backend passés, 1 ignoré, 27 subtests et les 2 warnings pandas
historiques ; 311 tests frontend ; compileall, Black (199 fichiers), Flake8, mypy (116 fichiers),
TypeScript, ESLint et build réussis. La preuve manuelle temporaire a obtenu `created`, `reused`,
`would-reuse`, un seul job, puis deux exports de 10 lignes byte-identiques au SHA-256
`665ee28a59826c17d74118cdd80f34083c8ac3b0c5c0bbe8f2998c11c90c26a4`, tous deux chargés.
La base temporaire a été supprimée ; la base locale réelle n'a pas été modifiée.

### Phase 2 — Fingerprint fort et manifeste de reproduction

Implémentée dans le worktree : le chargeur partagé calcule les hashes de chaque flux effectivement
consommé et leur agrégat ; le moteur confirme l'attendu avant de produire des résultats. La
migration 10 conserve le plan et la confirmation par job sans rétroattribuer de hash aux sources
Phase 1. Le service recrée une génération stale sans détruire l'ancienne et les claims restent
atomiques. Le manifeste de schéma 2 contient le config complet, le profil, les flux et les versions
du pipeline. `app.ml.cli.verify_ml_v2_source` vérifie une base candidate sans écriture ni réseau.
Les manifests v1 restent lisibles. La génération réelle, l'entraînement et le benchmark v2 restent
hors périmètre et appartiennent à la Phase 3.

Validation contrôlée : 1118 tests backend passés, 1 ignoré, 27 subtests, 2 warnings historiques ;
311 tests frontend ; compileall, Black, Flake8, mypy, TypeScript, ESLint, Vite et diff-check verts.
La preuve temporaire a obtenu `created → reused → stale → created`, a conservé l'ancien job,
ignoré une mutation hors plan et réduit deux appels concurrents à un seul nouveau job.

### Phase 3 — Dataset v2 réel et audit causal

Objectif : générer un dataset plus long/multi-régimes, vérifier couverture, distributions,
features, NATR et absence de fuite. Fichiers : CLI export, artefacts sous nouveau nom, documentation
ML v2 et tests d'intégration. Dépendance : Phases 1-2. Tests : double export byte-identique,
loader, audit de bornes, mutation future, profil/fingerprint uniques. Acceptation : manifest/hash
figés et rapport de qualité sans utiliser le test v1 consommé. Risque : données locales
insuffisantes ; aucune rupture de contrat attendue si versions v2 séparées.

### Phase 4 — Protocole expérimental et benchmark v2

Objectif : figer politiques/candidats/critères, réserver une période terminale ultérieure, entraîner
sur développement puis ouvrir une fois le test. Fichiers : feature policy v2 séparée, walk-forward,
benchmark models/services/CLI et doc dédiée. Dépendance : Phase 3. Tests : purge, fit train-only,
déterminisme et impossibilité de modifier v1. Acceptation : benchmark immuable et décision
explicite acceptée/rejetée. Risque majeur : fuite par réutilisation du test ; nouveau contrat de
benchmark possible, aucune migration applicative nécessaire.

## 21. Critères de preuve importants

- Profil/fingerprints : `models/backtest.py`, `domain/backtesting.py:profile_payload`,
  `services/backtest_engine.py:run`, `services/portfolio_replay.py:backtest_config_fingerprint` et
  tests moteur/API.
- Source ML : `repositories/backtest_repository.py:ml_source_rows` et test d'intégration.
- v2 : `ml/domain/ml_dataset_profile.py`, `ml/models/ml_dataset.py`,
  `ml/services/ml_dataset_builder.py`, `ml/services/ml_dataset_exporter.py` et tests v2.
- Causalité : `domain/backtesting.py`, `ml/domain/ml_dataset.py`, split/preprocessing/walk-forward
  et leurs tests.
- Portefeuille : `domain/portfolio`, `services/portfolio_replay.py`, repository portfolio et tests.
- État local : requêtes SQLite en lecture seule, integrity check et hashes SHA-256 calculés.

## 22. Éléments non vérifiés

- aucun appel réseau Binance/CCXT ni WebSocket réel ;
- aucun serveur FastAPI ou navigateur lancé pour un test manuel ;
- aucune nouvelle installation propre des dépendances frontend pendant la Phase 1 ; la preuve
  propre de Phase 0 reste valide ;
- aucune reconstruction du benchmark v1 ;
- aucun backtest/export v2 persistant sur la base locale réelle ; le parcours a été prouvé sur
  une base SQLite temporaire puis supprimé ;
- aucune performance ML/economique indépendante des artefacts existants ;
- contenus secrets de `.env`, volontairement non lus ;
- fidélité de la copie SQLite par rapport à un environnement externe.

## 23. Fichiers réellement inspectés

Inventaire complet recherché via `git ls-files`/`rg`, avec lecture ciblée des éléments suivants :

- racine/config : `README.md`, `.gitignore`, `.flake8`, `backend/{README.md,requirements.txt,
pyproject.toml,main.py,indicators.py,.env.example}`, `frontend/{package.json,pnpm-lock.yaml,
vite.config.ts,vitest.config.ts,eslint.config.js,tsconfig*.json,.env.example}` ;
- backend application : tous les fichiers sous `backend/app/api`, `core`, `database`, `domain`,
  `models`, `repositories`, `services`, `exporters`, `experiments`, `cli` et `ml`, par inventaire
  de symboles/références ; lecture intégrale ou contextuelle renforcée de `main.py`,
  `models/backtest.py`, `services/{backtest_engine,backtest_manager,portfolio_replay,market_stream}.py`,
  `repositories/backtest_repository.py`, `database/{schema,migrations,connection}.py`,
  `domain/{backtesting,signal_evaluation,indicator_bundle}.py` et tout `app/ml` ;
- tests backend : inventaire complet sous `backend/tests`, lecture ciblée de tous les tests
  backtest, portfolio et `tests/ml`, puis exécution complète ;
- scripts : tous les fichiers sous `backend/scripts` et les CLI backend/ML ;
- frontend : `src/app`, toutes les pages, `src/api`, `src/stores`, `src/types`, `src/schemas`,
  features scanner/market/backtests/experiments, composants dashboard/indicator-signals/UI et
  tests associés ; `src/lib/utils.ts` ignoré mais requis ; exécution complète ;
- documentation : les 76 fichiers suivis sous `docs` et `backend/docs` ont été inventoriés et
  recherchés ; lecture intégrale des deux documents prioritaires et lecture ciblée des docs
  backtest, portefeuille, indicateurs, marqueurs, structured filters, frontend et audits ;
- données/artefacts : schéma et comptes de `backend/data/scanner_crypto.sqlite3` en lecture seule,
  tous les manifests/datasets/benchmarks suivis sous `backend/artifacts` et leurs hashes.

Cette liste ne prétend pas que chaque ligne des 444 fichiers a été lue manuellement ; elle décrit
exactement l'inventaire exhaustif, les recherches transversales, les lectures approfondies et les
exécutions réalisées.
