# Fonctionnalité marché

## Profil et états de calcul

Le profil est conservé dans l'URL et transmis à REST/WebSocket. Les cartes
affichent la valeur confirmée en premier, puis la valeur provisoire « En
formation ». L'indisponibilité et les erreurs de connexion sont visibles. Le
détail repliable de confluence expose poids et contributions sans présenter le
score comme une probabilité.

La page affiche le statut WebSocket avec texte, icône et badge. Les quatre états
réels sont `connecting`, `connected`, `disconnected` et `error`. Une erreur produit
une alerte expliquant que les dernières données restent affichées mais peuvent
être figées ; la reconnexion automatique existante continue sans bouton ou socket
supplémentaire.

## Sources de vérité

`MarketPage` valide `symbol` et `timeframe` depuis l'URL. SQLite est la source de
vérité de l'historique ; le WebSocket Binance est la source des changements
temps réel. Le hook REST initialise le store avant l'ouverture du socket.

Les timeframes acceptés vont de `1m` à `1w`, selon la liste canonique du projet.
Changer de paire ou de timeframe annule les requêtes, incrémente une génération,
ferme l'ancien socket et vide les données sans perdre les préférences visuelles.

## Pagination

La première requête lit les dernières bougies. La souscription Lightweight
Charts à la plage logique appelle `loadMore()` lorsqu'il reste moins de
`VITE_MARKET_PREFETCH_THRESHOLD_BARS` avant le bord gauche. La page suivante
utilise `before=earliestLoadedTime`, curseur exclusif en millisecondes.

Une seule requête historique peut être active. Les lots sont fusionnés par
timestamp, triés et dédupliqués. Avant `setData`, le graphique mémorise la plage
logique ; après préfixage, il ajoute aux deux bornes le nombre réel de nouvelles
bougies. Aucun délai arbitraire ni `fitContent()` automatique n'est utilisé.

Les commandes permettent de suivre le temps réel, ajuster la vue, charger une
page, enchaîner les pages jusqu'au début (opération annulable) ou revenir à la
dernière bougie. Le statut, les erreurs REST/WS, le nombre chargé/disponible, la
complétude et les trous sont visibles.

## Indicateurs et temps réel

L'API renvoie les indicateurs et marqueurs calculés en Python avec préchauffage.
Le frontend ne duplique pas les formules. Les pages fusionnent leurs points et
ne tronquent plus les marqueurs à 400.

Le nouveau client ouvre normalement `/ws?...&include_history=false`. Si la
première lecture SQLite est vide, il demande temporairement
`include_history=true`, laisse le socket synchroniser les dernières bougies,
puis relit immédiatement REST pour obtenir couverture et pagination. À chaque
reconnexion normale, il relit les lignes SQLite après la dernière bougie connue
avec une superposition d'une milliseconde. Un message `history` est toujours
fusionné et ne remplace jamais les pages chargées.

## Snapshots et signaux structurés

Les messages `history` et `update` transportent un `snapshot` avec deux vues :

- `confirmed` utilise uniquement les bougies closes ;
- `provisional` inclut la bougie ouverte, porte `is_forming=true` et n'existe que
  lorsqu'une bougie est en formation.

Au passage à une nouvelle bougie, l'ancienne bougie ouverte rejoint les closes :
le confirmé avance et un nouveau provisoire commence. Le navigateur ne déduit
jamais ce statut depuis son heure locale. Les champs racine du snapshot restent
un alias legacy du provisoire s'il existe, sinon du confirmé.

Sous le graphique, `MarketSignalsSection` compose deux
`MarketSignalSnapshot` et la bibliothèque `IndicatorSignalsPanel`. RSI, SMA, EMA,
MACD, Bollinger et Stochastique peuvent être affichés, dans l'ordre canonique et
sans calcul frontend. Score et grade de confluence viennent directement du
backend. SMA/EMA restent des signaux individuels : ils ne remplacent pas le
facteur historique `trend`, calculé par `detect_trend` pour la confluence marché.

Un champ `indicator_signals` absent reste distinct de `{}` afin de préserver les
anciens messages. Un dictionnaire partiel n'affiche que les indicateurs reçus et
les statuts d'indisponibilité sont transmis sans transformation.

Sur mobile, les vues sont navigables par onglets clavier, confirmé sélectionné
initialement. Sur desktop, elles sont côte à côte. La section reste après le
graphique afin de préserver sa priorité visuelle. Le scanner est déjà migré ; le
backtest reste volontairement hors de cette phase.

## Configuration et mémoire

- `VITE_MARKET_INITIAL_CANDLE_LIMIT=2000`
- `VITE_MARKET_HISTORY_PAGE_LIMIT=2000`
- `VITE_MARKET_PREFETCH_THRESHOLD_BARS=100`
- `VITE_MARKET_MAX_CANDLES_IN_MEMORY=0`

La valeur mémoire `0` conserve tout l'historique chargé. Une valeur positive
arrête la pagination à cette taille et est affichée dans la page ; ce mode ne
prétend donc pas présenter tout l'historique simultanément.
