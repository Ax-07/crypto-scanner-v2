# Dépannage

## Installation et démarrage

| Symptôme | Vérification | Correction |
|---|---|---|
| `No module named uvicorn` | `python -m pip show uvicorn` et `python -c "import sys; print(sys.executable)"` | Activer `backend/venv`, puis installer `requirements.txt`. |
| `ModuleNotFoundError: app` | Contrôler le dossier courant et la cible Uvicorn. | Depuis `backend/`, lancer `python -m uvicorn main:app`. |
| Environnement virtuel non actif | `python -c "import sys; print(sys.prefix)"` | PowerShell : `.\venv\Scripts\Activate.ps1`; Bash : `source venv/bin/activate`. |
| Port déjà utilisé | Essayer la sonde et inspecter le processus qui écoute 8000. | Arrêter ce processus ou ajouter `--port 8001`, puis adapter le proxy Vite. |
| `/` répond 503 ou un asset 404 | Vérifier `frontend/dist/index.html`. | Depuis `frontend`, exécuter `pnpm install` puis `pnpm run build`, ou utiliser `pnpm run dev`. |

## Navigateur et WebSockets

| Symptôme | Cause probable / vérification | Correction |
|---|---|---|
| Erreur CORS | Origine du navigateur absente de `CORS_ORIGINS`. | Ajouter l'URL exacte, séparée par une virgule, puis redémarrer. |
| WebSocket interrompu | Redémarrage, proxy sans Upgrade, timeout ou Binance indisponible. | Lire `scanner.log`, tester sans proxy et configurer Upgrade/timeout. |
| Progression refusée 4404 | Job absent, purgé ou créé dans un autre worker. | Vérifier l'identifiant et utiliser un seul worker. |
| Message `Symbole Binance inconnu` | Symbole absent de `exchange.markets` après normalisation. | Interroger `/api/scanner/markets` ou utiliser un symbole CCXT comme `BTC/USDC`. |
| Message `Timeframe non pris en charge` | Valeur hors de la table du backend. | Utiliser un timeframe documenté dans [configuration.md](configuration.md). |

## Scans et résultats

| Symptôme | Vérification | Correction |
|---|---|---|
| Aucune paire trouvée | Appeler `/api/scanner/markets` avec la même quote/type ; vérifier les filtres de stablecoins. | Corriger `quote`, `market_type` ou désactiver l'exclusion si voulu. |
| Rate limit | Chercher `OHLCV abandonné` dans les logs. | Réduire `max_concurrency`, augmenter le délai initial ou réduire `max_pairs`. |
| Job `failed` | Lire `error` puis la trace dans `scanner.log`. | Corriger l'exchange/configuration ou l'indisponibilité globale ; les erreurs de paire seules ne causent pas `failed`. |
| Résultats vides | Comparer `filtered` et `errors`; vérifier les seuils. | Assouplir RSI, tendance, signaux ou confluence, ou augmenter l'historique. |
| Données insuffisantes | `errors` augmente, logs/données du marché trop courtes. | Réduire les périodes ou choisir un marché/timeframe avec davantage d'historique. |
| Export CSV répond 409 | Le job est `pending`, `running` ou `failed`. | Attendre `completed`, annuler pour exporter le partiel, ou diagnostiquer l'échec. |
| Job introuvable après redémarrage | Le registre est en mémoire. | Relancer le scan ; télécharger les exports avant les redémarrages. |

## Diagnostic minimal

```powershell
cd backend
python -c "from main import app; print(app.title)"
python -m pytest -q
Invoke-RestMethod http://127.0.0.1:8000/api/health
Get-Content .\logs\scanner.log -Tail 100
```

La sonde `ok` ne garantit pas l'accès à Binance. Pour ce dernier, tester `/api/scanner/markets` et consulter les journaux.
