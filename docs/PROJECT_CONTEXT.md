# Contexte technique — scanner_crypto

> Photographie consolidée le 2 août 2026.
> Pour l’état exhaustif, utiliser `CURRENT_APP_STATE_FOR_AI.md`.
> Pour les événements graphiques, utiliser
> `docs/backend/indicator-events-and-market-markers.md`.

## 1. Résumé

`scanner_crypto` est une application locale FastAPI + React d’analyse technique
crypto. Elle comprend :

- un scanner CCXT asynchrone et multi-paires ;
- un marché Binance live par CCXT Pro/WebSocket ;
- un stockage SQLite des bougies, jobs, observations et résultats ;
- un backtest causal close-only avec outcomes futurs ;
- une simulation optionnelle de portefeuille fictif v1 ;
- des expériences, profils, shadow et promotion contrôlée.

L’application ne passe aucun ordre réel. Les signaux, marqueurs, outcomes et
résultats de portefeuille restent informatifs et ne garantissent aucune
performance future.

## 2. Stack

Backend : Python 3.11+, FastAPI, Uvicorn, Pydantic, pandas, NumPy, CCXT,
CCXT Pro, aiosqlite, pytest, Black, Flake8 et mypy.

Frontend : React 19, TypeScript 6, Vite 8, React Router 7, Zustand 5,
React Hook Form, Zod 4, Tailwind 4, Shadcn/Radix, Lightweight Charts 5.2,
Vitest et Testing Library.

## 3. Architecture

```text
backend/app/
├── api/              REST et WebSocket
├── core/             settings, erreurs, logs
├── database/         SQLite et migrations
├── domain/
│   ├── indicators/   calculs purs, signaux et événements
│   ├── portfolio/    simulation fictive v1
│   └── ...           replay, confluence, expériences
├── models/           contrats Pydantic
├── repositories/     persistance
└── services/         scanner, marché, backtest, sync, shadow

frontend/src/
├── api/              clients et validation Zod
├── app/              routeur et layout
├── components/       UI partagée et graphique
├── features/         scanner, marché, backtests, expériences
├── stores/           Zustand
└── types/            contrats TypeScript
```

Points d’entrée : `backend/main.py` et `frontend/src/main.tsx`.

## 4. Domaine des indicateurs

Le calcul est séparé de l’orchestration. Chaque module sous
`backend/app/domain/indicators/` calcule ses séries et construit ses signaux
structurés. `indicator_bundle.py` agrège les séries déjà calculées ; il ne fait
aucun réseau.

Indicateurs présents :

- RSI ;
- SMA et EMA ;
- MACD ;
- Bollinger et largeur de bande ;
- Stochastique ;
- ATR/NATR ;
- ADX/DMI ;
- Supertrend ;
- Donchian ;
- Keltner.

ATR/NATR, ADX/DMI, Supertrend, Donchian et Keltner restent optionnels. Leur
présence n’ajoute pas automatiquement de filtre ou de poids de confluence.

## 5. Contrat des signaux

`IndicatorSignal` contient :

```text
status, direction, signal, state, strength, reason, raw_value, components?
```

Statuts : `available`, `insufficient_data`, `invalid_data`, `disabled`.
Directions : `bullish`, `bearish`, `neutral`.

`strength` est une intensité technique bornée dans `[0, 1]`, jamais une
probabilité. `components` transporte les valeurs multi-composants.

Le scanner, le marché et le backtest exposent les signaux structurés en plus des
champs legacy. Les indicateurs désactivés sont normalement omis du mapping.

## 6. Événements historiques et marqueurs

Le marché possède une chaîne générique :

```text
module indicateur
→ IndicatorEvent
→ build_indicator_events
→ build_indicator_event_markers
→ REST / WebSocket
→ Zustand
→ Lightweight Charts
```

`IndicatorEvent` contient `indicator`, `position`, `direction`, `event`, `kind`
et éventuellement `strength`/`metadata`.

Marqueurs close-only :

- EMA : croisements ;
- MACD : histogramme traversant zéro ;
- Supertrend : flips ;
- RSI : sorties de survente/surachat ;
- Stochastique : croisements dans les zones extrêmes ;
- Bollinger : réintégrations ;
- Donchian : premières cassures du canal `t-1` ;
- Keltner : cassures des bandes précédentes ;
- ADX/DMI : croisements confirmés par le seuil ADX faible ;
- ATR/NATR : expansion/contraction de volatilité, direction neutre.

Les séries graphiques et le snapshot provisional peuvent inclure la bougie
ouverte, mais les marqueurs confirmés ne l’utilisent pas.

## 7. Frontend des marqueurs

`MarketMarker` porte notamment :

```text
time, position, shape, color, text, category, indicator
```

Le frontend :

1. normalise les anciens marqueurs sans `indicator` ;
2. fusionne et déduplique les marqueurs ;
3. exige `visibility.signals` pour les signaux ;
4. applique ensuite la visibilité de l’indicateur.

ATR/NATR utilise `visibility.volatility`. La normalisation historique reconnaît
`ATR`, `NATR`, `volatilité`, `volatilite` et `volatility`.

## 8. Scanner

Le scanner :

- charge et filtre les marchés CCXT ;
- normalise les OHLCV et retire la bougie ouverte ;
- calcule seulement les indicateurs activés ;
- applique filtres legacy et structurés v1 ;
- calcule une confluence explicable ;
- expose progression, résultats, annulation et CSV.

La tendance scanner reste multi-timeframes. SMA/EMA structurés individuels sont
surtout utilisés dans le marché mono-timeframe ; ils ne remplacent pas le vote de
tendance scanner/replay.

## 9. Marché live

Le marché Binance :

- charge jusqu’à la limite de calcul ;
- sépare snapshots `confirmed` et `provisional` ;
- diffuse historique puis mises à jour incrémentales ;
- conserve les séries et marqueurs dans Zustand ;
- permet la pagination historique et la navigation par date ;
- ferme toujours l’exchange lors de la déconnexion.

Les routes historiques et le WebSocket réutilisent les mêmes builders de séries
et de marqueurs.

## 10. Backtest et portefeuille

Le replay est causal et close-only. Il lit SQLite, coupe l’information au temps
de décision et calcule observations, rejets et outcomes futurs. Les outcomes ne
sont pas des trades réalisés.

La simulation de portefeuille v1 est optionnelle et séparée :

- long-only ;
- pas de levier, short, stop-loss ou take-profit ;
- capital fictif et sizing configurables ;
- trades et equity persistés ;
- routes et exports dédiés ;
- résumé et graphique frontend.

## 11. Expérimentation

La recherche reste séparée de la production :

- splits chronologiques ;
- embargo ;
- train/validation/OOS/test final ;
- fingerprints et manifestes ;
- profils immuables ;
- shadow sans effet sur la décision de production ;
- correction de multiplicité et garde-fous de robustesse.

Les Phases 7 ont conclu qu’aucune variante d’assouplissement RSI ne devait être
promue. Les indicateurs étendus n’ont pas encore été ajoutés aux poids ou filtres
de production.

## 12. Routes principales

```text
/api/scanner/*
/api/candles/*
/api/history/*
/api/backtests/*
/api/experiments/*
/api/signal-profiles/*
/api/shadow/*
/ws
```

Les listes exhaustives et modèles associés sont dans
`CURRENT_APP_STATE_FOR_AI.md`.

## 13. Configuration

Backend : `DATABASE_PATH`, `CORS_ORIGINS`, options `CANDLE_*`,
`MARKET_HISTORY_*`, `BACKFILL_*`, rétention des jobs et
`SHADOW_MODE_ENABLED`.

Frontend : `VITE_API_URL`, `VITE_WS_URL`,
`VITE_MARKET_MAX_CANDLES_IN_MEMORY` et paramètres de préchargement du marché.

Le contenu réel des fichiers `.env` ne doit jamais être copié dans un contexte IA.

## 14. Commandes

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

## 15. Fichiers importants

```text
backend/app/domain/indicators/types.py
backend/app/domain/indicators/
backend/app/domain/indicator_bundle.py
backend/app/domain/backtesting.py
backend/app/services/scanner.py
backend/app/services/market_stream.py
backend/app/services/backtest_engine.py
backend/app/api/candles.py

frontend/src/types/market.ts
frontend/src/features/market/market-history.ts
frontend/src/stores/market-store.ts
frontend/src/features/market/components/trading-chart.tsx

docs/CURRENT_APP_STATE_FOR_AI.md
docs/SIGNALS_CURRENT_STATE.md
docs/SIGNALS_CONTRACT.md
docs/backend/indicator-events-and-market-markers.md
```

## 16. Neutralité de la mise à jour du 2 août 2026

La généralisation des marqueurs est une évolution de calcul événementiel et de
présentation du marché. Elle ne modifie pas :

- les poids de confluence ;
- les filtres structurés v1 ;
- le critère `accepted` ;
- les outcomes ;
- les ordres, trades ou résultats de portefeuille ;
- les conclusions de recherche des Phases 7.

La visibilité des marqueurs ATR a été confirmée manuellement après correction du
filtre global `signals`, du filtre `volatility` et de la normalisation des anciens
libellés. Aucune suite complète n’est déclarée comme relancée dans cette mise à
jour documentaire.
