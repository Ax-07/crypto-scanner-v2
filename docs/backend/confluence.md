# Score de confluence

La confluence agrège des signaux techniques hétérogènes sur une échelle de 0 à 100. Elle sert au filtrage et au classement ; ce n'est ni une probabilité ni une estimation de gain.

## Facteurs bruts

Chaque facteur se situe entre 0 et 1 :

| Indicateur | Signal | Facteur |
|---|---|---:|
| RSI | `rsi <= 30` | 1,00 |
| RSI | `30 < rsi <= rsi_threshold` | 0,75 |
| RSI | `rsi_threshold < rsi < 50` | 0,30 |
| RSI | `rsi >= 50` | 0,00 |
| Tendance | `trend_score / max_trend_score` | borné entre 0 et 1 |
| MACD | `bullish` / `neutral` / `bearish` | 1,00 / 0,40 / 0,00 |
| Bollinger | `oversold` / `near_oversold` / `neutral` / `near_overbought` / `overbought` | 1,00 / 0,75 / 0,35 / 0,10 / 0,00 |
| Stochastique | `bullish_cross` / `oversold` / `neutral` / `bearish_cross` / `overbought` | 1,00 / 0,90 / 0,35 / 0,10 / 0,00 |

Une valeur RSI non finie n'ajoute aucun facteur. La tendance exige un score présent et au moins un timeframe MA calculable. Les signaux inconnus MACD deviennent 0 ; les positions Bollinger ou Stochastique inconnues n'ajoutent pas de facteur.

## Poids configurés et effectifs

`ScannerService` écarte d'abord les indicateurs désactivés. `calculate_confluence_score()` conserve ensuite les facteurs calculables de poids strictement positif.

Pour un ensemble actif `A` :

```text
poids_effectif(i) = poids(i) / somme_des_poids(A) × 100
contribution(i) = facteur(i) × poids_effectif(i)
score = somme des contributions
```

`effective_weights` et `breakdown` sont arrondis à deux décimales, tout comme `score`. Le score reste sur 100 même si des indicateurs sont désactivés ou non calculables.

## Exemple RSI et MACD seulement

Poids configurés : RSI 20, MACD 20. Somme active : 40. Les poids effectifs valent donc 50 % chacun.

Avec un RSI de 25 (facteur 1) et un MACD `neutral` (facteur 0,4) :

```json
{
  "score": 70.0,
  "grade": "B",
  "breakdown": {"rsi": 50.0, "macd": 20.0},
  "effective_weights": {"rsi": 50.0, "macd": 50.0}
}
```

## Grades et filtre

| Score | Grade |
|---:|---|
| ≥ 90 | `A+` |
| ≥ 80 | `A` |
| ≥ 70 | `B` |
| ≥ 60 | `C` |
| ≥ 50 | `D` |
| < 50 | `F` |

Si `use_confluence_score=true` et que le score calculé est strictement inférieur à `min_confluence_score`, la paire est filtrée. Un score égal au seuil passe.

La validation de `ScanConfig` interdit une confluence active sans aucun indicateur actif de poids positif. Malgré cela, les données peuvent rendre tous les facteurs incalculables : la fonction retourne alors `None`, le résultat conserve les champs de confluence vides ou `null` et le seuil minimum ne s'applique pas.

Les poids n'ont pas besoin de totaliser 100 et les poids nuls sont autorisés. Les clés acceptées sont exclusivement `rsi`, `trend`, `macd`, `bollinger` et `stochastic`.

## Mode structuré (`indicator_signals`)

`calculate_confluence_score()` accepte un paramètre optionnel `indicator_signals`, une table `{nom_indicateur: IndicatorSignal}` (voir `docs/backend/indicators.md`). Ce mode rétrocompatible est branché sur le moteur canonique du replay et sur le snapshot marché. Le scanner construit les mêmes signaux dans son passage unique ; sa parité de score est contrôlée en tests. Le marché exclut volontairement les clés structurées `sma`/`ema` de son appel de confluence afin de conserver son facteur historique `trend`.

Clés reconnues: `rsi`, `sma`, `ema` (agrégées en un facteur `trend` unique), `macd`, `bollinger`, `stochastic`.

### Règle de priorité

Pour chaque indicateur, si sa clé est présente dans `indicator_signals`, le signal structuré est **toujours prioritaire** sur les arguments historiques correspondants (`rsi_value`, `macd_signal`, `bb_position`, `stoch_signal`, `trend_score`/`trend_states`) — y compris lorsque le signal structuré est indisponible (`status != "available"`): l'indicateur ne participe alors pas au score, même si l'argument historique aurait donné un résultat exploitable. Le repli sur l'argument historique ne s'applique que si la clé structurée est **totalement absente** de `indicator_signals`.

### Conversion signal → facteur

`calculate_signal_factor(indicator, signal)` retourne `None` si `signal["status"] != "available"`. Sinon, chaque indicateur a sa propre table:

| Indicateur | Champ lu | États/événements → facteur |
|---|---|---|
| `rsi` | `state` | `oversold` 1,00 · `near_oversold` 0,75 · `neutral` 0,30 · `near_overbought` 0,00 · `overbought` 0,00 |
| `sma` / `ema` | `signal` | `bullish_cross`/`bullish_alignment` 1,00 · `price_above` 0,75 · `neutral` 0,50 · `price_below` 0,25 · `bearish_alignment`/`bearish_cross` 0,00 |
| `macd` | `direction` | `bullish` 1,00 · `neutral` 0,40 · `bearish` 0,00 |
| `bollinger` | `state` | identique à la table historique ci-dessus (`oversold` → `overbought`) |
| `stochastic` | `signal` | identique à la table historique ci-dessus (`bullish_cross` → `overbought`) |

`calculate_signal_factor("rsi", signal)` (table ci-dessus, basée sur `state`) reste disponible mais n'est **plus** utilisée pour le RSI par `calculate_confluence_score()` en mode structuré: elle ne permet pas de distinguer tous les cas historiques dépendant du seuil configurable `rsi_threshold` (ex. RSI=45 et RSI=55 partagent `state="neutral"` mais ont des facteurs historiques différents, 0,30 et 0,00).

`calculate_confluence_score()` appelle donc `calculate_rsi_signal_factor(signal, rsi_threshold=rsi_threshold)` pour la clé `"rsi"`, qui reproduit **exactement** les seuils historiques à partir de `signal["raw_value"]` (la valeur RSI brute, voir `docs/backend/indicators.md`):

| Condition sur `raw_value` | Facteur |
|---|---:|
| `<= 30` | 1,00 |
| `<= rsi_threshold` | 0,75 |
| `< 50` | 0,30 |
| `>= 50` | 0,00 |

Elle retourne `None` si `signal["status"] != "available"` ou si `raw_value` est absent/non fini (l'indicateur ne participe alors pas au score, conformément à la règle de priorité ci-dessus). Les autres indicateurs (`sma`, `ema`, `macd`, `bollinger`, `stochastic`) continuent d'utiliser `calculate_signal_factor`/`calculate_trend_signal_factor` sans changement.

`calculate_trend_signal_factor(signals)` agrège une séquence de signaux SMA/EMA (mêmes états que le tableau ci-dessus) par moyenne simple des facteurs disponibles; retourne `None` si aucun n'est exploitable. Un désaccord SMA/EMA se traduit par une moyenne proche de 0,5, comme le fait déjà `detect_trend` avec `"neutral"`.

### Enrichissement de `details`

En mode structuré, `details[nom]` gagne quatre champs supplémentaires (`None` si aucun signal structuré n'a été utilisé pour cet indicateur): `structured_signal`, `structured_state`, `direction`, `strength` (recopiés depuis l'`IndicatorSignal` source). Les champs historiques (`status`, `raw_value`, `signal`, `factor`, `configured_weight`, `effective_weight`, `contribution`, `reason`) conservent leur forme et leur sémantique; `status`/`reason` reflètent alors ceux du signal structuré plutôt que la table `availability`/`raw_values` historique, et `raw_value` reflète `signal["raw_value"]` plutôt que la table `raw_values` historique dès qu'une clé structurée est présente.

### Câblage dans les services

Les signaux structurés `IndicatorSignal` (rsi/macd/bollinger/stochastic, +sma/ema selon le service) sont désormais construits via un builder commun, `app.domain.indicator_bundle.build_indicator_signals(...)`, et exposés dans les trois services:

- **Moteur canonique** (`app.domain.backtesting.evaluate_information_set`, utilisé par le backtest et les oracles): appelle `build_indicator_signals(...)` sans `sma`/`ema` (la tendance reste gérée en multi-timeframe historique via `trend_states`/`trend_score`), passe le résultat à `calculate_confluence_score(indicator_signals=...)`, et l'expose via le nouveau champ `SignalObservation.indicator_signals: dict[str, IndicatorSignalModel]`.
- **`ScannerService.analyze_symbol`**: construit une seule fois les mêmes signaux à partir de ses séries déjà nécessaires aux champs legacy, puis les place dans `ScanResult.indicator_signals`.
- **`market_stream.calculate_market_snapshot`** (mono-timeframe): construit en plus des signaux structurés `sma`/`ema` (séries disponibles localement, contrairement au moteur canonique). Ces clés sont exposées dans la sortie `indicator_signals` du snapshot mais **volontairement exclues** de l'appel à `calculate_confluence_score`, car `calculate_trend_signal_factor` (moyenne simple des facteurs sma/ema) peut diverger subtilement de `detect_trend`/`trend_states` (règle de blending par état) sur des cas limites; le score de confluence continue donc d'utiliser le mode historique pour la tendance dans ce service, comme avant ce câblage.

Compatibilité: `indicator_signals` est additif partout (nouveau champ optionnel avec `default_factory=dict`), aucun champ historique n'a été retiré ou renommé. Les tests anti-look-ahead (`tests/test_backtesting_domain.py::test_future_mutation_cannot_change_indicator_signals`) confirment que la mutation de bougies futures ne change pas les `indicator_signals` calculés, au même titre que les autres champs de `SignalObservation`.

L'export CSV (`app.exporters.csv_exporter`) n'inclut pas `indicator_signals` (décision documentée dans le code: structure imbriquée, pas de consommateur identifié à ce stade).

## Distinction entre confluence et filtres structurés

La Phase 5.7 ajoute un moteur de filtres versionné, indépendant du calcul de
confluence. Il lit les mêmes `IndicatorSignal`, mais ne change aucun facteur,
poids, score ou grade. Les règles `all`/`any`, le statut disponible implicite et
le fallback legacy par indicateur sont documentés dans
[structured-signal-filters.md](structured-signal-filters.md).
La mesure de parité et la suppression du second passage scanner sont détaillées
dans [structured-signal-filters-v1-stability.md](structured-signal-filters-v1-stability.md).
