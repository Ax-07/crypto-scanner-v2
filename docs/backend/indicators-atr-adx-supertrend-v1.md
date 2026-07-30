# ATR/NATR, ADX/DMI et Supertrend v1

## Portée

La Phase 8.2 ajoute trois observations techniques optionnelles et désactivées
par défaut. Elles sont calculées par les mêmes fonctions pures dans le scanner,
le marché confirmé/provisoire et le replay. Elles ne participent à aucun filtre,
score de confluence, décision `accepted`, stratégie, trade, outcome ou calcul de
portefeuille.

## Primitives Wilder

Pour la première bougie, `TR = high - low`. Ensuite :

```text
TR = max(high - low, abs(high - previous_close), abs(low - previous_close))
```

Le lissage Wilder de période `p` est amorcé par la moyenne simple des `p`
premières valeurs valides, puis :

```text
smoothed[t] = (smoothed[t-1] * (p - 1) + value[t]) / p
```

Une donnée OHLC non finie, non positive ou telle que `high < low` coupe la
séquence et produit `invalid_data` au point courant. Les dénominateurs nuls de
DMI/DX donnent explicitement zéro.

## ATR et NATR

Configuration :

```json
{"atr": {"version": 1, "enabled": false, "period": 14}}
```

`ATR` utilise le lissage ci-dessus et `NATR = 100 * ATR / close`. La première
ATR est disponible à la bougie `p`; le signal public exige deux NATR, donc
`p + 1` bougies. `direction` reste toujours `neutral`. L'état est `expanding`,
`contracting` ou `stable`; un événement n'est émis que lors d'un changement
d'état. `raw_value` est le NATR en pourcentage.

Composants : `true_range`, `atr`, `natr`, `natr_change`.

## ADX et DMI

Configuration :

```json
{
  "adx": {
    "version": 1,
    "enabled": false,
    "period": 14,
    "weak_threshold": 20,
    "strong_threshold": 25
  }
}
```

`+DM` et `-DM` sont strictement exclusifs ; une égalité met les deux à zéro.
Les premiers DI/DX existent à l'index `p - 1`. L'ADX, amorcé sur `p` DX, existe
à l'index `2p - 2`, soit 27 bougies pour `p=14`. La direction vient de la
comparaison `+DI/-DI`. Les états sont `weak_trend`, `developing_trend` et
`strong_trend`. Les croisements DI ont priorité sur les transitions de force.

Composants : `adx`, `plus_di`, `minus_di`, `dx`.

## Supertrend

Configuration :

```json
{
  "supertrend": {
    "version": 1,
    "enabled": false,
    "atr_period": 10,
    "multiplier": 3
  }
}
```

Les bandes de base utilisent `hl2 ± multiplier * ATR`. Les bandes finales et le
régime courant ne lisent que la bande et le close précédents. Le premier point
ATR initialise le régime ; `bullish_flip` ou `bearish_flip` n'est émis que si
le régime change. La force est la distance absolue ligne/close exprimée en ATR
et bornée dans `[0, 1]`.

Composants : `supertrend`, `upper_band`, `lower_band`, `atr`,
`distance_ratio`.

## Contrat et coût

`IndicatorSignal.components` est additif et optionnel. Chaque composant contient
`value`, `normalized_value` et `unit`. Le True Range est calculé une fois par
bundle ; les ATR de même période sont réutilisés. Activer ADX porte le besoin
minimal à `2p - 1` bougies, ATR à `p + 1`, et Supertrend à `p`, en plus de la
marge opérationnelle existante.

Les observations JSON SQLite acceptent ces clés sans migration. L'export CSV
historique reste volontairement plat et n'exporte pas `indicator_signals`.
