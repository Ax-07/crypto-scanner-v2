# Méthodologie d'évaluation des signaux et stratégies

## Objet

Une baseline est un point de comparaison figé : même code de signaux, mêmes
filtres, même stratégie et mêmes règles comptables. Elle empêche d'attribuer à
une modification un écart provenant en réalité des données, des coûts ou du
simulateur. La baseline v1 mesure le système existant ; elle ne recherche aucun
paramètre.

## Unités d'analyse

Une observation décrit les informations disponibles à la clôture d'une bougie
et la décision accepted/rejected. Un outcome mesure indépendamment le futur
après chaque observation. Un portefeuille applique une séquence exclusive
d'entrées et sorties, avec cash, frais, slippage et exposition. La somme des
outcomes n'est jamais un P&L de portefeuille.

Les résultats sont rapportés par combinaison symbole/timeframe/période. Les
comptes mono-symboles sont indépendants : additionner leurs P&L ne constitue pas
une simulation multi-actifs.

## Séparation chronologique

Chaque plage contiguë sélectionnée est découpée sans permutation :

```text
60 % développement | 20 % validation | 20 % test final
```

Les indices sont calculés sur les observations strictement ordonnées. Les bornes
ne se chevauchent pas. Les paramètres restent identiques. En Phase 7.1, les
trois segments servent uniquement à décrire la stabilité de la configuration
actuelle.

Le test final est gelé pour les expériences futures. Une Phase 7.2 peut utiliser
développement puis validation ; elle ne consulte le test final qu'après gel de
la variante et de ses critères. Un échec sur validation arrête l'expérience
avant le test final.

## Couverture et taille d'échantillon

Les seuils v1 sont fixés avant les performances :

- au moins 500 bougies closes dans une plage contiguë ;
- continuité minimale de 98 % pour l'inventaire, et plage exécutée sans gap ;
- au moins 30 trades pour retirer l'avertissement de faible échantillon.

Ces seuils sont des garde-fous, pas une preuve de puissance statistique. Une
moyenne sur trois trades demeure descriptive. Chaque tableau affiche le nombre
de bougies, observations et trades. Une combinaison est classée évaluable,
faible échantillon ou non évaluable.

## Mesures économiques

La configuration canonique emploie 10 000 unités de cotation, 100 % du cash,
0,1 % de frais, aucun slippage, exécution à l'ouverture suivante et clôture
forcée. Rendement, drawdown positif, frais, exposition, win rate, rendement
moyen et durée sont calculés par le moteur de portefeuille v1.

Profit factor, gain/perte moyens et extrêmes sont dérivés des trades fermés.
Aucun Sharpe, Sortino ou rendement annualisé n'est publié sans calendrier et
convention de fréquence explicites.

## Coûts et sizing

Les matrices sont définies avant lecture :

- frais : 0, 0,05 %, 0,1 %, 0,2 % ;
- slippage : 0, 0,05 %, 0,1 %, 0,2 % ;
- sizing : 25 %, 50 %, 100 %.

Elles réutilisent les mêmes observations et transitions. Une différence de
nombre de trades causée uniquement par les coûts est une anomalie. Le sizing
mesure la composition et le risque monétaire, pas la qualité intrinsèque du
signal.

## Concentration des profits

Le P&L des meilleur, trois meilleurs, cinq meilleurs et 10 % meilleurs trades
est comparé au P&L total ; le miroir est calculé pour les pires trades. Si le
total est nul, la part est indéfinie. S'il est négatif, le ratio signé est
conservé mais explicitement marqué : il ne doit pas être lu comme une part
positive classique.

Une performance positive dépendant majoritairement de cinq trades est moins
robuste qu'une distribution régulière. Cette mesure est toujours accompagnée du
nombre total de trades.

## Stabilité temporelle et inter-marchés

La stabilité temporelle compare développement, validation, test et, si la
profondeur le permet, périodes calendaires. Sont signalés : changement de signe
du rendement, hausse du drawdown, baisse des trades, hausse relative des frais,
baisse du win rate et changement de durée ou d'acceptation.

La stabilité inter-marchés exige un effet visible sur plusieurs symboles ou
timeframes. Une performance limitée à un seul actif, timeframe ou segment est
classée peu généralisée. Aucune combinaison n'est appelée « meilleure » sur un
simple classement historique.

## Indicateurs, confluence et corrélations

Disponibilité, direction, signal, state et strength sont décrits aux
observations, entrées, gains et pertes. `strength` est une intensité technique,
jamais une probabilité. Les vocabulaires ouverts signal/state sont inventoriés à
partir des valeurs observées.

Les buckets de confluence sont pré-définis : faible `<40`, moyen `[40,70[`,
fort `>=70`. La tendance multi-timeframe, les signaux SMA/EMA structurés et la
confluence restent des champs distincts.

Pearson/Spearman existants sont descriptifs, avec effectifs pairwise. Une
corrélation n'est ni une causalité ni une autorisation d'ajouter un filtre. Les
ablations d'outcomes ne sont pas assimilées à une simulation de portefeuille.

## Prévention du surapprentissage

Sont interdits pendant une baseline : sélection a posteriori de symboles,
timeframes ou buckets, grid search, recherche aléatoire, optimisation
bayésienne, modification après lecture du test final et combinaison de plusieurs
changements.

Une expérience future :

1. formule une hypothèse sur un seul composant ;
2. fixe métrique principale, garde-fous et critères d'abandon ;
3. implémente la modification minimale ;
4. mesure développement puis validation ;
5. rejette la variante si elle ne généralise pas ;
6. ouvre le test final une seule fois après gel.

## Règle de décision

Une variante n'est acceptée que si le rendement est amélioré ou stable, le
drawdown ne se dégrade pas au-delà du seuil pré-déclaré, l'effectif reste
suffisant, l'effet apparaît sur plusieurs périodes et marchés, les coûts restent
maîtrisés et aucune fuite temporelle n'est détectée. Une métrique isolée ou une
catégorie rare ne justifie aucune modification.

