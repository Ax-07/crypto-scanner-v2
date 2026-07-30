# Rapport d'implémentation — Phase 8.2

## Synthèse numérotée

1. **État Git initial** — branche `main`, index vide, arbre non propre à cause
   des livrables documentaires Phase 8.1 déjà présents.
2. **HEAD initial** — `cb231a1` (`cb231a1f39ea44f2c1f98cd456c3213d28c563ce`).
3. **Changements préexistants** — `docs/CURRENT_APP_STATE_FOR_AI.md` modifié ;
   `docs/architecture/`, `docs/audits/indicator-catalog-v1.{md,json}`,
   `docs/audits/indicator-complementarity-matrix-v1.md` et `docs/roadmaps/` non
   suivis. Ils ont été conservés ; aucun `git add` ou commit n'a été exécuté.
4. **Fichiers inspectés** — configuration, limites, indicateurs, bundle,
   scanner, flux marché, replay/backtest, portefeuille, modèles/API, persistance,
   export CSV, types/schémas/composants/tests frontend, tests backend et
   documentation Phase 8.1.
5. **Architecture retenue** — primitives Wilder pures, orchestrateur étendu
   partagé, blocs de configuration optionnels versionnés et contrat additif
   `components`.
6. **Modules créés** — `wilder.py`, `atr.py`, `adx.py`, `supertrend.py`, le test
   Phase 8.2 et la documentation technique dédiée.
7. **Modules modifiés** — settings, limites, types/exports domaine, bundle,
   backtesting, scanner, market stream, modèle public, fingerprint portefeuille,
   types/Zod/formulaire/cartes/tests frontend et documents d'état.
8. **True Range** — première ligne `high-low`, puis maximum de la plage et des
   deux gaps au close précédent.
9. **ATR** — lissage Wilder du True Range.
10. **Amorçage ATR** — moyenne simple des `p` premières valeurs valides.
11. **Warm-up ATR** — ATR à `p` bougies ; signal ATR/NATR à `p+1`, car deux
    valeurs NATR sont nécessaires.
12. **NATR** — `100 * ATR / close`.
13. **Unité NATR** — pourcentage ; `raw_value` ATR est donc un pourcentage.
14. **Composants ATR** — `true_range`, `atr`, `natr`, `natr_change`.
15. **Sémantique ATR** — volatilité uniquement, direction toujours `neutral`.
16. **Signaux ATR** — `volatility_expansion`, `volatility_contraction` ou
    `volatility_stable`, seulement lors d'une transition d'état.
17. **Directional Movement** — `up=high-high[-1]`, `down=low[-1]-low` ;
    `+DM=up` uniquement si `up>down` et `up>0`, symétriquement pour `-DM` ;
    égalité = deux zéros.
18. **+DI** — `100 * Wilder(+DM) / Wilder(TR)`.
19. **-DI** — `100 * Wilder(-DM) / Wilder(TR)`.
20. **DX** — `100 * abs(+DI - -DI) / (+DI + -DI)` ; dénominateur nul = zéro.
21. **ADX** — lissage Wilder de DX.
22. **Amorçage ADX** — DMI/DX à l'index `p-1`, puis SMA des `p` premiers DX.
23. **Warm-up ADX** — premier ADX à l'index `2p-2`, soit `2p-1` bougies
    (27 pour `p=14`).
24. **Composants ADX** — `adx`, `plus_di`, `minus_di`, `dx`.
25. **États ADX** — `weak_trend` sous 20, `developing_trend` de 20 à moins de
    25, `strong_trend` à partir de 25 ; seuils configurables.
26. **Signaux ADX** — croisements haussier/baissier prioritaires, puis
    `trend_strengthening`/`trend_weakening`.
27. **Direction DMI** — comparaison stricte de `+DI` et `-DI`, égalité neutre.
28. **Strength ADX** — `clamp(ADX/50, 0, 1)`.
29. **Supertrend** — bandes de base `hl2 ± multiplier*ATR`.
30. **Amorçage Supertrend** — au premier ATR valide, bandes finales initialisées
    aux bandes de base et régime défini par `close >= hl2`.
31. **Bandes finales** — récurrence causale sur bande et close précédents.
32. **Direction Supertrend** — `bullish/uptrend` ou `bearish/downtrend`.
33. **Flips** — événement seulement si le régime de la ligne précédente change.
34. **Composants Supertrend** — ligne, bandes haute/basse, ATR et
    `distance_ratio`.
35. **Strength Supertrend** — distance absolue close/ligne en unités ATR, bornée.
36. **Statuts** — `available`, `insufficient_data`, `invalid_data`, `disabled`
    restent le vocabulaire commun.
37. **Données invalides** — non-finies, prix non positifs ou `high<low`
    produisent un statut explicite et réamorcent la séquence ; aucun NaN public.
38. **Désactivation** — bloc absent ou `enabled=false` : aucun nouveau signal
    n'est ajouté au dictionnaire public.
39. **Mutualisation** — un seul True Range par bundle et cache ATR par période ;
    Supertrend réutilise l'ATR identique.
40. **Configuration backend** — blocs `atr`, `adx`, `supertrend` optionnels dans
    `ScanConfig` et `MarketIndicatorConfig`.
41. **Valeurs par défaut** — ATR 14 ; ADX 14/20/25 ; Supertrend 10 × 3 ; tous
    désactivés.
42. **Validation** — versions littérales v1, périodes bornées, multiplicateur
    fini positif et seuil ADX faible strictement inférieur au fort.
43. **Fingerprints** — les champs absents sont exclus pour conserver les hashes
    historiques ; un bloc déclaré devient une partie du fingerprint.
44. **Contrat `components`** — mapping optionnel de composants
    `{value, normalized_value, unit}` avec unités bornées.
45. **Versionnement** — version `1` obligatoire dans chaque bloc.
46. **Bundle** — `calculate_extended_indicator_bundle` construit calculs bruts
    et signaux structurés.
47. **Live** — le marché confirmé et provisoire appelle le bundle partagé.
48. **Backtest** — `evaluate_information_set` appelle le même bundle et persiste
    les signaux dans l'observation.
49. **Parité** — un test compare exactement les payloads marché et replay.
50. **Filtres** — aucun nom nouveau n'est accepté par les filtres structurés v1.
51. **Confluence** — seuls RSI/MACD/Bollinger/Stochastique sont transmis au
    calcul structuré ; poids et résultat historiques sont inchangés.
52. **Trades** — le test de neutralité compare les listes de trades.
53. **API** — les blocs apparaissent dans OpenAPI et les observations sérialisées
    exposent les composants.
54. **Persistance** — le JSON générique d'`indicator_signals` absorbe les clés
    sans migration SQL.
55. **Exports** — l'export CSV historique reste volontairement inchangé et
    n'aplatit pas les signaux structurés.
56. **TypeScript** — trois noms, trois configurations, composant/unité et unions
    de composants ajoutés.
57. **Zod** — objets de composants stricts, valeurs finies, unités énumérées et
    dictionnaire à neuf indicateurs.
58. **Formulaire** — trois cartes de configuration ; les anciens payloads sont
    normalisés vers des blocs désactivés.
59. **Payload** — après édition, les blocs versionnés explicites sont envoyés ;
    l'API continue d'accepter leur absence.
60. **Cartes frontend** — état, valeur principale, composants, force et raison.
61. **Unités** — prix, pourcentage, ratio et index rendus sans ambiguïté.
62. **Libellés** — noms, états et événements Phase 8.2 traduits en français.
63. **Accessibilité** — structure `article`, titre accessible, badges existants
    et composants en liste de définition.
64. **Responsive** — grille de composants deux colonnes dans les cartes et
    grille globale existante mobile/desktop.
65. **Tests ATR** — TR connu, seed Wilder, NATR, neutralité, états/transitions,
    invalides et zéros.
66. **Tests ADX** — égalités DM, DI/DX/ADX connus, warm-up et dénominateurs nuls.
67. **Tests Supertrend** — bandes/régime, flip non répété et données invalides.
68. **Anti-look-ahead** — comparaison de tous les préfixes Supertrend avant
    ajout de la dernière bougie.
69. **Parité** — payloads marché/replay strictement identiques.
70. **Neutralité** — filtres, confluence, `accepted`, trades et equity comparés.
71. **API** — OpenAPI config, schéma Pydantic des composants et JSON sans NaN.
72. **Frontend** — validation legacy/nouveaux blocs, composants stricts,
    libellés, unités et rendu.
73. **Performance** — mesure indicative locale : 100 bundles complets de 500
    bougies en 20,586521 s, moyenne 205,865 ms ; aucune assertion temporelle
    fragile.
74. **Fichiers créés** — les quatre modules indicateurs, le test Phase 8.2, cette
    documentation et `indicators-atr-adx-supertrend-v1.md`.
75. **Fichiers modifiés** — voir sections 7 et le `git diff --stat` final.
76. **Tests backend ciblés** — 10 tests Phase 8.2 réussis ; avec le contrat
    filtres/fingerprint : 87 réussis lors du passage ciblé précédent.
77. **Tests frontend ciblés** — 55 tests ciblés, puis suite complète verte.
78. **Backend complet** — 707 réussis, 1 ignoré, 27 subtests, 2 avertissements
    pandas préexistants.
79. **Frontend complet** — 48 fichiers, 306 tests ; typecheck, ESLint et build
    Vite réussis.
80. **Lockfile** — `frontend/pnpm-lock.yaml` inchangé.
81. **Dépendances** — `backend/requirements.txt` et `frontend/package.json`
    inchangés ; installation `--frozen-lockfile --force` réussie depuis le cache.
82. **Diff Git final** — `git diff --check` réussi, index vide, HEAD
    `cb231a1`, branche `main`; avertissements locaux LF/CRLF seulement.
83. **Limites** — valeurs observables mais non évaluées comme features de
    stratégie ; Supertrend est itératif ; CSV structuré toujours absent ; aucune
    donnée externe au OHLCV.
84. **Phase 8.3** — ne pas la commencer ici. Prochaine famille recommandée :
    Bollinger Band Width et Donchian causal, toujours sans filtre/confluence
    avant une expérience séparée.

## Extraits réels

### True Range

```python
value = current_high - current_low
if previous_close is not None:
    value = max(
        value,
        abs(current_high - previous_close),
        abs(current_low - previous_close),
    )
```

### ATR/NATR et signal ATR

```python
def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
    *,
    true_range: pd.Series | None = None,
) -> dict[str, pd.Series]:
    tr = true_range if true_range is not None else calculate_true_range(high, low, close)
    return {"true_range": tr.copy(), "atr": wilder_smoothing(tr, period)}

result.loc[valid] = 100.0 * aligned.loc[valid, "atr"] / aligned.loc[valid, "close"]

return IndicatorSignal(
    status="available",
    direction="neutral",
    signal=event,
    state=state,
    strength=_clamp_strength(relative_change),
    raw_value=current_natr,
    components=components,
)
```

### ADX/DMI et signal structuré

```python
def calculate_adx_dmi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
    *,
    true_range: pd.Series | None = None,
) -> dict[str, pd.Series]:
    tr = true_range if true_range is not None else calculate_true_range(high, low, close)
    movement = calculate_directional_movement(high, low)
    smoothed_tr = wilder_smoothing(tr, period)
    smoothed_plus = wilder_smoothing(movement["plus_dm"], period)
    smoothed_minus = wilder_smoothing(movement["minus_dm"], period)

plus_di.loc[positive] = 100.0 * smoothed_plus.loc[positive] / smoothed_tr.loc[positive]
minus_di.loc[positive] = 100.0 * smoothed_minus.loc[positive] / smoothed_tr.loc[positive]
dx.loc[di_ready & (denominator == 0)] = 0.0
adx = wilder_smoothing(dx, period).rename("adx")

return IndicatorSignal(
    status="available",
    direction=direction,
    signal=event,
    state=state,
    strength=_clamp_strength(adx / 50.0),
    raw_value=adx,
    components={
        "adx": _component(adx),
        "plus_di": _component(plus_di),
        "minus_di": _component(minus_di),
        "dx": _component(dx),
    },
)
```

### Supertrend et signal structuré

```python
def calculate_supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr_period: int = 10,
    multiplier: float = 3.0,
    *,
    atr: pd.Series | None = None,
) -> dict[str, pd.Series]:
    frame = pd.concat(
        [
            high.astype(float).rename("high"),
            low.astype(float).rename("low"),
            close.astype(float).rename("close"),
        ],
        axis=1,
    )

basic_upper = hl2 + multiplier * atr_series
basic_lower = hl2 - multiplier * atr_series
upper.loc[index] = (
    current_values[4]
    if current_values[4] < previous_upper or previous_close > previous_upper
    else previous_upper
)
lower.loc[index] = (
    current_values[5]
    if current_values[5] > previous_lower or previous_close < previous_lower
    else previous_lower
)

return IndicatorSignal(
    status="available",
    direction=direction,
    signal=event,
    state=state,
    strength=_clamp_strength(distance_atr),
    raw_value=current["supertrend"],
    components={
        "supertrend": _price_component(current["supertrend"]),
        "upper_band": _price_component(current["upper_band"]),
        "lower_band": _price_component(current["lower_band"]),
        "atr": _price_component(current["atr"]),
        "distance_ratio": IndicatorComponent(
            value=distance_ratio,
            normalized_value=distance_ratio,
            unit="ratio",
        ),
    },
)
```

### Schémas frontend des composants

```typescript
export const indicatorComponentSchema: z.ZodType<IndicatorComponent> = z.strictObject({
  value: z.number().finite().nullable(),
  normalized_value: z.number().finite().nullable(),
  unit: z.enum(["price", "percent", "ratio", "index", "volume", "unitless"]),
})

const atrComponentsSchema = z.strictObject({
  true_range: indicatorComponentSchema,
  atr: indicatorComponentSchema,
  natr: indicatorComponentSchema,
  natr_change: indicatorComponentSchema,
})
```

### Rendu d'un nouvel indicateur

```tsx
{!compact && signal.components ? (
  <dl className="grid grid-cols-2 gap-x-3 gap-y-2 rounded-md border p-3 text-sm">
    {Object.entries(signal.components).map(([name, component]) => (
      <div key={name} className="min-w-0">
        <dt className="truncate text-xs text-muted-foreground">
          {formatTechnicalLabel(name)}
        </dt>
        <dd className="truncate font-medium">{formatComponentValue(component)}</dd>
      </div>
    ))}
  </dl>
) : null}
```

### Preuve de neutralité portefeuille

```python
# Nouveaux indicateurs activés -> accepted, trades et equity inchangés.
assert observed.accepted == base.accepted
assert observed_result.trades == base_result.trades
assert observed_result.equity_curve == base_result.equity_curve
```

## Validations finales

```text
Pytest       707 passed, 1 skipped, 27 subtests, 2 warnings
compileall   succès
Black        139 fichiers inchangés
Flake8       succès
mypy         succès, 90 fichiers source
TypeScript   succès
ESLint       succès, zéro warning
Vitest       48 fichiers / 306 tests
Vite build   succès, 2065 modules transformés
```
