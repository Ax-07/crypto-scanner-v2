# Audit et catalogue des indicateurs v1

## 1. Résumé exécutif

La Phase 8.1 a audité le dépôt au `HEAD` initial `cb231a1`, branche `main`, avec
un arbre propre, sans changement indexé ou non suivi. Elle ne modifie aucun
calcul, filtre, score de confluence, service, route, modèle public, export,
fichier frontend, dépendance ou lockfile.

Le runtime contient exactement six indicateurs techniques : RSI, SMA, EMA,
MACD, bandes de Bollinger et oscillateur stochastique. RSI, MACD, Bollinger et
Stochastique sont `fully_integrated`. SMA et EMA sont
`partially_integrated` : leurs calculs et signaux structurés existent, mais le
scanner et le replay exposent seulement leur agrégation de tendance
multi-timeframe ; leurs signaux structurés individuels ne sont produits que par
le marché live.

La couverture est concentrée sur tendance directionnelle, momentum et position
dans une enveloppe de volatilité. Il manque surtout la force de tendance, la
volatilité normalisée, le volume, les cassures causales, la structure de marché
et un régime explicite. Douze composants sont retenus sur quatre phases :
ATR/NATR, ADX/DMI, Supertrend, Bollinger Band Width, Donchian, volume relatif,
CMF, features OBV, distance au VWAP roulant, CCI et ROC.

La recommandation unique pour la Phase 8.2 est :

```text
ATR + ATR normalisé + ADX/DMI + Supertrend
```

ATR est une primitive mutualisable ; ADX sépare force et direction via +DI/-DI ;
Supertrend réutilise ATR et fournit un état persistant. La Phase 8.2 ne devra
modifier aucun filtre de production.

## 2. Contexte et périmètre

La Phase 7.2 s'est conclue par
`no_variant_increased_sample_enough`. R1 et R2 n'ont pas atteint 38 trades de
développement et sont restées concentrées sur BTC/USDC 4h ; R3 a produit 197
trades mais un rendement de -5,4395 %, 33,2200 % de drawdown et 3 391,60 de
frais. Aucune variante n'a été sélectionnée, le test final n'a pas été ouvert
et la production demeure `RSI < 35`.

Cet audit couvre les modules de domaine, le builder, scanner, marché live,
replay/backtest, modèles Pydantic, filtres, API, exports, contrats TypeScript et
Zod, composants UI, stores, tests, documentation et historique Git local. Il
n'implémente aucun candidat.

## 3. État Git initial et historique

- branche : `main` ;
- HEAD court : `cb231a1` ;
- commit : `cb231a1f39ea44f2c1f98cd456c3213d28c563ce` ;
- sujet : `Add validation results for RSI filter experiment v1 in JSON format` ;
- arbre initial : propre ;
- index : vide ;
- non suivis : aucun ;
- changements préexistants : aucun ;
- contrainte locale : Git requiert `-c safe.directory=...` en raison d'un
  propriétaire Windows différent ; aucune configuration Git n'a été changée.

L'historique contient `backend/indicators.py`, mais ce module n'a jamais porté
d'indicateur supplémentaire dans l'historique disponible : il réexporte les
mêmes primitives. Les anciens noms `scanner.py`, `exchange.py` et `config.py`
correspondent aux services/configurations actuels, pas à un catalogue caché.

## 4. Définitions des statuts d'intégration

| Statut | Définition exclusive |
|---|---|
| `fully_integrated` | Calcul, signal structuré, tests, live, backtest et au moins une consommation publique présents. |
| `partially_integrated` | Calcul présent, mais au moins un lien structuré, scanner, live, backtest, filtre, confluence, frontend ou test est incomplet. |
| `calculated_but_unused` | Calcul actif présent sans consommateur applicatif. |
| `legacy_only` | Présent uniquement dans un chemin historique ou de compatibilité. |
| `experimental` | Limité à une expérience déclarée, hors production. |
| `deprecated` | Explicitement remplacé et destiné au retrait. |
| `unknown` | Preuves insuffisantes pour une classification sûre. |

Aucun indicateur actuel n'est `calculated_but_unused`, `legacy_only`,
`experimental`, `deprecated` ou `unknown`. Les divergences RSI/MACD sont des
événements dérivés utilisés pour des marqueurs/audits, pas des indicateurs
structurés du catalogue.

## 5. Inventaire actuel

| ID | Famille | Module/fonctions | Inputs | Defaults | Disponibilité minimale | Statut |
|---|---|---|---|---|---|---|
| `rsi` | momentum | `rsi.py`; `calculate_rsi`, `detect_rsi_signal` | close | 14 ; zones 30/70 ; filtre production 35 | valeur à la 15e bougie | `fully_integrated` |
| `sma` | trend | `moving_averages.py`; `calculate_sma`, `detect_moving_average_signal` | close | 20/50 | valeur à `period`; événement à `period+1` | `partially_integrated` |
| `ema` | trend | `moving_averages.py`; `calculate_ema`, `detect_moving_average_signal` | close | 20/50 | valeur à `period`; événement à `period+1` | `partially_integrated` |
| `macd` | trend, secondaire momentum | `macd.py`; `calculate_macd`, `build_macd_signal` | close | 12/26/9 | ligne signal à 34 bougies ; croisement à 35 | `fully_integrated` |
| `bollinger` | volatility, secondaire support/résistance | `bollinger.py`; `calculate_bollinger_bands`, `build_bollinger_signal` | close | 20, écart-type population × 2 | état à 20 ; transition à 21 | `fully_integrated` |
| `stochastic` | momentum | `stochastic.py`; `calculate_stochastic`, `build_stochastic_signal` | high, low, close | 14/3 ; 20/80 | `%D` à 16 ; bundle disponible à 17 | `fully_integrated` |

Le scanner demande au moins `min_ohlcv_bars=200`. `primary_ohlcv_limit` ajoute
une marge de 10 et prend le maximum des besoins actifs. Cette marge
opérationnelle est distincte du lookback mathématique.

### 5.1 Signaux, états, force et valeur brute

| ID | `signal` | `state` | `strength` | `raw_value` |
|---|---|---|---|---|
| RSI | état courant ou `exit_oversold`/`exit_overbought` | cinq zones | 0 / 0,5 / 0,75 / 1 | RSI courant |
| SMA/EMA | cross, alignment, `price_above`, `price_below`, `neutral` | toujours `null` | 0 / 0,25 / 0,5 / 0,75 | moyenne rapide |
| MACD | cross, `above_signal`, `below_signal`, `neutral` | position ligne + position zéro | 0 à 1, règle relative | ligne MACD |
| Bollinger | breakout/reentry ou position courante | cinq positions | 0 / 0,5 / 0,6 / 0,75 / 1 | close courant |
| Stochastique | cross prioritaire, sinon zone/neutral | `oversold`, `neutral`, `overbought` | 0 / 0,5 / 0,6 / 1 | `%K` |

Les `reason` actuelles sont des phrases françaises déterministes, parfois avec
une valeur formatée. Elles conviennent à l'affichage actuel, mais ne constituent
pas encore des codes stables indépendants de la locale.

### 5.2 Extrait réel d'un indicateur intégré

```python
def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.astype(float).diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(100).where(avg_gain.notna())
```

RSI est calculé dans le domaine, assemblé par `build_indicator_signals`, utilisé
par scanner/live/replay, exposé par Pydantic et Zod, affiché par le frontend,
testé mathématiquement, causalement et de bout en bout.

## 6. Matrice de traçabilité

Légende : `✓` complet, `△` partiel/spécifique, `—` absent ou hors rôle.

| Indicateur | Calcul | Signal structuré | Bundle | Scanner | Live | Backtest | Filtre | Confluence | API | Frontend | Tests |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| RSI | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | seuil legacy, pas v1 | ✓ | ✓ | ✓ | ✓ |
| SMA | ✓ | ✓ | ✓ | △ agrégat trend | ✓ | △ agrégat trend | trend legacy | △ via trend | △ live seulement | ✓ live | ✓ |
| EMA | ✓ | ✓ | ✓ | △ agrégat trend | ✓ | △ agrégat trend | trend legacy | △ via trend | △ live seulement | ✓ live | ✓ |
| MACD | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ legacy/v1 | ✓ | ✓ | ✓ | ✓ |
| Bollinger | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ legacy/v1 | ✓ | ✓ | ✓ | ✓ |
| Stochastique | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ legacy/v1 | ✓ | ✓ | ✓ | ✓ |

### Ruptures de chaîne

1. SMA/EMA structurés sont omis du scanner et de
   `evaluate_information_set`; les deux chemins utilisent `trend_states` et
   `trend_score` multi-timeframe.
2. Le marché calcule SMA/EMA structurés mais les retire avant la confluence,
   qui conserve le facteur historique `trend`.
3. Les filtres structurés v1 n'acceptent que MACD, Bollinger et Stochastique ;
   RSI reste filtré par son seuil historique, la tendance par son score.
4. Le CSV scanner n'exporte pas `indicator_signals`.
5. Le marché n'a pas de modèle Pydantic `MarketSnapshot`; son contrat est
   protégé par code, Zod et tests.
6. Les clés backend Pydantic sont ouvertes (`dict[str, ...]`) alors que Zod et
   TypeScript ferment la liste aux six IDs.
7. Un indicateur désactivé est normalement omis du bundle public ; un signal
   `disabled` n'est synthétisé que dans une copie locale pour les filtres.
8. Les divergences visuelles sont placées au pivot mais ne deviennent connues
   qu'après confirmation ; elles ne participent pas aux six signaux.

## 7. Contrat structuré actuel

Extrait réel :

```python
class IndicatorSignalModel(BaseModel):
    status: Availability
    direction: SignalDirection
    signal: str | None = None
    state: str | None = None
    strength: float = Field(ge=0.0, le=1.0)
    reason: str | None = None
    raw_value: float | None = None
```

| Champ | Type backend | Nullabilité | Règle |
|---|---|---:|---|
| `status` | quatre littéraux | non | disponible, insuffisant, invalide, désactivé |
| `direction` | trois littéraux | non | neutre obligatoire si indisponible |
| `signal` | chaîne ouverte | oui | événement principal ou état copié selon l'indicateur |
| `state` | chaîne ouverte | oui | état persistant, parfois composé avec `/` |
| `strength` | float `[0,1]` | non | intensité technique, jamais probabilité |
| `reason` | chaîne | oui | diagnostic lisible |
| `raw_value` | float | oui | une seule valeur scalaire choisie par indicateur |

Pydantic sérialise les modèles en JSON. Zod exige un objet strict, des nombres
finis, une force bornée, et seulement les six clés connues. Les champs
`indicator_signals` restent optionnels côté TypeScript pour les anciens
payloads. L'UI masque direction/signal/state/strength quand le statut n'est pas
`available`.

### Comportements d'erreur

- historique trop court : `insufficient_data`, direction neutre, force 0,
  valeurs métier nulles ;
- valeur non finie ou bande/plage dégénérée : `invalid_data` ;
- désactivation : clé publique généralement omise ; vue filtrable locale
  `disabled` ;
- un calcul disponible et neutre reste `available`, pas `insufficient_data` ;
- aucun `NaN` ou infini ne doit franchir le contrat public.

## 8. Familles et couverture fonctionnelle

| Famille | Couverture actuelle |
|---|---|
| trend | couverte par SMA/EMA/MACD, force absente |
| momentum | couverte par RSI/Stochastique et partiellement MACD |
| volatility | partielle via position Bollinger ; niveau normalisé absent |
| volume | non couverte |
| market_structure | non couverte |
| support_resistance | partielle via bandes dynamiques |
| statistical | partielle via moyenne/écart-type Bollinger |
| composite | confluence présente, régime absent |

| Besoin | État | Preuve |
|---|---|---|
| direction de tendance | couvert | MA, MACD, trend multi-TF |
| force de tendance | non couvert | aucun ADX ou équivalent |
| momentum | couvert | RSI, Stochastique, MACD |
| surachat/survente | couvert | RSI, Stochastique, Bollinger position |
| volatilité absolue | partiellement couvert | bandes, sans ATR explicite |
| volatilité relative | partiellement couvert | position normalisée, largeur non exposée |
| compression / expansion | non couvert | largeur Bollinger non exposée |
| volume cumulatif | non couvert | aucun OBV/ADL |
| flux acheteur/vendeur | non couvert | aucun proxy OHLCV |
| volume relatif | non couvert | volume brut seulement |
| prix pondéré volume | non couvert | aucun VWAP |
| cassure | partiellement couvert | breakout Bollinger, pas niveau précédent |
| sommets/creux | non couvert | divergences hors décision, pivots confirmés seulement |
| support/résistance | partiellement couvert | bandes dynamiques |
| distance à une moyenne | non couvert comme feature | comparaison qualitative MA seulement |
| distance à un niveau | non couvert | pas de feature normalisée |
| régime de marché | non couvert | confluence n'est pas un régime |

## 9. Redondances actuelles

- SMA/EMA : redondance élevée de niveau et de tendance ; l'EMA réagit plus vite
  et reste utile pour MACD. Les deux ne sont pas des doublons exacts.
- RSI/Stochastique : redondance modérée à forte sur les extrêmes ; RSI mesure
  gains/pertes lissés, Stochastique situe le close dans sa plage high/low.
- EMA/MACD : redondance élevée, MACD étant dérivé de deux EMA ; sa ligne signal
  et son histogramme ajoutent une dynamique d'écart.
- Bollinger/SMA : redondance modérée car la bande médiane est une SMA ; les
  bandes ajoutent l'écart-type et la position relative.
- Bollinger/RSI/Stochastique : redondance modérée dans une confluence orientée
  repli ; les formules restent distinctes.

La baseline disponible ne justifie pas une corrélation massive : les comptes
de trades sont faibles et SMA/EMA structurés sont absents des observations.
Les ablations sont descriptives et ne prouvent pas l'indépendance causale.

## 10. Critères de sélection et échelle

Chaque note est favorable : `0` mauvais/incompatible, `1` faible, `2` bon,
`3` excellent. Colonnes : complémentarité (`C`), interprétabilité (`I`),
causalité (`Ca`), live (`L`), backtest (`B`), disponibilité OHLCV (`D`),
stabilité multi-TF (`M`), coût (`Cpu`), faible redondance (`R`), testabilité
(`T`), normalisation (`N`), valeur IA (`AI`), résistance au surapprentissage
(`O`).

| Candidat | C | I | Ca | L | B | D | M | Cpu | R | T | N | AI | O | Décision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ATR/NATR | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | P0 |
| ADX/DMI | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 2 | 3 | 3 | 3 | 3 | 3 | P0 |
| Supertrend | 2 | 3 | 3 | 3 | 3 | 3 | 2 | 2 | 2 | 3 | 3 | 2 | 2 | P0 |
| BB Width | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 2 | 3 | 3 | 3 | 3 | P0 |
| Donchian | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | P0 |
| Volume relatif | 3 | 3 | 3 | 3 | 3 | 3 | 2 | 3 | 3 | 3 | 3 | 3 | 3 | P0 |
| CMF | 3 | 3 | 3 | 3 | 3 | 3 | 2 | 3 | 3 | 3 | 3 | 3 | 2 | P0 |
| OBV dérivé | 3 | 2 | 3 | 3 | 3 | 3 | 2 | 3 | 2 | 3 | 3 | 3 | 2 | P1 |
| VWAP roulant | 3 | 3 | 3 | 3 | 3 | 3 | 2 | 3 | 3 | 3 | 3 | 3 | 2 | P1 |
| CCI | 2 | 3 | 3 | 3 | 3 | 3 | 2 | 3 | 2 | 3 | 2 | 2 | 2 | P1 |
| ROC | 2 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 2 | 3 | 3 | 3 | 2 | P1 |
| Aroon | 2 | 3 | 3 | 3 | 3 | 3 | 2 | 3 | 2 | 3 | 3 | 2 | 2 | P2 |
| Keltner | 1 | 3 | 3 | 3 | 3 | 3 | 2 | 2 | 1 | 3 | 3 | 2 | 1 | P2 |
| Choppiness | 2 | 2 | 3 | 3 | 3 | 3 | 2 | 2 | 2 | 3 | 3 | 2 | 2 | P2 |
| Volatilité historique | 2 | 3 | 3 | 3 | 3 | 3 | 2 | 3 | 2 | 3 | 3 | 3 | 2 | P2 |
| MFI | 2 | 3 | 3 | 3 | 3 | 3 | 2 | 3 | 1 | 3 | 3 | 2 | 1 | P2 |
| ADL | 2 | 2 | 3 | 3 | 3 | 3 | 2 | 3 | 1 | 3 | 2 | 2 | 2 | P2 |
| Ichimoku | 1 | 2 | 2 | 2 | 2 | 3 | 2 | 2 | 1 | 1 | 2 | 2 | 1 | reporté |
| PSAR | 1 | 3 | 3 | 3 | 3 | 3 | 1 | 2 | 1 | 2 | 3 | 1 | 1 | reporté |
| KAMA | 1 | 2 | 3 | 3 | 3 | 3 | 2 | 2 | 1 | 2 | 3 | 2 | 2 | reporté |
| TSI | 1 | 2 | 3 | 3 | 3 | 3 | 2 | 2 | 1 | 2 | 3 | 2 | 1 | reporté |
| Ultimate Oscillator | 1 | 2 | 3 | 3 | 3 | 3 | 2 | 2 | 1 | 2 | 3 | 1 | 1 | reporté |
| Ease of Movement | 2 | 1 | 3 | 3 | 3 | 3 | 1 | 2 | 2 | 2 | 2 | 1 | 1 | reporté |
| Williams %R | 0 | 3 | 3 | 3 | 3 | 3 | 2 | 3 | 0 | 3 | 3 | 1 | 1 | rejeté |
| Momentum | 0 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 0 | 3 | 3 | 1 | 1 | rejeté |
| HMA | 1 | 2 | 3 | 3 | 3 | 3 | 2 | 2 | 0 | 2 | 3 | 1 | 1 | rejeté |

## 11. Candidats tendance

| Indicateur | Mesure et paramètres | Complément / redondance | Signal structuré possible | Recommandation |
|---|---|---|---|---|
| ADX/+DI/-DI | TR et directional movement, Wilder 14 | apporte la force absente ; direction distincte des MA | cross DI, strengthening/weakening ; states weak/developing/strong | P0 |
| Aroon | ancienneté du plus haut/bas, 25 | utile pour émergence/range, complément modéré d'ADX | bullish/bearish cross, trend emergence, range | P2 après ADX |
| Supertrend | médiane HL + ATR(10) × 3 | état persistant ; redondance modérée MA/ATR | bullish_flip, bearish_flip ; above/below band | P0 avec ATR |
| Ichimoku | 9/26/52, projection 26 | riche mais redondant et complexe | cloud breakout, TK cross, cloud state | reporté |
| Parabolic SAR | AF 0,02 à 0,2 | whipsaw en range, proche de Supertrend | bullish_flip/bearish_flip | reporté |
| HMA | WMA combinées, période typique 20 | nouvelle moyenne sans lacune fonctionnelle | slope/cross | rejeté |
| KAMA | efficiency ratio 10, fast 2, slow 30 | adaptatif mais proche des MA | slope/cross/efficiency state | reporté |

ADX ne porte pas de direction prix : +DI/-DI la portent. Une proposition
cohérente avec le contrat actuel est :

```text
direction = bullish si +DI > -DI, bearish si -DI > +DI, neutral à égalité
state = weak_trend | developing_trend | strong_trend
signal = bullish_cross | bearish_cross | trend_strengthening |
         trend_weakening | none
```

Les seuils d'état doivent être configurés et testés, pas déduits du vocabulaire.
`trend_strengthening` est un événement sur ADX ; il ne doit pas devenir
`bullish` sans DMI.

Ichimoku reste causal seulement si les composants sont alignés au temps de
décision. Senkou A/B peuvent être calculés avec les données connues à `t` puis
projetés pour l'affichage ; une décision à `t` ne peut pas lire une projection
qui incorpore des données postérieures à son origine. Chikou doit rester une
vue historique, jamais une comparaison utilisant le futur. Warmup recommandé :
78 bougies pour les 52 périodes plus déplacement 26.

## 12. Candidats momentum

| Indicateur | Normalisation / signaux | Relation aux indicateurs actuels | Décision |
|---|---|---|---|
| CCI(20) | non borné ; z-like robuste/clippé ; cross zéro et ±100 | distance au prix typique moyen, différente du RSI | P1 |
| ROC(12) | pourcentage ; signe, cross zéro, variation/accélération | feature simple ; préférée à Momentum | P1 |
| Williams %R(14) | `[-100,0]`, zones et cross | transformation affine quasi exacte du `%K` stochastique | rejeté |
| Momentum(12) | différence ou ratio | même variation que ROC sans avantage | rejeté |
| Ultimate Oscillator(7/14/28) | `[0,100]` | multi-horizon mais redondant RSI/Stoch | P2 |
| MFI(14) | `[0,100]`, prix typique × volume | pont momentum-volume, mais redondant RSI/CMF | P2 |
| TSI(25/13) | borné approximativement `[-100,100]` | double lissage du momentum, proche MACD/ROC | P2 |

CCI est complémentaire car il exprime une distance normalisée au prix typique,
mais ses seuils usuels ne doivent pas être adoptés comme filtres. ROC est
retenu comme feature ; une accélération éventuelle doit rester un composant
dérivé explicitement versionné.

## 13. Candidats volatilité

| Indicateur | Rôle | Point causal | Décision |
|---|---|---|---|
| ATR | amplitude absolue et gap via true range | close précédent et OHLC de `t` | P0 |
| NATR | `ATR/close` ou pourcentage | disponible à la clôture de `t` | P0 |
| BB Width | `(upper-lower)/middle` | réutilise Bollinger actuel | P0, composant Bollinger |
| Donchian | bornes roulantes et largeur | breakout compare `close[t]` au canal fini à `t-1` | P0 |
| Keltner | EMA ± ATR × multiplicateur | causal mais dérivé ATR/EMA | P2 |
| volatilité historique | écart-type des log-rendements | causal, annualisation dépend TF | P2 |
| Choppiness | somme TR / plage high-low | causal, régime range/trend | P2 |

ATR montant signifie expansion de volatilité, pas hausse du prix. Son
`direction` doit donc rester `neutral` sauf si ce champ est interprété comme
biais prix ; l'évolution appartient à `signal`/`state`.

BB Width doit enrichir le composant multi-valeurs Bollinger plutôt que refaire
les bandes. Des états compression/normal/expansion exigent un contexte roulant
(percentile ou z-score entraîné causalement), pas un seuil universel improvisé.

Keltner rend possible un futur squeeze Bollinger/Keltner, mais aucune
« squeeze strategy » n'est sélectionnée ici.

## 14. Candidats volume

Le volume Binance est celui du marché/symbole négocié sur Binance, pas celui du
marché crypto global. Les comparaisons inter-symboles exigent donc une
normalisation locale.

| Indicateur | Usage | Normalisation | Décision |
|---|---|---|---|
| OBV | pression cumulative selon signe du close | delta, pente/ATR ou distance à EMA OBV ; jamais niveau brut inter-actifs | P1 |
| CMF(20) | money-flow multiplier × volume | naturellement environ `[-1,1]` | P0 |
| MFI(14) | momentum prix-volume | `[0,100]` | P2 |
| volume relatif(20) | volume / moyenne ou médiane roulante | ratio, log-ratio, clip | P0 |
| VWAP roulant(20) | prix typique pondéré volume | distance `(close-vwap)/vwap` | P1 |
| ADL | cumul du money-flow volume | pente/delta, proche CMF | P2 |
| Ease of Movement | déplacement médian rapporté au volume | rolling z-score | P2 |

Le VWAP journalier/session suppose une frontière de session qui est ambiguë en
crypto 24/7. La première version doit donc être explicitement `rolling_vwap`,
pas « VWAP » générique. Volume nul rend la fenêtre invalide, pas neutre.

## 15. Structure de marché, supports et régime

La première structure causale recommandée repose sur les primitives Donchian :
rolling high/low, position dans le canal, largeur et breakout contre les bornes
calculées jusqu'à `t-1`. Des séquences de higher-high/higher-low peuvent être
ajoutées plus tard avec une définition strictement roulante.

Les pivots centrés et fractales nécessitant des bougies à droite sont rejetés
pour une décision immédiate. Un pivot confirmé peut être utilisé au temps de
confirmation et stocker séparément `pivot_time` et `confirmation_time`; il ne
doit jamais être rejoué comme connu au pivot.

Un régime futur peut combiner des features observées (force ADX, NATR, BB
Width, Choppiness) dans un composant `market_regime`. Il ne doit pas être
introduit avant validation séparée des primitives ni participer d'emblée aux
filtres/confluence.

## 16. Causalité et repaint

Tous les candidats retenus utilisent uniquement OHLCV jusqu'à la clôture de
`t`. Le signal est disponible après cette clôture et une stratégie peut
exécuter à l'ouverture de `t+1`. Le live provisoire peut afficher une valeur
intrabar révisable, mais elle doit porter `is_forming`; le backtest confirmé
n'enregistre que la valeur close.

| Risque | Règle |
|---|---|
| bougie courante dans un breakout | canal de référence arrêté à `t-1` |
| états roulants normalisés | fenêtre finissant à `t`, jamais centrée |
| pivots/fractales | décision seulement au temps de confirmation |
| Ichimoku déplacé | séparer calcul causal et coordonnées d'affichage |
| divergences | conserver pivot et confirmation, décider à confirmation |
| provisional live | ne jamais l'assimiler à confirmed historique |

## 17. Warmup recommandé

| Composant | Minimum | Warmup opérationnel recommandé | Avant disponibilité |
|---|---:|---:|---|
| ATR/NATR(14) | 15 | 114 | `insufficient_data` |
| ADX/DMI(14) | 29 | 128 | bundle entier insuffisant |
| Supertrend(10) | 11-12 | 110 | dépend d'ATR disponible |
| BB Width(20) | 20 | 120 si état percentile | valeur possible, état percentile insuffisant |
| Donchian(20) breakout causal | 21 | 21 | `insufficient_data` |
| volume relatif(20) | 21 si baseline exclut `t` | 21 | `insufficient_data` |
| CMF(20) | 20 | 20 | invalide si plage/volume dégénéré |
| OBV features(20) | 21 | 21 | ne pas exposer seulement le cumul brut |
| VWAP roulant(20) | 20 | 20 | invalide si somme volume nulle |
| CCI(20) | 20 | 20 | invalide si déviation moyenne nulle |
| ROC(12) | 13 | 13 | `insufficient_data` |

Le warmup opérationnel ATR/ADX supérieur au strict minimum vise la stabilité du
lissage Wilder ; il doit être mesuré et versionné. Un composant multi-valeurs
est `available` seulement lorsque tous les composants requis pour son contrat
le sont.

## 18. Normalisation

- prix/distance : `(x-close)/close`, pourcentage ou division par ATR ;
- volatilité : `ATR/close`, BB Width, volatilité des log-rendements ;
- oscillateurs bornés : transformation vers `[0,1]` ou `[-1,1]` en conservant
  la valeur native ;
- séries cumulatives : variation, pente normalisée ou distance à une moyenne ;
- volume : ratio à moyenne/médiane locale, éventuellement `log1p` et clip ;
- valeurs non bornées : z-score rolling causal ou quantiles appris sur train.

Chaque observation future doit conserver `raw_values` et `normalized_values`.
Les paramètres de normalisation font partie de la configuration et du
fingerprint. Une normalisation statistique destinée à l'IA est ajustée sur
train uniquement.

## 19. Composants multi-valeurs et futur contrat

ADX/DMI doit exposer au minimum `adx`, `plus_di`, `minus_di`; ATR
`raw_atr`, `normalized_atr`; Donchian `upper`, `middle`, `lower`, `width`,
`position`; CMF une valeur mais aussi son éventuelle pente ; Supertrend
`line`, `upper_band`, `lower_band`, `trend`.

Le contrat actuel à `raw_value` scalaire ne peut pas porter cela sans ambiguïté.
La proposition est de conserver un scalaire principal pour compatibilité et
d'ajouter dans une future version :

```json
{
  "raw_value": 27.4,
  "components": {
    "adx": {"value": 27.4, "unit": "index"},
    "plus_di": {"value": 31.2, "unit": "index"},
    "minus_di": {"value": 18.7, "unit": "index"}
  }
}
```

La forme détaillée est spécifiée dans
`docs/architecture/indicator-extension-contract-v1.md`. Aucun contrat public
actuel n'est modifié par cet audit.

## 20. Direction, signal, state, strength, reason et status

- `direction` : biais de prix courant, jamais direction de la volatilité.
- `signal` : événement ponctuel ; `none` ou `null` quand rien ne change.
- `state` : régime persistant ; il peut rester identique plusieurs bougies.
- `strength` : intensité technique documentée par indicateur, jamais
  probabilité, performance ni score de confluence.
- `reason` : à terme un code stable (`adx.di_bullish_cross`) plus paramètres
  bruts séparés ; le frontend traduit le code. Les longues phrases localisées
  ne doivent pas devenir une clé d'API.
- `status` : conserver les quatre valeurs actuelles. Aucun nouveau statut n'est
  nécessaire ; une dépendance insuffisante propage `insufficient_data`, une
  division dégénérée `invalid_data`, une désactivation `disabled`.

Un état persistant ne doit pas générer un événement à chaque bougie. Les tests
doivent vérifier explicitement cette distinction.

## 21. Données requises et hors périmètre

Tous les candidats recommandés utilisent uniquement timestamp/OHLCV. Sont
reportés hors première génération : carnet d'ordres, open interest, funding,
liquidations, données on-chain, sentiment, trades individuels et vrai volume
delta. Aucun de ces flux ne doit être simulé depuis les bougies.

## 22. Dépendances et primitives mutualisables

```text
true range + Wilder smoothing
├── ATR ──> normalized ATR
├── ADX/DMI
├── Supertrend
└── Keltner (reporté)

rolling min/max
├── Stochastique existant
├── Donchian
└── structure high/low causale

prix typique + volume
├── CMF
├── MFI (reporté)
├── ADL (reporté)
└── VWAP roulant

Bollinger existant
└── Band Width
```

Les primitives ne doivent pas exposer de décisions métier. Un cache de calcul
par snapshot/configuration peut éviter les recalculs, mais ne doit pas devenir
un état global mutable.

## 23. Architecture de calcul recommandée

Conserver une fonction pure par indicateur, extraire quelques primitives
mathématiques pures et ajouter progressivement un registre déclaratif léger :
ID, version, dépendances, besoins OHLCV, lookback, calculateur et builder de
signal. Un planificateur topologique peut ensuite calculer le graphe une seule
fois par snapshot.

Cette approche est préférable à :

- un module géant, difficile à tester ;
- une registry magique fondée sur l'import dynamique ;
- des copies de formules dans scanner/live/backtest ;
- un DAG complet introduit avant d'avoir plusieurs dépendances réelles.

Le même résultat de calcul doit alimenter scanner, marché, replay, audits et
future extraction IA. Seule la source des bougies varie.

Les calculs pandas/NumPy `float64` conviennent aux indicateurs. `Decimal` reste
approprié pour comptabilité, cash, frais et persistance économique, pas pour
remplacer toutes les fenêtres vectorisées. Les seuils comparent des floats
finis validés ; la sérialisation rejette NaN/infini ; le fingerprint utilise la
configuration JSON canonique, pas les séries flottantes.

## 24. Classement

### P0 — fondamentaux manquants

ATR, NATR, ADX/DMI, Supertrend, BB Width, Donchian, volume relatif, CMF.

### P1 — extension utile

Features OBV, distance au VWAP roulant, CCI, ROC.

### P2 — spécialisés

Aroon, Keltner, Choppiness, volatilité historique, MFI, ADL, Ichimoku, PSAR,
KAMA, TSI, Ultimate Oscillator, Ease of Movement.

### Reportés faute de données

Order-book imbalance, open interest, funding, liquidations, volume delta réel,
on-chain et sentiment.

### Rejetés

- Williams %R : quasi-duplicata affine du `%K` stochastique ;
- Momentum : quasi-duplicata de ROC ;
- HMA : nouvelle variante de moyenne sans lacune prioritaire couverte ;
- pivots centrés/fractales utilisés au pivot : non causaux et repaint.

Le catalogue recommandé contient 12 composants cohérents, pas une vingtaine
d'ajouts simultanés.

## 25. Usage futur par une IA

Observation conceptuelle :

```text
metadata: timestamp, symbol, timeframe, source/version
features: raw values, normalized values, states, events, market regime
labels: rendements/risque futurs calculés après le temps de décision
```

Règles anti-fuite :

1. toutes les features sont calculées au temps de décision ;
2. les labels sont calculés après et stockés séparément ;
3. aucun label/outcome/trade futur n'entre dans les features ;
4. découpage chronologique sans permutation ;
5. normalisation ajustée uniquement sur train ;
6. aucun calcul centré ou pivot futur ;
7. test final gelé ;
8. aucune sélection de features sur le test final.

L'IA pourra estimer utilité, redondance, pondération par régime et qualité, mais
ne justifiera pas rétroactivement un catalogue incontrôlé. `strength` reste une
feature technique potentielle et non une cible.

## 26. Risques et limites

- baseline économique faible : 22 trades full, cinq plages, forte domination
  USDC/BTC ;
- pas de corrélation pair-à-pair fiable pour les candidats non implémentés ;
- volume limité à Binance et au symbole ;
- warmups Wilder à mesurer empiriquement avant de figer ;
- états de compression/régime nécessitent un contexte causal versionné ;
- le contrat actuel scalaire ne représente pas proprement ADX/DMI ;
- scanner et replay ont encore des assemblages distincts protégés par oracle ;
- la liste TypeScript/Zod fermée nécessitera une évolution coordonnée, mais pas
  pendant cette phase.

## 27. Ordre d'implémentation

1. Phase 8.2 : ATR/NATR + ADX/DMI + Supertrend.
2. Phase 8.3 : BB Width + Donchian et primitives de structure causale.
3. Phase 8.4 : volume relatif + CMF + OBV dérivé + distance VWAP roulant.
4. Phase 8.5 : CCI + ROC.
5. Phase 8.6 : évaluer un régime composite à partir des seules primitives
   validées ; aucune nouvelle stratégie automatique.

Chaque phase doit ajouter calculs purs, statut/signal, tests de formule et
causalité, intégration unique live/backtest, documentation et contrat frontend,
mais laisser filtres/confluence de production inchangés jusqu'à une expérience
séparée préenregistrée.

## 28. Recommandation Phase 8.2

```text
Implémenter uniquement la famille cohérente ATR/NATR + ADX/DMI + Supertrend.
Mutualiser true range et lissage Wilder.
Exposer des composants multi-valeurs versionnés.
Garantir close[t] -> décision[t] -> exécution possible open[t+1].
Intégrer scanner, confirmed live et replay via les mêmes fonctions.
Ne modifier ni filtre, ni confluence, ni stratégie de production.
```

Critères de sortie : formules caractérisées sur séries connues, égalités et
données dégénérées couvertes, warmup déterministe, aucun repaint, parité
scanner/live/backtest, NaN/infini bloqués, coût mesuré, contrats et UI
compatibles, suite complète verte.

## 29. Fichiers inspectés

Documentation principale et liée : `CURRENT_APP_STATE_FOR_AI.md`,
`SIGNALS_CURRENT_STATE.md`, `BACKTESTING.md`, baseline et résumé JSON,
méthodologie, plan/résultats RSI, filtres structurés/stabilité, UI des signaux,
scanner, marché, confluence, contrats et exports.

Code principal : `app/domain/indicators/*`, `indicator_bundle.py`,
`signal_filters.py`, `backtesting.py`, `signal_evaluation.py`, `limits.py`,
`core/settings.py`, modèles scanner/backtest, services scanner/market/backtest,
API, exporter CSV, types/schémas/stores/composants frontend et tests associés.

## 30. Livrables

- `docs/audits/indicator-catalog-v1.json` ;
- `docs/audits/indicator-catalog-v1.md` ;
- `docs/audits/indicator-complementarity-matrix-v1.md` ;
- `docs/architecture/indicator-extension-contract-v1.md` ;
- `docs/roadmaps/indicator-expansion-v1.md` ;
- mise à jour de `docs/CURRENT_APP_STATE_FOR_AI.md`.

Exemple machine lisible réel :

```json
{
  "id": "adx_dmi",
  "name": "ADX and Directional Movement Index",
  "family": "trend",
  "priority": "P0",
  "data_requirements": ["high", "low", "close"],
  "causal": true,
  "recommended_phase": "8.2",
  "status": "recommended"
}
```

## 31. Validation réalisée

### Catalogue documentaire

- JSON parsé avec succès ;
- 6 indicateurs actuels ;
- 28 candidats évalués ;
- 12 composants recommandés ;
- 0 ID dupliqué ;
- 0 famille invalide ;
- causalité renseignée pour tous les candidats ;
- Phase 8.2 unique : `atr`, `normalized_atr`, `adx_dmi`, `supertrend`.

Aucun script d'inventaire n'a été créé : l'inspection manuelle croisée des
modules, appels, modèles, contrats frontend, tests et historique local est plus
fiable qu'une détection par nom/import pour distinguer SMA/EMA structurés de
leur agrégat de tendance.

### Backend

Depuis `backend/`, avec `venv/Scripts/python.exe` :

| Commande | Résultat |
|---|---|
| `python -m pytest -q` | 697 réussis, 1 ignoré, 27 subtests, 2 warnings, 27,40 s |
| `python -m compileall -q app scripts` | succès |
| `python -m black --check app tests scripts` | 134 fichiers inchangés |
| `python -m flake8 app tests scripts` | succès, aucune sortie |
| `python -m mypy app scripts` | succès, 86 fichiers |

Les deux warnings préexistants viennent de
`app/services/market_data.py:96` : pandas signale l'abandon de nanosecondes lors
de `to_pydatetime()`.

### Frontend

Depuis `frontend/` :

| Commande | Résultat |
|---|---|
| `pnpm install --frozen-lockfile` | lockfile à jour, 335 paquets réutilisés, 0 téléchargement |
| `pnpm run typecheck` | succès |
| `pnpm run lint` | succès, 0 warning |
| `pnpm run test` | 48 fichiers, 299 tests réussis, 30,52 s |
| `pnpm run build` | succès, 2 065 modules transformés |

La première tentative d'installation a dépassé la limite d'exécution pendant
la recréation de `node_modules`; la seconde a révélé l'accès réseau restreint.
La reprise autorisée a restauré l'installation depuis le store local sans
téléchargement. Aucun fichier suivi frontend ni lockfile n'a changé.

### Périmètre Git final

Fichiers créés :

```text
docs/audits/indicator-catalog-v1.json
docs/audits/indicator-catalog-v1.md
docs/audits/indicator-complementarity-matrix-v1.md
docs/architecture/indicator-extension-contract-v1.md
docs/roadmaps/indicator-expansion-v1.md
```

Fichier modifié :

```text
docs/CURRENT_APP_STATE_FOR_AI.md
```

Aucun fichier sous `frontend/src/`, backend de production, filtre, confluence,
route, modèle public, migration, export, lockfile, manifeste de dépendances,
base ou CSV suivi n'est modifié. Aucun commit ni `git add` n'a été créé. Le HEAD
reste `cb231a1`.

## Mise à jour Phase 8.2

La recommandation est désormais implémentée : ATR/NATR, ADX/DMI et Supertrend
sont `fully_integrated` comme observations optionnelles dans le scanner, le
marché, le replay, les contrats publics et l'interface. Ils restent hors filtres
et confluence. L'inventaire principal conserve la photographie auditée de la
Phase 8.1 ; le delta exécutable est décrit dans
`docs/backend/indicators-atr-adx-supertrend-v1.md`.

## Mise à jour Phase 8.3

Bollinger Band Width, Donchian Channels et Keltner Channels sont désormais
`fully_integrated` comme observations dans scanner, marché, replay, API,
TypeScript/Zod et interface. La largeur Bollinger réutilise strictement les
bandes existantes. Donchian distingue canal courant et bornes causales
précédentes ; Keltner réutilise EMA et ATR. Donchian et Keltner sont désactivés
par défaut. Les trois restent hors filtres, confluence et décisions. Le
catalogue JSON marque ces candidats `implemented`.
