# Audit final d'implémentation des phases 1 à 4

Date : 24 juillet 2026.

Le dossier `.git` est vide : branche, commit et diff Git sont indisponibles. Cet
audit repose donc sur le code, les migrations, les contrats, les routes et les
tests exécutés localement.

## Statut

| Périmètre | Statut | Preuve principale |
|---|---|---|
| Phases 1–2 existantes | validées avec corrections | primitives, contrats et suites scanner/market |
| Phase 3 confirmed/close-only | complète | moteur causal, observation v2, outcomes, stats, checkpoint/reprise |
| Phase 3 provisional historique | indisponible par conception | capability explicite ; aucune donnée intrabar fidèle |
| Phase 4 protocole expérimental | complète | split, double embargo, sélection validation, OOS, test final |
| Phase 4 gouvernance/shadow | complète hors outcomes shadow futurs | profils immuables, lifecycle, promotion, calcul automatique |
| Visualisations avancées | partielle | tableaux/cartes présents, graphiques de sensibilité absents |

## Changements structurants

- façade `evaluate_signal_snapshot` utilisée par replay, scanner et shadow ;
- divergences causales intégrées aux observations avec temps de confirmation ;
- observation v2 versionnée et fingerprintée, outcomes et analytics enrichis ;
- migration 7 : checkpoints, artefacts, lifecycle et idempotence shadow ;
- reprise réelle après interruption et restauration frontend ;
- oracle golden chiffré ;
- walk-forward train/validation/OOS avec sélection sans fuite vers OOS/test ;
- bootstrap par blocs, sensibilité poids/coûts et Benjamini–Hochberg ;
- variantes Bollinger/Stoch/MACD/divergence/liquidité/qualité/régime/timeframe ;
- contenu des profils immutable par hash, statut et historique séparés ;
- shadow automatique sur clôture, sans effet sur la production ;
- APIs et interface enrichies pour historique, reprise, profils et shadow.

## Limites explicites

1. Le provisional historique reste refusé : les seules données stockées sont des
   OHLCV closes, insuffisantes pour reconstruire les révisions intrabar.
2. Le snapshot graphique live conserve son adaptateur de présentation
   confirmed/provisional, tout en réutilisant les primitives d'indicateurs. La
   décision scanner, le replay et shadow passent par la façade canonique.
3. Les outcomes futurs des comparaisons shadow ne sont pas encore complétés
   automatiquement.
4. L'interface fournit des tableaux de recherche mais pas les graphiques
   statistiques avancés demandés.
5. Aucun résultat historique n'est une garantie de performance future.

## Vérification

Les commandes finales et leurs résultats sont consignés dans
`CURRENT_APP_STATE_FOR_AI.md`. Les tests utilisent SQLite temporaire et des
fixtures ; aucun appel réel à Binance n'est requis.

Résultat final : backend 251 passed, 1 skipped (benchmark opt-in), 22 subtests ;
benchmark opt-in 1 passed ; frontend 52 passed ; Black, Flake8, mypy, ESLint,
TypeScript et build Vite réussis.
