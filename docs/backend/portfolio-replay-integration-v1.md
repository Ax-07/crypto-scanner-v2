# Intégration replay–portefeuille v1

## Périmètre de la Phase 6.3

La Phase 6.3 relie le moteur pur de la Phase 6.2 au replay de backtest. Elle
ajoute une configuration publique optionnelle, un fingerprint déterministe, un
résumé public et un résultat détaillé conservé en mémoire. Elle ne crée ni
endpoint de détail, ni export, ni persistance SQLite des ordres, trades ou
points d'equity, ni interface frontend.

Le principe de compatibilité est strict :

```text
portfolio_simulation absent
→ replay, outcomes, statistiques, checkpoints et JSON historiques inchangés
→ moteur de portefeuille non appelé
```

## Configuration publique

```json
{
  "portfolio_simulation": {
    "version": 1,
    "quote_asset": "USDC",
    "initial_capital": "10000",
    "position_sizing": {
      "mode": "percent_cash",
      "value": "100"
    },
    "execution_policy": "next_open",
    "fee_rate": "0.001",
    "slippage_rate": "0",
    "end_of_test_policy": "force_close"
  }
}
```

Le bloc absent désactive la simulation. Aucun champ `enabled` n'est ajouté :
un bloc présent mais désactivé aurait deux représentations du même état et
compliquerait inutilement les fingerprints.

Valeurs par défaut : version 1, capital 10 000, sizing `percent_cash` à 100 %,
exécution `next_open`, frais 0,1 %, slippage nul et clôture forcée.

Les objets `PortfolioSimulationConfigV1` et
`PortfolioPositionSizingConfig` interdisent les clés inconnues. Les décimaux
doivent être finis; capital et sizing sont strictement positifs; sizing au plus
100; frais et slippage dans `[0, 1[`. Les versions, modes et politiques inconnus
sont rejetés par Pydantic.

## Décimaux publics et fingerprint

Les décimaux publics du nouveau contrat sont des chaînes JSON canoniques :

```text
Decimal("100.00") → "100"
Decimal("0.0010") → "0.001"
Decimal("-0") → "0"
```

Cette convention évite les pertes de précision binaires et les exposants
variables. Le moteur conserve ses `Decimal`. Le fingerprint reprend exactement
le payload historique du profil quand le bloc est absent. Quand il est présent,
le sous-objet canonique `portfolio_simulation` est ajouté avant le
`json.dumps(sort_keys=True, separators=(",", ":"))` et SHA-256. Les
représentations numériques équivalentes ont donc le même fingerprint; toute
différence de valeur, de devise ou de politique le modifie.

Le fingerprint étendu est exposé sur les nouveaux jobs configurés et copié dans
leurs checkpoints. Le champ est omis des payloads historiques.

## Quote asset, symbole et timeframe

`quote_asset` est obligatoire et normalisé en majuscules, comme les symboles du
backtest. Le contrat v1 exige exactement un symbole. Pour un symbole clairement
formé comme `BASE/QUOTE`, la partie après le dernier `/` doit être exactement
égale au quote asset normalisé. Un symbole non standard reste accepté avec sa
devise explicite : le backend ne tente pas de l'inventer.

Le timeframe primaire est `BacktestConfig.signal_config.timeframe`. Sa durée
vient exclusivement de `app.domain.candles.timeframe_milliseconds`; les
timeframes de tendance ne participent jamais à l'exécution.

## Adaptateurs purs

`to_internal_portfolio_config` copie chaque champ validé vers
`PortfolioSimulationConfig` et convertit les littéraux publics vers les enums du
domaine. Il ne lit ni environnement, ni base, ni valeur historique de frais.

`build_portfolio_simulation_steps` consomme seulement les observations déjà
persistées et les bougies primaires déjà chargées. La clé exacte est :

```text
SignalObservation.source_open_time
== datetime UTC de Candle.open_time
```

La correspondance doit être unique. `decision_time` doit ensuite être
exactement égal au `close_time` de cette bougie, ou à `open_time + durée` si le
champ de clôture est absent. L'adaptateur copie l'ID d'observation, `accepted`,
l'open et le close de la bougie. Il refuse timestamp naïf, ID ou timestamp
dupliqué, ordre non strict, symbole/timeframe divergent, bougie absente,
prix non positif/non fini et incohérence de clôture. Il ne trie rien.

Le replay `every_bar` crée et conserve une observation pour chaque bougie
évaluée. `state_changes` et `filtered_signals` n'en conservent qu'une sélection.
Comme l'absence d'observation ne signifie pas `accepted=false`, la v1 exige
`replay_mode="every_bar"` lorsque la simulation est configurée.

## Continuité et gaps

Chaque paire d'étapes consécutives doit satisfaire :

```text
next.source_open_time - current.source_open_time
== durée exacte du timeframe primaire
```

Tout gap invalide la simulation demandée avec
`portfolio_time_gap`, indépendamment de la politique historique des outcomes.
Un ordre `next_open` n'est donc jamais transporté jusqu'à une ouverture
distante. Aucune bougie artificielle n'est ajoutée. Une intention sur la dernière
observation est rejetée `end_of_data` par le moteur; une position restante est
ensuite liquidée `end_of_test`.

## Ordre d'exécution et absence de recalcul

Le point d'intégration est `BacktestEngine.run`, après la lecture finale des
observations et outcomes et après le calcul analytique, mais avant la
publication du résumé :

```text
OHLCV chargés une fois
→ replay causal et observations
→ outcomes indépendants
→ analytics historiques
→ adaptation observations + bougies déjà en mémoire
→ simulate_portfolio
→ résumé public et artefacts historiques
```

Il n'existe aucun paramètre `outcomes` dans l'adaptateur ou le moteur. Aucun
`ForwardOutcome`, prix futur, MFE ou MAE n'est lu. La simulation ne rappelle ni
indicateur, ni confluence, ni filtre, ni générateur d'observation. Les tests
comparent les compteurs `before`/`range` avec et sans portefeuille : aucun accès
OHLCV supplémentaire n'est créé.

## Résultat public et stockage interne

Le bloc public, sous `BacktestSummary.portfolio_simulation`, contient seulement :

```json
{
  "version": 1,
  "quote_asset": "USDC",
  "summary": {
    "version": 1,
    "quote_asset": "USDC",
    "initial_capital": "10000",
    "final_cash": "10350.25",
    "final_equity": "10350.25",
    "net_profit": "350.25",
    "total_return_ratio": "0.035025",
    "realized_pnl": "350.25",
    "unrealized_pnl": "0",
    "total_fees": "20.1",
    "trade_count": 2,
    "winning_trade_count": 1,
    "losing_trade_count": 1,
    "breakeven_trade_count": 0,
    "win_rate": "0.5",
    "average_trade_return": "0.018",
    "max_drawdown_ratio": "0.012",
    "exposure_ratio": "0.75",
    "open_position_count": 0
  },
  "has_trades": true,
  "has_equity_curve": true
}
```

`to_public_portfolio_summary` reprend directement `PortfolioMetrics`; aucune
métrique n'est recalculée. Le drawdown reste positif. `win_rate` et
`average_trade_return` restent `null` sans trade. Avec `force_close`,
`open_position_count` vaut normalement zéro.

Depuis la Phase 6.4, le `PortfolioSimulationResult` complet — ordres,
exécutions, trades, equity, métriques et éventuelle position — est persisté
atomiquement avant le résumé public. L'attribut privé du `BacktestJob` est
ensuite remis à `None`. Un redémarrage conserve le résumé et permet de relire
les pages et exports depuis SQLite. Voir
[`portfolio-persistence-api-v1.md`](portfolio-persistence-api-v1.md).

## Checkpoints, reprise et annulation

La stratégie retenue est la simulation finale : le checkpoint historique reste
un curseur du replay. La configuration complète est déjà figée dans
`backtest_jobs.config_json`; les nouveaux checkpoints ajoutent seulement
`config_fingerprint`. Un ancien checkpoint sans ce champ reste lisible et la
version de schéma demeure 1.

À la reprise, les insertions d'observations/outcomes restent idempotentes, puis
le portefeuille est reconstruit depuis toutes les observations finales. Les
compteurs locaux du moteur reproduisent les IDs d'ordres, exécutions, positions
et trades. Une reconstruction depuis un checkpoint terminé produit exactement
le même résultat.

Une annulation efface le détail interne et retire tout aperçu portefeuille qui
aurait été construit avant un `await` ultérieur. Aucun résultat partiel n'est
présenté comme final. Aucun nouveau statut public n'est ajouté.

## Échecs et codes

Une simulation demandée mais causalement impossible fait échouer le job. Le
champ `error` reçoit un code stable suivi d'un message, sans stack trace; la
trace technique reste dans les logs. Codes principaux :

- `portfolio_symbol_mismatch`;
- `portfolio_timeframe_mismatch`;
- `portfolio_missing_primary_candle`;
- `portfolio_duplicate_primary_candle`;
- `portfolio_duplicate_observation`;
- `portfolio_invalid_timestamp`;
- `portfolio_incoherent_decision_time`;
- `portfolio_invalid_step_order`;
- `portfolio_time_gap`;
- `portfolio_invalid_price`.

Le replay reste disponible en relançant la même configuration sans le bloc.

## Compatibilité historique

Le repository omet `portfolio_simulation` dans `config_json` lorsqu'il est
absent. Les payloads du job et du résumé omettent également les nouveaux champs
absents. Les valeurs par défaut historiques, outcomes, statistiques, exports,
pagination et tri ne changent pas. `trade_simulation_included` reste `false`
sans simulation et devient `true` uniquement après une simulation réussie.

## Coût mémoire et limites

Le moteur est O(n + k) et conserve O(n) points d'equity plus O(k) événements.
Un point Python avec ses huit `Decimal`, son datetime et ses références occupe
grossièrement 0,7 à 1,2 Kio en mémoire réelle. Un an de bougies 1 minute
(525 600 points) représente donc un ordre de grandeur de 0,35 à 0,65 Gio par
job, hors observations et trades. Cette estimation justifie la pagination,
l'échantillonnage et/ou la persistance de la Phase 6.4; aucune limite arbitraire
n'est ajoutée ici.

Restent reportés : frontend, endpoints publics ordres/exécutions, filtre
temporel d'equity, multi-actifs, short, levier, pyramiding, stops, take profits
et résultats partiels publics.
