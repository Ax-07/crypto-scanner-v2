# Backtesting et replay historique

État vérifié le 24 juillet 2026.

> La simulation de portefeuille v1 est conçue dans
> [`BACKTEST_PORTFOLIO_SIMULATION_DESIGN.md`](BACKTEST_PORTFOLIO_SIMULATION_DESIGN.md)
> et résumée par
> [`adr/ADR-portfolio-backtest-v1.md`](adr/ADR-portfolio-backtest-v1.md).
> **Le moteur de portefeuille est intégré de manière optionnelle et ses détails
> sont persistés depuis la Phase 6.4.** Le bloc absent conserve le replay
> historique. Un bloc présent produit un résumé public, des pages trades/equity
> et deux exports v1. Voir
> [`backend/portfolio-simulation-engine-v1.md`](backend/portfolio-simulation-engine-v1.md)
> et [`backend/portfolio-replay-integration-v1.md`](backend/portfolio-replay-integration-v1.md).
> La persistance et les routes sont décrites dans
> [`backend/portfolio-persistence-api-v1.md`](backend/portfolio-persistence-api-v1.md).

## Architecture et causalité

Le moteur `BacktestEngine` est indépendant de FastAPI et ne télécharge jamais de
données. Il lit SQLite, avance chronologiquement et appelle
`domain.signal_evaluation.evaluate_signal_snapshot`, la même façade de décision
que le scanner et le mode shadow.

Une observation ne voit que les bougies closes à sa date de décision. Les
timeframes supérieurs sont coupés sur leur propre `close_time`. Les divergences
sont émises au temps de confirmation du second pivot, jamais rétroactivement au
temps du pivot. Les outcomes futurs sont calculés seulement après la décision.

Le mode `confirmed` est disponible. Le mode `provisional` est volontairement
refusé tant qu'aucune source intrabar historisée et versionnée n'existe. Cette
capacité est annoncée par `GET /api/backtests/capabilities`.

## Contrats persistés

Chaque `SignalObservation` contient notamment :

- versions du schéma, de l'algorithme, du dataset et fingerprint du profil ;
- timestamp de calcul, décision, OHLCV source et mode de calcul ;
- valeurs brutes, classes, tendance, score/grade et détail de confluence ;
- poids configurés/effectifs, disponibilités et trace complète des filtres ;
- divergences avec pivot, confirmation et paramètres ;
- métriques de qualité des données.

Les outcomes conservent entrée/sortie, brut/net, frais/slippage, MFE, MAE,
extrêmes, nombre de barres disponibles, validité et motif de censure. Ce ne sont
pas des trades de portefeuille : aucune taille, equity ou règle de chevauchement
n'est simulée.

La configuration optionnelle `portfolio_simulation.version=1` est distincte des
hypothèses d'outcomes. Elle exige un symbole, `replay_mode="every_bar"` et un
`quote_asset` explicite. Le moteur consomme les observations et bougies déjà
constituées, exécute à l'ouverture suivante et clôture la position au dernier
close. Aucun outcome n'est une entrée du portefeuille.

## Statistiques et artefacts

Le résumé expose effectif, moyenne, médiane, dispersion, extrema, quantiles,
taux positif/négatif/nul, MFE/MAE, ratio MFE/MAE, couverture et censures. Les
segments couvrent symbole, timeframe, année, mois, grade, classes techniques,
zones RSI/confluence, facteurs disponibles et décision acceptée/rejetée.

Pearson et Spearman utilisent les paires réellement disponibles, sans imputation.
Les ablations individuelles et groupées, le funnel, les segments, corrélations,
divergences et résumés sont persistés comme artefacts séparés.

## Checkpoints et reprise

La migration 7 ajoute des checkpoints versionnés. Le curseur contient symbole,
index de décision, compteurs, dernier état, version d'algorithme et dataset. Les
insertions observation/outcome sont idempotentes. Au redémarrage, un job actif
devient `interrupted`, et `POST /api/backtests/{id}/resume` reprend au dernier
checkpoint. Un test interrompt réellement un replay, le reprend et vérifie
l'absence de doublons. La simulation Phase 6.3 est reconstruite à la fin depuis
les observations finales; le checkpoint v1 ajoute son fingerprint uniquement
pour les jobs portefeuille.

## API et interface

```text
POST /api/backtests
GET  /api/backtests
GET  /api/backtests/capabilities
GET|DELETE /api/backtests/{job_id}
POST /api/backtests/{job_id}/resume
GET  /api/backtests/{job_id}/summary
GET  /api/backtests/{job_id}/observations
GET  /api/backtests/{job_id}/outcomes
GET  /api/backtests/{job_id}/segments
GET  /api/backtests/{job_id}/funnel
GET  /api/backtests/{job_id}/correlations
GET  /api/backtests/{job_id}/ablations
GET  /api/backtests/{job_id}/divergences
GET  /api/backtests/{job_id}/exports
GET  /api/backtests/{job_id}/portfolio
GET  /api/backtests/{job_id}/trades
GET  /api/backtests/{job_id}/equity
GET  /api/backtests/{job_id}/trades/export.csv
GET  /api/backtests/{job_id}/equity/export.csv
WS   /api/backtests/{job_id}/ws
```

Les pages de portefeuille lisent SQLite par séquence. L'equity propose un mode
échantillonné déterministe qui ne fabrique aucun point. Les exports v1 sont lus
par lots. Depuis la Phase 6.5, l'interface React consomme ces routes uniquement
pour les jobs ayant demandé une simulation.

L'interface restaure l'historique persistant, rouvre les résultats et propose la
reprise d'un job interrompu. Les tableaux de recherche et exports sont présents.
La page n'implémente pas encore de graphiques statistiques avancés. Elle pagine
les observations par 50 et permet d'ouvrir leurs signaux structurés ; les APIs
paginées et filtrées restent disponibles pour les autres analyses.

## Oracle synthétique

`tests/fixtures/synthetic_backtest_v1.py` et
`synthetic_backtest_v1_golden.json` verrouillent désormais une observation
complète et ses outcomes chiffrés à 1/3/6 bougies. Toute modification
intentionnelle de l'algorithme exige une nouvelle version de fixture et une
justification.

## Observations Phase 8.2

Le replay peut persister ATR/NATR, ADX/DMI et Supertrend dans
`indicator_signals`. Les calculs utilisent uniquement l'information close
disponible au temps de décision et les mêmes fonctions que le marché. Les
fingerprints historiques restent identiques quand les trois blocs optionnels
sont absents ; une configuration qui les déclare est, elle, fingerprintée.

Ces features n'affectent ni `accepted`, ni le funnel, ni les outcomes futurs, ni
les étapes d'exécution ou les résultats du portefeuille. Aucune baseline Phase
7 n'a été recalculée ou modifiée.

## Observations Phase 8.3

Le replay persiste aussi les composants Bollinger enrichis et, lorsqu'ils sont
activés, Donchian et Keltner. Donchian compare `close_t` aux extrema des
`period` bougies terminées à `t-1`. Keltner compare `close_t` aux bandes
EMA/ATR de `t-1`. Les égalités Donchian ne cassent pas le canal et les sorties
Keltner persistantes ne répètent pas l'événement.

Les fingerprints historiques restent inchangés lorsque les blocs optionnels
Donchian/Keltner sont absents. Toute présence ou modification de leur
configuration est fingerprintée. Ces observations ne sont lues par aucun
filtre, outcome, ordre, exécution, trade ou calcul d'equity.

## Observations Phase 8.4

Le replay peut persister le volume relatif, le CMF et les features OBV dans
`indicator_signals`. Le volume relatif compare la bougie courante à la moyenne
causale des volumes précédents; le CMF est borné et traite une somme de volume
nulle comme une observation neutre; la pente OBV est normalisée par le volume
local pour éviter de comparer les niveaux cumulatifs entre symboles.

Les blocs volume sont absents ou désactivés par défaut. Leurs fingerprints sont
exclus lorsqu'ils sont absents, puis inclus lorsqu'ils sont déclarés. Ces
observations ne sont lues par aucun filtre, outcome, ordre, exécution, trade ou
calcul d'equity. VWAP reste hors de la Phase 8.4 implémentée.
