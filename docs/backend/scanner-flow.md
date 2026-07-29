# Flux complet d'un scan

## Séquence

1. `POST /api/scanner/jobs` reçoit un objet JSON.
2. Pydantic construit `ScanConfig`, normalise certains champs et applique les validations croisées.
3. `ScanManager.create_job()` purge les anciens jobs terminés, enregistre un `ScanJob` `pending`, sa condition et sa version.
4. Une tâche `asyncio` lance `_run_job()`, qui passe le job à `running`, renseigne `started_at` et publie cet état.
5. `ScannerService.scan()` crée l'exchange configuré.
6. `load_filtered_symbols()` charge et filtre les marchés, les trie, puis applique `max_pairs`.
7. La progression reçoit `total`; un premier snapshot est publié.
8. Jusqu'à `max_concurrency` tâches d'analyse sont créées. Chaque fin de tâche libère une place pour le symbole suivant : il s'agit d'une fenêtre progressive de tâches, renforcée par un sémaphore, pas d'une file de workers persistants.
9. La limite OHLCV principale prend le maximum de `min_ohlcv_bars` et des besoins des indicateurs actifs, avec une marge de 10. Le scanner demande une ligne supplémentaire.
10. `get_closed_candles()` retire toute bougie dont le timeframe complet n'est pas écoulé.
11. Les indicateurs sont calculés selon l'ordre décrit ci-dessous.
12. Un rejet produit `filtered`; une exception isolée ou une donnée obligatoire absente produit `error` ; sinon un `ScanResult` est ajouté.
13. Après chaque symbole, `processed` et exactement un compteur d'issue sont incrémentés, puis une copie de la progression est publiée.
14. Les résultats sont triés.
15. L'exchange est fermé dans `finally`, y compris après annulation.
16. Le manager passe le job à `completed`, `cancelled` ou `failed`, fixe `completed_at` et publie le dernier état.

## Ordre des filtres

Pour un symbole :

1. données principales disponibles et au moins une bougie clôturée ;
2. RSI calculable puis filtre strict `rsi >= rsi_threshold` ;
3. tendance MA multi-timeframes puis `trend_score < min_trend_score` ;
4. MACD, Bollinger et Stochastique actifs ;
5. listes `filter_*` ;
6. score de confluence puis `confluence_score < min_confluence_score` ;
7. construction du résultat.

Le RSI précoce évite donc les requêtes MA supplémentaires pour une paire déjà rejetée. La tendance évite les indicateurs multiples et la confluence. Lorsqu'un indicateur est désactivé, sa limite, son calcul et son filtre sont ignorés.

## Cache et historique

Le cache appartient à l'instance de `ScannerService` et utilise `(symbol, timeframe)` comme clé. Une donnée en cache est réutilisée si elle contient au moins `limit - 1` lignes, tolérance cohérente avec la ligne supplémentaire demandée pour la bougie ouverte. Le cache n'est ni global ni partagé entre jobs.

Le timeframe principal peut être réutilisé pour les MA s'il contient assez de lignes. Les autres timeframes sont récupérés au besoin.

## Tri final

La première stratégie active s'applique :

1. confluence décroissante si `use_confluence_score` ;
2. RSI croissant si `use_rsi` ;
3. `trend_score` décroissant si `use_ma` ;
4. symbole alphabétique.

Le symbole départage toujours les égalités des trois premiers modes. Les valeurs absentes sont placées derrière les valeurs présentes.

Voir [les jobs et l'annulation](jobs-and-progress.md) et [les indicateurs](indicators.md).
