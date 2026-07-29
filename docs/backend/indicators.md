# Indicateurs et tendance

Les fonctions de `app.domain.indicators` sont pures : elles reçoivent des séries pandas et n'accèdent jamais à CCXT. Une phase d'amorçage insuffisante produit des valeurs absentes.

## RSI

Le RSI utilise les variations des clôtures, sépare gains et pertes et applique des moyennes exponentielles de facteur `1 / period`. La formule finale est `100 - 100 / (1 + gain_moyen / perte_moyenne)`. La période vaut 14 par défaut. Une perte moyenne nulle après amorçage donne 100.

Dans le scanner, un RSI absent est une erreur de symbole. Une paire est filtrée si `rsi >= rsi_threshold` ; le scan cible donc les valeurs strictement inférieures au seuil.

## SMA, EMA et tendance multi-timeframes

La SMA est la moyenne arithmétique de `period` clôtures. L'EMA utilise `span=period`, `adjust=false` et exige la période complète avant sa première valeur.

Pour chaque timeframe MA :

1. toutes les périodes configurées et actives sont calculées et publiées ;
2. les périodes disponibles sont triées ;
3. les deux plus courtes sont utilisées comme fast et slow ; les périodes suivantes restent exposées mais ne votent pas ;
4. avec une seule période, la famille vote vrai si le prix est au-dessus de cette moyenne ;
5. avec deux périodes, elle vote vrai si fast > slow et prix > fast ;
6. SMA et EMA votent séparément ; la majorité `ceil(nombre_de_votes / 2)` suffit.

Avec SMA et EMA disponibles, un vote haussier sur deux suffit donc. Sans valeur fast disponible, le timeframe vaut `null`. `trend_score` est le nombre de timeframes vrais et la paire est filtrée si ce score est inférieur à `min_trend_score`.

Les clés de `moving_averages` suivent `{sma|ema}_{period}_{timeframe}` :

```json
{
  "trend_score": 2,
  "trends": {"4h": true, "1d": true, "1w": false},
  "moving_averages": {"sma_20_4h": 64320.4, "sma_50_4h": 62980.8}
}
```

## MACD

La ligne MACD vaut `EMA_fast - EMA_slow`; le signal est une EMA de la ligne MACD ; l'histogramme vaut MACD moins signal. Les valeurs par défaut sont 12, 26 et 9.

Sur deux points valides, un croisement détermine `bullish` ou `bearish`. Sans croisement, la position actuelle des lignes donne le même classement. Moins de deux points donne `neutral`. Une liste `filter_macd_signal` peut ensuite rejeter le signal.

## Bandes de Bollinger

La bande centrale est une SMA. Les bandes valent `SMA ± écart_type_population × bollinger_std_dev`. La position normalisée du prix entre les bandes produit : ≤ 0 `oversold`, ≤ 0,15 `near_oversold`, ≥ 1 `overbought`, ≥ 0,85 `near_overbought`, sinon `neutral`. Sans bande valide, le signal est `neutral`.

## Stochastique

`%K = 100 × (close - plus_bas) / (plus_haut - plus_bas)` sur `k_period`; `%D` est la SMA de `%K` sur `d_period`. Un intervalle nul donne une valeur absente.

Un croisement K/D sur les deux derniers points est prioritaire (`bullish_cross` ou `bearish_cross`). Sinon, K et D simultanément sous le seuil donnent `oversold`, au-dessus donnent `overbought`, sinon `neutral`.

## Divergences du flux marché

Les divergences ne filtrent pas les jobs ; elles produisent des marqueurs pour `/ws`. Un pivot est strictement plus bas ou plus haut que les `DIVERGENCE_LEFT` et `DIVERGENCE_RIGHT` voisins. Deux pivots consécutifs doivent respecter la distance minimale et maximale.

- régulière haussière : creux de prix plus bas, creux RSI/MACD plus haut ;
- régulière baissière : sommet de prix plus haut, sommet d'indicateur plus bas ;
- cachée haussière : creux de prix plus haut, indicateur plus bas ;
- cachée baissière : sommet de prix plus bas, indicateur plus haut.

## Signaux structurés (`IndicatorSignal`)

En complément des fonctions historiques ci-dessus, chaque indicateur expose désormais une fonction produisant un résultat structuré et commun (`IndicatorSignal`, défini dans `app.domain.indicators.types`) : `status`, `direction`, `signal`, `state`, `strength`, `reason` et `raw_value`. Ces fonctions (`detect_rsi_signal`, `detect_moving_average_signal`, `build_macd_signal`, `build_bollinger_signal`, `build_stochastic_signal`) sont disponibles **en parallèle** de l'API historique. Le scanner, le backtest et le marché construisent les signaux via `app.domain.indicator_bundle.build_indicator_signals`; les champs et filtres historiques restent toutefois conservés pour compatibilité.

`raw_value` porte la valeur numérique brute ayant produit le signal (RSI, ligne MACD, clôture pour Bollinger, `%K` pour le stochastique, moyenne rapide pour SMA/EMA) lorsqu'elle est pertinente et sérialisable, sinon `None`. Une bande Bollinger dégénérée conserve toutefois la clôture finie avec `status="invalid_data"` afin d'expliquer le diagnostic. Ce champ permet un calcul de facteur exact dépendant d'un seuil configurable (voir `calculate_rsi_signal_factor` dans `docs/backend/confluence.md`) sans réintroduire de dépendance pandas/numpy dans le contrat.

Un indicateur désactivé est absent du mapping renvoyé par le builder; le statut
`disabled` est porté séparément par les tables de disponibilité des payloads.
Les valeurs courantes non finies sont classées `invalid_data` et ne sont jamais
publiées comme `raw_value`.

Le changement relatif du prix doit atteindre `DIVERGENCE_PRICE_MIN_CHANGE`. Le RSI exige en plus un écart d'indicateur de 2 ; le MACD utilise 0. En temps réel, un marqueur n'est émis que lorsque le pivot vient d'être confirmé par les bougies de droite.

## Valeurs absentes et prudence

Un indicateur désactivé n'est pas calculé. Un historique insuffisant peut laisser ses champs à `null`; lorsque le scanner considère cette valeur indispensable (RSI ou historique principal), le symbole est compté en erreur. Les filtres ne sont pas des recommandations.

Les signaux produits par l’application sont des informations techniques et ne constituent pas un conseil financier.
