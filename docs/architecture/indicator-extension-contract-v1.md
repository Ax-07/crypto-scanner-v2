# Proposition de contrat pour l'extension des indicateurs v1

## 1. Statut de ce document

Cette architecture est une proposition de Phase 8.1. Elle ne change pas le
contrat public actuel, dont la forme reste :

```text
status, direction, signal, state, strength, reason, raw_value
```

Une évolution publique devra être additive ou utiliser une nouvelle version,
avec Pydantic, OpenAPI, TypeScript, Zod, frontend, exports et fingerprints
modifiés ensemble.

## 2. Principes

1. Une fonction pure calcule chaque indicateur depuis des séries OHLCV.
2. Scanner, marché, replay, audit et extraction IA réutilisent la même fonction.
3. Le calcul numérique, la classification d'état et l'événement sont séparés.
4. Une primitive partagée ne produit aucune décision métier.
5. Le contrat ne publie jamais NaN ou infini.
6. Une valeur provisional est explicitement distincte d'une valeur confirmed.
7. Les dépendances sont déclarées et calculées une fois.
8. Les événements ponctuels ne sont pas répétés quand seul l'état persiste.

## 3. Enveloppe future

Forme conceptuelle, non implémentée :

```json
{
  "contract_version": 2,
  "indicator_id": "adx_dmi",
  "indicator_version": 1,
  "status": "available",
  "direction": "bullish",
  "signal": "bullish_cross",
  "state": "developing_trend",
  "strength": 0.62,
  "reason": {
    "code": "adx_dmi.bullish_cross",
    "params": { "adx": 27.4 }
  },
  "raw_value": 27.4,
  "components": {
    "adx": { "value": 27.4, "normalized_value": 0.548, "unit": "index" },
    "plus_di": { "value": 31.2, "normalized_value": 0.312, "unit": "index" },
    "minus_di": { "value": 18.7, "normalized_value": 0.187, "unit": "index" }
  },
  "warmup": {
    "minimum_bars": 29,
    "recommended_bars": 128,
    "bars_seen": 200,
    "ready": true
  },
  "provenance": {
    "decision_time": "2026-07-30T12:00:00Z",
    "data_through": "2026-07-30T12:00:00Z",
    "candle_state": "confirmed",
    "config_fingerprint": "sha256:..."
  }
}
```

Le contrat runtime pourra être plus compact. Les blocs de provenance et warmup
peuvent vivre au niveau du snapshot si cela évite leur répétition. Leur
sémantique, elle, doit rester disponible.

## 4. Contrat de base

| Champ               | Type           |     Obligatoire | Sémantique                        |
| ------------------- | -------------- | --------------: | --------------------------------- |
| `contract_version`  | entier         |       oui en v2 | version de l'enveloppe publique   |
| `indicator_id`      | ID canonique   |             oui | clé stable, ASCII snake_case      |
| `indicator_version` | entier         |             oui | version de formule/classification |
| `status`            | enum commun    |             oui | disponibilité du résultat         |
| `direction`         | enum commun    |             oui | biais de prix, sinon neutral      |
| `signal`            | code/null      |             oui | événement de la bougie            |
| `state`             | code/null      |             oui | état persistant                   |
| `strength`          | nombre `[0,1]` |             oui | intensité technique               |
| `reason`            | objet/null     |             oui | code stable et paramètres         |
| `raw_value`         | nombre/null    |             oui | scalaire principal compatible     |
| `components`        | objet strict   |             oui | valeurs nommées multi-composants  |
| `warmup`            | objet          | selon placement | disponibilité mathématique        |
| `provenance`        | objet          | selon placement | causalité et fingerprint          |

## 5. Statuts et propagation

Conserver :

```text
available
insufficient_data
invalid_data
disabled
```

Règles :

- `disabled` vient uniquement de la configuration ;
- une dépendance `disabled` désactive le composant dépendant si celui-ci est
  implicitement activé par elle, sinon la validation de configuration refuse
  la combinaison ;
- une dépendance `insufficient_data` propage `insufficient_data` ;
- une donnée non finie, division par zéro non définie ou plage dégénérée
  propage `invalid_data` ;
- un résultat neutre calculable reste `available` ;
- si le statut n'est pas `available`, direction=`neutral`, strength=`0`,
  signal/state/raw_value=`null`, sauf diagnostic de composant explicitement
  documenté ;
- ne pas créer de statut propre à ATR, ADX ou volume.

## 6. Direction

`direction` décrit seulement un biais de prix :

```text
bullish | bearish | neutral
```

Exemples :

- +DI > -DI : bullish ;
- close au-dessus du Supertrend : bullish ;
- ATR en hausse : neutral, car l'expansion n'a pas de direction de prix ;
- volume relatif élevé : neutral ;
- CMF positif : bullish si la règle de classification le décide explicitement.

La direction ne signifie ni achat/vente, ni acceptation par les filtres.

## 7. Signal et state

`signal` est un événement détecté entre `t-1` et `t` :

```text
bullish_cross
bearish_cross
trend_strengthening
trend_weakening
compression_started
expansion_started
breakout_up
breakout_down
none
```

`state` est une condition persistante :

```text
strong_uptrend
weak_trend
high_volatility
compression
above_vwap
below_vwap
```

Conventions :

- vocabulaire ASCII snake_case et versionné par indicateur ;
- `signal=null` ou `none` quand aucun événement n'a lieu ; choisir une seule
  convention lors de l'implémentation v2 ;
- ne jamais recopier automatiquement `state` dans `signal` ;
- un événement ne se répète pas à chaque bougie ;
- les filtres et l'UI doivent pouvoir cibler séparément événement et état.

## 8. Strength

`strength` reste bornée à `[0,1]` et non probabiliste. Chaque indicateur
documente sa formule.

Exemples conceptuels :

- ADX : intensité normalisée d'une force de tendance, indépendamment du signe
  DMI ;
- Supertrend : distance close/ligne normalisée par ATR, bornée ;
- NATR : aucune direction ; la force peut représenter l'intensité de
  l'expansion seulement si `signal/state` l'indiquent ;
- breakout Donchian : distance au canal divisée par ATR ;
- volume relatif : ratio transformé et borné.

Une force absente ne doit pas être inventée : utiliser 0 avec un état neutre ou
documenter une règle explicite.

## 9. Reason

Remplacer à terme la phrase API localisée par :

```json
{ "code": "supertrend.bullish_flip", "params": { "distance_atr": 0.42 } }
```

Règles :

- code stable, déterministe, non localisé ;
- paramètres numériques bruts séparés ;
- aucun timestamp courant implicite ;
- aucun long texte ou nombre déjà formaté ;
- frontend responsable des libellés et formats locaux ;
- logs peuvent composer une phrase à partir du même code.

Pour la compatibilité, une v2 peut ajouter `reason_code`/`reason_params` tout en
gardant temporairement `reason: string|null`. Aucun changement n'est fait ici.

## 10. Raw value et components

`raw_value` conserve la valeur principale :

- ATR : ATR normalisé de préférence, ATR brut dans `components.raw_atr` ;
- ADX/DMI : ADX ;
- Supertrend : ligne Supertrend ;
- Donchian : position normalisée ;
- CMF : CMF ;
- VWAP : distance normalisée.

`components` est un objet strict dont les clés sont définies par la version de
l'indicateur :

```json
{
  "raw_atr": { "value": 125.4, "normalized_value": null, "unit": "quote" },
  "normalized_atr": { "value": 0.0125, "normalized_value": 0.0125, "unit": "ratio" }
}
```

Chaque composant précise :

| Champ              | Usage                                                        |
| ------------------ | ------------------------------------------------------------ |
| `value`            | valeur native finie                                          |
| `normalized_value` | feature comparable, nullable si non définie                  |
| `unit`             | `price`, `ratio`, `percent`, `index`, `volume` ou `unitless` |

Les clés et unités font partie du contrat. Un dict arbitraire non validé
réintroduirait l'ambiguïté actuelle de `raw_value`.

## 11. Normalisation

Deux couches :

1. normalisation déterministe runtime, versionnée avec l'indicateur
   (`ATR/close`, distance/VWAP, position Donchian) ;
2. preprocessing statistique IA, ajusté uniquement sur le train.

La seconde ne doit pas apparaître comme valeur runtime universelle. Sa
configuration stocke méthode, fenêtre ou estimateur, période d'entraînement,
clip et fingerprint.

## 12. Warmup et lookback

Chaque définition déclare :

```text
minimum_bars
recommended_bars
first_available_index
dependency_warmup
```

Le minimum est mathématique ; le recommandé vise la stabilité. Les indicateurs
composés prennent le maximum causal de leurs dépendances et de leurs propres
besoins. Une valeur partielle n'est pas `available`.

Exemple :

```text
true_range: 2 bougies
atr_14: minimum 15, recommandé 114
supertrend_10: dépend d'atr_10, minimum effectif >= 12
adx_14: deux lissages Wilder, minimum 29, recommandé 128
```

## 13. Configuration

Proposition :

```json
{
  "indicator_catalog_version": 1,
  "indicators": {
    "atr": {
      "enabled": true,
      "version": 1,
      "parameters": { "period": 14, "warmup_bars": 114 }
    },
    "adx_dmi": {
      "enabled": true,
      "version": 1,
      "parameters": { "period": 14, "weak_max": 20, "strong_min": 25 }
    }
  }
}
```

Contraintes :

- objets stricts, clés inconnues refusées ;
- defaults documentés et injectés par validation ;
- `enabled` explicite ;
- absence compatible selon la version du profil ;
- paramètres bornés et relations validées ;
- ordre des listes conservé seulement s'il a une sémantique ;
- JSON canonique, clés triées, nombres finis, fingerprint SHA-256 ;
- ajout d'un indicateur non activé ne change pas le fingerprint historique ;
- changement de formule ou sémantique augmente `indicator_version`.

## 14. Registry et graphe de calcul

Interface conceptuelle :

```python
class IndicatorDefinition:
    id: str
    version: int
    inputs: tuple[str, ...]
    dependencies: tuple[str, ...]
    minimum_bars: Callable[[Mapping[str, object]], int]
    calculate: Callable[..., Mapping[str, pd.Series]]
    classify: Callable[..., IndicatorSignal]
```

Le registre est explicite, importé statiquement et testé pour IDs uniques. Un
plan topologique :

1. valide la configuration ;
2. résout les dépendances sans cycle ;
3. calcule les primitives ;
4. calcule les indicateurs ;
5. construit signal/state ;
6. sérialise à la frontière.

Commencer avec un registre léger et quelques appels explicites. Ne pas
introduire une infrastructure complexe avant que les dépendances ATR le
justifient.

## 15. Primitives proposées

```text
true_range(high, low, previous_close)
wilder_smoothing(series, period)
rolling_extrema(high, low, period, exclude_current)
typical_price(high, low, close)
safe_ratio(numerator, denominator)
finite_or_status(value)
```

Elles retournent des séries numériques ou un diagnostic technique, pas une
direction, un signal ou une phrase.

## 16. Parité live/backtest

Chaîne unique :

```text
OHLCV normalisé
-> plan de calcul partagé
-> valeurs/composants
-> classification partagée
-> bundle versionné
-> adaptateur public
```

Sources :

- scanner : bougies closes CCXT normalisées ;
- marché confirmed : bougies closes ;
- marché provisional : mêmes fonctions, avec `is_forming=true` ;
- replay : bougies persistées closes jusqu'au temps de décision ;
- audit/IA : bougies persistées closes.

Les services ne doivent contenir aucune copie de formule. Des oracles comparent
exactement valeurs, statuts, directions, événements et états aux mêmes bornes.

## 17. Sérialisation et précision

- pandas/NumPy `float64` pour fenêtres et lissages ;
- conversion en `float` Python uniquement à la frontière ;
- contrôle `math.isfinite` avant Pydantic/JSON ;
- arrondi réservé à l'affichage ou aux champs legacy déjà définis ;
- aucune conversion globale en `Decimal` pour les indicateurs ;
- `Decimal` conservé pour le portefeuille et les montants ;
- fingerprint construit sur configuration canonique, jamais sur un float
  formaté par locale.

## 18. Frontend futur

À l'implémentation :

- étendre `IndicatorName` et Zod explicitement ;
- créer des métadonnées d'ordre, libellés et unités ;
- rendre `components` sans supposer une monnaie ;
- traduire `reason.code` dans l'UI ;
- distinguer confirmed/provisional ;
- ne recalculer ni normalisation, ni signal, ni confluence dans React ;
- conserver les payloads historiques sans `indicator_signals`.

## 19. Exports

Ne pas injecter un JSON arbitraire dans le CSV scanner actuel. Choix futur :

- export long versionné : une ligne par timestamp/indicateur/composant ;
- export wide versionné : colonnes figées par version ;
- JSON/Parquet pour datasets IA.

Chaque export inclut version de contrat, indicateur, config fingerprint,
decision_time, data_through et candle_state.

## 20. Observation IA

```json
{
  "metadata": {
    "timestamp": "...",
    "symbol": "BTC/USDC",
    "timeframe": "4h",
    "feature_schema_version": 1
  },
  "features": {
    "indicator_raw_values": {},
    "indicator_normalized_values": {},
    "indicator_states": {},
    "indicator_signals": {},
    "market_regime": null
  },
  "labels": {
    "forward_return_6": null
  }
}
```

La génération construit d'abord et persiste les features au temps de décision.
Les labels sont joints ensuite par identifiant/temps, sans devenir des inputs.
Train, validation et test restent chronologiques ; les estimateurs de
normalisation et la sélection de features ignorent le test final.

## 21. Compatibilité et migration

1. implémenter les calculs internes sans exposition publique ;
2. figer leur formule et tests ;
3. proposer une enveloppe v2 additive ;
4. mettre à jour Pydantic/OpenAPI et Zod/TypeScript ensemble ;
5. supporter les anciens payloads ;
6. intégrer l'UI ;
7. ajouter exports versionnés ;
8. seulement ensuite envisager filtres/confluence dans une phase expérimentale.

La Phase 8.1 s'arrête avant l'étape 1.
