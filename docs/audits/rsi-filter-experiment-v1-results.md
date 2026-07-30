# Résultats — expérience filtre RSI v1

## 1. Résumé exécutif et conclusion

Catégorie finale : `no_variant_increased_sample_enough`.

R1 et R2 augmentent accepted et les trades, mais restent sous le seuil
préenregistré de 38 trades de développement, ne créent des trades que sur
BTC/USDC 4h et dépassent le garde-fou de concentration top-5. R3 démontre que
neutraliser le goulot RSI produit beaucoup plus de trades, mais dégrade
manifestement le drawdown et les coûts. Aucune variante ne survit, aucune
candidate n'est sélectionnée et le test final reste fermé. La production
`RSI < 35` demeure inchangée ; aucune Phase 7.3 d'assouplissement n'est
recommandée.

## 2. Hypothèse, règle réelle et audit du code

Le RSI est calculé dans `app/domain/indicators/rsi.py` avec Wilder/EWM,
`alpha=1/14`, `adjust=False`, `min_periods=14`. La valeur courante est calculée
dans `evaluate_information_set`, arrondie à deux décimales, puis filtrée par :

```python
rsi_pass = not config.use_rsi or (
    rsi is not None and rsi < config.rsi_threshold
)
```

`ScanConfig` fixe période 14 et seuil 35. La règle est une borne supérieure
stricte, non directionnelle. Elle précède tendance, filtres structurés et
confluence. Les quatre verdicts sont calculés et conservés dans `filter_trace`;
le premier échec devient `rejection_stage`/`rejection_reason`. Les zones 30/70
du signal structuré RSI sont distinctes et n'ont pas été modifiées.

## 3. Manifeste, hash, datasets et segments

- plan : `rsi-filter-experiment-v1-plan.md`
- hash : `sha256:e928998ad8f71429f85db51d3975dc6c46ec3a62f868ba407e5080f84f18ad64`
- baseline : `sha256:7a35c7442778828cd207b6fbaee4a6d8390d6bb8fcb7d79751030d433b44a1b6`
- datasets : BTC/USDC 4h et 1d, LINK/USDC 4h, ONDO/USDC 1h, SUI/USDC 1h
- segmentation : indices 60/20/20 exacts du manifeste Phase 7.1
- portefeuille : 10 000, percent_cash 100 %, frais 0,001, slippage 0,
  `next_open`, `force_close`

## 4. Variantes préenregistrées

```python
VARIANTS = {
    "R0": VariantSpec("R0", Decimal("0"), Decimal("35"), "<"),
    "R1": VariantSpec("R1", Decimal("5"), Decimal("40"), "<"),
    "R2": VariantSpec("R2", Decimal("10"), Decimal("45"), "<"),
    "R3": VariantSpec("R3", None, None, None, diagnostic_control=True),
}
```

R1/R2 conservent la politique des statuts. R3 neutralise uniquement le
prédicat de valeur : une valeur finie et un statut `available` restent requis.

## 5. Baseline reproduite et parité R0

| Bougies/observations | Accepted | Transitions entrée/sortie | Ordres exécutés/rejetés | Trades |
|---:|---:|---:|---:|---:|
| 12 973 | 33 | 22 / 22 | 44 / 0 | 22 |

Les cinq bornes, métriques par marché, raisons de rejet et métriques économiques
sont identiques à la Phase 7.1. Le fingerprint recalculé avant expérience
différait uniquement parce qu'il inclut le HEAD documentaire `3ac63df` au lieu
de `770f002`.

## 6. Funnel et résultats de développement

| Variante | Obs. | RSI fail | RSI seul | Accepted | Transitions | Trades | Rendement égal-pondéré | DD max | PF | Frais |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| R0 | 7 782 | 7 093 | 182 | 29 | 19/19 | 19 | −0,0235 % | 3,6952 % | 0,9854 | 384,45 |
| R1 | 7 782 | 6 388 | 175 | 36 | 24/24 | 24 | 0,3045 % | 3,9462 % | 1,1656 | 489,84 |
| R2 | 7 782 | 5 230 | 169 | 42 | 28/28 | 28 | 0,1967 % | 5,0328 % | 1,0858 | 567,96 |
| R3 | 7 782 | 52 | 0 | 211 | 197/197 | 197 | −5,4395 % | 33,2200 % | 0,7825 | 3 391,60 |

R0 rejette d'abord 7 093 observations au RSI. Les 182 rejets réellement dus au
seul RSI sont beaucoup moins nombreux : la majorité échoue aussi sur un autre
filtre.

## 7. Chevauchements et nouveau goulot

| Variante | RSI + confluence | RSI + tendance | RSI + plusieurs | Premier rejet tendance | Premier rejet confluence |
|---|---:|---:|---:|---:|---:|
| R0 | 1 871 | 102 | 4 938 | 645 | 15 |
| R1 | 1 823 | 96 | 4 294 | 1 295 | 63 |
| R2 | 1 708 | 77 | 3 276 | 2 332 | 178 |
| R3 | 0 | 19 | 33 | 5 633 | 1 886 |

Sans filtre de valeur RSI, la tendance devient le goulot dominant, puis la
confluence. La baisse des rejets RSI ne se transforme donc pas mécaniquement en
accepted ou en trades.

## 8. Résultats par marché et timeframe

| Marché | Variante | Accepted | Trades | Rendement | DD | Nouveaux/disparus |
|---|---|---:|---:|---:|---:|---:|
| BTC/USDC 4h | R0 | 29 | 19 | −0,1173 % | 3,6952 % | 0/0 |
| BTC/USDC 4h | R1 | 36 | 24 | 1,5224 % | 3,9462 % | 7/2 |
| BTC/USDC 4h | R2 | 42 | 28 | 0,9837 % | 5,0328 % | 11/2 |
| BTC/USDC 4h | R3 | 166 | 152 | −31,8708 % | 33,2200 % | 135/2 |
| BTC/USDC 1d | R0/R1/R2 | 0 | 0 | 0 | 0 | 0/0 |
| BTC/USDC 1d | R3 | 45 | 45 | 4,6735 % | 19,1391 % | 45/0 |
| LINK 4h, ONDO 1h, SUI 1h | toutes | 0 | 0 | 0 | 0 | 0/0 |

R1/R2 n'existent économiquement que sur BTC 4h. R3 touche deux plages, mais son
gain BTC 1d ne compense pas la forte perte BTC 4h. La stabilité
inter-marchés/timeframes et temporelle n'est pas démontrée.

## 9. Trades communs, supplémentaires, disparus et séquence

Les comparaisons utilisent la clé exacte
`(entry_observation_id, exit_observation_id, exit_reason)`.

- R1 BTC 4h : 17 communs, 7 supplémentaires, 2 disparus ;
- R2 BTC 4h : 17 communs, 11 supplémentaires, 2 disparus ;
- R3 BTC 4h : 17 communs, 135 supplémentaires, 2 disparus ;
- R3 BTC 1d : 45 supplémentaires.

Une nouvelle entrée peut occuper l'unique position et modifier un trade
ultérieur. Les trades communs ne sont donc pas supposés former une sous-séquence
économiquement indépendante. Aucun pyramiding n'est créé. Toutes les sorties de
développement observées restent `validation_lost`; `end_of_test` est couvert
par les tests de séquence.

## 10. RSI des entrées, outcomes et durée

BTC 4h :

| Variante | RSI entrées min / médiane / max | Durée médiane toutes / nouvelles |
|---|---|---|
| R1 | 25,45 / 33,13 / 39,46 | 1 / 1 barre |
| R2 | 25,45 / 33,33 / 43,98 | 1 / 1 barre |
| R3 | 25,45 / 62,165 / 89,50 | 1 / 1 barre |

Les JSON fournissent aussi q10/q25/q75/q90, distributions accepted/rejected,
gagnants/perdants et durée par raison de sortie.

Pour les nouvelles observations BTC 4h, le rendement outcome moyen à horizon 1
est +0,6166 % (R1, n=7), +0,2432 % (R2, n=13) et −0,2102 % (R3, n=137).
Aux horizons 3/6/12/24, R1 et R2 sont majoritairement négatifs. MFE/MAE,
médiane et taux positif restent dans le JSON. Ces outcomes ne sont jamais
sommés ni assimilés au P&L du portefeuille.

## 11. Élimination, validation et test final

- R1 : `trades<38`, concentration top-5 > 80 %, nouveaux trades sur moins de
  deux datasets ;
- R2 : mêmes motifs ;
- R3 : drawdown supérieur à 2× R0.

Aucune variante ne passe en validation. Le stage validation exécute uniquement
R0 : 2 595 observations, 4 accepted, 3 trades, rendement égal-pondéré
−0,5599 %, drawdown 3,4703 %, PF 0,2133 et 59,87 de frais.

Il n'existe aucun fichier de sélection. Le test final n'est pas ouvert ;
`rsi-filter-experiment-v1-final.json` contient `status=not_opened` et aucune
métrique finale. Aucune sensibilité frais/slippage n'est donc autorisée.

## 12. Invariants, causalité et reproductibilité

- mêmes RSI et signaux RSI pour R0/R1/R2/R3 ;
- SMA, EMA, MACD, Bollinger, Stochastic, confluence, tendance, raw values et
  profils inchangés ;
- R0 strictement identique à la production ;
- monotonie R0 → R1 → R2 sur toute valeur valide ;
- R3 ne transforme aucun statut indisponible/invalide/désactivé ;
- aucune valeur future, outcome, résultat de trade ou segment suivant dans le
  verdict ;
- `next_open`, coûts, sizing, capital et clôture inchangés ;
- quick reproduce/development/validation reproductibles hors durée murale ;
- aucune donnée test dans les JSON développement/validation.

Évaluateur contrefactuel :

```python
matrix = {
    str(item["stage"]): bool(item["passed"])
    for item in observation.filter_trace
}
matrix["rsi"] = rsi_filter_passes(observation, variant)
```

Protection finale :

```python
if len(selected_variants) != 1:
    raise ExperimentInvalidated(
        "le test final exige exactement une variante"
    )
if selection.get("manifest_hash") != manifest_digest:
    raise ExperimentInvalidated("sélection liée à un autre manifeste")
if validation.get("selected_variant") != selected:
    raise ExperimentInvalidated("candidate non issue de la validation")
```

Relaxation mécanique :

```python
if operator in {"<", "<="}:
    return min(Decimal("100"), threshold + delta)
if operator in {">", ">="}:
    return max(Decimal("0"), threshold - delta)
```

Parité production et anti-look-ahead :

```python
assert (r0.accepted, r0.rejection_stage, r0.filter_trace) == (
    original.accepted,
    original.rejection_stage,
    original.filter_trace,
)

before = apply_variant(observations[0], VARIANTS["R2"])
observations[2] = observations[2].model_copy(update={"rsi": 0.0})
after = apply_variant(observations[0], VARIANTS["R2"])
assert before == after
```

## 13. Limites, surapprentissage et recommandation

Les cinq plages sont presque toutes USDC, R1/R2 restent concentrées sur BTC 4h
et les effectifs demeurent faibles. Aucune optimisation exhaustive, permutation,
nouveau marché, cinquième variante, seuil dérivé des distributions ou lecture
du test final n'a été utilisée.

Le contrôle R3 indique que le RSI filtre une quantité importante
d'observations de faible qualité économique dans BTC 4h. Les relaxations
5/10 points sont trop faibles pour atteindre l'échantillon requis et ne se
généralisent pas. Conserver la production. Ne pas lancer une Phase 7.3
d'assouplissement RSI et ne pas improviser +15/+20 après lecture.
