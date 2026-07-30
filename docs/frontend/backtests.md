# Interface des backtests

> La future interface de simulation est conçue dans
> [`../BACKTEST_PORTFOLIO_SIMULATION_DESIGN.md`](../BACKTEST_PORTFOLIO_SIMULATION_DESIGN.md).
> **Le backend peut désormais produire un résumé optionnel de simulation de
> portefeuille.** L'interface ne configure ni n'affiche encore ce résumé.
> Aucune section de trades ou courbe d'equity n'existe dans l'application.

## Nature du module

Le socle historique reste un replay causal de signaux. Lorsque le nouveau bloc
backend est absent, il ne gère ni capital, taille, ordres, trades ou equity.
Lorsque le bloc est présent, le backend exécute une simulation long-only
distincte et joint seulement son résumé au job. Chaque `SignalObservation`
continue de décrire l'information disponible à la clôture d'une bougie et si le
candidat a passé les filtres.

Les outcomes sont un dataset séparé relié par `observation_id`. Ils mesurent des
rendements forward à plusieurs horizons. Cette relation n'est pas une relation
vers un trade et l'interface n'effectue aucun rapprochement heuristique.

## Prix et causalité

`close` est la clôture observée au temps de décision. Avec `signal_close`, elle
sert aussi de prix d'entrée théorique aux outcomes. Avec `next_open`, le prix
d'entrée théorique est l'ouverture suivante et n'appartient pas à l'observation.
La sortie théorique est la clôture à l'horizon demandé. Frais et slippage en bps
sont appliqués aux deux côtés pour calculer `net_return`; aucun capital n'est mis
à jour.

Le moteur coupe la fenêtre primaire à la bougie de décision et les timeframes
supérieurs à `close_time <= decision_time`. Les outcomes ne sont calculés qu'après
l'observation. Le mode provisional est refusé faute d'historique intrabar
versionné. L'interface explique donc que les signaux confirmed ne voient aucune
bougie future.

## Observations et pagination

`BacktestObservationsTable` utilise la pagination backend par lots de 50. Le store
conserve `observations`, `observationsTotal`, `observationsOffset`, les états de
chargement/erreur et l'action de changement de page. Une erreur de page ne retire
ni le job ni ses métriques globales. L'ordre renvoyé par le backend est conservé.

Chaque ligne contient un résumé compact puis ouvre localement un `Sheet`; cette
ouverture ne charge aucune donnée. Le détail affiche :

- décision « Signal accepté » ou « Signal rejeté » ;
- date, symbole, timeframe et clôture observée ;
- rejet et motif lorsqu'ils existent ;
- score, grade, facteurs, poids et contributions de confluence reçus ;
- `IndicatorSignalsPanel` dans l'ordre canonique ;
- explications causalité, prix d'outcome et absence de simulation de trades.

Un champ `indicator_signals` absent désigne un ancien résultat, `{}` un résultat
moderne sans signal produit, et un dictionnaire partiel n'affiche que ses clés.
Les statuts indisponibles sont transmis sans transformation.

## Performance et exports

Les cartes globales, horizons, funnel, corrélations et ablations restent séparés
des observations techniques. Une intensité n'est jamais présentée comme un taux
de réussite. Le CSV `observations` conserve `indicator_signals` sous forme JSON ;
le navigateur utilise l'URL existante et ne parse pas le fichier.

## Responsive et accessibilité

La table conserve un scroll horizontal sur petit écran. Le `Sheet` occupe toute la
largeur sur mobile et devient un panneau latéral large sur desktop. Radix gère
Échap, piège de focus et retour au bouton. Décisions, statuts, gains ou pertes ne
reposent jamais uniquement sur une couleur. Les raisons longues restent dans le
DOM et la pagination possède un `nav` nommé.

L'inventaire des champs persistés, de l'export observations et des conditions de
dépréciation est dans l'[audit transversal](structured-signals-migration-audit.md).

La Phase 6.4 devra fournir les endpoints paginés de trades/equity et leurs
exports. Aucune donnée détaillée n'est actuellement consultable depuis
l'interface.
