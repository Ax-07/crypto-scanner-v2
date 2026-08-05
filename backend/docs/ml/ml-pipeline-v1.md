# Pipeline de machine learning v1

## 1. Statut du document

| Élément                    | Valeur                            |
| -------------------------- | --------------------------------- |
| Version du pipeline        | ML v1                             |
| Statut de l’infrastructure | Validée                           |
| Modèle évalué              | Régression logistique multiclasse |
| Statut du modèle           | Rejeté                            |
| Utilisation en production  | Interdite                         |
| Test terminal consommé     | Oui                               |
| Horizon de prédiction      | 6 bougies                         |
| Timeframe de l’expérience  | `1h`                              |
| Marché de l’expérience     | `BTC/USDC` Binance Spot           |
| Date du benchmark          | 3 août 2026                       |
| Schéma du benchmark        | `ml-benchmark-v1`                 |

Ce document décrit l’infrastructure de machine learning v1, le contrat du dataset causal, la procédure d’évaluation temporelle et les résultats du premier benchmark.

L’infrastructure est considérée comme fonctionnelle et reproductible. Le premier modèle évalué ne généralise toutefois pas suffisamment pour être utilisé dans l’application.

Les résultats, métriques, nombres de caractéristiques, hashes et périodes présentés comme appartenant au benchmark v1 décrivent des artefacts historiques immuables.

Les enrichissements d’indicateurs réalisés après le gel du benchmark sont présentés séparément comme des travaux préparatoires à une future expérimentation v2. Ils ne modifient pas rétroactivement les artefacts v1.

---

## 2. Objectifs

Le pipeline ML v1 a pour objectifs de :

* construire un dataset supervisé à partir des observations persistées par les backtests ;
* garantir qu’aucune information future n’entre dans les caractéristiques ;
* classer le mouvement futur du marché en `DOWN`, `NEUTRAL` ou `UP` ;
* séparer chronologiquement les données d’entraînement, de validation et de test ;
* purger les observations dont la cible chevauche une partition future ;
* sélectionner les hyperparamètres uniquement sur la partie développement ;
* évaluer une seule fois la configuration retenue sur un test terminal ;
* conserver un benchmark immuable et vérifiable par SHA-256.

Le pipeline ne fournit actuellement pas :

* de prédiction en direct ;
* d’endpoint API d’inférence ;
* de modèle sérialisé destiné à la production ;
* de stratégie d’exécution ou de prise de position ;
* de mécanisme de réentraînement automatique ;
* de validation suffisante pour autoriser un usage financier réel.

---

## 3. Organisation du code

Le code ML est isolé dans le package suivant :

```text
backend/app/ml/
├── __init__.py
├── cli/
│   ├── __init__.py
│   ├── export_ml_benchmark.py
│   └── export_ml_dataset.py
├── domain/
│   ├── __init__.py
│   ├── ml_dataset.py
│   ├── ml_evaluation.py
│   ├── ml_feature_policy.py
│   ├── ml_preprocessing.py
│   ├── ml_temporal_split.py
│   └── ml_walk_forward.py
├── models/
│   ├── __init__.py
│   ├── ml_benchmark.py
│   ├── ml_dataset.py
│   └── ml_dataset_export.py
└── services/
    ├── __init__.py
    ├── ml_baseline_trainer.py
    ├── ml_benchmark_builder.py
    ├── ml_benchmark_exporter.py
    ├── ml_dataset_builder.py
    ├── ml_dataset_exporter.py
    ├── ml_dataset_loader.py
    ├── ml_final_evaluator.py
    └── ml_walk_forward_evaluator.py
```

Les tests suivent la même organisation :

```text
backend/tests/ml/
├── __init__.py
├── cli/
├── domain/
├── integration/
├── models/
└── services/
```

Le test d’intégration du repository est placé dans :

```text
tests/ml/integration/test_backtest_repository_ml.py
```

Le repository lui-même reste dans le domaine backtest :

```text
app/repositories/backtest_repository.py
```

La méthode `BacktestRepository.ml_source_rows(...)` constitue la frontière entre la persistance des backtests et le pipeline ML.

---

## 4. Dépendances

Les dépendances spécifiques utilisées par le pipeline sont :

```text
scikit-learn == 1.9.0
joblib == 1.5.3
```

Ces versions ont été vérifiées dans l’environnement backend avant le démarrage des travaux v2.

Le pipeline utilise également les dépendances déjà présentes dans le backend, notamment :

* Pydantic pour les contrats et leurs invariants ;
* NumPy pour les tableaux numériques ;
* pytest pour les tests ;
* mypy pour le typage statique ;
* Flake8 pour la qualité du code.

---

## 5. Source des données

Le dataset ML est construit à partir de deux entités persistées par le système de backtest :

* `SignalObservation` ;
* `ForwardOutcome`.

Une observation représente l’ensemble d’informations disponible au moment de la décision. Un outcome décrit le résultat futur associé à cette observation pour un horizon défini.

Le repository ML applique notamment les règles suivantes :

* seules les observations confirmées sont éligibles ;
* un outcome correspondant exactement à l’horizon demandé doit être disponible ;
* les lignes sont chargées dans l’ordre chronologique ;
* l’ordre secondaire est stable grâce à l’identifiant d’observation ;
* la pagination est déterministe ;
* un seul job et un seul horizon sont utilisés pour un export.

Les observations provisoires ne doivent pas entrer dans un dataset d’entraînement final.

Les signaux structurés et leurs composants sont persistés dans le contenu complet de l’observation. L’ajout de composants d’indicateurs ne nécessite donc pas de migration spécifique du schéma relationnel lorsque le contrat Pydantic reste compatible.

---

## 6. Contrat du dataset

### 6.1 Versions

Le premier dataset validé utilise les versions suivantes :

| Contrat          | Version                |
| ---------------- | ---------------------- |
| Manifeste        | `1`                    |
| Dataset          | `1`                    |
| Caractéristiques | `causal-features-v1`   |
| Labels           | `direction-natr-h6-v1` |
| Benchmark        | `ml-benchmark-v1`      |

Ces versions appartiennent au dataset et au benchmark v1 historiques.

Un futur dataset comportant un ensemble de caractéristiques différent devra utiliser un nouveau contrat ou une version explicitement distincte. Il ne devra pas être présenté comme une reproduction du dataset v1.

### 6.2 Ligne de dataset

Une ligne `MLDatasetRow` contient notamment :

* l’identifiant de l’observation ;
* l’identifiant du job source ;
* le symbole et le timeframe ;
* le temps de décision ;
* le temps d’ouverture de la bougie source ;
* le statut du snapshot ;
* les versions de l’algorithme et du dataset source ;
* l’horizon ;
* les temps et prix d’entrée et de sortie ;
* le NATR disponible au temps de décision ;
* le seuil neutre calculé ;
* le rendement futur ;
* le label cible ;
* les caractéristiques causales.

Les informations futures nécessaires à la cible sont présentes dans la ligne supervisée, mais elles sont explicitement interdites dans le dictionnaire des caractéristiques.

### 6.3 Valeurs de caractéristiques

Les caractéristiques acceptent uniquement les valeurs suivantes :

```python
bool | int | float | str | None
```

Les valeurs numériques non finies sont refusées.

Les noms de caractéristiques réservés aux cibles, outcomes ou informations futures sont également refusés par le contrat.

### 6.4 Aplatissement des signaux structurés

Les signaux d’indicateurs sont aplatis de manière générique dans le dictionnaire de caractéristiques.

Pour chaque signal, le pipeline peut notamment exporter :

```text
indicator.<nom>.status
indicator.<nom>.direction
indicator.<nom>.signal
indicator.<nom>.state
indicator.<nom>.strength
indicator.<nom>.raw_value
```

Pour chaque composant structuré :

```text
indicator.<nom>.component.<composant>.value
indicator.<nom>.component.<composant>.normalized_value
indicator.<nom>.component.<composant>.unit
```

Le mécanisme d’aplatissement est générique. L’ajout d’un composant causal à un indicateur le rend donc disponible dans un futur export sans nécessiter une règle d’extraction propre à cet indicateur.

La sélection finale des représentations utiles au modèle relève ensuite de la politique de caractéristiques.

---

## 7. Construction des labels

Le pipeline prédit trois classes :

```text
DOWN
NEUTRAL
UP
```

L’horizon v1 est fixé à six bougies :

```text
horizon = 6
```

Pour une bougie de décision donnée, le seuil neutre est calculé à partir du NATR connu à ce moment :

```text
neutral_threshold_return =
    (natr_percent / 100) × natr_multiplier
```

Pour l’expérience v1 :

```text
natr_multiplier = 1.0
```

La classification est ensuite définie ainsi :

```text
future_return < -neutral_threshold_return
    → DOWN

future_return > neutral_threshold_return
    → UP

sinon
    → NEUTRAL
```

Les deux frontières du seuil appartiennent donc à la classe `NEUTRAL`.

Cette définition adapte la zone neutre à la volatilité disponible au moment de la décision.

Le NATR est obligatoire pour construire le label. Une observation sans NATR exploitable ne peut pas produire une ligne de dataset valide.

---

## 8. Garanties de causalité

Le pipeline applique plusieurs protections contre les fuites temporelles.

### 8.1 Bougies fermées

Les caractéristiques sont calculées à partir de l’information disponible sur des bougies fermées au temps de décision.

### 8.2 Caractéristiques causales

Le dictionnaire `features` ne doit contenir aucune donnée provenant :

* du prix de sortie ;
* du temps de sortie ;
* du rendement futur ;
* du label ;
* d’une bougie postérieure au temps de décision ;
* d’un outcome futur.

### 8.3 Composants précédents

Les composants décrivant une valeur précédente ou une variation doivent uniquement utiliser les valeurs disponibles à `t` et `t-1`.

Ils ne doivent jamais utiliser une moyenne, une borne, un régime ou une transformation calculée avec une bougie postérieure au temps de décision.

### 8.4 Apprentissage du prétraitement

Le prétraitement est ajusté uniquement sur les lignes d’entraînement de chaque évaluation.

Les médianes, constantes, catégories et colonnes générées ne sont jamais apprises depuis la validation ou le test.

### 8.5 Purge temporelle

Avant chaque frontière temporelle, une ligne est purgée lorsque sa cible se termine dans la partition suivante.

La condition de chevauchement est :

```text
exit_time >= début de la partition suivante
```

Cette purge évite qu’un échantillon d’entraînement utilise une cible dépendant de prix appartenant à la validation ou au test.

### 8.6 Test terminal

Le test terminal est ouvert une seule fois après la sélection de la configuration.

Une fois évalué, il est marqué :

```text
test_consumed = true
```

Il ne peut plus être considéré comme un test inédit pour cette expérience.

---

## 9. Export du dataset

Le service `MLDatasetExporter` produit :

* un fichier JSONL contenant les lignes ;
* un manifeste JSON décrivant l’export ;
* un SHA-256 calculé sur le fichier JSONL.

Les lignes sont triées de manière déterministe avant l’écriture.

Le JSON est sérialisé sous une forme canonique afin que le même contenu produise le même hash.

Le chargeur `MLDatasetLoader` vérifie notamment :

* le manifeste ;
* le nom sûr du fichier de données ;
* l’existence du JSONL ;
* le SHA-256 exact ;
* le nombre de lignes ;
* les identifiants ;
* l’ordre chronologique ;
* les métadonnées du dataset ;
* la présence d’un saut de ligne final conforme.

Toute divergence entre le manifeste et le fichier de données provoque un rejet.

---

## 10. Premier dataset exporté

Le premier dataset a été construit depuis le job suivant :

```text
cc776c29c7e74f74a7910d91fc3b92cc
```

Fichiers :

```text
artifacts/ml-datasets/btc-usdc-1h-h6-v1.jsonl
artifacts/ml-datasets/btc-usdc-1h-h6-v1.manifest.json
```

SHA-256 du JSONL :

```text
sha256:a94660d07503b9494ac646ad948d0738d7b6a6941b1893c40a3a671484e4b2a4
```

Résumé de la construction :

| Mesure                     | Valeur |
| -------------------------- | -----: |
| Lignes source              |    719 |
| Lignes générées            |    713 |
| Outcomes censurés          |      6 |
| NATR manquants             |      0 |
| Caractéristiques exportées |    136 |

Période couverte :

```text
2026-07-04 15:00:00 UTC
→
2026-08-03 07:00:00 UTC
```

Distribution des labels :

| Label     | Nombre |    Part |
| --------- | -----: | ------: |
| `DOWN`    |    172 | 24,12 % |
| `NEUTRAL` |    380 | 53,30 % |
| `UP`      |    161 | 22,58 % |
| Total     |    713 |   100 % |

Le dataset est relativement court et couvre environ un mois de marché. Cette durée est insuffisante pour représenter correctement plusieurs régimes de volatilité et de tendance.

Les nombres de cette section décrivent exclusivement l’artefact v1 existant. Un nouvel export effectué après l’enrichissement des signaux structurés produira un ensemble de caractéristiques différent et devra utiliser un autre nom ainsi qu’un contrat explicitement distinct.

---

## 11. Prétraitement

Le prétraitement est implémenté par `MLFeaturePreprocessor`.

### 11.1 Caractéristiques numériques

Les caractéristiques numériques utilisent :

* une imputation par la médiane apprise sur le train ;
* des indicateurs de valeur manquante ;
* une standardisation.

Une caractéristique numérique comportant des valeurs manquantes n’est pas considérée comme constante uniquement parce qu’une seule valeur non manquante est présente.

### 11.2 Événements et divergences

L’absence d’un événement ou d’une divergence structurée est représentée par zéro lorsque ce contrat est applicable.

### 11.3 Caractéristiques catégorielles

Les catégories utilisent :

* un token explicite pour les valeurs manquantes ;
* un encodage one-hot ;
* `handle_unknown="ignore"` pour les catégories inconnues hors train.

### 11.4 Constantes

Les caractéristiques constantes sont détectées uniquement depuis le train courant.

Elles sont supprimées avant la transformation finale.

### 11.5 Labels

L’ordre stable des classes est :

```text
DOWN     → 0
NEUTRAL  → 1
UP       → 2
```

Cet ordre est utilisé dans les métriques, les matrices de confusion et les comptes de prédictions.

---

## 12. Politiques de caractéristiques

Le benchmark v1 évalue exactement quatre politiques historiques.

Cette liste est explicitement figée dans `ML_FEATURE_POLICIES_V1` afin qu’une future politique de caractéristiques ne modifie pas silencieusement les candidats, le classement ou la reproductibilité du benchmark v1.

### `all`

Conserve toutes les caractéristiques exportées.

### `without_absolute`

Retire les valeurs absolues de prix, volume et indicateurs identifiées par le contrat historique v1.

### `without_duplicates`

Retire les caractéristiques considérées par le contrat v1 comme des représentations dupliquées de la même information.

### `normalized_deduplicated`

Applique simultanément les exclusions des valeurs absolues et des doublons définies pour la v1.

Cette dernière politique a été sélectionnée pendant le walk-forward.

Les politiques ajoutées après le gel de la v1 ne font pas partie de ce walk-forward historique et ne doivent pas être utilisées pour reconstruire le benchmark `ml-benchmark-v1`.

Dans l’évaluation finale, 18 caractéristiques présentes ont été exclues :

```text
candle.close
candle.high
candle.low
candle.open
candle.volume
indicator.atr.component.atr.value
indicator.atr.component.natr.normalized_value
indicator.atr.component.natr.value
indicator.atr.component.true_range.value
indicator.atr.raw_value
indicator.bollinger.component.band_position.normalized_value
indicator.bollinger.component.band_width.value
indicator.bollinger.component.band_width_percent.normalized_value
indicator.bollinger.component.lower_band.value
indicator.bollinger.component.middle_band.value
indicator.bollinger.component.upper_band.value
price.close
quality.quote_volume_median
```

Résumé du prétraitement final :

| Étape                                     | Nombre |
| ----------------------------------------- | -----: |
| Caractéristiques exportées                |    136 |
| Caractéristiques exclues par la politique |     18 |
| Entrées du prétraitement                  |    118 |
| Constantes supprimées                     |     28 |
| Caractéristiques actives                  |     90 |
| Colonnes transformées finales             |    139 |

Ces nombres décrivent exclusivement le dataset et le benchmark v1 immuables.

Ils ne représentent pas le nombre de caractéristiques qu’un nouvel export effectué avec le code actuel produirait. Après le gel du benchmark v1, les signaux structurés ont été enrichis avec des composants causaux supplémentaires pour :

* RSI ;
* MACD ;
* stochastique ;
* SMA et EMA ;
* Bollinger ;
* ATR et NATR ;
* ADX et DMI ;
* Supertrend ;
* Donchian ;
* Keltner.

Ces enrichissements sont préparatoires à un futur dataset v2. Ils ne modifient rétroactivement ni le JSONL v1, ni son manifeste, ni ses 136 caractéristiques exportées, ni les 18 exclusions enregistrées dans le benchmark.

Le nombre de colonnes transformées peut être supérieur au nombre de caractéristiques actives en raison :

* des indicateurs de valeurs manquantes ;
* de l’encodage one-hot des catégories.

---

## 13. Découpage temporel initial

Le découpage temporel utilise les temps de décision uniques et respecte l’ordre chronologique.

La répartition initiale est :

```text
60 % entraînement
20 % validation
20 % test terminal
```

Les lignes dont la cible chevauche la partition suivante sont ensuite purgées.

Pour le dataset v1 :

| Partition                | Nombre |
| ------------------------ | -----: |
| Entraînement après purge |    421 |
| Validation après purge   |    137 |
| Test                     |    143 |
| Purge avant validation   |      6 |
| Purge avant test         |      6 |

Le test terminal commence à :

```text
2026-07-28T09:00:00Z
```

Pour l’évaluation finale, l’entraînement utilise tout le développement causal disponible avant ce test :

| Ensemble final                      | Nombre |
| ----------------------------------- | -----: |
| Développement                       |    564 |
| Chevauchements exclus avant le test |      6 |
| Test terminal                       |    143 |
| Total source                        |    713 |

---

## 14. Baselines

Deux approches sont comparées.

### 14.1 Dummy majoritaire

Le dummy prédit toujours la classe majoritaire apprise sur le développement.

Il permet de vérifier qu’un modèle entraîné apporte réellement plus qu’une stratégie triviale.

### 14.2 Régression logistique

Le modèle principal v1 est une régression logistique multiclasse avec équilibrage des classes.

Le pipeline compare plusieurs valeurs du paramètre de régularisation `C`.

Valeurs évaluées :

```text
1.0
0.3
0.1
0.03
0.01
0.003
```

---

## 15. Sélection walk-forward

La sélection est réalisée uniquement avant le test terminal.

Configuration :

| Paramètre                       |                           Valeur |
| ------------------------------- | -------------------------------: |
| Type                            | Fenêtre d’entraînement expanding |
| Nombre de folds                 |                                4 |
| Taille de validation par fold   |                               72 |
| Fenêtre minimale d’entraînement |                              200 |
| Politiques évaluées             |                                4 |
| Valeurs de `C`                  |                                6 |
| Nombre total de candidats       |                               24 |

Les quatre politiques candidates sont celles de `ML_FEATURE_POLICIES_V1`. Une future valeur ajoutée à l’enum `MLFeaturePolicy` ne doit pas augmenter automatiquement ce nombre de candidats.

Tailles réellement utilisées :

| Fold | Train | Validation | Lignes purgées |
| ---- | ----: | ---------: | -------------: |
| 1    |   270 |         72 |              6 |
| 2    |   342 |         72 |              6 |
| 3    |   414 |         72 |              6 |
| 4    |   486 |         72 |              6 |

Le classement déterministe applique successivement les critères suivants :

1. moyenne du macro-F1 de validation, décroissante ;
2. minimum du macro-F1 parmi les folds, décroissant ;
3. macro-F1 des prédictions de validation regroupées, décroissant ;
4. moyenne de la balanced accuracy de validation, décroissante ;
5. valeur absolue du generalization gap, croissante ;
6. valeur de `C`, croissante ;
7. nom de la politique, ordre lexical.

La configuration sélectionnée est :

```text
policy = normalized_deduplicated
C = 0.03
```

Résultats walk-forward :

| Mesure                       | Valeur |
| ---------------------------- | -----: |
| Macro-F1 moyen du train      | 0,5799 |
| Macro-F1 moyen de validation | 0,3018 |
| Écart-type du macro-F1       | 0,0581 |
| Macro-F1 minimum             | 0,2327 |
| Macro-F1 regroupé            | 0,3373 |
| Balanced accuracy moyenne    | 0,3795 |
| Generalization gap moyen     | 0,2781 |

Comptes des prédictions de validation regroupées :

| Classe    | Nombre |
| --------- | -----: |
| `DOWN`    |    112 |
| `NEUTRAL` |    104 |
| `UP`      |     72 |
| Total     |    288 |

Les résultats sont instables entre les folds, notamment en raison de la faible quantité de données et de distributions de classes différentes selon les périodes.

---

## 16. Évaluation finale

Après la sélection walk-forward, la configuration retenue est entraînée sur toutes les lignes causales de développement.

Aucune nouvelle sélection de politique ou de valeur de `C` ne doit être faite à partir des résultats du test.

### 16.1 Dummy sur le test

| Mesure            | Valeur |
| ----------------- | -----: |
| Accuracy          | 0,4895 |
| Balanced accuracy | 0,3333 |
| Macro-F1          | 0,2191 |
| Weighted-F1       | 0,3217 |

Prédictions :

| Classe    | Nombre |
| --------- | -----: |
| `DOWN`    |      0 |
| `NEUTRAL` |    143 |
| `UP`      |      0 |

### 16.2 Régression logistique sur le développement

| Mesure            | Valeur |
| ----------------- | -----: |
| Accuracy          | 0,5532 |
| Balanced accuracy | 0,5603 |
| Macro-F1          | 0,5354 |
| Weighted-F1       | 0,5639 |

Prédictions :

| Classe    | Nombre |
| --------- | -----: |
| `DOWN`    |    175 |
| `NEUTRAL` |    218 |
| `UP`      |    171 |

### 16.3 Régression logistique sur le test terminal

| Mesure            | Valeur |
| ----------------- | -----: |
| Nombre de lignes  |    143 |
| Accuracy          | 0,3007 |
| Balanced accuracy | 0,3358 |
| Macro-F1          | 0,2898 |
| Weighted-F1       | 0,2897 |

Prédictions :

| Classe    | Nombre |
| --------- | -----: |
| `DOWN`    |     20 |
| `NEUTRAL` |     42 |
| `UP`      |     81 |

Matrice de confusion :

| Réel \ Prédit | `DOWN` | `NEUTRAL` | `UP` |
| ------------- | -----: | --------: | ---: |
| `DOWN`        |      7 |        14 |   20 |
| `NEUTRAL`     |     11 |        17 |   42 |
| `UP`          |      2 |        11 |   19 |

Rappel par classe :

| Classe    | Rappel |
| --------- | -----: |
| `DOWN`    | 0,1707 |
| `NEUTRAL` | 0,2429 |
| `UP`      | 0,5938 |

Le modèle sur-prédit fortement la classe `UP` et identifie mal les classes `DOWN` et `NEUTRAL`.

---

## 17. Décision du benchmark

Le modèle v1 est rejeté.

```text
status = rejected
test_consumed = true
```

Motifs enregistrés :

```text
balanced accuracy du test proche du hasard
généralisation temporelle insuffisante
surprédiction importante de la classe UP
```

La balanced accuracy de `0,3358` est très proche de la valeur `1/3` attendue pour une classification équilibrée aléatoire à trois classes.

Le modèle dépasse le dummy sur le macro-F1 du test, mais cette amélioration reste insuffisante et ne démontre pas une généralisation exploitable.

Le modèle ne doit pas être :

* intégré au marché en direct ;
* utilisé pour filtrer les signaux ;
* utilisé pour ouvrir ou simuler des positions ;
* présenté comme une prédiction fiable ;
* optimisé de nouveau à partir de ce test terminal.

---

## 18. Benchmark immuable

Le rapport final est enregistré dans :

```text
artifacts/ml-benchmarks/btc-usdc-1h-h6-logistic-v1-rejected.benchmark.json
```

SHA-256 canonique :

```text
sha256:dab10c9e3de2e160fd25b8259dc37e444190f8dc4d925d33bea87b0407f109dc
```

Le rapport contient notamment :

* les versions des contrats ;
* le SHA-256 du dataset ;
* la période couverte ;
* la frontière du test ;
* les paramètres du walk-forward ;
* la configuration sélectionnée ;
* les comptes de caractéristiques ;
* les métriques du dummy ;
* les métriques du développement ;
* les métriques du test ;
* la décision finale ;
* la confirmation que le test est consommé.

L’exporteur utilise un JSON canonique :

* UTF-8 ;
* clés triées ;
* aucune indentation ;
* séparateurs compacts ;
* un unique saut de ligne final ;
* valeurs non finies interdites.

Une seconde exportation identique réutilise le fichier existant.

Un contenu différent avec le même nom est refusé afin d’empêcher un écrasement silencieux.

Le fichier canonique ne doit pas être reformaté manuellement. Une indentation automatique change ses octets et donc son SHA-256, même lorsque le contenu JSON logique reste identique.

Le benchmark v1 conserve son propre contrat de politiques et ne doit pas accepter automatiquement une politique introduite pour une expérimentation ultérieure.

---

## 19. Commandes CLI

Toutes les commandes doivent être exécutées depuis `backend/`.

### 19.1 Exporter un dataset

```powershell
python -m app.ml.cli.export_ml_dataset `
    "<job_id>" `
    --output-directory "artifacts\ml-datasets" `
    --batch-size 500 `
    --natr-multiplier 1.0 `
    --file-stem "<nom-du-dataset>"
```

La commande :

1. initialise l’accès à la base ;
2. charge les observations et outcomes ;
3. construit les lignes causales ;
4. produit le JSONL ;
5. produit le manifeste ;
6. calcule le SHA-256 ;
7. ferme proprement la base.

### 19.2 Reproduire le benchmark v1

```powershell
python -m app.ml.cli.export_ml_benchmark `
    "artifacts\ml-datasets\btc-usdc-1h-h6-v1.manifest.json" `
    --output-directory "artifacts\ml-benchmarks" `
    --benchmark-name "btc-usdc-1h-h6-logistic-v1" `
    --file-stem "btc-usdc-1h-h6-logistic-v1-rejected" `
    --created-at "2026-08-03T23:23:00+02:00" `
    --selected-policy "normalized_deduplicated" `
    --selected-c-value 0.03 `
    --fold-count 4 `
    --validation-window 72 `
    --minimum-train-window 200 `
    --candidate-c-values 1.0 0.3 0.1 0.03 0.01 0.003 `
    --status "rejected" `
    --decision-reason "balanced accuracy du test proche du hasard" `
    --decision-reason "généralisation temporelle insuffisante" `
    --decision-reason "surprédiction importante de la classe UP"
```

La date `created-at` est obligatoire afin que le rapport reste reproductible.

La commande refuse l’export lorsque la politique ou la valeur de `C` transmise ne correspond pas au meilleur candidat du walk-forward reconstruit.

Les choix proposés par cette commande pour un benchmark v1 doivent provenir exclusivement de `ML_FEATURE_POLICIES_V1`.

---

## 20. Vérifications techniques

### 20.1 Code applicatif ML

```powershell
python -m compileall -q app tests
```

```powershell
python -m mypy app\ml
```

État vérifié avant le démarrage de la v2 :

```text
24 fichiers sources analysés
aucune erreur mypy
```

```powershell
python -m flake8 app\ml
```

### 20.2 Tests ML

```powershell
python -m pytest -q tests\ml
```

État validé lors du gel initial de la phase :

```text
288 tests réussis
```

État vérifié avant le démarrage de la v2 :

```text
300 tests réussis
```

L’augmentation correspond à des tests ajoutés après le gel du benchmark. Elle ne modifie pas les artefacts v1.

### 20.3 Typage des tests

La configuration mypy ne découvre pas nécessairement les tests lorsqu’un dossier est fourni directement. La liste des fichiers peut être transmise explicitement :

```powershell
$files = Get-ChildItem `
    "tests\ml" `
    -Recurse `
    -File `
    -Filter "*.py" |
    ForEach-Object {
        $_.FullName
    }

python -m mypy $files
```

État vérifié avant le démarrage de la v2 :

```text
25 fichiers sources analysés
aucune erreur mypy
```

### 20.4 Style

```powershell
python -m flake8 `
    app\ml `
    tests\ml
```

### 20.5 Validation étendue préparatoire à la v2

Les tests ML peuvent être exécutés avec les tests des signaux et des indicateurs enrichis :

```powershell
python -m pytest -q `
    tests\ml `
    "tests\test_indicator_signals.py" `
    "tests\test_indicator_extension_phase_8_2.py" `
    "tests\test_indicator_extension_phase_8_3.py"
```

État vérifié avant le démarrage de la v2 :

```text
373 tests réussis
```

Cette validation couvre notamment les composants causaux ajoutés aux indicateurs. Elle ne transforme pas ces composants en caractéristiques du benchmark v1 existant.

---

## 21. Règles pour une future expérimentation

Depuis le gel du benchmark v1, les signaux structurés des indicateurs ont été enrichis afin de préparer une nouvelle politique de sélection de caractéristiques.

Les enrichissements validés concernent notamment :

* les valeurs actuelles normalisées ;
* les valeurs précédentes ;
* les variations causales ;
* les distances normalisées au prix ;
* les distances exprimées en ATR ;
* les positions dans les canaux ;
* les largeurs relatives ;
* les écarts directionnels ;
* les distances aux seuils d’indicateurs.

Ces travaux préparatoires ne constituent pas encore un pipeline ML v2 complet.

Avant tout nouvel entraînement, il reste nécessaire de :

* définir une politique `normalized_deduplicated_v2` distincte des politiques v1 ;
* figer un nouveau contrat de caractéristiques ;
* définir un profil de génération activant explicitement les indicateurs étendus nécessaires ;
* exporter un nouveau dataset sous un nouveau nom ;
* réserver une nouvelle période terminale postérieure à la période consommée ;
* documenter la nouvelle expérimentation séparément du benchmark v1.

Le test terminal actuel couvre la période suivante :

```text
2026-07-28T09:00:00Z
→
2026-08-03T07:00:00Z
```

Cette période est désormais connue et ne peut plus servir de test inédit pour une nouvelle variante directement comparable.

Elle peut être intégrée à un futur ensemble de développement uniquement si :

* un dataset plus long est construit ;
* une nouvelle période terminale ultérieure est réservée ;
* cette nouvelle frontière est définie avant toute sélection ;
* aucun résultat de la nouvelle période de test n’est consulté pendant le développement.

La prochaine expérimentation doit suivre cet ordre :

1. définir et tester le nouveau contrat de caractéristiques ;
2. définir la politique `normalized_deduplicated_v2` sans modifier les politiques v1 ;
3. définir un profil de dataset activant explicitement les indicateurs nécessaires ;
4. accumuler un historique beaucoup plus long ;
5. inclure plusieurs régimes de marché ;
6. exporter un nouveau dataset sous un nouveau nom ;
7. vérifier son manifeste et son SHA-256 ;
8. définir à l’avance la nouvelle période de test terminale ;
9. définir les candidats et critères de classement ;
10. sélectionner uniquement sur le développement ;
11. figer la configuration retenue ;
12. évaluer une seule fois le nouveau test ;
13. produire un nouveau benchmark immuable.

Les critères d’acceptation du prochain modèle doivent être définis avant l’ouverture du nouveau test.

---

## 22. Préparatifs réalisés pour la v2

Les indicateurs suivants ont été audités et enrichis avec des composants structurés causaux :

```text
RSI
MACD
Stochastique
SMA
EMA
Bollinger
ATR
NATR
ADX
DMI
Supertrend
Donchian
Keltner
```

### 22.1 Principes appliqués

Les enrichissements suivent les principes suivants :

* conserver les valeurs brutes utiles à l’audit ;
* exposer une représentation normalisée lorsqu’elle est pertinente ;
* préférer les ratios et distances relatives aux niveaux de prix absolus ;
* calculer les variations uniquement avec les valeurs courantes et précédentes ;
* ne pas modifier les décisions métier historiques ;
* ne pas ajouter les indicateurs étendus à la confluence historique ;
* ne pas modifier les résultats de portefeuille ;
* conserver la parité entre marché en direct et backtest ;
* ne pas modifier le benchmark v1 existant.

### 22.2 Neutralité métier

Les enrichissements concernent l’observabilité et la future construction du dataset.

Ils ne doivent pas modifier :

* l’acceptation ou le rejet d’un signal ;
* le score de confluence historique ;
* la note de confluence ;
* les facteurs historiques ;
* les ordres simulés ;
* les exécutions ;
* les trades ;
* la courbe d’équité ;
* les métriques de portefeuille.

### 22.3 Activation explicite

Les indicateurs étendus restent optionnels dans `ScanConfig`.

Ils doivent être explicitement activés dans le profil utilisé pour générer un futur dataset v2. Leur présence dans le code ne garantit pas qu’ils apparaîtront dans les observations d’un nouveau job.

Le profil du futur dataset devra donc être versionné, identifiable et reproductible.

---

## 23. Pistes d’amélioration

Les pistes suivantes peuvent être étudiées sur un nouveau dataset, sans utiliser le test consommé comme boucle d’optimisation :

* augmenter fortement la durée de l’historique ;
* inclure plusieurs phases haussières, baissières et latérales ;
* analyser plusieurs symboles tout en contrôlant les dépendances entre marchés ;
* mesurer les résultats par régime de volatilité ;
* mesurer les résultats par symbole et période ;
* vérifier la stabilité des probabilités prédites ;
* étudier la calibration des probabilités ;
* renforcer les caractéristiques relatives et normalisées ;
* analyser la dérive des distributions ;
* comparer des modèles non linéaires simples ;
* conserver une baseline logistique interprétable ;
* définir des seuils d’abstention lorsque la confiance est faible ;
* évaluer séparément la qualité prédictive et la valeur économique.

Toute amélioration doit conserver les garanties de causalité, de purge et d’évaluation terminale unique.

Une amélioration des résultats de développement ne doit pas être considérée comme suffisante si elle s’accompagne :

* d’une instabilité importante entre les folds ;
* d’un écart de généralisation élevé ;
* d’une prédiction concentrée sur une seule classe ;
* d’une dégradation sur plusieurs régimes de marché ;
* d’un nombre de données insuffisant ;
* d’un test terminal utilisé à plusieurs reprises.

---

## 24. Conclusion

La phase ML v1 a permis de mettre en place une infrastructure complète :

* dataset supervisé causal ;
* labels adaptatifs au NATR ;
* export et chargement vérifiés ;
* prétraitement appris uniquement sur le train ;
* sélection temporelle walk-forward ;
* comparaison à une baseline ;
* test terminal réservé ;
* benchmark canonique et immuable ;
* couverture de tests dédiée ;
* organisation du code sous `app/ml` et `tests/ml`.

Le pipeline technique v1 est validé.

Le premier modèle ne l’est pas.

Depuis le gel du benchmark, les signaux structurés ont été enrichis pour préparer un futur dataset. Ces enrichissements ne modifient pas le verdict v1 et ne constituent pas encore une expérimentation v2 complète.

```text
Infrastructure ML v1 : VALIDÉE
Modèle logistique v1 : REJETÉ
Production             : INTERDITE
Test terminal          : CONSOMMÉ
Benchmark v1           : FIGÉ
Préparatifs v2         : COMPOSANTS INDICATEURS VALIDÉS
Prochaine étape        : POLITIQUE V2 ET NOUVEAU DATASET PLUS LONG
```
