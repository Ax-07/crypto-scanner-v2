# Filtres de signaux structurés

## Contrat courant

La version courante et seule version acceptée est `1`. Le champ additif
`ScanConfig.structured_signal_filters` est optionnel et nullable. Une version
absente n'est jamais déduite de la forme du payload ; une version autre que `1`
est rejetée par Pydantic avec une réponse HTTP 422 et par Zod côté frontend.

```json
{
  "version": 1,
  "indicators": {
    "macd": {
      "match": "all",
      "conditions": [
        {"field": "direction", "values": ["bullish"]}
      ]
    }
  }
}
```

Les seuls indicateurs filtrables en v1 sont `macd`, `bollinger` et
`stochastic`. Les champs sont strictement limités à :

- `direction` : `bullish`, `bearish` ou `neutral` ;
- `signal` : chaîne non vide ;
- `state` : chaîne non vide ;
- `status` : `available`, `insufficient_data`, `invalid_data` ou `disabled`.

`raw_value` et `strength` ne sont pas filtrables en v1. Chaque `values` est une
liste non vide, sans doublon. Les objets refusent les clés inconnues.
`conditions: []` est toutefois autorisé : il neutralise explicitement le filtre
de cet indicateur et empêche tout fallback vers son champ legacy.

## Logique de correspondance

Les valeurs d'une condition sont combinées en OR. Les conditions utilisent le
`match` du groupe :

- `all` : toutes les conditions doivent passer ;
- `any` : au moins une condition doit passer.

Les différents indicateurs présents sont toujours combinés en AND. Un groupe
non vide sans condition `status` exige implicitement `status="available"`.
Une condition `status` explicite est évaluée strictement. Un signal absent ne
correspond à aucune condition. Seule la désactivation configurée est synthétisée
dans une copie locale pour rendre `status=["disabled"]` filtrable ; elle n'est
pas ajoutée aux résultats publics, qui continuent d'omettre l'indicateur.

## Audit et matrice legacy

| Champ historique | Valeur | Dimension v1 de l'adaptateur | Valeur v1 |
|---|---|---|---|
| `filter_macd_signal` | `bullish` | `direction` | `bullish` |
| | `bearish` | `direction` | `bearish` |
| | `neutral` | `direction` | `neutral` |
| `filter_bb_position` | `oversold` | `state` | `oversold` |
| | `near_oversold` | `state` | `near_oversold` |
| | `neutral` | `state` | `neutral` |
| | `near_overbought` | `state` | `near_overbought` |
| | `overbought` | `state` | `overbought` |
| `filter_stoch_signal` | `bullish_cross` | `signal` | `bullish_cross` |
| | `oversold` | `signal` | `oversold` |
| | `neutral` | `signal` | `neutral` |
| | `bearish_cross` | `signal` | `bearish_cross` |
| | `overbought` | `signal` | `overbought` |

Le cas Stochastique est volontairement précis. Historiquement,
`detect_stochastic_signal` renvoie un croisement en priorité, sinon une zone,
sinon `neutral`. Le builder structuré recopie exactement cette classe dans
`IndicatorSignal.signal` et conserve simultanément la zone courante dans
`state`. Mapper le legacy `oversold` vers `state` accepterait à tort un
`bullish_cross` survenu en survente. L'adaptateur utilise donc `signal` pour ses
cinq valeurs, ce que les tests exhaustifs de parité vérifient. Une nouvelle
configuration peut librement cibler `state`.

## Priorité et compatibilité

`check_signal_filters` reste inchangée et demeure le chemin exécuté lorsqu'aucun
nouveau contrat n'est fourni. En coexistence, la priorité est résolue par
indicateur :

1. si une clé structurée existe, son groupe est utilisé, même vide ;
2. sinon, le filtre legacy de cet indicateur est converti et utilisé ;
3. les indicateurs effectifs sont combinés en AND.

Les champs `filter_macd_signal`, `filter_bb_position` et
`filter_stoch_signal` ne sont ni retirés ni renommés. Les anciens payloads et
jobs restent valides. Le fingerprint des profils historiques sans nouveau
contrat reste inchangé.

Le moteur pur est :

```python
check_structured_signal_filters(
    *,
    indicator_signals: Mapping[str, IndicatorSignal],
    filters: Mapping[str, object],
) -> bool
```

L'adaptateur pur est :

```python
legacy_filters_to_structured(
    *,
    filter_macd: Sequence[str] | None,
    filter_bb: Sequence[str] | None,
    filter_stoch: Sequence[str] | None,
) -> dict[str, object] | None
```

Le scanner et le moteur canonique du replay utilisent les signaux déjà calculés.
Depuis la Phase 5.8, le scanner ne relance plus le moteur canonique uniquement
pour contrôler la parité : ce contrôle est conservé dans les tests. Cette
migration n'ajoute aucun appel OHLCV et ne modifie ni score de confluence, ni
export CSV.

Le contrat figé, les matrices complètes, fingerprints et compteurs d'appels sont
documentés dans
[structured-signal-filters-v1-stability.md](structured-signal-filters-v1-stability.md).

## Exemples

MACD :

```json
{"version":1,"indicators":{"macd":{"match":"all","conditions":[{"field":"direction","values":["bullish"]}]}}}
```

Bollinger :

```json
{
  "version": 1,
  "indicators": {
    "bollinger": {
      "match": "any",
      "conditions": [
        {"field": "state", "values": ["oversold", "near_oversold"]},
        {"field": "signal", "values": ["lower_band_reentry"]}
      ]
    }
  }
}
```

Stochastique, nouvelle règle événement OU état :

```json
{
  "version": 1,
  "indicators": {
    "stochastic": {
      "match": "any",
      "conditions": [
        {"field": "signal", "values": ["bullish_cross"]},
        {"field": "state", "values": ["oversold"]}
      ]
    }
  }
}
```

L'équivalent strict du legacy
`filter_stoch_signal=["bullish_cross","oversold"]` utilise une seule condition
`{"field":"signal","values":["bullish_cross","oversold"]}`.

## Dépréciation progressive

La v1 est additive. Aucun calendrier de suppression n'est annoncé. Toute rupture
exige une nouvelle version ; `strength` et `raw_value` restent hors v1. La
prochaine étape doit être choisie à partir de mesures d'usage réelles.
