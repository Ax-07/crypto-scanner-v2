# Matrice de complémentarité des indicateurs v1

## Convention

`low`, `moderate`, `high`, `near_duplicate` et `unknown` qualifient la
redondance conceptuelle, pas une corrélation empirique. La complémentarité vaut
`low`, `moderate` ou `high`. Aucun candidat non implémenté n'a reçu une
corrélation inventée.

## Indicateurs actuels entre eux

| Indicateur A | Indicateur B | Familles | Redondance | Complémentarité | Risque | Décision | Justification |
|---|---|---|---|---|---|---|---|
| RSI | SMA | momentum / trend | low | high | faible | conserver | Oscillateur gains/pertes contre niveau moyen. |
| RSI | EMA | momentum / trend | low | high | faible | conserver | Même distinction, EMA plus réactive. |
| RSI | MACD | momentum / trend | moderate | moderate | double comptage momentum | surveiller | Tous deux réagissent au mouvement, formules et échelles distinctes. |
| RSI | Bollinger | momentum / volatility | moderate | moderate | confluence orientée repli | surveiller | Extrêmes parfois simultanés, mais Bollinger dépend de la dispersion. |
| RSI | Stochastique | momentum / momentum | high | moderate | surpondération extrêmes | ne pas ajouter Williams %R | Gains/pertes lissés contre position dans la plage. |
| SMA | EMA | trend / trend | high | low | double vote de tendance | conserver comme primitives | Même rôle, pondérations différentes. |
| SMA | MACD | trend / trend | moderate | moderate | MACD dérive d'EMA | surveiller | SMA n'entre pas directement dans MACD. |
| SMA | Bollinger | trend / volatility | moderate | moderate | bande médiane = SMA | mutualiser la primitive | Bollinger ajoute l'écart-type. |
| SMA | Stochastique | trend / momentum | low | high | faible | conserver | Informations distinctes. |
| EMA | MACD | trend / trend | high | moderate | double comptage EMA | surveiller | MACD est une différence d'EMA plus signal. |
| EMA | Bollinger | trend / volatility | low | high | faible | conserver | Niveau adaptatif contre enveloppe SMA/écart-type. |
| EMA | Stochastique | trend / momentum | low | high | faible | conserver | Informations distinctes. |
| MACD | Bollinger | trend / volatility | low | high | faible | conserver | Direction dynamique contre dispersion/position. |
| MACD | Stochastique | trend-momentum / momentum | moderate | moderate | croisements synchrones | surveiller | Horizons et normalisations différents. |
| Bollinger | Stochastique | volatility / momentum | moderate | moderate | mêmes extrêmes de range | surveiller | L'un mesure dispersion/position, l'autre position high-low. |

## Candidats retenus face aux indicateurs actuels

| Candidat | Actuel | Familles | Redondance | Complémentarité | Risque | Décision | Justification |
|---|---|---|---|---|---|---|---|
| ATR/NATR | RSI | volatility / momentum | low | high | faible | P0 | Amplitude sans direction contre momentum borné. |
| ATR/NATR | SMA/EMA | volatility / trend | low | high | faible | P0 | Volatilité et niveau de tendance distincts. |
| ATR/NATR | MACD | volatility / trend | low | high | faible | P0 | Aucun dérivé commun direct. |
| ATR/NATR | Bollinger | volatility / volatility | moderate | high | double mesure volatilité | P0 | True range/gaps contre écart-type du close. |
| ATR/NATR | Stochastique | volatility / momentum | low | high | faible | P0 | Informations distinctes. |
| ADX/DMI | RSI | trend / momentum | low | high | faible | P0 | Force/direction de tendance contre momentum. |
| ADX/DMI | SMA/EMA | trend / trend | moderate | high | double direction | P0 | ADX ajoute la force absente, DMI confirme la direction. |
| ADX/DMI | MACD | trend / trend | moderate | high | facteurs corrélés en tendance | P0 | ADX mesure la force, MACD la dynamique d'EMA. |
| ADX/DMI | Bollinger | trend / volatility | low | high | faible | P0 | Force de tendance contre dispersion/position. |
| ADX/DMI | Stochastique | trend / momentum | low | high | faible | P0 | Permet de contextualiser les extrêmes. |
| Supertrend | SMA/EMA | trend / trend | high | moderate | double état directionnel | P0 après ATR | État ATR sensible à volatilité, mais rôle proche des MA. |
| Supertrend | MACD | trend / trend | moderate | moderate | whipsaw/croisements | P0 après ATR | État persistant contre dynamique MACD. |
| Supertrend | Bollinger | trend / volatility | moderate | moderate | tous deux enveloppes | P0 après ATR | Bandes ATR directionnelles contre bandes statistiques. |
| BB Width | Bollinger | volatility / volatility | near_duplicate | high | calcul dupliqué | enrichir Bollinger | Feature dérivée exacte des bandes existantes. |
| BB Width | ATR/NATR | volatility / volatility | moderate | high | deux régimes vol | P0 | Dispersion close contre true range. |
| Donchian | Bollinger | support-resistance / volatility | moderate | high | deux canaux | P0 | Extrema observés contre enveloppe statistique. |
| Donchian | Stochastique | structure / momentum | moderate | high | même rolling min/max | mutualiser | Stochastique positionne ; Donchian détecte les niveaux/cassures. |
| Volume relatif | tous actuels | volume / prix | low | high | qualité volume Binance | P0 | Première information de participation. |
| CMF | RSI | volume / momentum | moderate | high | oscillateurs corrélables | P0 | Pression prix-volume contre gains/pertes du close. |
| CMF | Stochastique | volume / momentum | moderate | high | extrêmes simultanés | P0 | Ajoute le volume. |
| OBV dérivé | MACD | volume / trend | moderate | high | pentes similaires | P1 | Tendance du volume contre tendance du prix. |
| VWAP roulant | SMA/EMA | volume / trend | moderate | high | niveau moyen similaire | P1 | Pondération volume distincte. |
| CCI | RSI | momentum / momentum | moderate | moderate | multiplication des oscillateurs | P1 limité | Distance au prix typique moyen, non ratio gains/pertes. |
| CCI | Stochastique | momentum / momentum | moderate | moderate | multiplication des extrêmes | P1 limité | Mesures différentes, sélection empirique ultérieure. |
| ROC | RSI | momentum / momentum | moderate | moderate | même mouvement sous-jacent | P1 | Retour signé simple utile comme feature. |
| ROC | MACD | momentum / trend | moderate | moderate | dynamique du close | P1 | Horizon fixe contre lissage EMA. |

## Candidats retenus entre eux

| Indicateur A | Indicateur B | Familles | Redondance | Complémentarité | Risque | Décision | Justification |
|---|---|---|---|---|---|---|---|
| ATR | NATR | volatility / volatility | near_duplicate | high | double stockage | même composant | NATR est la normalisation inter-actifs d'ATR. |
| ATR/NATR | ADX/DMI | volatility / trend | moderate | high | primitive TR partagée | même phase | ADX réutilise TR mais mesure une force directionnelle. |
| ATR/NATR | Supertrend | volatility / trend | high | high | dépendance directe | même phase | Supertrend dépend d'ATR ; ne pas recalculer. |
| ADX/DMI | Supertrend | trend / trend | moderate | high | double direction | même phase | Force/direction DMI contre état de bande ATR. |
| BB Width | Donchian | volatility / structure | moderate | high | deux largeurs | même phase | Compression statistique contre étendue des extrema. |
| BB Width | ATR/NATR | volatility / volatility | moderate | high | régime volatilité doublé | conserver | Sensibilités différentes aux gaps et distributions. |
| Donchian | Supertrend | structure / trend | moderate | high | breakouts proches | conserver | Niveau causal contre trailing band. |
| Volume relatif | CMF | volume / volume | moderate | high | même volume brut | conserver | Intensité de participation contre localisation du close. |
| Volume relatif | OBV dérivé | volume / volume | moderate | high | volume commun | conserver | Anomalie locale contre cumul directionnel. |
| Volume relatif | VWAP roulant | volume / volume | moderate | high | volume commun | conserver | Participation contre niveau moyen pondéré. |
| CMF | OBV dérivé | volume / volume | high | moderate | pression cumulative similaire | valider avant confluence | CMF rolling borné ; OBV dépend du signe du close. |
| CMF | VWAP roulant | volume / support-resistance | moderate | high | prix typique-volume commun | conserver | Flux borné contre distance à un niveau. |
| OBV dérivé | VWAP roulant | volume / support-resistance | moderate | high | volume commun | conserver | Pente cumulative contre niveau pondéré. |
| CCI | ROC | momentum / momentum | moderate | moderate | même mouvement | limiter à deux | Déviation au prix typique contre retour à horizon fixe. |
| CCI | ADX/DMI | momentum / trend | low | high | faible | conserver | Momentum relatif contre force de tendance. |
| ROC | ADX/DMI | momentum / trend | low | high | faible | conserver | Retour signé contre force/direction lissée. |

## Paires importantes rejetées ou reportées

| Indicateur A | Indicateur B | Redondance | Décision | Justification |
|---|---|---|---|---|
| Williams %R | Stochastique `%K` | near_duplicate | rejeter Williams %R | Transformation affine de la même position high-low. |
| Momentum | ROC | near_duplicate | rejeter Momentum | Même variation absolue/relative à horizon fixe. |
| HMA | SMA/EMA | high | rejeter HMA | Nouvelle moyenne avant de combler volume/force/structure. |
| MFI | RSI + CMF | high | reporter | Combine des dimensions déjà retenues séparément. |
| Keltner | EMA + ATR + Bollinger | high | reporter | Utile surtout pour un squeeze futur non sélectionné. |
| ADL | CMF | high | reporter | Même money-flow multiplier, cumul contre fenêtre. |
| Ichimoku | MA + Donchian | high | reporter | Multiples midpoints high-low et décalages complexes. |

## Exemple demandé

```text
RSI / Stochastique
redondance: high
complémentarité: moderate
raison: tous deux décrivent des extrêmes de momentum, mais RSI lisse les
gains/pertes tandis que Stochastique situe le close dans la plage high-low.
décision: conserver les deux actuels, ne pas ajouter Williams %R.
```
