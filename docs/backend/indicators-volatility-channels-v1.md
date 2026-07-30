# Indicateurs de volatilité et canaux v1

## Périmètre

La Phase 8.3 ajoute trois observations causales : la largeur des bandes de
Bollinger, les canaux de Donchian et les canaux de Keltner. Elles traversent le
scanner, le marché confirmé/provisoire, le replay, les modèles publics et
l'interface. Elles ne sont utilisées par aucun filtre, poids de confluence,
verdict `accepted`, outcome ou calcul de portefeuille.

## Bollinger existant et Band Width

Le calcul historique reste une SMA de période 20 par défaut, encadrée de
`2 × std(ddof=0)`. `calculate_bollinger_band_width(close, bands)` reçoit les
bandes déjà calculées et ne rappelle jamais `calculate_bollinger_bands`.

```text
band_width = upper_band - lower_band
band_width_percent = 100 × band_width / middle_band
band_position = (close - lower_band) / band_width
```

`band_width` est un prix, `band_width_percent` un pourcentage et
`band_position` un ratio non borné. Pour une largeur nulle valide,
`band_position=0.5`. Un milieu non positif ne produit pas de pourcentage
public. Les composants sont `middle_band`, `upper_band`, `lower_band`,
`band_width`, `band_width_percent` et `band_position`.

Le contrat v1 possède un unique couple `signal/state`. Publier
`expanding/contracting/stable` dans ces champs aurait changé le verdict
Bollinger historique. La Phase 8.3 conserve donc intégralement statut,
direction, signal, state, strength, reason et raw_value et ajoute seulement les
composants numériques. Leur évolution causale prépare une observation future,
sans créer ici de squeeze ni de second calcul.

## Donchian descriptif et précédent

Configuration par défaut :

```json
{"version": 1, "enabled": false, "period": 20}
```

Le canal descriptif inclut la bougie courante :

```text
upper_channel_t = max(high[t-period+1:t])
lower_channel_t = min(low[t-period+1:t])
middle_channel_t = (upper_channel_t + lower_channel_t) / 2
```

Le canal de décision exclut strictement `t` :

```text
previous_upper_channel_t = max(high[t-period:t-1])
previous_lower_channel_t = min(low[t-period:t-1])
```

`breakout_up` exige `close_t > previous_upper_channel_t` et
`breakout_down` exige `close_t < previous_lower_channel_t`. L'égalité n'est
jamais une cassure. Un événement déjà actif à la bougie précédente n'est pas
répété. L'état reste `above_channel`, `below_channel` ou `inside_channel`.
La direction est haussière/baissière seulement pour l'événement ; sinon elle
est neutre. La force est la distance à la borne précédente divisée par le
close, bornée dans `[0,1]`, jamais une probabilité.

```text
channel_width = upper_channel - lower_channel
channel_width_percent = 100 × channel_width / middle_channel
channel_position = (close - lower_channel) / channel_width
```

La position n'est pas clampée. Une largeur nulle valide donne `0.5`. Le canal
descriptif apparaît après `period` bougies et le canal précédent après
`period + 1`.

## Keltner

Configuration par défaut :

```json
{
  "version": 1,
  "enabled": false,
  "ema_period": 20,
  "atr_period": 10,
  "multiplier": 2
}
```

La ligne centrale appelle l'EMA canonique. L'ATR appelle le calcul Wilder de
Phase 8.2 et partage localement sa série avec ATR public ou Supertrend lorsque
la période est identique.

```text
middle_line = EMA(close, ema_period)
upper_channel = middle_line + multiplier × ATR(atr_period)
lower_channel = middle_line - multiplier × ATR(atr_period)
channel_width = upper_channel - lower_channel
channel_width_percent = 100 × channel_width / middle_line
channel_position = (close - lower_channel) / channel_width
```

L'événement utilise uniquement les bandes de `t-1` :

```text
breakout_up =
  close_t > upper_channel_(t-1)
  et close_(t-1) <= upper_channel_(t-1)

breakout_down =
  close_t < lower_channel_(t-1)
  et close_(t-1) >= lower_channel_(t-1)
```

Cette transition empêche toute répétition tant que le prix reste dehors.
L'état courant est `above_channel`, `below_channel` ou `inside_channel`. La
direction décrit cet état relatif, jamais une recommandation. Lors d'une
cassure, la force est la distance à la bande précédente exprimée en ATR et
bornée dans `[0,1]`. Hors cassure, elle vaut zéro.

## Statuts, validation et warmup

- bloc absent ou `enabled=false` : clé publique omise, comme en Phase 8.2 ;
- historique incomplet : `insufficient_data` ;
- valeur non finie, close non positif ou `high < low` :
  `invalid_data` ;
- résultat exploitable : `available`.

Les objets publics ne contiennent ni NaN ni infini. Les périodes sont des
entiers de 1 à 1000 et les multiplicateurs sont finis, strictement positifs et
au plus 100. Keltner attend les warmups combinés EMA/ATR et une bande
précédente pour un événement.

## Bundle, causalité et parité

`calculate_extended_indicator_bundle` mutualise True Range, ATR par période et
EMA locale. Donchian calcule séparément bornes descriptives et précédentes.
Scanner, marché et replay appellent le même bundle. Le marché provisional reste
révisable selon la politique existante ; confirmed et replay utilisent les
mêmes bougies closes.

Les tests modifient les bougies futures et vérifient l'identité du passé. Une
fixture commune compare live et replay. Une preuve de neutralité compare
accepted, rejets, confluence, outcomes, ordres, exécutions, trades, equity et
métriques de portefeuille.

## Limites

Aucun percentile de largeur, squeeze, TTM Squeeze, filtre de cassure,
classificateur de régime ou modèle IA n'est implémenté. Le volume et la
structure de marché avancée restent hors Phase 8.3.
