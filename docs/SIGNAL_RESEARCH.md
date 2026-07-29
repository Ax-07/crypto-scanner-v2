# Méthode de recherche sur les signaux

La recherche reste séparée de la production :

1. figer la configuration du signal ;
2. choisir avant calcul plage, univers, horizons et entrée ;
3. contrôler la couverture et documenter les trous ;
4. rejouer causalement les décisions, rejets compris ;
5. rapporter effectifs, censure et disponibilité avant les coefficients ;
6. traiter corrélations, segmentations et ablations comme exploratoires ;
7. confirmer sur une période hors échantillon distincte.

Pearson décrit une relation linéaire ; Spearman une relation monotone sur les rangs.
Leur divergence, un faible `pair_count`, une forte censure ou une disponibilité
sélective imposent de la prudence. Une corrélation ne prouve ni causalité ni
rentabilité.

Une ablation répond seulement à « que serait devenu ce score sur cet échantillon si
ce facteur avait été omis ? ». Elle ne choisit pas de nouveaux poids. Toute évolution
de production appartient à une phase ultérieure.

Un résultat publié doit joindre configuration et dataset, dates UTC, univers,
timeframe, horizons, décision, entrée, frais, slippage, trous, censure, effectifs par
cellule et nombre de comparaisons. Il ne doit promettre aucune performance.
