# Rapport d'implémentation Phase 8.3

## Synthèse

La Phase 8.3 implémente Bollinger Band Width, Donchian Channels et Keltner
Channels comme observations additives. Le backend complet est vert. Les
validations frontend ciblées ont réussi avant la reconstruction exigée de
`node_modules`; l'installation complète est ensuite restée bloquée par des
fichiers optionnels verrouillés et un téléchargement refusé par la plateforme.
Le lockfile et les manifestes restent inchangés.

## Rapport demandé

1. **Git initial** — branche `main`, index vide, nombreux changements non
   indexés/non suivis correspondant à la Phase 8.2.
2. **HEAD initial** — `cb231a1` (`cb231a1f39ea44f2c1f98cd456c3213d28c563ce`).
3. **Préexistant** — toute la Phase 8.2 backend/frontend/docs a été préservée ;
   aucun fichier n'a été restauré ou écrasé.
4. **Fichiers inspectés** — sources de vérité imposées, modules d'indicateurs,
   bundle, limites, scanner, marché, replay, modèles, types, Zod, formulaire,
   cartes et tests Phase 8.2.
5. **Architecture** — Bollinger enrichi depuis ses bandes existantes ;
   Donchian/Keltner intégrés à l'orchestrateur étendu partagé.
6. **Modules créés** — `donchian.py`, `keltner.py`, test Phase 8.3,
   documentation backend et présent rapport.
7. **Modules modifiés** — Bollinger, bundle, types/exports, settings, limites,
   trois adaptateurs, fingerprint portefeuille, modèles, frontend et docs.
8. **Bollinger existant** — SMA, écart-type population `ddof=0`,
   multiplicateur configurable, 20 × 2 par défaut.
9. **Enrichissement Bollinger** — un seul calcul des bandes ; composants
   dérivés transmis au signal existant.
10. **Band Width** — `upper_band - lower_band`, unité de prix.
11. **Band Width Percent** — `100 × width / middle_band`, pourcentage.
12. **Position Bollinger** — `(close-lower)/width`, non clampée ; `0.5` si
    largeur nulle valide.
13. **État de volatilité** — le contrat v1 ne possède qu'un `state`; il reste
    celui du verdict historique conformément à l'interdiction de le modifier.
    La série de largeur causale est exposée pour une future observation dédiée.
14. **Signaux Width** — aucun squeeze ou événement arbitraire ajouté.
15. **Neutralité Bollinger** — golden sur les sept champs historiques hors
    `components`.
16. **Donchian descriptif** — rolling max/min incluant `t`.
17. **Donchian précédent** — rolling max/min après `shift(1)`.
18. **Breakout up** — `close_t > previous_upper_channel_t`.
19. **Breakout down** — `close_t < previous_lower_channel_t`.
20. **Égalités** — strictement aucune cassure.
21. **Position Donchian** — ratio non clampé, `0.5` pour largeur nulle.
22. **Largeur Donchian** — absolue et `100 × width / middle`.
23. **Composants Donchian** — huit clés strictes côté TypeScript/Zod.
24. **Signaux Donchian** — `breakout_up`, `breakout_down`, sinon `null`.
25. **States Donchian** — `above_channel`, `below_channel`,
    `inside_channel`.
26. **Direction Donchian** — directionnelle seulement lors d'une nouvelle
    cassure, neutre sinon.
27. **Strength Donchian** — distance à la borne précédente / close, clampée.
28. **EMA Keltner** — `calculate_ema` canonique, aucune copie de formule.
29. **ATR Keltner** — ATR Wilder Phase 8.2 mutualisé par période.
30. **Bandes Keltner** — EMA ± multiplicateur × ATR.
31. **Position Keltner** — ratio non clampé.
32. **Largeur Keltner** — absolue et pourcentage de la ligne centrale.
33. **Signaux Keltner** — franchissement de la bande précédente.
34. **States Keltner** — au-dessus, sous ou dans le canal courant.
35. **Direction Keltner** — décrit l'état relatif du prix.
36. **Strength Keltner** — distance de cassure exprimée en ATR, clampée.
37. **Warmups** — Donchian descriptif `period`, précédent `period+1` ;
    Keltner maximum EMA/ATR plus bande précédente pour l'événement.
38. **Statuts** — quatre statuts communs conservés.
39. **Invalides** — non-fini, close non positif et `high < low` donnent
    `invalid_data`; aucun NaN/infini public.
40. **Désactivés** — Donchian/Keltner absents du payload et non calculés.
41. **Mutualisation** — bandes Bollinger, True Range, ATR et EMA locaux.
42. **Configuration backend** — deux objets version 1 et `extra=forbid`.
43. **Defaults** — Donchian 20 ; Keltner 20/10 × 2 ; désactivés.
44. **Validations** — périodes 1..1000, multiplicateur fini `>0` et `<=100`.
45. **Fingerprints** — champs absents exclus ; présence/activation/paramètres
    fingerprintés ; goldens historiques conservés.
46. **Components** — valeurs, normalisation et unités explicites ; Zod strict.
47. **Bundle** — entrées `donchian`/`keltner`, signaux étendus partagés.
48. **Live** — calcul dans `calculate_indicator_bundle`, vue confirmed et
    provisional selon la politique existante.
49. **Replay** — `evaluate_information_set` utilise le même orchestrateur.
50. **Parité** — fixture commune compare les dictionnaires complets.
51. **Filtres** — aucun nom ajouté aux filtres structurés v1.
52. **Confluence** — les nouveaux noms ne sont jamais transmis au calcul.
53. **Trades** — identiques dans le test bloquant.
54. **Outcomes** — identiques pour le même historique/configuration métier.
55. **Equity** — ordres, exécutions, trades, courbe et métriques identiques.
56. **API** — OpenAPI expose les deux blocs ; anciens payloads reparsés.
57. **Persistance** — JSON `indicator_signals` existant, aucune migration.
58. **Exports** — CSV historiques inchangés.
59. **TypeScript** — noms, configurations et unions de composants étendus.
60. **Zod** — objets Bollinger/Donchian/Keltner stricts et finis.
61. **Formulaire** — switches, périodes et multiplicateur via RHF/Shadcn Field.
62. **Payload** — valeurs normalisées sans mutation ; blocs historiques
    matérialisés désactivés.
63. **Affichage Bollinger** — six composants ajoutés à sa carte.
64. **Affichage Donchian** — bornes, milieu, précédentes, largeur, position,
    état et cassure.
65. **Affichage Keltner** — ligne, bornes, ATR, largeur, position, état,
    cassure.
66. **Unités** — prix, pourcentage et ratio.
67. **Libellés** — français, dont cassures et états de canal.
68. **Accessibilité** — labels associés, textes sans dépendance à la couleur,
    article nommé et statuts textuels.
69. **Responsive** — grilles existantes une colonne puis `sm`/`md`/`xl`.
70. **Tests Bollinger** — réutilisation, formules, constante, golden.
71. **Tests Donchian** — bornes, largeur, position, warmup, égalité,
    cassures, constante et invalidité.
72. **Tests Keltner** — EMA/ATR, bandes, largeur, cassure, non-répétition,
    validation et invalidité.
73. **Anti-look-ahead** — futur modifié pour les trois calculs.
74. **Live/replay** — égalité complète sur fixture synthétique.
75. **Neutralité** — test portefeuille bloquant.
76. **API** — ancien payload, OpenAPI et clés de configuration inconnues.
77. **Frontend** — schéma, config, formulaire, carte et libellés ciblés.
78. **Performance indicative** — 5 000 points, moyenne de 20 passages :
    Bollinger avant 0,528 ms ; enrichi 4,270 ms ; Donchian 7,055 ms ;
    Keltner 316,703 ms ; combiné 327,281 ms.
79. **Créés** — voir point 6 et diff final.
80. **Modifiés** — voir point 7 et diff final.
81. **Backend ciblé** — 58 tests + 11 subtests réussis en 7,08 s.
82. **Frontend ciblé** — 9 fichiers / 101 tests réussis en 7,48 s ;
    typecheck réussi avant la reconstruction `node_modules`.
83. **Backend complet** — 717 réussis, 1 ignoré, 27 subtests, 2 warnings ;
    compileall, Black (142 fichiers), Flake8, mypy (92 sources) verts.
84. **Frontend complet** — non relançable après reconstruction pnpm bloquée :
    paquets optionnels verrouillés, tarball `@hookform/resolvers` absent du
    cache, téléchargement refusé par la plateforme.
85. **Lockfile** — inchangé.
86. **Dépendances** — aucun manifeste modifié, aucune dépendance ajoutée.
87. **Diff Git** — HEAD/index inchangés ; vérification finale documentée au
    terme de la mission.
88. **Limites** — pas de state Width séparé dans le contrat v1, pas de squeeze,
    CSV structuré absent, installation frontend complète bloquée localement.
89. **Phase 8.4** — uniquement la prochaine famille volume de la roadmap
    (volume relatif, CMF, OBV/VWAP selon décision actualisée), toujours sans
    filtre/confluence avant expérience.

## Extraits réels

### Bollinger Band Width et mutualisation

```python
def calculate_bollinger_band_width(
    close: pd.Series,
    bands: dict[str, pd.Series],
) -> dict[str, pd.Series]:
    width = (frame["upper"] - frame["lower"]).rename("band_width")
    width_percent.loc[valid_middle] = (
        100.0 * width.loc[valid_middle] / frame.loc[valid_middle, "middle"]
    )
```

Le builder reçoit le résultat existant :

```python
signals["bollinger"] = build_bollinger_signal(close, bollinger_bands)
```

### Donchian et cassure causale

```python
upper = clean_high.rolling(period, min_periods=period).max()
lower = clean_low.rolling(period, min_periods=period).min()
return {
    "upper_channel": upper,
    "middle_channel": middle,
    "lower_channel": lower,
    "previous_upper_channel": clean_high.shift(1).rolling(
        period, min_periods=period
    ).max(),
    "previous_lower_channel": clean_low.shift(1).rolling(
        period, min_periods=period
    ).min(),
}
```

```python
above = current_close > values["previous_upper_channel"]
below = current_close < values["previous_lower_channel"]
```

### Keltner et événement non répété

```python
middle = middle_line if middle_line is not None else calculate_ema(close, ema_period)
atr_series = (
    atr if atr is not None else calculate_atr(high, low, close, atr_period)["atr"]
)
upper = middle + float(multiplier) * atr_series
lower = middle - float(multiplier) * atr_series
```

```python
if current_close > previous_upper and previous_close <= previous_upper:
    event = "breakout_up"
elif current_close < previous_lower and previous_close >= previous_lower:
    event = "breakout_down"
```

### Zod

```typescript
const donchianComponentsSchema = z.strictObject({
  upper_channel: indicatorComponentSchema,
  middle_channel: indicatorComponentSchema,
  lower_channel: indicatorComponentSchema,
  previous_upper_channel: indicatorComponentSchema,
  previous_lower_channel: indicatorComponentSchema,
  channel_width: indicatorComponentSchema,
  channel_width_percent: indicatorComponentSchema,
  channel_position: indicatorComponentSchema,
})
```

### Rendu React

```tsx
{Object.entries(signal.components).map(([name, component]) => (
  <div key={name} className="min-w-0">
    <dt className="truncate text-xs text-muted-foreground">
      {formatTechnicalLabel(name)}
    </dt>
    <dd className="truncate font-medium">{formatComponentValue(component)}</dd>
  </div>
))}
```

### Neutralité métier

```python
assert observed.accepted == base.accepted
assert observed_portfolio.orders == base_portfolio.orders
assert observed_portfolio.executions == base_portfolio.executions
assert observed_portfolio.trades == base_portfolio.trades
assert observed_portfolio.equity_curve == base_portfolio.equity_curve
assert observed_portfolio.metrics == base_portfolio.metrics
```
