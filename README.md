# Scanner Binance · FastAPI + React + shadcn/ui + Zustand

Le dépôt fournit scanner, marché live, replay historique et un socle
d’expérimentation, sans exécution d’ordres. Les quatre phases ne sont pas toutes
complètes : consultez l’[audit vérifié](docs/PHASES_IMPLEMENTATION_AUDIT.md) et le
[contexte autonome pour IA](docs/CURRENT_APP_STATE_FOR_AI.md). Les limites du
walk-forward, des variantes et du shadow sont détaillées dans
[SIGNAL_OPTIMIZATION.md](docs/SIGNAL_OPTIMIZATION.md).

## Arborescence

```text
scanner_binance_v2/
├── backend/
│   ├── main.py              # point d'entrée ASGI compatible
│   ├── indicators.py        # réexports historiques, sans implémentation dupliquée
│   ├── app/                 # backend FastAPI actif
│   └── tests/
└── frontend/
    ├── index.html
    ├── package.json
    ├── pnpm-lock.yaml
    ├── src/
    │   ├── App.tsx
    │   ├── app/             # routeur, providers et layout
    │   ├── components/
    │   ├── features/        # scanner et marché
    │   ├── hooks/
    │   ├── lib/
    │   ├── pages/
    │   ├── stores/
    │   └── types/
```

## Développement

Terminal 1 :

1. Créer un environnement virtuel Python :

```bash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Terminal 2 :

```bash
cd frontend
pnpm install
pnpm run dev
```

Ouvrir <http://127.0.0.1:5173>.

Vite transmet `/ws` et `/health` à FastAPI sur le port 8000.

## Backend

Le backend FastAPI gère les jobs de scan asynchrones, le stockage durable des
bougies dans `backend/data/scanner_crypto.sqlite3`, les calculs d'indicateurs,
les exports CSV et les WebSockets de progression et de marché. Son point d'entrée
stable est `backend/main.py` avec la cible ASGI `main:app`.

Démarrage rapide :

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Tests :

```powershell
cd backend
python -m pytest -q
```

SQLite est embarqué et ne demande aucun serveur. Le chemin se configure avec
`DATABASE_PATH`; les bougies sont synchronisées progressivement avec CCXT,
réutilisées par le scanner et le graphique, puis exportables via
`GET /api/market/candles/export.csv`. Voir
[le stockage OHLCV](docs/backend/ohlcv-storage.md).

La page marché amorce désormais le graphique avec `GET /api/market/candles`,
charge les pages plus anciennes par curseur lorsque l'utilisateur se déplace à
gauche et conserve en parallèle les updates WebSocket. La vue logique, les
indicateurs et les marqueurs restent alignés pendant le préfixage.

Une date peut aussi être ouverte directement sans parcourir toutes les pages
intermédiaires. Seule la fenêtre demandée est récupérée depuis Binance lorsqu'elle
manque au cache SQLite ; les updates live restent isolées jusqu'au retour au temps
réel. Voir [l'historique à la demande](docs/backend/on-demand-market-history.md).

Le téléchargement historique massif est une commande distincte, en simulation
par défaut :

```powershell
cd backend
python -m app.cli.backfill_candles --quote USDC --symbols all --timeframes all
```

L'exécution réelle exige `--execute`. La reprise, la synchronisation
incrémentale, les limites de découverte Binance et la sauvegarde sont détaillées
dans [la documentation du backfill](docs/backend/historical-backfill.md).

La [documentation backend complète](docs/backend/README.md) couvre l'architecture,
la configuration, l'API, les indicateurs, les WebSockets, les tests, le déploiement
et le dépannage. Le fichier [backend/README.md](backend/README.md) reste le mémo
proche du code.

## Production locale

```powershell
cd frontend
pnpm install
pnpm run build
cd ..\backend
python -m uvicorn main:app
```

Ouvrir <http://127.0.0.1:8000>. FastAPI sert alors `frontend/dist`.

## Ajouter un composant shadcn/ui

Depuis `frontend/` :

```powershell
pnpm dlx shadcn@latest add button
```
