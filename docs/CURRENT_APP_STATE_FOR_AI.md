# État complet de `scanner_crypto` pour contexte IA

Ce document est la source de reprise principale après l'audit des signaux structurés des
Phases 1 à 4 puis des Phases 5.1 à 5.6. Il décrit le code réellement présent,
pas une cible. Les contrats et composants frontend sont intégrés ; le scanner,
le marché temps réel et le backtest affichent désormais ces composants.

L'inventaire transversal des composants, champs historiques, filtres, exports et
conditions de dépréciation est maintenu dans
[`docs/frontend/structured-signals-migration-audit.md`](frontend/structured-signals-migration-audit.md).

## 1. Métadonnées de génération

- Audit réalisé le 29 juillet 2026, sous Windows/PowerShell, fuseau Europe/Paris.
- Périmètre inspecté : backend, frontend, tests, manifests, documentation, Git et
  artefacts locaux.
- Python validé : 3.11.5 via le virtualenv du projet.
- Node : 24.12.0 ; pnpm : 10.15.1.
- Aucun secret n'est reproduit dans ce document.
- Corrections d'audit : typage mypy de la confluence et du modèle de backtest,
  formatage Black, rejet des valeurs non finies dans les signaux de moyennes mobiles
  et Bollinger, avec deux tests de régression.

## 2. Résumé fonctionnel du projet

Application locale d'analyse technique crypto comprenant :

- un scanner CCXT asynchrone et multi-paires ;
- un dashboard de marché Binance en direct par WebSocket ;
- un stockage SQLite des bougies et des jobs ;
- un replay historique causal produisant des observations et des rendements futurs ;
- un module d'expérimentation, de profils, de shadow et de promotion.

Le produit ne passe aucun ordre. Il ne gère ni portefeuille, capital, taille de
position, equity curve, stop-loss ni chevauchement de trades. Le « backtest » est un
replay de signaux avec outcomes forward, pas un simulateur de portefeuille.

La Phase 6.1 a produit la conception
[`BACKTEST_PORTFOLIO_SIMULATION_DESIGN.md`](BACKTEST_PORTFOLIO_SIMULATION_DESIGN.md)
et l'ADR proposé
[`adr/ADR-portfolio-backtest-v1.md`](adr/ADR-portfolio-backtest-v1.md).
**Le moteur de portefeuille pur sous `backend/app/domain/portfolio/` est
désormais intégré optionnellement aux jobs et à leur résumé public.** Sa
documentation technique est
[`backend/portfolio-simulation-engine-v1.md`](backend/portfolio-simulation-engine-v1.md).
L'intégration est détaillée dans
[`backend/portfolio-replay-integration-v1.md`](backend/portfolio-replay-integration-v1.md).
Le bloc absent conserve le comportement et les payloads historiques.

## 3. État Git

- Branche déclarée : `main`.
- Commit initial de la Phase 5.3 : `7afd857` (« Ajout du fichier README.md avec la
  documentation du projet et des instructions de développement »).
- Le dépôt possède désormais un `HEAD` et l'arbre était propre avant la Phase 5.3.
- Git exige aussi `safe.directory` dans cet environnement à cause d'une différence
  de propriétaire Windows ; l'audit a utilisé `git -c safe.directory=...` sans
  modifier la configuration globale.

## 4. Arborescence principale

```text
backend/
  app/
    api/              routes scanner, candles, history, backtests, expériences
    core/             configuration, settings, logs, exceptions
    database/         connexion, schéma, migrations
    domain/           bougies, indicateurs, confluence, replay, évaluation
    exporters/        CSV scanner
    models/           contrats Pydantic publics
    repositories/     SQLite
    services/         scanner, marché, backtest, sync, shadow
  tests/              366 tests collectés/réussis après correction (+ 1 skipped)
  requirements.txt
  pyproject.toml
frontend/
  src/
    api/              fetch, WebSocket et schémas Zod
    components/       UI Shadcn et composants dashboard
    features/         scanner, marché, backtests, expériences
    stores/           Zustand
    types/            contrats TypeScript
  package.json
  pnpm-lock.yaml
docs/
  backend/
  frontend/
  BACKTESTING.md
  SIGNAL_*.md
  CURRENT_APP_STATE_FOR_AI.md
```

Artefacts locaux observés, non supprimés : `backend/venv`, `backend/data` avec une
base SQLite, `backend/logs/scanner.log`, caches Python, `frontend/node_modules`,
`frontend/dist`, fichiers `*.tsbuildinfo`, `frontend/.env` et exemples `.env`.
Le contenu de `.env` n'a pas été lu ni reproduit. Le dépôt pèse localement environ
663 Mio côté backend et 1,24 Gio côté frontend, principalement à cause des
dépendances et builds.

## 5. Stack et dépendances

Backend déclaré : Python 3.11+, FastAPI, Uvicorn, Pydantic, CCXT, pandas, NumPy,
aiosqlite, pytest/pytest-asyncio, Black, Flake8 et mypy. PyQt6, matplotlib et
openpyxl restent déclarés pour l'application desktop historique.

Frontend déclaré : React 19, TypeScript 6, Vite 8, React Router 7, Zustand 5,
React Hook Form, Zod 4, composants Radix/Shadcn, Tailwind 4,
lightweight-charts, Vitest et Testing Library.

Interpréteurs :

- `python` du terminal : Python 3.11.5 système ; FastAPI 0.140.13, pytest 9.0.3,
  pytest-asyncio 1.4.0 et Flake8 7.3.0 ; Black et mypy absents.
- `backend/venv/Scripts/python.exe` : Python 3.11.5 ; FastAPI 0.139.2,
  pytest 9.1.1, pytest-asyncio 1.4.0, Black 26.5.1, Flake8 7.3.0,
  mypy 2.3.0.
- VS Code cible explicitement `${workspaceFolder}/backend/venv/Scripts/python.exe`.

Les validations complètes doivent donc employer le virtualenv ou l'activer. Les
versions sont seulement bornées par des minima dans `requirements.txt`, pas figées.

## 6. Architecture backend

Le domaine des indicateurs est pur vis-à-vis de FastAPI et CCXT. Le builder commun
assemble les séries déjà calculées. `domain.signal_evaluation.evaluate_signal_snapshot`
est la façade canonique du replay et délègue à
`domain.backtesting.evaluate_information_set`. Depuis la Phase 5.8, le scanner
effectue un seul passage dans son adaptateur historique ; la parité avec le
moteur canonique est contrôlée par un oracle de service en tests.

Le marché live reste un adaptateur mono-timeframe distinct : il réutilise les mêmes
primitives d'indicateurs, le builder et la confluence, mais ne passe pas son snapshot
d'affichage par `evaluate_information_set`.

## 7. Architecture frontend

SPA React structurée par features. React Router gère les pages, Zustand les jobs et
le marché, RHF/Zod les formulaires, et Shadcn/Radix les primitives visuelles.
Les appels REST génériques de `apiRequest<T>` sont des casts TypeScript sans
validation runtime. Les frontières WebSocket scanner et marché utilisent Zod.

`types/indicator-signals.ts` est la source canonique frontend de
`IndicatorSignal`/`IndicatorSignals`. Les types scanner, marché et backtest exposent
le champ optionnel pendant la migration. Un schéma Zod commun valide statuts,
directions, clés connues, nombres finis et force entre 0 et 1. Les frontières REST
scanner/backtest valident ce champ sans retirer leurs champs historiques ; le schéma
marché le conserve dans les vues racine, confirmée et provisoire. Les trois stores
Zustand stockent les objets complets. La bibliothèque Phase 5.2 est montée par la
table scanner depuis la Phase 5.3 et par les panneaux confirmed/provisional du
marché depuis la Phase 5.4 et par les observations de backtest depuis la Phase 5.5.

## 8. Routes REST

Routes principales :

```text
GET  /api/health
GET  /health

GET  /api/scanner/config
GET  /api/scanner/markets
POST /api/scanner/jobs
GET  /api/scanner/jobs/{id}
GET  /api/scanner/jobs/{id}/results
GET  /api/scanner/jobs/{id}/export.csv
DELETE /api/scanner/jobs/{id}

GET  /api/candles
GET  /api/candles/status
GET  /api/candles/window
GET  /api/candles/export.csv
GET  /api/history/coverage
GET  /api/history/coverage/{symbol}
GET  /api/history/runs
GET  /api/history/runs/{run_id}

POST /api/backtests
GET  /api/backtests
GET  /api/backtests/capabilities
GET  /api/backtests/{id}
POST /api/backtests/{id}/resume
DELETE /api/backtests/{id}
GET  /api/backtests/{id}/summary[.json]
GET  /api/backtests/{id}/observations
GET  /api/backtests/{id}/outcomes
GET  /api/backtests/{id}/correlations
GET  /api/backtests/{id}/segments
GET  /api/backtests/{id}/funnel
GET  /api/backtests/{id}/divergences
GET  /api/backtests/{id}/ablations
GET  /api/backtests/{id}/exports
GET  /api/backtests/{id}/export.csv
```

Des routes complètes existent aussi pour les jobs d'expériences, candidats,
walk-forward, sensibilité, exports, profils de signal, cycle de vie, promotion,
shadow, retraite et comparaisons shadow. `/` et `/{frontend_path:path}` servent le
build React ou le fallback SPA.

## 9. WebSockets

- `/api/scanner/ws/{job_id}` : snapshots de progression de `ScanJob`.
- `/api/backtests/{job_id}/ws` : snapshots de progression de `BacktestJob`.
- `/ws?symbol=...&timeframe=...&include_history=...&profile=...` : marché
  Binance, messages `history`, `update`, `error`.

Le marché accepte la socket, charge les marchés, synchronise/charge jusqu'à
`CALCULATION_LIMIT`, envoie éventuellement `history`, puis suit `watch_ohlcv`.
L'exchange est toujours fermé. Les marqueurs sont calculés uniquement sur bougies
closes ; les indicateurs graphiques et la vue provisional utilisent aussi la bougie
ouverte.

## 10. Modèles et contrats publics

`IndicatorSignalModel` :

```python
status: Literal["available", "insufficient_data", "invalid_data", "disabled"]
direction: Literal["bullish", "bearish", "neutral"]
signal: str | None = None
state: str | None = None
strength: float = Field(ge=0.0, le=1.0)
reason: str | None = None
raw_value: float | None = None
```

`ScanResult` exige `symbol` et `timeframe`; tous les scalaires historiques sont
optionnels avec `None`, tous les dictionnaires ont une factory vide. Il expose
`indicator_signals: dict[str, IndicatorSignalModel] = {}`.

`SignalObservation` exige notamment `job_id`, `symbol`, `timeframe`,
`decision_time`, `accepted` et `close`. Il porte les classes historiques,
confluence, traces, provenance, qualité et
`indicator_signals: dict[str, IndicatorSignalModel] = {}`. `schema_version=2`,
`calculation_mode="canonical"`, `algorithm_version="signal-evaluation-v2"`.

`BacktestResult` n'existe pas. Les contrats sont `BacktestJob`,
`BacktestSummary`, `SignalObservation` et `ForwardOutcome`.
`BacktestSummary.trade_simulation_included` vaut `False` sans configuration et
`True` après une simulation réussie. Son champ optionnel
`portfolio_simulation` expose seulement version, quote asset, résumé et
indicateurs de présence des détails. `BacktestJob` conserve le résultat complet
en mémoire sans le sérialiser.

Il n'existe pas de modèle Pydantic `MarketSnapshot`; le marché retourne des
dictionnaires. Scanner et backtest ont donc une validation Pydantic/OpenAPI
explicite ; le snapshot marché repose sur le code et les tests.

Les defaults vides rendent `indicator_signals` additif et compatible avec les
anciens payloads Pydantic qui ne le fournissent pas. Les clés de dictionnaire ne
sont pas restreintes par Pydantic, même si le domaine reconnaît six indicateurs.

## 11. Configuration scanner

`ScanConfig` couvre exchange/type/quote, limites et retries, timeframe et minimum
OHLCV, RSI, activation SMA/EMA et périodes, timeframes de tendance, MACD,
Bollinger, Stochastique, score minimum, poids et filtres historiques.

Defaults techniques principaux : timeframe `4h`, RSI 14/seuil 35, SMA et EMA
20/50, MACD 12/26/9, Bollinger 20 × 2, stochastique 14/3 avec 20/80,
confluence minimale 60. Les validateurs imposent notamment périodes ordonnées et
uniques, fast < slow, seuil oversold < overbought et au moins une famille MA si
`use_ma=True`.

## 11 bis. Filtres structurés Phase 5.7

Le scanner accepte maintenant `structured_signal_filters.version=1` pour
`macd`, `bollinger` et `stochastic`, sans retirer les trois filtres legacy. La
priorité est structurée par indicateur, le fallback legacy reste local et un
groupe vide neutralise explicitement le fallback. Le formulaire produit le
nouveau contrat après conversion non destructive d'une ancienne configuration ;
les stores et résultats historiques ne sont pas transformés.

Le moteur, l'adaptateur, la matrice exacte (dont la nuance Stochastique), les
statuts et les exemples JSON sont documentés dans
[`docs/backend/structured-signal-filters.md`](backend/structured-signal-filters.md).
La stabilisation v1, la matrice exhaustive et les compteurs d'appels sont dans
[`docs/backend/structured-signal-filters-v1-stability.md`](backend/structured-signal-filters-v1-stability.md).
Le CSV, le marché et les intégrations frontend du backtest restent inchangés.

## 12. Flux d'un scan

1. Charge et filtre les symboles CCXT.
2. Pour chaque paire, récupère le timeframe primaire (`required + 1`) via cache.
3. Normalise et retire la bougie ouverte avec `get_closed_candles`.
4. L'adaptateur historique applique RSI, tendance multi-timeframes, indicateurs,
   filtres puis confluence ; il ne calcule pas un indicateur désactivé.
5. Les timeframes MA réutilisent le primaire si possible, sinon font un fetch
   cache par symbole/timeframe. Aucun fetch n'est ajouté par les signaux structurés.
6. Le builder assemble `indicator_signals` à partir des séries déjà calculées.
7. La parité accepted/rejected avec `evaluate_information_set` est vérifiée
   hors production par les tests de service.
8. Tri : confluence décroissante, sinon RSI croissant, sinon tendance
   décroissante, sinon symbole ; symbole départage toujours.
9. REST/WS expose le résultat ; CSV utilise une liste de colonnes figée.

Le second calcul complet scanner/canonique a été retiré en Phase 5.8 après
instrumentation. Chaque indicateur actif est calculé une fois par passage scanner,
sans fetch supplémentaire. Les deux assemblages restent distincts et leur
équivalence est conservée par les tests de parité.

## 13. Marché temps réel

`calculate_indicator_bundle` calcule seulement les familles activées et conserve
les séries pandas internes. `bundle_to_chart_data` élimine les points non finis.
`calculate_market_snapshot` produit les anciens champs, disponibilité, confluence
et signaux structurés. `calculate_market_snapshots` sépare :

- `confirmed` : uniquement les dernières bougies closes ;
- `provisional` : tout l'historique, bougie ouverte comprise, avec
  `is_forming=true`, s'il existe une bougie ouverte ;
- les anciens champs au niveau racine : `provisional` s'il existe, sinon
  `confirmed`.

Ainsi `snapshot.indicator_signals` au niveau racine peut utiliser la bougie ouverte,
alors que `snapshot.confirmed.indicator_signals` utilise toujours la dernière
bougie close. Les marqueurs et divergences sont toujours confirmés sur bougies
closes. Les séries graphiques de `history`/`update` incluent la bougie ouverte.

SMA et EMA sont construits et exposés dans chaque vue `indicator_signals`. Ils sont
retirés de la copie passée à `calculate_confluence_score` : le marché conserve le
facteur historique `trend` issu de `detect_trend`, car la moyenne des facteurs
SMA/EMA structurés divergerait sur certains désaccords.

Exemple compact mais complet de message `history` :

```json
{
  "type": "history",
  "symbol": "BTC/USDC",
  "timeframe": "4h",
  "candles": [
    {"time": 1785240000, "open": 100.0, "high": 103.0, "low": 99.0, "close": 102.0, "volume": 12.5}
  ],
  "indicators": {"rsi_14": [{"time": 1785240000, "value": 31.4}]},
  "markers": [],
  "snapshot": {
    "price": 102.0,
    "timestamp": 1785240000,
    "rsi": 31.4,
    "trend": "bullish",
    "macd": "bullish",
    "bollinger": "near_oversold",
    "stochastic": "bullish_cross",
    "confluence": {
      "score": 84.5,
      "grade": "A",
      "breakdown": {"rsi": 15.0, "trend": 30.0, "macd": 20.0, "bollinger": 7.5, "stochastic": 12.0},
      "effective_weights": {"rsi": 20.0, "trend": 30.0, "macd": 20.0, "bollinger": 15.0, "stochastic": 15.0},
      "details": {}
    },
    "availability": {"rsi": "available", "trend": "available", "macd": "available", "bollinger": "available", "stochastic": "available"},
    "indicator_signals": {
      "rsi": {"status": "available", "direction": "bullish", "signal": "exit_oversold", "state": "near_oversold", "strength": 0.75, "reason": "RSI sort de la zone de survente (31.40)", "raw_value": 31.4},
      "sma": {"status": "available", "direction": "bullish", "signal": "bullish_alignment", "state": null, "strength": 0.5, "reason": "SMA: alignement haussier prix > rapide > lente", "raw_value": 100.8},
      "ema": {"status": "available", "direction": "bullish", "signal": "bullish_cross", "state": null, "strength": 0.75, "reason": "EMA: croisement haussier rapide/lente", "raw_value": 101.1},
      "macd": {"status": "available", "direction": "bullish", "signal": "bullish_cross", "state": "above_signal/above_zero", "strength": 0.95, "reason": "Croisement haussier du MACD au-dessus de sa ligne de signal", "raw_value": 1.2},
      "bollinger": {"status": "available", "direction": "bullish", "signal": "lower_band_reentry", "state": "near_oversold", "strength": 0.6, "reason": "Réintégration au-dessus de la bande basse: rebond potentiel", "raw_value": 102.0},
      "stochastic": {"status": "available", "direction": "bullish", "signal": "bullish_cross", "state": "oversold", "strength": 1.0, "reason": "Croisement haussier du stochastique en zone de survente", "raw_value": 18.0}
    },
    "confirmed": {
      "price": 101.5,
      "timestamp": 1785225600,
      "rsi": 30.8,
      "trend": "bullish",
      "macd": "bullish",
      "bollinger": "neutral",
      "stochastic": "neutral",
      "confluence": null,
      "availability": {"rsi": "available", "trend": "available", "macd": "available", "bollinger": "available", "stochastic": "available"},
      "indicator_signals": {
        "rsi": {"status": "available", "direction": "bullish", "signal": "near_oversold", "state": "near_oversold", "strength": 0.5, "reason": "RSI en zone near_oversold (30.80)", "raw_value": 30.8},
        "sma": {"status": "available", "direction": "bullish", "signal": "bullish_alignment", "state": null, "strength": 0.5, "reason": "SMA: alignement haussier prix > rapide > lente", "raw_value": 100.6},
        "ema": {"status": "available", "direction": "bullish", "signal": "bullish_alignment", "state": null, "strength": 0.5, "reason": "EMA: alignement haussier prix > rapide > lente", "raw_value": 100.9},
        "macd": {"status": "available", "direction": "bullish", "signal": "above_signal", "state": "above_signal/above_zero", "strength": 0.6, "reason": "MACD maintenu au-dessus de sa ligne de signal", "raw_value": 1.0},
        "bollinger": {"status": "available", "direction": "neutral", "signal": "neutral", "state": "neutral", "strength": 0.0, "reason": "Position Bollinger courante: neutral", "raw_value": 101.5},
        "stochastic": {"status": "available", "direction": "neutral", "signal": "neutral", "state": "neutral", "strength": 0.0, "reason": "Stochastique en zone neutre", "raw_value": 42.0}
      }
    },
    "provisional": null,
    "profile": {"rsi_period": 14, "rsi_threshold": 35, "use_rsi": true, "use_ma": true, "use_sma": true, "use_ema": true, "sma_periods": [20, 50], "ema_periods": [20, 50], "macd_fast_period": 12, "macd_slow_period": 26, "macd_signal_period": 9, "use_macd": true, "bollinger_period": 20, "bollinger_std_dev": 2.0, "use_bollinger": true, "stochastic_k_period": 14, "stochastic_d_period": 3, "stochastic_oversold": 20, "stochastic_overbought": 80, "use_stochastic": true, "use_confluence_score": true, "confluence_weights": {"rsi": 0.2, "trend": 0.3, "macd": 0.2, "bollinger": 0.15, "stochastic": 0.15}, "origin": "default"}
  }
}
```

Dans un vrai historique suffisamment amorcé, les trois objets
`indicator_signals` ci-dessus contiennent les signaux décrits en section 16.

Exemple complet de message incrémental :

```json
{
  "type": "update",
  "candle": {"time": 1785254400, "open": 102.0, "high": 104.0, "low": 101.0, "close": 103.0, "volume": 4.2},
  "indicators": {"rsi_14": {"time": 1785254400, "value": 35.2}},
  "markers": [],
  "snapshot": {
    "price": 103.0,
    "timestamp": 1785254400,
    "rsi": 35.2,
    "trend": "bullish",
    "macd": "bullish",
    "bollinger": "neutral",
    "stochastic": "neutral",
    "confluence": null,
    "availability": {"rsi": "available", "trend": "available", "macd": "available", "bollinger": "available", "stochastic": "available"},
    "indicator_signals": {},
    "confirmed": {"price": 102.0, "timestamp": 1785240000, "rsi": 31.4, "trend": "bullish", "macd": "bullish", "bollinger": "near_oversold", "stochastic": "bullish_cross", "confluence": null, "availability": {"rsi": "available", "trend": "available", "macd": "available", "bollinger": "available", "stochastic": "available"}, "indicator_signals": {}},
    "provisional": {"price": 103.0, "timestamp": 1785254400, "rsi": 35.2, "trend": "bullish", "macd": "bullish", "bollinger": "neutral", "stochastic": "neutral", "confluence": null, "availability": {"rsi": "available", "trend": "available", "macd": "available", "bollinger": "available", "stochastic": "available"}, "indicator_signals": {}, "is_forming": true},
    "profile": {"rsi_period": 14, "rsi_threshold": 35, "use_rsi": true, "use_ma": true, "use_sma": true, "use_ema": true, "sma_periods": [20, 50], "ema_periods": [20, 50], "macd_fast_period": 12, "macd_slow_period": 26, "macd_signal_period": 9, "use_macd": true, "bollinger_period": 20, "bollinger_std_dev": 2.0, "use_bollinger": true, "stochastic_k_period": 14, "stochastic_d_period": 3, "stochastic_oversold": 20, "stochastic_overbought": 80, "use_stochastic": true, "use_confluence_score": true, "confluence_weights": {"rsi": 0.2, "trend": 0.3, "macd": 0.2, "bollinger": 0.15, "stochastic": 0.15}, "origin": "default"}
  }
}
```

## 14. Backtest

Le replay charge les bougies depuis SQLite, jamais depuis le réseau. Pour chaque
index de décision, il coupe la fenêtre primaire à `index + 1` et filtre chaque
timeframe supérieur à `close_time <= decision_ms`, puis appelle
`evaluate_signal_snapshot`.

Sans `portfolio_simulation`, il ne possède aucun capital fictif ni sizing. Une
observation est acceptée ou rejetée par les mêmes filtres que le scanner.
`calculate_forward_outcomes` mesure ensuite les rendements :

- `signal_close` : entrée à la clôture de la bougie de décision ;
- `next_open` : entrée à l'ouverture de la bougie suivante ;
- sortie : clôture à `entry_index + horizon` ;
- frais et slippage en bps appliqués à l'entrée et à la sortie ;
- MFE/MAE, highest/lowest, gross/net return, censure de fin de série ou trou.

Les métriques incluent statistiques descriptives, taux positifs, segments, funnel,
corrélations Pearson/Spearman, cooccurrences et ablations. Elles ne constituent pas
une performance de portefeuille.

Protection anti-look-ahead :

- `evaluate_information_set` lève `ValueError` si une bougie primaire ou de
  tendance ferme après `decision_time_ms`;
- le moteur tronque explicitement primaire et higher timeframes ;
- les croisements lisent seulement les deux derniers points de cette fenêtre ;
- `test_future_mutation_cannot_change_signal` mute une bougie future et vérifie
  l'identité des champs historiques passés ;
- `test_future_mutation_cannot_change_indicator_signals` fait la même vérification
  sur tout `indicator_signals`;
- `test_information_set_rejects_future_primary_or_higher_timeframe` vérifie les
  garde-fous explicites.

Ces tests garantissent l'invariance du signal à une mutation située après la
décision, mais ne prouvent pas à eux seuls la qualité économique du signal.

Avec `portfolio_simulation.version=1`, le replay exige un symbole et
`every_bar`, adapte exactement `source_open_time` à la bougie primaire déjà
chargée, rejette tout gap, puis lance le moteur après la constitution des
observations et outcomes. Les outcomes ne sont jamais lus par la simulation.
Les détails restent en mémoire; seul un résumé décimal sérialisé en chaînes est
public. La reprise reconstruit le portefeuille à la fin et aucun résumé partiel
n'est publié après annulation.

## 15. Contrat `IndicatorSignal`

Le domaine définit un `TypedDict` obligatoire à sept clés :

```python
class IndicatorSignal(TypedDict):
    status: Availability
    direction: SignalDirection
    signal: str | None
    state: str | None
    strength: float
    reason: str | None
    raw_value: float | None
```

`Availability = Literal["available", "insufficient_data", "invalid_data",
"disabled"]`; direction est bullish/bearish/neutral. `_clamp_strength` borne la
force dans `[0, 1]`. Le miroir Pydantic impose aussi `ge=0`, `le=1`.

`signal` est volontairement une chaîne libre par indicateur, nullable si
indisponible. `state`, `reason` et `raw_value` sont nullables. `strength` est une
intensité technique conventionnelle, jamais une probabilité de gain.

`NaN` d'une série entièrement vide devient généralement `insufficient_data`; une
valeur courante non finie devient `invalid_data`. Après la correction de cet audit,
RSI, MA, MACD, Bollinger et Stochastique rejettent les valeurs courantes non finies.
La fonction `_unavailable_signal` renvoie direction neutral, signal/state/raw null,
force 0 et une raison. Les exports publics du package incluent les types et toutes
les fonctions structurées.

Exemple RSI conforme au code :

```json
{
  "status": "available",
  "direction": "bullish",
  "signal": "exit_oversold",
  "state": "near_oversold",
  "strength": 0.75,
  "reason": "RSI sort de la zone de survente (31.40)",
  "raw_value": 31.4
}
```

## 16. Signaux par indicateur

| Indicateur | Calcul historique | Signal structuré / événements | État | Force | `raw_value` |
|---|---|---|---|---|---|
| RSI | Wilder `calculate_rsi`, `get_latest_rsi` | `oversold`, `near_oversold`, `neutral`, `near_overbought`, `overbought`, sorties `exit_oversold`/`exit_overbought` prioritaires | cinq zones | extrême 1, near 0,5, sortie 0,75, neutre 0 | RSI courant |
| SMA/EMA | rolling/ewm, `detect_trend` | `bullish_cross`, `bearish_cross`, `bullish_alignment`, `bearish_alignment`, `price_above`, `price_below`, `neutral`; croisement prioritaire | toujours `null` | 0,75 / 0,5 / 0,25 / 0 | moyenne rapide courante |
| MACD | lignes macd/signal/histogram ; `detect_macd_signal` | croisements prioritaires, sinon `above_signal`, `below_signal`, `neutral` | `line_state/zero_state` | croisement base 0,75 + cohérence zéro/distance ; état base 0,5 + distance ; borné à 1 | ligne MACD courante |
| Bollinger | upper/middle/lower ; position historique | cassures/réintégrations basse/haute prioritaires, sinon position | oversold/near/neutral/near/overbought | cassure 0,75, réintégration 0,6, extrême 1, near 0,5, neutre 0 | clôture courante |
| Stochastique | `%K`, `%D`; détecteur historique | croisements prioritaires, sinon oversold/overbought/neutral | zone courante | croisement extrême 1, croisement normal 0,6, état extrême 0,5, neutre 0 | `%K` courant |

Directions : RSI et états extrêmes utilisent une lecture mean-reversion ; Bollinger
distingue correctement une cassure basse baissière d'une réintégration basse
haussière. Une bande dégénérée active est `invalid_data`, jamais `disabled`.
Le builder exige deux lignes stochastiques valides pour préserver la parité du
détecteur historique.

Exemple complet de mapping :

```json
{
  "rsi": {"status": "available", "direction": "bullish", "signal": "exit_oversold", "state": "near_oversold", "strength": 0.75, "reason": "RSI sort de la zone de survente (31.40)", "raw_value": 31.4},
  "sma": {"status": "available", "direction": "bullish", "signal": "bullish_alignment", "state": null, "strength": 0.5, "reason": "SMA: alignement haussier prix > rapide > lente", "raw_value": 100.8},
  "ema": {"status": "available", "direction": "bullish", "signal": "bullish_cross", "state": null, "strength": 0.75, "reason": "EMA: croisement haussier rapide/lente", "raw_value": 101.1},
  "macd": {"status": "available", "direction": "bullish", "signal": "bullish_cross", "state": "above_signal/above_zero", "strength": 0.95, "reason": "Croisement haussier du MACD au-dessus de sa ligne de signal", "raw_value": 1.2},
  "bollinger": {"status": "available", "direction": "bullish", "signal": "lower_band_reentry", "state": "near_oversold", "strength": 0.6, "reason": "Réintégration au-dessus de la bande basse: rebond potentiel", "raw_value": 102.0},
  "stochastic": {"status": "available", "direction": "bullish", "signal": "bullish_cross", "state": "oversold", "strength": 1.0, "reason": "Croisement haussier du stochastique en zone de survente", "raw_value": 18.0}
}
```

## 17. Builder commun

Signature exacte :

```python
build_indicator_signals(
    *,
    close: pd.Series,
    rsi_series: pd.Series | float | None = None,
    use_rsi: bool = True,
    sma_fast: pd.Series | None = None,
    sma_slow: pd.Series | None = None,
    use_sma: bool = False,
    ema_fast: pd.Series | None = None,
    ema_slow: pd.Series | None = None,
    use_ema: bool = False,
    macd_data: dict[str, pd.Series] | None = None,
    use_macd: bool = True,
    bollinger_bands: dict[str, pd.Series] | None = None,
    use_bollinger: bool = True,
    stochastic_data: dict[str, pd.Series] | None = None,
    use_stochastic: bool = True,
    stochastic_oversold: float = 20,
    stochastic_overbought: float = 80,
) -> dict[str, IndicatorSignal]
```

Il ne calcule aucune série, ne fait aucun réseau, n'importe ni FastAPI ni CCXT,
n'a aucune logique scanner et ne retourne que des dict/str/float/null JSON. Il
réutilise les séries calculées par l'appelant.

Point contractuel important : un indicateur désactivé est **absent du mapping**,
pas présent avec `status="disabled"` ; ce comportement est testé. `disabled`
reste exposé séparément dans les tables `availability`. Un indicateur activé dont
la série manque devient `insufficient_data`. Les builders peuvent produire
`invalid_data` pour une série active non exploitable. SMA/EMA ne sont inclus que
si le flag et la série rapide sont présents.

## 18. Confluence structurée

Signatures :

```python
calculate_signal_factor(indicator: str, signal: IndicatorSignal) -> float | None
calculate_rsi_signal_factor(signal: IndicatorSignal, *, rsi_threshold: float) -> float | None
calculate_trend_signal_factor(signals: Sequence[IndicatorSignal]) -> float | None
check_signal_filters(*, macd_signal, bb_position, stoch_signal,
                     filter_macd, filter_bb, filter_stoch) -> bool
calculate_confluence_score(*, rsi_value, rsi_threshold, trend_score,
    max_trend_score, macd_signal, bb_position, stoch_signal, weights,
    trend_states=None, availability=None, raw_values=None,
    indicator_signals=None) -> dict[str, Any] | None
```

Facteurs réellement implémentés :

| Facteur | Règle |
|---|---|
| RSI historique et structuré effectif | `raw <= 30`: 1 ; `<= seuil`: 0,75 ; `< 50`: 0,3 ; sinon 0 |
| RSI générique par état (`calculate_signal_factor`) | oversold 1 ; near_oversold 0,75 ; neutral 0,3 ; near_overbought/overbought 0 |
| trend historique | moyenne de bullish 1, neutral 0,5, bearish 0 ; fallback `trend_score/max` |
| SMA/EMA structuré | cross/alignment bullish 1 ; price_above 0,75 ; neutral 0,5 ; price_below 0,25 ; bearish alignment/cross 0 |
| MACD | direction bullish 1 ; neutral 0,4 ; bearish 0 |
| Bollinger | oversold 1 ; near_oversold 0,75 ; neutral 0,35 ; near_overbought 0,1 ; overbought 0 |
| Stochastique | bullish_cross 1 ; oversold 0,9 ; neutral 0,35 ; bearish_cross 0,1 ; overbought 0 |

La présence d'une clé structurée est prioritaire. Si elle est indisponible ou
inconnue, le facteur ne participe pas et le legacy n'est pas repris. Le fallback
historique ne s'applique que si la clé structurée est absente. SMA/EMA présents
sont agrégés sous `trend`. Les poids strictement positifs des facteurs disponibles
sont renormalisés à 100. Score = somme pondérée × 100. Grades : F < 50, D < 60,
C < 70, B < 80, A < 90, A+ sinon.

`breakdown` contient les contributions en points, `effective_weights` les poids
renormalisés, `details` les statuts, raw, signal legacy, facteur, poids configuré,
poids effectif, contribution, raison et métadonnées structurées. Exemple :

```json
{
  "score": 82.5,
  "grade": "A",
  "breakdown": {"rsi": 15.0, "trend": 30.0, "macd": 20.0, "bollinger": 7.5, "stochastic": 10.0},
  "effective_weights": {"rsi": 20.0, "trend": 30.0, "macd": 20.0, "bollinger": 15.0, "stochastic": 15.0},
  "details": {
    "rsi": {"status": "available", "raw_value": 31.4, "signal": "near_oversold", "factor": 0.75, "configured_weight": 0.2, "effective_weight": 20.0, "contribution": 15.0, "reason": "RSI sort de la zone de survente (31.40)", "structured_signal": "exit_oversold", "structured_state": "near_oversold", "direction": "bullish", "strength": 0.75}
  }
}
```

## 19. Parité historique

Les tests structurés couvrent RSI à tous les seuils, tables MACD/Bollinger/
Stochastique, scénarios tout haussier/neutre/baissier, conflits structuré/legacy,
fallback absent et clé présente indisponible.

- RSI utilise `raw_value`, ce qui distingue correctement 45 (facteur 0,3) de
  55 (0), malgré le même état structuré `neutral`.
- MACD garde 1/0,4/0 selon direction.
- Bollinger garde 1/0,75/0,35/0,1/0 selon position.
- Stochastique garde 1/0,9/0,35/0,1/0 selon signal historique.
- Les filtres continuent exclusivement à lire les classifications historiques.

La tendance scanner/backtest reste multi-timeframes via `trend_states`, alors que
SMA/EMA structurés sont mono-timeframe. Le scanner/backtest n'en construisent donc
pas. Le marché les construit mais conserve le facteur historique `trend`.
C'est la principale zone où la compatibilité repose volontairement sur le chemin
historique.

## 20. Tendance multi-timeframes

Pour chaque timeframe configuré, le scanner/replay calcule toutes les périodes
SMA/EMA activées, prend les deux plus courtes de chaque famille et appelle
`detect_trend`. Une seule moyenne compare prix/moyenne. Deux familles doivent être
d'accord, sinon neutral. `trend_score` compte les timeframes bullish ;
`trend_net_score` ajoute +1/0/-1.

Le snapshot marché n'a qu'un timeframe et appelle la même primitive sur ses
dernières valeurs. Les signaux structurés SMA/EMA représentent chaque famille
séparément et ne sont pas un substitut exact au vote multi-timeframes.

## 21. Moteur canonique `evaluate_information_set`

Entrées exactes : `job_id`, `symbol`, `decision_time_ms`, séquence `primary`,
mapping `trend_candles`, `config`, puis `snapshot_status`, `dataset_version`,
`profile_id` optionnels. Sortie : `SignalObservation`.

Il valide la causalité, transforme les bougies en DataFrame, calcule uniquement
les indicateurs activés, établit historiques/disponibilités, construit RSI/MACD/
Bollinger/Stochastique structurés, passe ces signaux à la confluence, construit
la trace ordonnée des filtres et enrichit provenance, fingerprint, divergences
confirmées et qualité. Les données insuffisantes ne sont pas imputées.

## 22. Câblage scanner

Le scanner construit `ScanResult.indicator_signals` dans son passage unique à
partir des séries déjà nécessaires aux champs legacy. Un oracle de test exécute
séparément `evaluate_information_set` sur les mêmes bougies et compare décision,
classes et signaux. Les anciens champs restent présents. Les filtres
MACD/Bollinger/Stochastique lisent toujours `macd_signal_type`, `bb_position` et
`stoch_signal`. Les signaux structurés n'ajoutent aucun appel OHLCV.

Exemple `ScanResult` valide :

```json
{
  "symbol": "BTC/USDC", "timeframe": "4h", "rsi": 31.4,
  "last_close_price": 102.0, "last_close_time": "2026-07-28T12:00:00Z",
  "trend_score": 2, "trends": {"1h": true, "4h": true},
  "trend_states": {"1h": "bullish", "4h": "bullish"}, "trend_net_score": 2,
  "moving_averages": {"sma_20_4h": 100.8, "ema_20_4h": 101.1},
  "macd": 1.2, "macd_signal": 1.0, "macd_histogram": 0.2,
  "macd_signal_type": "bullish", "bb_upper": 110.0, "bb_middle": 103.0,
  "bb_lower": 96.0, "bb_position": "near_oversold", "stoch_k": 18.0,
  "stoch_d": 17.0, "stoch_signal": "bullish_cross",
  "confluence_score": 82.5, "confluence_grade": "A",
  "confluence_breakdown": {"rsi": 15.0, "trend": 30.0, "macd": 20.0, "bollinger": 7.5, "stochastic": 10.0},
  "confluence_effective_weights": {"rsi": 20.0, "trend": 30.0, "macd": 20.0, "bollinger": 15.0, "stochastic": 15.0},
  "confluence_details": {},
  "indicator_availability": {"rsi": "available", "trend": "available", "macd": "available", "bollinger": "available", "stochastic": "available"},
  "indicator_signals": {
    "rsi": {"status": "available", "direction": "bullish", "signal": "exit_oversold", "state": "near_oversold", "strength": 0.75, "reason": "RSI sort de la zone de survente (31.40)", "raw_value": 31.4}
  }
}
```

## 23. Câblage marché

Le snapshot backend expose bien `indicator_signals`, y compris SMA/EMA. Le même
contrat est recalculé sur chaque `update`. Il n'existe pas de Pydantic qui filtre
la sortie. Les valeurs indicateurs sont converties en floats Python et les points
graphiques non finis sont exclus. La correction de cet audit empêche aussi les
builders MA/Bollinger de publier un `raw_value` infini.

Depuis la Phase 5.1, le schéma Zod frontend décrit explicitement ce champ et le
store conserve le snapshot complet pour `history` comme pour `update`.

## 24. Câblage backtest

Le moteur appelle `evaluate_signal_snapshot` pour chaque fenêtre causale, qui
délègue à `evaluate_information_set`. `SignalObservation.indicator_signals` est
persisté dans le payload d'observation et renvoyé par l'API.

Exemple :

```json
{
  "id": 42, "job_id": "bt-001", "symbol": "BTC/USDC", "timeframe": "4h",
  "decision_time": "2026-07-28T12:00:00Z", "snapshot_status": "confirmed",
  "accepted": true, "rejection_stage": null, "rejection_reason": null,
  "close": 102.0, "rsi": 31.4, "trend_score": 2,
  "trend_states": {"1h": "bullish", "4h": "bullish"},
  "macd_signal": "bullish", "bollinger_position": "near_oversold",
  "stochastic_signal": "bullish_cross", "confluence_score": 82.5,
  "confluence_grade": "A", "confluence_factors": {"rsi": 0.75, "trend": 1.0},
  "availability": {"rsi": "available", "trend": "available", "macd": "available", "bollinger": "available", "stochastic": "available"},
  "indicator_signals": {"rsi": {"status": "available", "direction": "bullish", "signal": "exit_oversold", "state": "near_oversold", "strength": 0.75, "reason": "RSI sort de la zone de survente (31.40)", "raw_value": 31.4}},
  "filter_trace": [], "algorithm_version": "signal-evaluation-v2",
  "profile_id": "inline", "profile_fingerprint": "example", "dataset_version": "dataset-v1",
  "calculation_mode": "canonical", "schema_version": 2,
  "created_at": "2026-07-28T12:00:00Z", "source_open_time": "2026-07-28T08:00:00Z",
  "source_ohlcv": {"open": 100.0, "high": 103.0, "low": 99.0, "close": 102.0, "volume": 12.5},
  "raw_values": {"rsi": 31.4}, "classes": {"macd": "bullish"},
  "trend_net_score": 2, "confluence_breakdown": {"rsi": 15.0},
  "configured_weights": {"rsi": 0.2}, "effective_weights": {"rsi": 20.0},
  "signal_profile": {}, "divergences": [], "quality": {"available_bars": 60}
}
```

## 25. Sérialisation et Pydantic

Les modèles utilisent `model_dump(mode="json")`. Dates et enums deviennent JSON.
`strength` est bornée par Pydantic. Les dictionnaires structurés sont validés lors
de la construction de `ScanResult`/`SignalObservation`. Les builders évitent les
objets pandas/NumPy dans leur retour et convertissent explicitement en `float`.

Le client générique reste un cast, mais les frontières concernées valident
désormais `indicator_signals`. Scanner/backtest utilisent des enveloppes additives
pour conserver leurs champs historiques ; le signal et le dictionnaire de six clés
sont stricts. Les vues/messages marché connus sont stricts et conservent le champ.

## 26. Export CSV

Le CSV scanner conserve 23 colonnes historiques fixes. Les dictionnaires
`trends`, `moving_averages`, `confluence_breakdown` et
`confluence_effective_weights` sont encodés avec `json.dumps`, ordre d'insertion
stable. `indicator_signals` n'est pas exporté intentionnellement, pas plus que
`trend_states`, `trend_net_score`, `confluence_details` et
`indicator_availability`.

Les signaux structurés sont présents dans les payloads JSON du scanner et des
observations de backtest, ainsi que dans le snapshot backend du marché, mais ne
sont actuellement pas inclus dans l'export CSV du scanner. L'export CSV
`observations` du backtest, lui, sérialise tous les champs du modèle, donc inclut
`indicator_signals` comme JSON dans une cellule.

## 27. État actuel du frontend

- `types/indicator-signals.ts` centralise `IndicatorSignal`, les unions et le
  dictionnaire partiel ; scanner, marché et backtest l'importent.
- Le tableau scanner affiche symbole, prix, RSI, tendance, signaux historiques,
  confluence et une colonne additive `Signaux` avec résumé et détail structuré.
- `market-metrics` affiche prix, RSI, tendance, MACD, Bollinger, Stochastique,
  confluence et disponibilité historiques.
- La table backtest pagine les observations par 50, affiche un résumé des six
  indicateurs et ouvre leur détail dans un panneau local.
- `apiRequest<T>` caste `response.json()`.
- Le scanner WS et ses résultats REST valident le champ structuré.
- Le marché Zod conserve `indicator_signals` jusqu'au store.
- L'API backtest valide les observations et le store conserve le champ.
- Les payloads historiques sans champ restent valides et aucun fallback n'est créé.

Le module métier isolé `components/indicator-signals/` affiche statut, direction,
événement, état, `strength`, raison et `raw_value`. Le scanner le compose via des
composants dédiés sous `features/scanner/components/`; le marché et le backtest
le composent également. Le graphique ne l'importe pas.

## 28. Contrats TypeScript ajoutés en Phase 5.1

Contrat recommandé strictement aligné :

```typescript
export type IndicatorSignalStatus =
  | "available"
  | "insufficient_data"
  | "invalid_data"
  | "disabled"

export type IndicatorSignalDirection = "bullish" | "bearish" | "neutral"
export type IndicatorName =
  | "rsi" | "sma" | "ema" | "macd" | "bollinger" | "stochastic"

export interface IndicatorSignal {
  status: IndicatorSignalStatus
  direction: IndicatorSignalDirection
  signal: string | null
  state: string | null
  strength: number // 0..1, intensité technique
  reason: string | null
  raw_value: number | null
}

export type IndicatorSignals =
  Partial<Record<IndicatorName, IndicatorSignal>>
```

Le `Partial` est requis car le builder omet les indicateurs désactivés et le
scanner/backtest omettent toujours SMA/EMA. `indicator_signals?` est présent dans
`ScanResult`, `SignalView`/`MarketSnapshot` et `SignalObservation`. Il n'est pas
nullable. Le job de backtest n'embarque pas directement les observations.

## 29. Bibliothèque visuelle Phase 5.2

`components/indicator-signals/` contient `IndicatorStatusBadge`,
`IndicatorDirectionBadge`, `IndicatorStrength`, `IndicatorSignalCard` et
`IndicatorSignalsPanel`, plus la configuration, les formatters et un barrel
public. L'ordre RSI/SMA/EMA/MACD/Bollinger/Stochastique est explicite. Les
libellés techniques ont un fallback `snake_case`, et les nombres emploient
`Intl.NumberFormat("fr-FR")`.

Les quatre statuts et trois directions combinent texte, icône Lucide et style
sémantique. La force est nommée « intensité technique », bornée visuellement et
exposée par une progressbar 0–100 ; elle n'est jamais présentée comme une
probabilité. Les statuts indisponibles masquent la direction neutre contractuelle.
Les champs nuls ne produisent aucune ligne vide. Le panneau accepte un
dictionnaire partiel, ne le mute pas, filtre optionnellement les indisponibles et
emploie une grille responsive. Voir `docs/frontend/indicator-signals-ui.md`.

La Phase 5.2 n'a modifié ni contrats, ni schémas Zod, ni API, ni stores. Scanner,
marché et backtest composent désormais la même bibliothèque dans leurs vues
métier respectives.

## 29 bis. Intégration scanner Phase 5.3

`ScannerResultsTable` conserve les colonnes historiques conditionnées par
`job.config` et ajoute `Signaux`. `ScannerResultSignalsSummary` décrit les entrées
reçues sans agréger les intensités ni produire une recommandation.
`ScannerResultSignals` gère un `Sheet` local par ligne et
`ScannerResultSignalsDetails` réutilise `IndicatorSignalsPanel`.

Le `Sheet` est pleine largeur et scrollable sur mobile, puis latéral large sur
desktop. Son bouton inclut symbole/timeframe dans son nom accessible ; Radix gère
focus, Échap et retour au déclencheur. Une fermeture visible en français est
également fournie.

Un champ absent affiche l'indisponibilité d'un payload historique, tandis que `{}`
indique qu'aucun signal moderne n'a été produit. Les dictionnaires partiels restent
partiels et les cartes affichent directement les statuts indisponibles reçus. Aucun
objet `disabled` n'est synthétisé depuis la configuration. Le score/grade de
confluence reste affiché comme contexte historique distinct et n'est jamais
recalculé. L'ouverture ne touche ni Zustand, ni URL, ni ordre des résultats.

## 29 ter. Intégration backtest Phase 5.5

`BacktestObservationsTable` remplace la table inline historique. Elle conserve
l'ordre des observations renvoyées, affiche les décisions backend
`accepted`/`rejected` sans inventer de sémantique de trade, et résume les six
indicateurs dans l'ordre canonique partagé.

`BacktestObservationDetails` ouvre un `Sheet` local, plein écran sur mobile et
latéral sur desktop. Il affiche les signaux déjà chargés, le contexte de
confluence backend et, le cas échéant, l'étape et la raison de rejet. L'ouverture
ne lance aucun appel API. Un champ absent désigne un payload historique ; `{}` un
payload moderne sans signal ; un dictionnaire partiel reste partiel.

Le store gère séparément la page d'observations, son total, son chargement et son
erreur. L'API utilise `offset` et `limit=50`. Une erreur de pagination ne détruit
ni le job ni ses métriques globales. Les exports restent servis par le backend ;
l'export des observations contient `indicator_signals` sérialisé en JSON.

Cette interface ne relie pas heuristiquement une observation à un outcome et ne
présente ni trade, ni position, ni capital : le backend est un replay causal de
signaux avec rendements futurs, pas un simulateur de portefeuille.

## 30. Gestion de l'état frontend

Ne pas créer un store dédié. Étendre les objets métier déjà stockés dans les
stores scanner, marché et backtest. React Router continue de porter symbole,
timeframe et vue. RHF reste réservé aux formulaires. Zod doit valider
`IndicatorSignal` aux frontières réseau, idéalement avec `.passthrough()` au
niveau des enveloppes pour compatibilité additive, mais un schéma strict pour les
sept champs connus.

## 31. Tests backend

Commandes finales, depuis `backend/`, avec le virtualenv réel :

| Commande | Code | Résultat |
|---|---:|---|
| `.\venv\Scripts\python.exe -m pytest -q` | 0 | 366 passed, 1 skipped, 22 subtests passed, 2 warnings pandas |
| `.\venv\Scripts\python.exe -m compileall -q app` | 0 | aucune erreur |
| `.\venv\Scripts\python.exe -m black --check app tests` | 0 | 96 fichiers inchangés |
| `.\venv\Scripts\python.exe -m flake8 app tests` | 0 | aucune erreur |
| `.\venv\Scripts\python.exe -m mypy app` | 0 | 64 fichiers, aucune erreur |

Groupes ciblés finaux :

| Fichier | Code | Résultat |
|---|---:|---|
| `tests/test_indicator_signals.py` | 0 | 36 passed |
| `tests/test_indicator_bundle.py` | 0 | 7 passed |
| `tests/test_confluence_structured.py` | 0 | 71 passed |
| `tests/test_backtesting_domain.py` | 0 | 6 passed |
| `tests/test_scanner_service.py` | 0 | 10 passed, 6 subtests |
| `tests/test_market_stream.py` | 0 | 3 passed |
| `tests/test_backtest_engine.py` | 0 | 3 passed |

Avant correction : Black signalait 7 fichiers ; mypy 8 erreurs ; les deux nouveaux
tests non-finite échouaient comme prévu. Après correction, tout passe. Les deux
warnings restants proviennent de `market_data.py` et concernent la perte de
nanosecondes lors de `to_pydatetime()`.

## 32. Tests frontend

Depuis `frontend/` :

| Commande | Code | Résultat |
|---|---:|---|
| `$env:CI='true'; pnpm install --frozen-lockfile` | 0 | lockfile à jour, 335 paquets réutilisés |
| `pnpm run typecheck` | 0 | TypeScript réussi |
| `pnpm run lint` | 0 | ESLint, 0 warning |
| `pnpm exec vitest run src/components/indicator-signals` | 0 | 5 fichiers, 55 tests passed |
| `pnpm run test` | 0 | 25 fichiers, 143 tests passed |
| `pnpm run build` | 0 | 2034 modules, build Vite réussi |

La validation Phase 5.2 a utilisé pnpm 10.15.1. Une première tentative
d'installation a rencontré l'accès réseau restreint lors de la vérification des
métadonnées ; la relance autorisée en mode CI a confirmé le lockfile à jour et
les dépendances déjà installées. TypeScript, ESLint, les tests et le build ont
ensuite tous réussi.

Validation Phase 5.3 :

| Commande | Code | Résultat |
|---|---:|---|
| `$env:CI='true'; pnpm install --frozen-lockfile` | 0 | lockfile à jour, 335 paquets réutilisés |
| `pnpm exec vitest run src/features/scanner` | 0 | 3 fichiers, 21 tests passés |
| `pnpm run typecheck` | 0 | TypeScript réussi |
| `pnpm run lint` | 0 | ESLint, 0 warning |
| `pnpm run test` | 0 | 26 fichiers, 154 tests passés |
| `pnpm run build` | 0 | 2045 modules transformés, build Vite réussi |
| `python -m pytest -q` depuis `backend/` | 0 | 366 passés, 1 ignoré, 22 subtests, 3 warnings |

Validation Phase 5.4 :

| Commande | Code | Résultat |
|---|---:|---|
| `$env:CI='true'; pnpm install --frozen-lockfile` | 0 | lockfile à jour, 335 paquets réutilisés, 0 téléchargé |
| `pnpm exec vitest run src/features/market` | 0 | 8 fichiers, 31 tests passés |
| `pnpm exec vitest run src/stores/market-store.test.ts` | 0 | 1 fichier, 9 tests passés |
| `pnpm exec vitest run src/api/market-contract.test.ts` | 0 | 1 fichier, 6 tests passés |
| `pnpm run typecheck` | 0 | TypeScript réussi |
| `pnpm run lint` | 0 | ESLint, 0 warning |
| `pnpm run test` | 0 | 31 fichiers, 174 tests passés |
| `pnpm run build` | 0 | 2 048 modules transformés, build Vite réussi |
| `.\venv\Scripts\python.exe -m pytest -q` depuis `backend/` | 0 | 366 passés, 1 ignoré, 22 subtests, 2 warnings |

Validation Phase 5.5 :

| Commande | Code | Résultat |
|---|---:|---|
| `$env:CI='true'; pnpm install --frozen-lockfile` | 0 | lockfile à jour, 335 paquets réutilisés, 0 téléchargé |
| `pnpm exec vitest run src/api/backtests.test.ts src/stores/backtest-store.test.ts src/features/backtests src/pages/backtests-page.test.tsx` | 0 | 8 fichiers, 34 tests passés |
| `pnpm run typecheck` | 0 | TypeScript réussi |
| `pnpm run lint` | 0 | ESLint, 0 warning |
| `pnpm run test` | 0 | 36 fichiers, 200 tests passés |
| `pnpm run build` | 0 | 2 052 modules transformés, build Vite réussi |
| `.\venv\Scripts\python.exe -m pytest -q tests/test_backtesting_domain.py tests/test_backtest_engine.py tests/test_backtest_api.py` depuis `backend/` | 0 | 12 tests passés |
| `.\venv\Scripts\python.exe -m pytest -q` depuis `backend/` | 0 | 366 passés, 1 ignoré, 22 subtests, 2 warnings |

Validation Phase 5.6 :

| Commande | Code | Résultat |
|---|---:|---|
| `$env:CI='true'; pnpm install --frozen-lockfile` | 0 | lockfile à jour, 335 paquets réutilisés, 0 téléchargé |
| `pnpm exec vitest run src/components/indicator-signals` | 0 | 6 fichiers, 68 tests passés |
| `pnpm exec vitest run src/features/scanner` | 0 | 3 fichiers, 21 tests passés |
| `pnpm exec vitest run src/features/market` | 0 | 8 fichiers, 31 tests passés |
| `pnpm exec vitest run src/features/backtests` | 0 | 5 fichiers, 21 tests passés |
| `pnpm run typecheck` | 0 | TypeScript réussi |
| `pnpm run lint` | 0 | ESLint, 0 warning |
| `pnpm run test` | 0 | 37 fichiers, 213 tests passés |
| `pnpm run build` | 0 | 2 054 modules transformés, build Vite réussi |
| `.\venv\Scripts\python.exe -m pytest -q` depuis `backend/` | 0 | 366 passés, 1 ignoré, 22 subtests, 1 warning |

Validation Phase 5.8 :

| Commande | Code | Résultat |
|---|---:|---|
| `.\venv\Scripts\python.exe -m pytest -q` | 0 | 540 passés, 1 ignoré, 27 subtests, 2 warnings |
| `.\venv\Scripts\python.exe -m compileall -q app` | 0 | aucune erreur |
| `.\venv\Scripts\python.exe -m black --check app tests` | 0 | 100 fichiers inchangés |
| `.\venv\Scripts\python.exe -m flake8 app tests` | 0 | aucune erreur |
| `.\venv\Scripts\python.exe -m mypy app` | 0 | 66 fichiers, aucune erreur |
| `$env:CI='true'; pnpm install --frozen-lockfile` | 0 | lockfile à jour, 335 paquets réutilisés, 0 téléchargé |
| `pnpm run typecheck` | 0 | TypeScript réussi |
| `pnpm run lint` | 0 | ESLint, 0 warning |
| `pnpm run test` | 0 | 41 fichiers, 251 tests passés |
| `pnpm run build` | 0 | 2 056 modules transformés, build Vite réussi |

## 33. Commandes de développement

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload
python -m pytest -q
python -m compileall -q app
python -m black --check app tests
python -m flake8 app tests
python -m mypy app

cd ..\frontend
pnpm install --frozen-lockfile
pnpm run dev
pnpm run typecheck
pnpm run lint
pnpm run test
pnpm run build
```

## 34. Variables d'environnement

Backend : `DATABASE_PATH`, `CORS_ORIGINS`, `JOB_TTL_SECONDS`,
`MAX_RETAINED_JOBS`, options `CANDLE_*`, `MARKET_HISTORY_*`, `BACKFILL_*` et
`SHADOW_MODE_ENABLED`. Frontend : `VITE_API_URL` et `VITE_WS_URL`.
Le code backend lit `os.getenv`; charger explicitement `.env` ou utiliser
`uvicorn --env-file`. Ne jamais injecter le contenu d'un `.env` dans un contexte IA.

## 35. Limites et dette technique

- Dépôt Git initialisé avec un historique récent ; `safe.directory` reste requis
  dans cet environnement Windows.
- Scanner : adaptateur historique en un passage ; assemblage replay distinct
  maintenu en parité par les tests.
- Marché : pas de modèle Pydantic public.
- Builder : `disabled` signifie omission, contrairement à une phrase obsolète de
  sa docstring de module à corriger si ce contrat change.
- Frontend : scanner, marché et backtest structurés sont intégrés ; les champs
  legacy restent volontairement présents.
- Backtest : simulation v1 optionnelle intégrée au résumé; détails non
  persistés, sans endpoints paginés ni frontend.
- Versions Python non figées exactement.
- Artefacts lourds présents localement mais ignorés : `dist`, `node_modules`,
  environnements virtuels, caches, logs, bases locales et `.env`.

## 36. Problèmes connus

Deux warnings pandas sur les nanosecondes. Les chemins scanner et replay
pourraient diverger lors d'une évolution de règle ; les oracles de domaine et de
service doivent donc rester bloquants.

Corrections réalisées pendant cet audit :

1. `confluence.py` : source structurée mise en variable locale pour permettre le
   narrowing mypy sans changer le payload.
2. `backtesting.py` : cast explicite à la frontière Pydantic.
3. MA/Bollinger : valeurs courantes/précédentes non finies deviennent
   `invalid_data`, raw null, force 0 ; deux tests ajoutés.
4. Formatage Black des sept fichiers signalés.

## 37. Risques de régression

- Confondre `strength` et taux de réussite.
- Injecter SMA/EMA marché dans la confluence et modifier les scores.
- Remplacer `raw_value` RSI par l'état et perdre la parité 45/55.
- Faire participer un structured key indisponible via fallback legacy.
- Calculer un croisement avec une bougie future ou ouverte dans un flux confirmé.
- Rendre `indicator_signals` obligatoire côté frontend et casser les anciens
  payloads.
- Ajouter `indicator_signals` au CSV scanner sans stratégie de colonnes stable.

## 38. Fichiers importants

```text
backend/app/domain/indicators/types.py
backend/app/domain/indicators/{rsi,moving_averages,macd,bollinger,stochastic}.py
backend/app/domain/indicators/confluence.py
backend/app/domain/indicator_bundle.py
backend/app/domain/backtesting.py
backend/app/domain/signal_evaluation.py
backend/app/services/scanner.py
backend/app/services/market_stream.py
backend/app/services/backtest_engine.py
backend/app/models/{scanner,backtest}.py
backend/app/exporters/csv_exporter.py
frontend/src/types/{scanner,market,backtest}.ts
frontend/src/api/{scanner,market,backtests}.ts
frontend/src/stores/{scanner-store,market-store,backtest-store}.ts
frontend/src/components/indicator-signals/
docs/frontend/indicator-signals-ui.md
```

## 39. Où modifier quoi

- Contrat/directions/statuts : `indicators/types.py`, puis modèle Pydantic et TS.
- Règle native : module de l'indicateur + `test_indicator_signals.py`.
- Assemblage : `indicator_bundle.py` + `test_indicator_bundle.py`.
- Facteur/poids/grade : `confluence.py` + tests structurés.
- Décision scanner/backtest : `backtesting.py`, façade et tests causaux.
- Snapshot live : `market_stream.py` + schémas Zod/tests marché.
- Présentation : composants scanner/market/backtests, sans modifier le domaine.

## 40. Plan recommandé pour la Phase 5 frontend

### 5.1 — Contrats TypeScript — terminée

Types et schémas communs intégrés aux trois payloads. Le champ reste optionnel,
non nullable et n'est plus supprimé par le marché. Les tests couvrent parsing,
absence compatible, dictionnaire partiel, clés inconnues, nombres non finis,
force hors bornes et conservation dans les stores.

### 5.2 — Composants réutilisables — terminée

Module créé sous `components/indicator-signals/` avec cinq composants publics,
configuration et formatters centralisés, mode compact, grille responsive,
accessibilité et tests Testing Library. Aucun branchement page/store/API n'a été
ajouté.

### 5.3 — Scanner — terminée

Colonne compacte ajoutée sans retirer les colonnes historiques. Un `Sheet`
responsive par ligne affiche `IndicatorSignalsPanel`, distingue payload absent,
objet vide et dictionnaire partiel, et conserve les statuts indisponibles.
L'ouverture est locale, accessible et sans effet sur le tri, les filtres, le store
ou le lien marché.

### 5.4 — Marché

Terminée. `MarketConnectionStatus` expose les quatre états réels du store et une
alerte d'erreur sans effacer les données. `MarketSignalsSection` utilise des
onglets locaux sur mobile et deux colonnes sur desktop ; ses deux
`MarketSignalSnapshot` lisent séparément les vues confirmed/provisional et
composent `IndicatorSignalsPanel` sous le graphique. Les six indicateurs sont
pris en charge, le champ absent reste distinct de `{}`, et la note SMA/EMA versus
facteur historique trend est visible. Aucun contrat, socket, graphique ou calcul
métier n'a été modifié.

### 5.5 — Backtest

Terminée. La table d'observations est paginée et affiche un résumé compact des
signaux structurés. Un `Sheet` local détaille les six indicateurs, la confluence
backend et le rejet éventuel. Les décisions restent `accepted`/`rejected` :
aucune entrée, sortie, position ou performance réalisée n'est inventée. Les
payloads absents, vides et partiels ainsi que les états réseau sont couverts.

### 5.6 — Audit transversal et préparation de la dépréciation — terminée

Les trois intégrations ont été vérifiées dans le code. Les compteurs et états de
collection réellement communs sont factorisés, la convention d'intensité est
partagée, et l'inventaire versionné est documenté dans
[`structured-signals-migration-audit.md`](frontend/structured-signals-migration-audit.md).
Aucun champ historique, contrat backend ou format CSV n'a été supprimé ou modifié.

### 5.7 — Validation finale

Ajouter tests de schémas réseau, quatre statuts, six indicateurs, WebSocket update,
scanner/marché/backtest, puis exécuter typecheck, lint, tests et build. Risque :
fixtures incomplètes masquant la compatibilité. Acceptation : suite complète verte
avec fixtures backend réelles et payload legacy.

## 41. Instructions d'utilisation comme contexte IA

Donner ce fichier en premier à l'IA chargée de la Phase 5, puis les seuls fichiers
de code concernés. Exiger une vérification directe avant toute modification car le
dépôt n'a pas d'historique Git. Ne jamais inférer qu'un champ frontend existe parce
qu'il existe dans le backend. Préserver les champs legacy, la causalité, la
distinction confirmed/provisional et l'exclusion SMA/EMA de la confluence marché.

## 42. Matrice de compatibilité

| Fonctionnalité | Scanner | Marché backend | Backtest | CSV scanner | Frontend actuel |
|---|---:|---:|---:|---:|---:|
| Anciens signaux | oui | oui | oui | oui | oui |
| Signaux structurés | oui | oui | oui | non | affichés dans le scanner, le marché et le backtest |
| Confluence structurée | oui, sauf trend | oui, sauf SMA/EMA | oui, sauf trend | résultat legacy | contexte backend affiché sans recalcul |
| SMA/EMA structurés | non | oui | non | non | affichés dans le marché |
| Tendance multi-timeframes | oui | non | oui | score/trends | scanner seulement |
| `raw_value` | JSON | JSON backend | JSON | non | affichable dans les détails structurés |
| Affichage utilisateur | legacy + structuré | legacy + structuré | legacy + structuré | téléchargement | scanner, marché et backtest migrés |

## 43. Statut des Phases 1 à 4

- Phase 1, contrat et qualité : implémentée ; garde-fous non-finis complétés lors
  de cet audit.
- Phase 2, indicateurs structurés et confluence : implémentée et couverte.
- Phase 3, builder/moteur canonique/parité : implémentée ; le double passage
  scanner a été retiré en Phase 5.8 et remplacé par des oracles de tests.
- Phase 4, câblage scanner/marché/backtest : implémentée côté backend et modèles,
  tests causaux présents.
- Phase 5.1, contrats frontend : implémentée ; types, schémas, frontières et stores
  couverts, sans modification visuelle.
- Phase 5.2, composants frontend : implémentée ; bibliothèque métier, formatters,
  accessibilité et tests présents.
- Phase 5.3, scanner frontend : implémentée ; résumé compact, détail en `Sheet`,
  compatibilité historique et colonnes existantes préservées.
- Phase 5.4, marché frontend : implémentée ; connexion/erreur visibles, vues
  confirmed/provisional distinctes, six signaux structurés et confluence backend
  affichés sous le graphique, responsive et accessibles.
- Phase 5.5, backtest frontend : implémentée ; observations paginées, décisions
  `accepted`/`rejected`, résumé et détail structurés, compatibilité historique et
  séparation explicite entre signal, outcome futur et simulation de portefeuille.
- Phase 5.6, audit transversal : implémentée ; helpers de résumé/état et note
  d'intensité communs, inventaire legacy et plan de dépréciation sans suppression.
- Phase 5.7, filtres structurés : implémentée ; contrat v1 additif, priorité
  locale et fallback legacy.
- Phase 5.8, stabilisation : contrat JSON figé, parité exhaustive, fingerprints
  et compteurs d'appels ; aucun champ legacy déprécié.

Conclusion : la donnée structurée arrive jusqu'aux stores et les trois interfaces
la présentent sans recalcul. La suite doit être choisie à partir de mesures
d'usage réelles : v2, dépréciation formelle ou nouvelle optimisation prouvée.
Aucune suppression de champ ne doit précéder cette décision.
