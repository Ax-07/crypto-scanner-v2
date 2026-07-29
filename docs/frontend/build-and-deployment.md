# Build et déploiement

## Production

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm run build
```

Le script exécute d’abord `tsc -b`, puis `vite build`. Les fichiers statiques sont produits dans `frontend/dist`.

Pour une validation locale :

```bash
pnpm run preview
```

## Variables au build

Les variables `VITE_*` sont intégrées au bundle au moment du build. Fournir les origines publiques correspondant à l’environnement cible :

```dotenv
VITE_API_URL=https://api.example.com
VITE_WS_URL=wss://api.example.com
```

Elles ne doivent contenir ni secret ni jeton. Tout contenu `VITE_*` est lisible par le navigateur.

## Exigences du serveur statique

- Servir `dist` avec une politique de cache adaptée : longue durée pour les assets fingerprintés, revalidation pour `index.html`.
- Réécrire les routes inconnues vers `index.html` afin que React Router traite `/scanner` et `/market`.
- Autoriser les connexions WebSocket et leur upgrade sur l’origine configurée.
- En HTTPS, utiliser uniquement HTTPS/WSS.
- Configurer CORS côté API pour l’origine publique du frontend si les deux origines diffèrent.

Exemple conceptuel de fallback : une requête de fichier existant sert ce fichier ; toute autre requête frontend sert `/index.html`. Ne pas appliquer cette réécriture aux routes API ou WebSocket sur un reverse proxy partagé.

## Contrôles de livraison

```bash
pnpm run typecheck
pnpm run lint
pnpm run test
pnpm run build
```

Vérifier ensuite directement une URL profonde, le rafraîchissement de `/market?...`, le démarrage d’un scan, le téléchargement CSV et une reconnexion WebSocket.
