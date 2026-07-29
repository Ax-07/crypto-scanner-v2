# Expérimentation et optimisation contrôlée

État vérifié le 24 juillet 2026.

## Protocole

Une expérience part d'un backtest `confirmed` terminé et conserve le fingerprint
du dataset, la version du code, l'algorithme, la graine, l'espace exploré, le
nombre total d'essais et tous les résultats, y compris négatifs.

Le découpage global train/validation/test est chronologique et applique un
embargo au moins égal à l'horizon évalué. Le classement ne consulte jamais le
test final.

Chaque fold walk-forward contient :

1. une fenêtre train ;
2. une validation après embargo ;
3. une fenêtre OOS distincte après un second embargo ;
4. un choix de candidat basé exclusivement sur la validation ;
5. une mesure OOS agrégée uniquement pour les gagnants ainsi sélectionnés.

Le résultat conserve séparément métriques train/validation, folds détaillés,
agrégat OOS sélectionné et test final intact.

## Robustesse

Les contraintes actives portent sur les effectifs globaux, par fold, timeframe,
nombre de symboles, périodes calendaires, concentration symbole, dégradation
train/validation et sensibilité locale.

Sont calculés :

- brut/net, MFE/MAE, quantile défavorable et dispersion ;
- stabilité mensuelle, annuelle, symbole et timeframe ;
- sensibilité RSI, confluence et poids par pas borné ;
- scénarios de coûts en bps ;
- intervalles bootstrap par blocs déterministes ;
- p-values ajustées par Benjamini–Hochberg, utilisées comme pénalité de rang.

Les variantes opérationnelles comprennent poids/exclusions/groupes, politiques
de tendance, seuils, Bollinger, MACD, Stochastique, divergences, liquidité,
qualité, régimes et groupes de timeframes. Une variante qui requiert une donnée
absente rejette l'observation ; elle n'invente jamais une valeur neutre.

## Profils et gouvernance

`SignalProfileVersion` est frozen et porte un `content_hash` SHA-256 excluant le
statut. Le JSON de contenu n'est jamais muté lors d'une transition. Les statuts
`draft`, `candidate`, `shadow`, `production`, `retired` vivent dans une colonne
séparée, et chaque transition est ajoutée transactionnellement à
`signal_profile_lifecycle`.

Une promotion exige une expérience terminée, un candidat sélectionné et éligible,
des observations confirmed, un lien au run, validation/OOS/test final
non négatifs, dégradation OOS bornée, contrôle de multiplicité, commentaire et
confirmation explicites. Un rollback est une repromotion auditée.

## Shadow automatique

Avec `SHADOW_MODE_ENABLED=true`, chaque clôture reçue par le flux live déclenche
la façade canonique pour le profil de production et tous les profils `shadow` du
timeframe. Les deux évaluations utilisent exactement la même information
causale. La comparaison est persistée de façon idempotente et n'affecte jamais
la réponse de production.

Les APIs exposent les comparaisons paginées et un résumé (accord, motifs,
outcomes disponibles). Les futurs outcomes shadow ne sont pas encore enrichis
automatiquement après leurs horizons ; le champ reste explicitement nul.

## Interface

La page Expériences affiche les splits, résultats, folds/OOS, test final,
correction BH, exports, profils versionnés, hash, passage en shadow, promotion
explicite et résumé shadow. Les visualisations sont actuellement des tableaux et
cartes ; aucun graphique interactif de courbe de sensibilité n'est encore fourni.
