# État actuel des signaux

État revérifié le 29 juillet 2026. Ce document décrit le code actif, pas l’intention historique.

L'audit frontend transversal, l'inventaire legacy et le plan de dépréciation sont
dans [`frontend/structured-signals-migration-audit.md`](frontend/structured-signals-migration-audit.md).

## Sources canoniques

- Formules/classes/confluence : `backend/app/domain/indicators.py`.
- Normalisation et clôtures : `backend/app/domain/candles.py`.
- Assemblage scanner : `backend/app/services/scanner.py`.
- Snapshots/graphiques/marqueurs live : `backend/app/services/market_stream.py`.
- Assemblage replay : `backend/app/domain/backtesting.py`.
- Contrats scanner/profil : `backend/app/core/settings.py`, `models/scanner.py`.

`backend/indicators.py` ne contient pas de logique : il réexporte les primitives pour compatibilité.

Depuis la Phase 4, un builder commun `app.domain.indicator_bundle.build_indicator_signals` construit les signaux structurés `IndicatorSignal` (rsi/sma/ema/macd/bollinger/stochastique). Il est utilisé par le moteur canonique de replay (`app.domain.backtesting.evaluate_information_set`), par le passage unique du scanner et par `market_stream`. Ces signaux structurés sont exposés en plus des champs legacy via `ScanResult.indicator_signals` et `SignalObservation.indicator_signals` (additifs, sans rupture de compatibilité). La tendance (SMA/EMA) reste gérée par la logique historique multi-timeframe côté scanner/replay; seul `market_stream` (mono-timeframe) calcule aussi des signaux structurés sma/ema, exposés mais exclus du calcul de confluence pour éviter une divergence avec `detect_trend`.

Risque restant : l’assemblage des filtres/disponibilité conserve encore des chemins distincts entre scanner, marché et replay. La matrice legacy est exhaustive et un oracle de service compare scanner/replay ; tout nouveau vocabulaire structuré doit encore compléter ces garde-fous.

## Données et clôtures

Les lignes CCXT sont converties en nombres, les timestamp/OHLC non finis supprimés et un volume invalide remplacé par zéro. Une bougie est close si `open_time + durée_timeframe <= now`. Le scanner contrôle le minimum final après normalisation et retrait de l’open. Le bootstrap live ne fait pas `history[:-1]`.

Les trous sont connus par SQLite/backfill et traités par le backtest. Le scanner/live n’interrompent pas automatiquement un calcul pour un trou interne.

## Indicateurs

| Élément | Calcul/règle | Disponibilité et limites |
|---|---|---|
| RSI | Wilder via EWM alpha `1/period`, close, 14 par défaut | warm-up ; constante sans pertes → 100 |
| SMA | rolling mean, close | valeur après `period` points |
| EMA | EWM span, adjust false, close | valeur après `period` points |
| MACD | EMA fast-slow, signal EWM, histogramme | classe après deux couples MACD/signal valides |
| Bollinger | SMA ± `std_dev × std(ddof=0)` | bande dégénérée → `invalid_data` dans scanner/live/replay |
| Stochastique | %K sur high/low/close, %D SMA | plage constante → `invalid_data`; croisements prioritaires |
| Tendance | prix + deux MA par famille | bullish/bearish si familles disponibles concordent, sinon neutral ; aucune MA → unavailable |
| Confluence | moyenne pondérée de facteurs sur 100 | seuls facteurs disponibles et poids > 0 participent |

Paramètres personnalisables : périodes RSI/SMA/EMA/MACD/Bollinger/Stochastique, seuils RSI/Stochastique, écart Bollinger, poids et activations.

## Disponibilité

`Availability` :

- `available` : valeur calculable, y compris une classe neutral ;
- `insufficient_data` : warm-up/historique insuffisant ;
- `invalid_data` : données calculées mais dégénérées/non exploitables ;
- `disabled` : indicateur désactivé.

Il n’existe pas de littéral `unavailable` dans ce type. La tendance utilise son propre état `unavailable`. L’UI traduit les quatre causes et n’affiche pas un calcul absent comme neutral.

Correction de l’audit 2026-07-24 : le scanner marque désormais Bollinger/Stochastique constants `invalid_data`, en cohérence avec live et replay.

## Confirmed et provisional

`calculate_market_snapshots` produit :

- `confirmed` : uniquement les bougies closes ;
- `provisional` : historique complet incluant l’open, seulement si une open existe ;
- champs racine legacy : provisional si présent, sinon confirmed ;
- `profile` : profil exact utilisé.

Le scanner et le replay utilisent confirmed. Le replay provisional est explicitement non supporté, faute de révisions intrabar historiques.

Au passage à une nouvelle bougie, l’ancienne open est persistée close, le confirmed avance et une nouvelle provisional commence. Le store protège contre les anciens sockets et réconcilie REST après reconnexion.

## Profil

`MarketIndicatorConfig` valide un profil default, `scan` ou `custom`. Le lien d’un résultat scanner encode symbole, timeframe et profil dans l’URL. Changer le marché conserve le profil ; rechargement/partage restaure l’URL ; REST et WS reçoivent le même JSON.

La tendance scanner peut couvrir plusieurs timeframes (`ma_timeframes`, défaut 1w/1d/4h) et applique `min_trend_score`. Le snapshot marché classe uniquement le timeframe affiché : les deux valeurs ne doivent pas être assimilées.

## Confluence

Facteurs longs/repli haussier :

- RSI : 1 sous 30, 0,75 jusqu’au seuil, 0,3 sous 50, sinon 0 ;
- tendance : bullish 1, neutral 0,5, bearish 0 ;
- MACD : bullish 1, neutral 0,4, bearish 0 ;
- Bollinger : 1 / 0,75 / 0,35 / 0,1 / 0 ;
- Stochastique : bullish_cross 1, oversold 0,9, neutral 0,35, bearish_cross 0,1, overbought 0.

Le résultat contient score, grade, breakdown, poids effectifs et, par facteur, statut, raw value, classe, facteur, poids configuré/effectif, contribution et raison. Le détail est rendu dans `MarketMetrics` et la table scanner.

La confluence n’est ni une probabilité, ni un ensemble de facteurs indépendants. RSI/Stochastique/Bollinger et EMA/MACD sont corrélés ; le score est orienté long/repli et n’a pas de miroir short.

## Croisements et divergences

Les marqueurs live close-only couvrent :

- croisement EMA des deux premières périodes disponibles ;
- passage du MACD autour de sa ligne signal ;
- divergences RSI et MACD régulières/cachées.

Pivots : fenêtre gauche/droite stricte de 3 ; distance 5 à 60 ; variation de prix minimale 0,1 % ; delta RSI minimal 2 ; delta MACD minimal 0 (égalité acceptée, règle caractérisée). Le marqueur contient temps, position, forme, couleur, texte, catégorie, source, type et détails des deux pivots. Il est placé au second pivot, bien qu’il ne soit connu qu’après la fenêtre droite : l’UI peut donc sembler « backdater » visuellement.

Les divergences ne participent ni au scanner, ni à la confluence, ni au replay phase 3.

## Contrats backend/frontend

Pydantic et TypeScript synchronisent MACD, Bollinger, Stochastique, grades,
tendance, disponibilité, marqueurs et signaux structurés. Le schéma Zod commun
contrôle les six clés d'indicateur et conserve `indicator_signals` dans les flux
scanner, marché et backtest jusqu'aux stores. Le champ reste optionnel pour les
anciens payloads. Les interfaces scanner, marché et backtest le présentent avec
la bibliothèque visuelle partagée, sans recalcul.

## Tests

Backend relancé en Phase 5.8 : 540 tests passés, 1 ignoré et 27 subtests
passés, avec deux avertissements pandas préexistants. Les fichiers clés sont :

- `test_indicators_math.py` : séries connues, warm-up, custom, constantes, NaN ;
- `test_signal_classification.py` : bornes/égalités, croisements, grades, confluence ;
- `test_divergences.py` : pivots, quatre types, distances, confirmation ;
- `test_phase1_data_quality.py` : minimum final et clôtures temporelles ;
- `test_phase1_contracts.py` : Pydantic/OpenAPI ;
- `test_phase2_signal_coherence.py` : disponibilité, snapshots, profil et parité.
- `test_structured_signal_filters_v1_contract.py` : JSON v1, matrice legacy,
  statuts, priorité et fingerprints.
- `test_scanner_service.py` : oracle scanner/replay et compteurs d'appels.

Le frontend possède des tests dédiés aux contrats structurés, frontières
marché/scanner/backtest, stores, sockets, profils, helpers transversaux et rendus
historiques. Validation Phase 5.8 : 41 fichiers et 251 tests réussis, sans test
ignoré ou échoué ; typecheck, lint et build réussis.

## Phase 5.7 — filtres structurés

`ScanConfig` accepte le champ additif `structured_signal_filters`, explicitement
versionné en v1. Le moteur pur combine les valeurs d'une condition en OR, les
conditions selon `all` ou `any` et les indicateurs en AND. Sans condition de
statut, un signal doit être `available`.

La priorité est locale à chaque indicateur : groupe structuré présent, sinon
fallback legacy. Un groupe vide est une neutralisation explicite sans fallback.
`check_signal_filters` reste inchangée pour un payload entièrement legacy. La
matrice exhaustive et la nuance Stochastique sont dans
[`backend/structured-signal-filters.md`](backend/structured-signal-filters.md).
Les règles figées, fingerprints, oracles et compteurs Phase 5.8 sont dans
[`backend/structured-signal-filters-v1-stability.md`](backend/structured-signal-filters-v1-stability.md).

## Limites prioritaires

1. conserver la parité des assemblages scanner/replay sans réintroduire de double calcul runtime ;
2. compléter les oracles lors de toute nouvelle valeur de `signal` ou `state` ;
3. intégrer causalement les divergences au replay avant toute mesure ;
4. traiter/signaliser les trous dans scanner/live ;
5. décider si la tendance marché doit exposer l’agrégation multi-TF ;
6. conserver l’interprétation non probabiliste et les corrélations de facteurs.

## Phase 8.2 — observations ATR/ADX/Supertrend

Le contrat accepte désormais `atr`, `adx` et `supertrend`, ainsi qu'un champ
optionnel `components`. ATR expose TR/ATR/NATR/variation et reste
directionnellement neutre. ADX expose ADX/+DI/-DI/DX. Supertrend expose sa ligne,
ses bandes, son ATR et sa distance normalisée.

Les blocs de configuration version 1 sont optionnels et désactivés par défaut.
Ils empruntent le builder partagé scanner/marché/replay. La confluence reçoit
toujours exclusivement les indicateurs historiques, et les nouveaux noms ne
sont pas admissibles dans les filtres structurés v1.

## Phase 8.3 — largeur Bollinger, Donchian et Keltner

Bollinger expose ses bandes, leur largeur absolue et normalisée et la position
non bornée du prix dans `components`, sans modifier son signal, state,
direction, strength, reason ni son usage historique. Donchian sépare le canal
descriptif incluant `t` du canal précédent arrêté à `t-1`. Keltner réutilise
l'EMA et l'ATR Wilder ; ses événements comparent le close courant aux bandes
précédentes et ne se répètent pas hors canal.

Donchian (`20`) et Keltner (`EMA 20`, `ATR 10`, multiplicateur `2`) sont des
blocs versionnés optionnels, désactivés par défaut. Ils traversent scanner,
marché, replay, API et frontend. Aucun n'est admissible dans les filtres v1 ou
dans la confluence, et ils ne modifient ni accepted, outcomes, trades, equity
ou résumé portefeuille. Aucun squeeze ou régime n'est détecté.
