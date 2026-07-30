# Roadmap d'extension des indicateurs v1

## Principes communs

Chaque phase :

- utilise uniquement timestamp/OHLCV ;
- calcule sur les seules données disponibles à la clôture ;
- exécute potentiellement à l'ouverture suivante ;
- partage les mêmes fonctions entre scanner, live, replay, audit et IA ;
- refuse NaN, infini et valeurs partielles publiques ;
- ajoute des tests de formule, warmup, causalité, statut et parité ;
- ne modifie ni filtre ni confluence de production sans expérience séparée ;
- n'ajoute aucune dépendance technique externe.

Le catalogue cible 12 composants sur plusieurs phases. Une phase n'est pas une
autorisation d'implémenter la suivante.

## Phase 8.2 — primitive de volatilité et force de tendance

**Statut : implémentée.** ATR/NATR, ADX/DMI et Supertrend sont disponibles de
bout en bout comme observations optionnelles. Les critères de causalité,
mutualisation, parité et neutralité métier sont couverts ; aucun filtre ni
facteur de confluence n'a été ajouté. La Phase 8.3 reste non autorisée par ce
statut.

### Objectif

Ajouter une première famille cohérente et réutilisable :

```text
true range -> ATR/NATR -> ADX/DMI
                        -> Supertrend
```

### Indicateurs

- ATR brut ;
- ATR normalisé (`ATR/close`, plus variante pourcentage d'affichage) ;
- +DI, -DI et ADX ;
- Supertrend et ses bandes internes.

### Dépendances

- primitive `true_range` ;
- lissage Wilder partagé ;
- contrat multi-valeurs ;
- convention événement versus état ;
- warmup mathématique et recommandé.

### Fichiers probables

```text
backend/app/domain/indicators/true_range.py
backend/app/domain/indicators/atr.py
backend/app/domain/indicators/adx.py
backend/app/domain/indicators/supertrend.py
backend/app/domain/indicator_bundle.py
backend/app/domain/limits.py
backend/app/core/settings.py
backend/app/domain/backtesting.py
backend/app/services/scanner.py
backend/app/services/market_stream.py
backend/app/models/
frontend/src/types/
frontend/src/schemas/
frontend/src/components/indicator-signals/
```

La liste est indicative. L'implémentation doit réduire les modifications de
services en introduisant une orchestration partagée plutôt que copier les
formules.

### Tests

- true range avec gap haussier/baissier et égalités ;
- ATR Wilder sur série connue ;
- +DM/-DM mutuellement exclusifs et égalités ;
- ADX faible/fort, DI cross, strengthening/weakening ;
- Supertrend flip, état persistant, bandes finales ;
- lookback 15/29 et warmup configuré ;
- constantes, volume absent sans effet, NaN/infini, prix nul/invalide ;
- mutation de bougies futures sans effet sur `t` ;
- breakout/flip non répété ;
- parité scanner/confirmed live/replay ;
- provisional clairement révisable ;
- aucune modification des décisions/filtres/confluence existants quand les
  nouveaux indicateurs sont absents ou seulement observés.

### Documentation

- formule et conventions exactes ;
- paramètres/defaults ;
- exemples JSON ;
- migration Pydantic/TypeScript/Zod ;
- limites et coût ;
- mise à jour de l'état applicatif.

### Risques

- variantes incompatibles du lissage ADX ;
- initialisation de Supertrend ambiguë ;
- confusion ATR montant/biais bullish ;
- publication partielle de DMI ;
- double calcul du true range ;
- augmentation du lookback réseau ;
- dérive scanner/replay.

### Critères d'acceptation

- une seule définition de true range et Wilder ;
- résultats déterministes et finis ;
- composants ADX/+DI/-DI atomiques ;
- `direction` vient de DMI, force de ADX ;
- Supertrend dépend du résultat ATR partagé ;
- close `t` uniquement, exécution possible `t+1` ;
- runtime historique inchangé tant qu'aucun nouveau filtre n'est activé ;
- suites backend/frontend complètes vertes ;
- aucun nouveau filtre/confluence/stratégie.

## Phase 8.3 — compression et structure roulante

**Statut : implémentée.** Bollinger Band Width enrichit les composants
Bollinger sans modifier son verdict historique. Donchian et Keltner sont
disponibles de bout en bout, désactivés par défaut, avec cassures causales et
neutralité métier automatisée.

### Objectif

Exposer volatilité relative et cassure causale sans stratégie de squeeze.

### Indicateurs

- Bollinger Band Width comme composant des bandes existantes ;
- Donchian upper/middle/lower, largeur et position ;
- Keltner EMA/ATR, bornes, largeur et position ;
- primitive rolling high/low causale.

### Dépendances

- bandes Bollinger actuelles, sans recalcul ;
- rolling extrema avec option `exclude_current=True` ;
- ATR/NATR de 8.2 pour normaliser la distance de breakout.
- EMA canonique et ATR Wilder partagé pour Keltner.

### Fichiers probables

`bollinger.py`, nouveaux `donchian.py` et `keltner.py`, bundle, limites,
orchestration partagée, contrats et composants frontend.

### Tests

- largeur nulle/invalide ;
- compression/expansion avec contexte causal ;
- canal Donchian incluant/excluant `t` ;
- breakout comparé strictement au canal terminé à `t-1` ;
- aucun repaint après ajout de futures bougies ;
- réutilisation du calcul Bollinger.

### Risques

- déclarer une compression avec un seuil universel non validé ;
- fuite via borne de la bougie courante ;
- duplication de rolling min/max du Stochastique ;
- confusion état de canal et événement de cassure.

### Critères d'acceptation

BB Width est dérivé du résultat Bollinger existant, Donchian et Keltner sont
causaux et leurs événements ne se répètent pas. Aucun squeeze ou filtre de
breakout n'est ajouté.

## Phase 8.4 — participation et flux OHLCV

### Objectif

Combler la famille volume avec quatre vues complémentaires.

### Indicateurs

- volume relatif ;
- Chaikin Money Flow ;
- OBV avec features dérivées ;
- VWAP roulant et distance normalisée.

### Dépendances

- prix typique/money-flow multiplier ;
- fenêtres volume robustes ;
- convention volume nul ;
- normalisations inter-symboles.

### Fichiers probables

Nouveaux modules `volume.py`, `cmf.py`, `obv.py`, `vwap.py`, bundle,
configuration, contrats, frontend et tests.

### Tests

- volume nul, constant, extrême et non fini ;
- fenêtre sans volume -> `invalid_data` ;
- OBV indépendant du niveau initial pour ses features dérivées ;
- CMF borné sur séries connues ;
- VWAP rolling sans frontière de session implicite ;
- volume relatif excluant ou incluant `t` selon convention figée ;
- causalité/parité multi-surface.

### Risques

- présenter Binance comme volume global ;
- comparer OBV brut entre actifs ;
- ambiguïté session VWAP en crypto 24/7 ;
- CMF/OBV trop corrélés ;
- volume artificiel ou wash trading.

### Critères d'acceptation

La provenance Binance est documentée, aucune valeur cumulative brute n'est une
feature inter-actifs, et les quatre composants restent observatoires.

## Phase 8.5 — momentum complémentaire minimal

### Objectif

Ajouter seulement deux features de momentum dont la formule diffère des
oscillateurs existants.

### Indicateurs

- CCI(20) ;
- ROC(12).

### Dépendances

- prix typique ;
- safe ratio ;
- convention de normalisation non bornée.

### Fichiers probables

Nouveaux `cci.py`, `roc.py`, bundle/registry, configuration, contrats, frontend
et tests.

### Tests

- séries connues, constante et dénominateur nul ;
- cross zéro et événements extrêmes ;
- normalisation causale ;
- non-duplication de Momentum/Williams %R ;
- parité live/backtest.

### Risques

- multiplier des seuils de surachat/survente ;
- corrélation élevée à RSI/Stochastique ;
- z-score entraîné avec validation/test.

### Critères d'acceptation

CCI et ROC sont des features observatoires. Williams %R, Momentum, TSI, MFI et
Ultimate Oscillator ne sont pas ajoutés dans cette phase.

## Phase 8.6 — structure et régime, après mesure

### Objectif

Évaluer si les primitives validées suffisent à produire :

- higher-high/higher-low causaux ;
- cassures confirmées sans repaint ;
- régime trend/range et low/high volatility.

### Dépendances

Donchian, ADX, NATR, BB Width et résultats économiques des phases précédentes.

### Tests

Temps de pivot versus confirmation, aucune révision rétroactive, stabilité des
états, labels futurs séparés des features.

### Risques

Créer un indicateur composite opaque ou optimiser le régime sur le test final.

### Critères d'acceptation

Une spécification préenregistrée précède toute évaluation. Aucun pivot centré
n'est utilisable au temps du pivot.

## Candidats reportés

| Candidat | Condition de réexamen |
|---|---|
| Aroon | ADX validé mais détection d'émergence encore insuffisante |
| Keltner | ATR validé et besoin de squeeze démontré |
| Choppiness / volatilité historique | régime simple insuffisant |
| MFI / ADL | CMF/OBV insuffisants et redondance mesurée |
| Ichimoku | contrat multi-valeurs et alignement temporel stabilisés |
| PSAR / KAMA | besoin incrémental démontré face à Supertrend/MA |
| TSI / Ultimate / Ease of Movement | utilité hors échantillon démontrable |
| order book, OI, funding, liquidations, on-chain, sentiment | source historisée, versionnée et disponible live |

## Candidats rejetés

- Williams %R : quasi-duplicata du Stochastique `%K` ;
- Momentum : quasi-duplicata de ROC ;
- HMA : variante de moyenne avant les familles absentes ;
- pivots centrés/fractales utilisés rétroactivement : fuite temporelle.

## Préparation IA transversale

Les phases peuvent préparer des features, jamais des labels dans le bundle
runtime. Une phase dataset séparée devra :

1. figer un schéma de features ;
2. produire chaque ligne au temps de décision ;
3. joindre les outcomes après coup comme labels ;
4. découper chronologiquement ;
5. ajuster toute normalisation sur train ;
6. conserver validation/test final gelés ;
7. mesurer redondance et importance hors échantillon.

## Décision unique immédiate

La seule phase autorisée après cet audit est la Phase 8.2
`ATR/NATR + ADX/DMI + Supertrend`. Les Phases 8.3 à 8.6 restent une roadmap,
pas une autorisation d'implémentation.
