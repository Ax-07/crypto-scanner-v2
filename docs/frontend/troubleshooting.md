# Dépannage

## Le frontend ne démarre pas

- Vérifier la version de Node avec `node --version` ; Vite 8 exige `^20.19.0` ou `>=22.12.0`.
- Utiliser `pnpm install --frozen-lockfile`, pas npm.
- Le port `127.0.0.1:5173` est strict : arrêter l’autre processus qui l’utilise.

## Les appels API échouent

- Vérifier `VITE_API_URL` sans suffixe `/api` et redémarrer Vite.
- Tester l’endpoint backend `/health`.
- Examiner le statut HTTP et le champ `detail` dans l’onglet Réseau.
- Si le navigateur signale CORS, autoriser `http://127.0.0.1:5173` côté backend.
- `localhost` et `127.0.0.1` sont des origines différentes ; utiliser une configuration cohérente.

## Le marché ne se connecte pas

- Vérifier `VITE_WS_URL` sans suffixe `/ws`.
- Sous HTTPS, utiliser `wss://`.
- Confirmer que le reverse proxy transmet l’upgrade WebSocket.
- Ouvrir une URL avec symbole encodé, par exemple `/market?symbol=BTC%2FUSDC&timeframe=1h`.
- Une paire saisie dans la toolbar n’est appliquée que si elle figure dans la liste serveur spot/USDC.

Le hook reconnecte automatiquement avec backoff. Une succession de connexions toutes les 2 à 15 secondes indique généralement une fermeture serveur ou proxy.

## Avertissements React connus

`Received NaN for the colSpan attribute` indique qu’un nombre de colonnes indéfini a atteint la cellule vide du tableau. Le tableau courant calcule `colSpan` depuis un tableau de colonnes toujours défini ; toute nouvelle colonne doit passer par ce même calcul.

`No HydrateFallback element provided` indique qu’une route lazy n’a pas de secours initial. La route racine fournit actuellement `HydrateFallback: RouteLoading`; conserver ce fallback lors d’une restructuration du routeur.

`installHook.js` dans la pile provient généralement du hook React DevTools qui relaie l’avertissement : chercher le premier composant applicatif mentionné plus bas dans la pile.

## Une route directe renvoie 404

Le build est une SPA. Configurer le serveur pour servir `index.html` sur les routes frontend inconnues. Le serveur de développement et `vite preview` le font déjà, mais un serveur statique générique peut nécessiter une règle explicite.

## Un ancien marché continue d’écrire

Vérifier que l’effet socket dépend de `symbol` et `timeframe`, invalide sa génération au cleanup et ferme l’instance. Ne pas stocker la socket dans Zustand et ne pas retirer les gardes d’identité des callbacks.

## Diagnostic reproductible

```bash
pnpm run typecheck
pnpm run lint
pnpm run test
pnpm run build
```

Noter ensuite l’URL exacte, le statut réseau, le payload fautif et la première frame applicative de la console. Ces éléments permettent de distinguer validation, transport et rendu.
