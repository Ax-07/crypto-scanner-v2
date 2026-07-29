# WebSockets côté frontend

Le projet consomme deux flux distincts. Leur protocole serveur complet est documenté dans [WebSockets backend](../backend/websockets.md).

## Origine des connexions

Le socket scanner dérive toujours de `VITE_API_URL`, en transformant `http:` en `ws:` et `https:` en `wss:`.

Pour le marché, l’ordre de priorité est :

1. `VITE_WS_URL` ;
2. `VITE_API_URL` avec protocole WebSocket ;
3. l’origine courante de la page.

Un slash final est retiré avant l’ajout du chemin. En HTTPS, configurer `wss://` pour éviter le blocage de contenu mixte.

## Progression scanner

Connexion :

```text
ws://127.0.0.1:8000/api/scanner/ws/{job_id}
```

Chaque message correspond à un `ScanJob` sans les résultats volumineux. Exemple abrégé :

```json
{
  "id": "a1b2c3",
  "status": "running",
  "progress": {
    "processed": 12,
    "total": 50,
    "successful": 3,
    "filtered": 8,
    "errors": 1,
    "percent": 24
  },
  "error": null,
  "result_count": 3
}
```

Le frontend valide chaque snapshot avec `scannerJobMessageSchema` (Zod) avant de
modifier Zustand, puis récupère les résultats par HTTP après `completed` ou
`cancelled`. Un message invalide place l’interface en erreur sans remplacer le job
courant. Le flux est fermé après `failed` et n’a pas de reconnexion automatique.

## Marché temps réel

Connexion :

```text
ws://127.0.0.1:8000/ws?symbol=BTC%2FUSDC&timeframe=1h
```

`include_history=false` désactive le premier message `history` sans désactiver
les updates. La valeur par défaut reste `true` pour les anciens clients. Le
frontend charge SQLite par REST et utilise `false`, sauf lorsque cette première
lecture est vide : il demande alors un bootstrap puis relit REST.

Le premier message utile est un historique :

```json
{
  "type": "history",
  "symbol": "BTC/USDC",
  "timeframe": "1h",
  "candles": [{ "time": 1784710800, "open": 64000, "high": 64500, "low": 63800, "close": 64300, "volume": 125.4 }],
  "indicators": { "rsi_14": [{ "time": 1784710800, "value": 48.2 }] },
  "markers": [],
  "snapshot": {
    "price": 64300,
    "rsi": 48.2,
    "trend": "bullish",
    "indicator_signals": {
      "rsi": {
        "status": "available",
        "direction": "bullish",
        "signal": "exit_oversold",
        "state": "near_oversold",
        "strength": 0.75,
        "reason": "RSI sort de la zone de survente",
        "raw_value": 31.4
      }
    }
  }
}
```

Les messages suivants sont incrémentaux :

```json
{
  "type": "update",
  "candle": { "time": 1784714400, "open": 64300, "high": 64600, "low": 64200, "close": 64550, "volume": 82.1 },
  "indicators": { "rsi_14": { "time": 1784714400, "value": 51.7 } },
  "markers": [],
  "snapshot": { "price": 64550, "rsi": 51.7 }
}
```

Un message `{ "type": "error", "message": "..." }` place la connexion en erreur. Un JSON invalide produit le message local « Message WebSocket invalide ».

`indicator_signals` est optionnel pour accepter les anciens serveurs. Lorsqu'il
est présent dans `history` ou `update`, le schéma Zod le valide dans les vues
racine, `confirmed` et `provisional`, puis le store conserve le snapshot complet.
Son absence ne crée aucun fallback.

Le protocole réel ne possède pas de messages autonomes `confirmed` ou
`provisional` : ce sont deux vues de `snapshot` dans les messages `history` et
`update`. `confirmed` est calculé uniquement sur les bougies closes.
`provisional`, marqué `is_forming=true`, inclut la bougie ouverte et peut changer
avant sa clôture. Les champs racine legacy correspondent au provisoire lorsqu'il
existe, sinon au confirmé. La page marché affiche les deux vues sans substituer
l'une à l'autre.

## Reconnexion et courses

À la fermeture du flux marché, le hook reconnecte après 2 secondes. Le délai est multiplié par 1,5 jusqu’à un maximum de 15 secondes et revient à 2 secondes après une ouverture réussie.

Chaque connexion reçoit une génération. Tous ses gestionnaires vérifient que le hook est encore actif, que la génération est courante et, pour les messages, que l’instance correspond toujours. Cela empêche une fermeture ou un message tardif d’un ancien marché de modifier le store courant.

Après chaque ouverture, le client relit SQLite après la dernière bougie connue
avec une superposition d'une milliseconde. Cette réconciliation met à jour la
bougie courante et récupère les clôtures manquées pendant la coupure.

Le store expose exactement `connecting`, `connected`, `disconnected` et `error`.
Une reconnexion repasse par `connecting`; aucun état `reconnecting` ni compteur de
tentatives n'est disponible. L'interface affiche donc la reconnexion automatique
sans inventer de métrique. Une erreur utilise une alerte et conserve les derniers
snapshots, avec l'indication qu'ils peuvent être figés. Seul le court libellé du
statut est en `aria-live="polite"` afin de ne pas annoncer chaque variation de
marché.
