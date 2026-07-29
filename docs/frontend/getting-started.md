# Démarrage local

## Prérequis

- Node.js compatible avec Vite 8 : `^20.19.0` ou `>=22.12.0`.
- pnpm 10 ; le projet déclare `pnpm@10.15.1` dans `package.json`.
- Le backend FastAPI disponible, par défaut sur le port `8000`.

## Installation et lancement

Depuis la racine du dépôt :

```bash
cd frontend
pnpm install --frozen-lockfile
Copy-Item .env.example .env.local
pnpm run dev
```

Vite écoute sur `http://127.0.0.1:5173` avec un port strict. En cas de conflit, libérer ce port ou modifier explicitement `vite.config.ts`.

Sous Bash, remplacer la commande PowerShell de copie par `cp .env.example .env.local`.

## Variables d’environnement

```dotenv
VITE_API_URL=http://127.0.0.1:8000
VITE_WS_URL=ws://127.0.0.1:8000
```

| Variable | Usage | Repli |
| --- | --- | --- |
| `VITE_API_URL` | Origine HTTP utilisée par le client scanner | `http://localhost:8000` |
| `VITE_WS_URL` | Origine du flux marché | origine dérivée de `VITE_API_URL`, puis origine de la page |

Les suffixes `/api/...` et `/ws?...` sont ajoutés par le code. Ne pas les inclure dans ces variables. Après une modification de `.env.local`, redémarrer Vite.

Le proxy de développement ne couvre que `/health` et `/ws`. Les appels REST scanner utilisent une origine absolue issue de `VITE_API_URL` ; le backend doit donc autoriser l’origine du frontend via CORS.

## Vérification rapide

```bash
pnpm run typecheck
pnpm run lint
pnpm run test
pnpm run build
```

`pnpm run preview` sert ensuite le build local pour vérifier le comportement de production. Il ne remplace pas un serveur configuré pour renvoyer `index.html` sur les routes du navigateur.
