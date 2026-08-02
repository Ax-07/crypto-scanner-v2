# Contrat cohérent des signaux et événements

État mis à jour le 2 août 2026. Ce document conserve les règles de la Phase 2 et
ajoute les contrats utilisés par les événements historiques et les marqueurs du
marché.

## Disponibilité

Chaque facteur utilise `available`, `insufficient_data`, `invalid_data` ou
`disabled`. Un signal réellement `neutral` reste `available`. Seuls les facteurs
disponibles participent à la confluence ; les poids restants sont renormalisés.
Sans facteur disponible, score et grade sont `null`.

Un indicateur désactivé est généralement absent du mapping
`indicator_signals`. La table séparée de disponibilité peut porter
`disabled`. Cette distinction doit rester stable.

## Contrat `IndicatorSignal`

```python
class IndicatorSignal(TypedDict):
    status: Availability
    direction: Literal["bullish", "bearish", "neutral"]
    signal: str | None
    state: str | None
    strength: float
    reason: str | None
    raw_value: float | None
    components: NotRequired[Mapping[str, IndicatorComponent] | None]
```

`strength` est une intensité technique bornée dans `[0, 1]`, jamais une
probabilité de réussite. `components` est additif et transporte les valeurs
multi-composants d’ATR/NATR, ADX/DMI, Supertrend, Bollinger, Donchian et Keltner.

## Contrat `IndicatorEvent`

Un `IndicatorSignal` décrit principalement le dernier état connu. Un
`IndicatorEvent` décrit un changement ponctuel dans un historique :

```python
class IndicatorEvent(TypedDict):
    indicator: IndicatorName
    position: int
    direction: Literal["bullish", "bearish", "neutral"]
    event: str
    kind: Literal[
        "trend_change",
        "cross",
        "breakout",
        "reentry",
        "threshold_entry",
        "threshold_exit",
        "volatility_regime",
    ]
    strength: NotRequired[float]
    metadata: NotRequired[Mapping[str, object]]
```

`position` reste aligné sur les séries OHLCV. Les détecteurs ne doivent pas
faire de `dropna()` avant l’itération si cette opération change les positions.
Le timestamp est ajouté uniquement par la couche marché.

## Snapshots du marché

`snapshot.confirmed` utilise uniquement les bougies clôturées et contient prix,
timestamp, signaux, disponibilités et confluence. `snapshot.provisional` inclut
la bougie ouverte, porte `is_forming: true` et vaut `null` sans bougie ouverte.
Les updates intrabougie ne modifient pas `confirmed`. À la clôture, le provisoire
entre dans la vue confirmée et la nouvelle bougie devient provisoire.

Les anciens champs `snapshot.rsi`, `trend`, `macd`, `bollinger`, `stochastic` et
`confluence` restent dérivés de la vue active pour compatibilité. Leur suppression
est réservée à une future version majeure après vérification des consommateurs.

Les séries graphiques peuvent inclure la bougie ouverte. Les marqueurs de signal
et les divergences sont, eux, calculés uniquement sur bougies closes.

## Contrat `MarketMarker`

```typescript
export interface MarketMarker {
  time: number
  position: "aboveBar" | "belowBar" | "inBar"
  shape: "circle" | "square" | "arrowUp" | "arrowDown"
  color: string
  text: string
  category?: "signal" | "divergence"
  indicator?: MarkerIndicator
}
```

`MarkerIndicator` reconnaît :

```text
ema, macd, supertrend, rsi, stochastic,
bollinger, adx, atr, donchian, keltner
```

Les nouveaux marqueurs backend fournissent `indicator`. Le champ reste optionnel
en TypeScript pour accepter les anciens payloads. Le frontend peut alors inférer
l’indicateur depuis le texte avant fusion et filtrage.

## Événements actuellement exposés

- EMA : croisements des moyennes rapides/lentes ;
- MACD : histogramme traversant zéro ;
- Supertrend : flips haussier/baissier ;
- RSI : sorties de survente/surachat ;
- Stochastique : croisements `%K/%D` dans les zones extrêmes ;
- Bollinger : réintégrations des bandes basse/haute ;
- Donchian : premières cassures du canal précédent ;
- Keltner : cassures des bandes précédentes ;
- ADX/DMI : croisements directionnels avec ADX au-dessus du seuil faible ;
- ATR/NATR : expansion/contraction de volatilité, direction neutre.

La référence détaillée est
[`backend/indicator-events-and-market-markers.md`](backend/indicator-events-and-market-markers.md).

## Visibilité frontend

Un marqueur de signal n’est visible que lorsque :

```text
visibility.signals === true
```

et que la visibilité de l’indicateur est active. ATR/NATR utilise
`visibility.volatility`, les autres indicateurs leur clé correspondante.

Les anciens libellés `Volatilité en hausse` et `Volatilité en baisse` doivent être
normalisés vers `indicator="atr"` lorsqu’ils arrivent sans champ `indicator`.

## Profil d’indicateurs

`MarketIndicatorConfig` contient activations, périodes RSI/SMA/EMA, paramètres
MACD/Bollinger/Stochastique, seuil RSI et poids, ainsi que les blocs optionnels
ATR, ADX/DMI, Supertrend, Donchian et Keltner. Son origine est `default`, `scan`
ou `custom`. Il est sérialisé dans le profil transmis aux routes et au WebSocket.

## Tendance

Une famille est `bullish` si fast > slow et prix > fast, `bearish` si fast < slow
et prix < fast, sinon `neutral`. Sans fast elle est `unavailable`. Avec SMA et
EMA, un état directionnel exige leur accord ; tout désaccord produit `neutral`.

`trend_score` reste le nombre de timeframes bullish et continue d’alimenter
`min_trend_score`. `trend_net_score` utilise +1/0/-1 et `trend_states` expose le
détail. Le facteur de confluence est la moyenne bullish=1, neutral=0.5,
bearish=0, indisponible exclu.

## Confluence explicable

Chaque entrée `details` contient disponibilité, valeur brute, classe, facteur,
poids configuré, poids effectif, contribution et raison. Le score n’est ni une
probabilité ni une garantie. Il reste orienté vers une configuration haussière
après repli.

Les événements graphiques ne participent pas automatiquement à la confluence.
ATR, ADX, Supertrend, Donchian et Keltner restent hors des filtres structurés v1
et des poids de production tant qu’une phase de recherche distincte ne démontre
pas leur intérêt.

## Validation et migration

REST et WebSocket utilisent les mêmes vues et marqueurs. Le frontend valide les
messages réseau avant Zustand. Un message invalide rend une erreur visible sans
muter les séries et sans désactiver la reconnexion.

Le champ `indicator` des marqueurs est additif. Les anciens payloads restent
compatibles via normalisation frontend. Aucun changement de stratégie, de
backtest ou de portefeuille ne doit être inféré d’un changement de présentation.
