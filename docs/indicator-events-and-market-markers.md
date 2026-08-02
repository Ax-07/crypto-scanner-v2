# Événements d’indicateurs et marqueurs du marché

> Chemin recommandé dans le dépôt :
> `docs/backend/indicator-events-and-market-markers.md`

État fonctionnel confirmé le 2 août 2026. Ce document décrit les événements
ponctuels calculés sur bougies clôturées et leur conversion en marqueurs pour le
graphique du marché. Il ne modifie ni la confluence, ni les filtres de production,
ni la décision `accepted`, ni les outcomes ou la simulation de portefeuille.

## 1. Architecture

La chaîne de responsabilité est la suivante :

1. chaque module d’indicateur calcule ses séries et détecte ses événements métier ;
2. `app.domain.indicator_bundle.build_indicator_events` agrège les
   `IndicatorEvent` sans recalculer les indicateurs ;
3. `app.services.market_stream.build_indicator_event_markers` ajoute le timestamp
   OHLCV et les propriétés de présentation Lightweight Charts ;
4. les routes historiques et le WebSocket réutilisent le même builder de marqueurs ;
5. le frontend normalise les anciens payloads, fusionne les marqueurs et les filtre
   selon la visibilité globale et celle de l’indicateur.

Les événements et marqueurs confirmés utilisent uniquement des bougies closes.
La bougie ouverte continue d’alimenter les séries et le snapshot `provisional`,
mais ne crée pas de marqueur confirmé.

## 2. Contrat backend `IndicatorEvent`

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

`position` est l’index dans les séries déjà calculées. Le timestamp n’est ajouté
qu’au niveau du service marché. Les détecteurs ne doivent pas supprimer les
`NaN` avant l’itération, car cela décalerait les événements par rapport aux
bougies.

## 3. Contrat public des marqueurs

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

Pour les nouveaux marqueurs de signal, `category="signal"` et `indicator` est
toujours fourni par le backend. Le frontend conserve une inférence de secours
depuis le texte pour les payloads historiques qui ne possèdent pas ce champ.

## 4. Matrice des événements graphiques

| Indicateur | Événement | Détection | Direction | Présentation |
|---|---|---|---|---|
| EMA | croisement rapide/lente | première période EMA disponible contre la seconde | bullish/bearish | flèche verte sous la bougie / rouge au-dessus |
| MACD | histogramme traverse zéro | passage négatif→positif ou positif→négatif | bullish/bearish | cercle cyan sous la bougie / orange au-dessus |
| Supertrend | `bullish_flip` / `bearish_flip` | changement de tendance Supertrend | bullish/bearish | flèche générique |
| RSI | `exit_oversold` | RSI repasse au-dessus de 30 | bullish | flèche générique |
| RSI | `exit_overbought` | RSI repasse sous 70 | bearish | flèche générique |
| Stochastique | `bullish_cross` | `%K` croise `%D` dans la zone basse précédente ou courante | bullish | flèche générique |
| Stochastique | `bearish_cross` | `%K` croise `%D` dans la zone haute précédente ou courante | bearish | flèche générique |
| Bollinger | `lower_band_reentry` | close précédent sous/sur la bande basse, close courant au-dessus | bullish | carré vert sous la bougie |
| Bollinger | `upper_band_reentry` | close précédent au-dessus/sur la bande haute, close courant en dessous | bearish | carré rouge au-dessus |
| Donchian | `breakout_up` | première clôture au-dessus du canal terminé à `t-1` | bullish | flèche générique |
| Donchian | `breakout_down` | première clôture sous le canal terminé à `t-1` | bearish | flèche générique |
| Keltner | `breakout_up` | close courant au-dessus de la bande haute précédente | bullish | flèche générique |
| Keltner | `breakout_down` | close courant sous la bande basse précédente | bearish | flèche générique |
| ADX/DMI | `bullish_cross` | `+DI` croise au-dessus de `-DI` avec ADX ≥ seuil faible | bullish | flèche générique |
| ADX/DMI | `bearish_cross` | `-DI` croise au-dessus de `+DI` avec ADX ≥ seuil faible | bearish | flèche générique |
| ATR/NATR | `volatility_expansion` | le régime NATR bascule vers `expanding` | neutral | cercle orange dans la bougie |
| ATR/NATR | `volatility_contraction` | le régime NATR bascule vers `contracting` | neutral | cercle bleu dans la bougie |

Les transitions NATR vers `stable` ne sont pas affichées. ATR/NATR mesure un
régime de volatilité et ne reçoit jamais artificiellement une direction de prix.

## 5. Agrégation

La signature actuelle de l’agrégateur est :

```python
build_indicator_events(
    *,
    close_series: pd.Series | None = None,
    rsi_series: pd.Series | None = None,
    rsi_oversold_level: float = 30,
    rsi_overbought_level: float = 70,
    bollinger_bands: dict[str, pd.Series] | None = None,
    stochastic_data: dict[str, pd.Series] | None = None,
    stochastic_oversold_level: float = 20,
    stochastic_overbought_level: float = 80,
    adx_weak_threshold: float = 20,
    extended_data: dict[str, dict[str, pd.Series]] | None = None,
    only_last: bool = False,
) -> list[IndicatorEvent]
```

`extended_data` transporte ATR, ADX/DMI, Supertrend, Donchian et Keltner.
`only_last=True` est utilisé lorsqu’une nouvelle bougie vient d’être clôturée.
L’historique complet utilise `only_last=False`.

## 6. Frontend

`MarkerIndicator` contient :

```typescript
"ema" | "macd" | "supertrend" | "rsi" | "stochastic"
| "bollinger" | "adx" | "atr" | "donchian" | "keltner"
```

Un marqueur de signal n’est visible que si :

```text
visibility.signals === true
```

et si la visibilité de son indicateur est active. Le mapping particulier est :

```text
marker.indicator === "atr"  → visibility.volatility
```

Les autres indicateurs utilisent une clé du même nom. Les marqueurs historiques
sans `indicator` sont normalisés depuis leur texte ; les libellés contenant
`ATR`, `NATR`, `volatilité`, `volatilite` ou `volatility` sont associés à `atr`.

## 7. Fusion et compatibilité

`mergeMarkers` normalise les marqueurs avant leur insertion dans une map
dédupliquée. La clé de déduplication repose sur le temps, le texte, la catégorie,
la source et le type de divergence. Les marqueurs sont ensuite triés par temps
puis par texte.

Le champ `indicator` est additif. Les anciens payloads restent acceptés grâce à
l’inférence frontend ; les nouveaux payloads backend doivent toujours le fournir.

## 8. Neutralité métier

Ces marqueurs sont une couche d’observation et de présentation :

- aucun nouveau facteur n’est ajouté à la confluence ;
- aucun filtre scanner ou structuré v1 ne les consomme ;
- aucune décision de backtest n’est modifiée ;
- aucun ordre, trade, rendement ou portefeuille n’est créé depuis un marqueur ;
- les baselines et conclusions des Phases 7 restent inchangées.

## 9. Vérifications recommandées

Backend :

```powershell
python -m pytest -q tests/test_market_stream.py
python -m pytest -q tests/test_indicator_bundle.py
python -m pytest -q tests/test_indicator_signals.py
```

Frontend :

```powershell
pnpm exec vitest run src/features/market
pnpm exec vitest run src/stores/market-store.test.ts
pnpm run typecheck
pnpm run lint
```

Cas minimaux à verrouiller :

- RSI `[29, 31]` et `[71, 69]` ;
- Stochastique croisé dans les zones 20/80 ;
- réintégrations Bollinger ;
- première cassure Donchian/Keltner sans répétition ;
- DMI croisé avec ADX sous puis au-dessus du seuil ;
- NATR `[1.0, 0.9, 1.0]` et `[1.0, 1.1, 1.0]` ;
- affichage ATR avec `signals=true` et `volatility=true` ;
- compatibilité d’un marqueur historique sans `indicator`.
