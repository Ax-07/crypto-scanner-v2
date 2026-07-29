# Démarrage du backend

## Prérequis

Le dépôt utilise actuellement Python 3.11. Utiliser cette version évite les écarts de dépendances. Node.js et pnpm ne sont requis que pour le frontend. L'accès réseau à Binance est requis pour un scan réel ou le WebSocket marché, mais pas pour les tests.

## Installation sous PowerShell

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn main:app --reload
```

## Installation sous Bash

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn main:app --reload
```

Le code lit directement les variables du processus avec `os.getenv` ; le lancement Uvicorn montré ici ne charge pas automatiquement `.env`. Sous PowerShell, charger les valeurs utiles dans `$env:NOM`. On peut aussi utiliser l'option Uvicorn `--env-file .env`, disponible avec l'installation actuelle :

```powershell
python -m uvicorn main:app --reload --env-file .env
```

## Vérification

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/health
```

La première réponse est `{"status":"ok"}`. La seconde ajoute `symbol`, `timeframe` et `display_limit`.

Arrêter Uvicorn avec `Ctrl+C`. Les exchanges créés par les scans et les connexions WebSocket disposent de blocs `finally`, mais les jobs en mémoire sont perdus à l'arrêt.

## Frontend

En développement, lancer `pnpm run dev` depuis `frontend/`. En production locale, exécuter `pnpm run build` ; FastAPI servira ensuite `frontend/dist`.

## Problèmes de démarrage

- `No module named uvicorn` : activer le bon environnement puis réinstaller `requirements.txt`.
- erreur `from app...` : lancer Uvicorn depuis `backend/` avec `main:app`.
- réponse 503 sur `/` : construire React ou utiliser Vite sur le port 5173.
- port 8000 occupé : ajouter `--port 8001` et adapter le proxy frontend.

Les réglages disponibles sont détaillés dans [configuration.md](configuration.md).
