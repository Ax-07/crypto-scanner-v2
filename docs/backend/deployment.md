# Déploiement

## Mode pris en charge

Le point d'entrée est `backend/main.py`, importé avec `main:app` depuis le dossier `backend` :

```powershell
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Pour exposer le service derrière un reverse proxy, l'écoute peut être adaptée à l'environnement. Le dépôt ne contient actuellement ni `Dockerfile`, ni `docker-compose.yml`, ni configuration Gunicorn ; aucun mode conteneur n'est donc documenté comme supporté.

## Build React

```powershell
cd frontend
pnpm install
pnpm run build
cd ..\backend
python -m uvicorn main:app
```

FastAPI résout le build dans `frontend/dist` relativement au dépôt. Sans ce dossier, l'API reste disponible mais `/` répond 503.

## Variables et fichiers

Injecter les variables décrites dans [configuration.md](configuration.md) avant le démarrage. Le processus doit pouvoir créer `LOG_DIR` et écrire `scanner.log`. Aucune clé Binance n'est requise pour les marchés publics actuels.

Le reverse proxy doit :

- transmettre les connexions HTTP longues ;
- conserver les en-têtes `Upgrade` et `Connection` pour les deux WebSockets ;
- appliquer une durée d'inactivité compatible avec le flux marché ;
- terminer TLS si des clients HTTPS doivent utiliser `wss://` ;
- transmettre une origine autorisée par `CORS_ORIGINS` pour les appels navigateur.

## Un seul worker

Ne pas lancer plusieurs workers Uvicorn/Gunicorn pour ce backend dans son état actuel. `ScanManager` est un singleton en mémoire propre à chaque processus. Avec plusieurs workers, la création, la lecture, l'annulation et le WebSocket d'un même job pourraient atteindre des registres différents.

Le streaming `/ws` ne dépend pas de ce registre, mais cette propriété ne rend pas l'ensemble de l'API multi-processus. Une montée en charge nécessiterait un stockage partagé et un mécanisme de publication distribué, absents du dépôt.

## Santé, arrêt et journaux

Utiliser `/api/health` comme sonde minimale et `/health` pour contrôler les valeurs du flux. Ces sondes ne testent pas une connexion Binance.

Un arrêt du processus détruit les jobs et déconnecte les sockets. Les exchanges ouverts dans les coroutines ont un `finally`, mais aucun protocole de drainage persistant n'est implémenté. Prévoir une période de grâce du superviseur et avertir les clients avant un redémarrage planifié.

Les journaux vont vers stdout/stderr et `LOG_DIR/scanner.log`. Leur rotation n'est pas gérée par l'application ; elle appartient au superviseur ou au système.
