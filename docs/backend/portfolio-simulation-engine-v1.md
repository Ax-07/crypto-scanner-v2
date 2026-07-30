# Moteur pur de simulation de portefeuille v1

## Périmètre de la Phase 6.2

La Phase 6.2 implémente les modèles internes et le moteur de domaine sous
`backend/app/domain/portfolio/`. Le moteur est testé en mémoire et ne dépend ni
de FastAPI, SQLite, CCXT, pandas, HTTP, du replay, de `SignalObservation` ou de
`ForwardOutcome`.

Il n'est pas encore intégré aux jobs de backtest, à l'API, aux modèles Pydantic,
aux exports ou au frontend. Ces adaptations appartiennent à la Phase 6.3.

## Architecture

```text
portfolio/
├── decimal_utils.py  conversions, précision, erreurs et tolérance de cash
├── types.py          enums, configuration et résultats immuables
├── strategy.py       accepted_state_transition_v1
├── sizing.py         percent_cash
├── execution.py      fills d'achat et de vente
├── accounting.py     position, trade et valorisation
├── metrics.py        drawdown et métriques
└── simulation.py     état de travail et boucle événementielle
```

L'API interne principale est :

```python
result = simulate_portfolio(
    symbol="BTC/USDC",
    steps=steps,
    config=PortfolioSimulationConfig(
        quote_asset="USDC",
        initial_capital=Decimal("10000"),
    ),
)
```

Chaque `PortfolioSimulationStep` contient un `observation_id`, l'ouverture de la
bougie, son instant de décision à la clôture, ses prix open/close et le booléen
`accepted`. Les étapes sont déjà triées, ont des timestamps timezone-aware
strictement croissants, des IDs uniques et des prix finis strictement positifs.
Le moteur ne recalcule aucun signal et ne trie rien silencieusement.

## Configuration v1

`PortfolioSimulationConfig` est une dataclass gelée avec `slots=True` :

- `version=1`;
- `quote_asset`, fourni explicitement et non vide;
- `initial_capital=10000`, fini et strictement positif;
- `position_sizing_mode=percent_cash`;
- `position_size_percent=100`, dans `]0, 100]`;
- `execution_policy=next_open`;
- `fee_rate=0.001`, dans `[0, 1[`;
- `slippage_rate=0`, dans `[0, 1[`;
- `end_of_test_policy=force_close`.

Une version, un mode ou une politique inconnus et toute valeur vide, non finie
ou hors borne lèvent une `PortfolioValidationError`. Les erreurs de calcul et
d'invariant sont respectivement `PortfolioExecutionError` et
`PortfolioInvariantError`.

## Convention Decimal

Cash, allocation, notionnel, frais, quantité, prix d'exécution, valeur de
position, P&L, equity, rendements et drawdown utilisent `Decimal`. Les entrées
`int`, `str`, `float` et `Decimal` sont converties par `Decimal(str(value))`;
NaN et infinis sont refusés. Les calculs emploient un contexte local déterministe
de 28 chiffres significatifs.

Aucun tick size, step size, minimum notionnel ou arrondi exchange n'est inventé.
Les quantités sont fractionnaires. Une dérive de cash négative est ramenée à
zéro uniquement si sa valeur absolue est au plus `1e-12`; une dérive supérieure
viole un invariant.

## Stratégie et ordre causal

`evaluate_accepted_state_transition` isole
`accepted_state_transition_v1` :

```text
flat, false → true  : enter_long
flat, autres cas    : hold
long, true → false  : exit_long
long, autres cas    : hold
ordre déjà pending  : hold
```

L'état initial est `previous_accepted=false`. Une acceptation répétée ne
renforce jamais une position et un rejet à plat ne vend rien. La stratégie ne
calcule ni prix, frais ou quantité. Le moteur valide séparément la faisabilité
opérationnelle.

Pour chaque étape `t`, la boucle exécute exactement :

1. l'ordre créé à la clôture précédente au `source_open_time` de `t`;
2. la décision déjà calculée à la clôture de `t`;
3. la création éventuelle d'un ordre pour l'ouverture suivante;
4. la valorisation au `close` de `t` et l'enregistrement de l'equity.

Le fill d'ouverture est donc calculé avant de lire `accepted` à la clôture de la
même bougie. Changer ce close peut changer l'equity et la prochaine intention,
mais jamais le prix du fill déjà exécuté à son open.

## Sizing, frais et slippage

Le seul sizing est :

```text
requested_cash = available_cash × position_size_percent / 100
allocated_cash = min(requested_cash, available_cash)
```

Entrée longue :

```text
execution_price = reference_open × (1 + slippage_rate)
entry_notional = allocated_cash / (1 + fee_rate)
entry_fee = entry_notional × fee_rate
quantity = entry_notional / execution_price
cash_after = cash_before - entry_notional - entry_fee
```

Sortie longue :

```text
execution_price = reference_price × (1 - slippage_rate)
gross_exit_proceeds = quantity × execution_price
exit_fee = gross_exit_proceeds × fee_rate
net_exit_proceeds = gross_exit_proceeds - exit_fee
cash_after = cash_before + net_exit_proceeds
realized_pnl = net_exit_proceeds - total_entry_cost
return_ratio = realized_pnl / total_entry_cost
```

Le slippage est toujours défavorable. Les frais sont payés dans l'actif de
cotation à chaque côté. Avec sizing 100 %, l'allocation d'entrée inclut les
frais et le cash arrive à zéro sans devenir négatif.

## Ordres, exécutions, position et trades

Les IDs sont des compteurs locaux à chaque simulation :
`order-000001`, `execution-000001`, `position-000001` et `trade-000001`.
Ils ne lisent ni heure système, UUID ou compteur global.

Un `SimulatedOrder` garde observation source, côté, instant d'intention,
politique, allocation demandée, statut et rejet éventuel. Un
`SimulatedExecution` garde ordre, timestamp, prix de référence/d'exécution,
quantité, notionnel, frais et slippage.

Une seule `SimulatedPosition` longue peut exister. Elle conserve les références
d'entrée, la quantité, le coût et l'index de bougie. Un `SimulatedTrade` fermé
relie les deux ordres et exécutions, les frais, produits, P&L, rendement, durée
et raison de sortie.

La durée inclut chaque clôture pendant laquelle la position est exposée :
entrée à l'ouverture de `t+1`, sortie à l'ouverture de `t+2` donne une durée de
une bougie. Une sortie forcée au close final inclut cette dernière bougie.

## Equity, P&L latent et drawdown

À chaque clôture primaire :

```text
position_value = quantity × close
unrealized_pnl = position_value - total_entry_cost
equity = cash + position_value
```

Cette valeur est brute au close : elle n'anticipe ni frais ni slippage de sortie.
Le P&L latent ne modifie jamais le cash ou le P&L réalisé.

Le drawdown suit la décision Phase 6.1 et reste positif :

```text
running_peak = max(running_peak, equity)
drawdown_ratio = (running_peak - equity) / running_peak
```

Il vaut zéro au sommet. Après une clôture forcée, le dernier point est recalculé
avec cash final, position nulle et equity finale. L'exposition, elle, compte la
dernière clôture comme exposée si la position y était encore ouverte avant
l'événement administratif.

## Métriques

`PortfolioMetrics` expose capital, cash/equity finaux, profit net, rendement
total, P&L réalisé/latent, frais, nombres de trades gagnants/perdants/nuls, win
rate, rendement moyen, drawdown maximal, exposition et position finale.

```text
net_profit = final_equity - initial_capital
total_return_ratio = net_profit / initial_capital
win_rate = winning_trade_count / trade_count
exposure_ratio = clôtures exposées / clôtures primaires
```

Le dénominateur du win rate contient tous les trades fermés, y compris les
trades nuls. Win rate et rendement moyen valent `None` sans trade; aucune
métrique ne produit NaN.

## Fin de données et rejets

Un ordre `next_open` créé sur la dernière observation est rejeté
`end_of_data`; aucune exécution rétroactive n'est fabriquée. Si cet ordre est
une sortie, il expire puis `force_close` crée un ordre administratif distinct,
exécuté au dernier close avec frais et slippage, un trade `end_of_test` et sans
`exit_observation_id`.

Les raisons prévues sont `insufficient_cash`, `invalid_reference_price`,
`invalid_execution_price`, `missing_execution_candle`,
`position_already_open`, `no_open_position`,
`entry_order_already_pending`, `exit_order_already_pending`,
`below_internal_minimum`, `end_of_data` et `invalid_quantity`. Elles sont
distinctes des rejets de filtres scanner.

## Invariants et garanties

Après chaque étape :

- cash et frais sont finis et non négatifs;
- zéro ou une position et zéro ou un ordre pending existent;
- quantité et coût d'une position sont strictement positifs;
- chaque exécution référence un ordre et aucun ordre n'est exécuté deux fois;
- chaque trade possède une entrée et une sortie;
- frais cumulés et P&L réalisé correspondent aux exécutions et trades;
- une simulation répétée donne exactement les mêmes objets et IDs.

Les tests transforment en oracles les scénarios sans frais, avec frais 1 %, avec
slippage 1 %, perdant, deux trades composés et clôture forcée. Ils couvrent aussi
les transitions, validations décimales, timestamps, ordre causal, dernier ordre,
métriques, reproductibilité et imports interdits.

Exécution ciblée depuis `backend/` :

```powershell
.\venv\Scripts\python.exe -m pytest tests\domain\portfolio -q
```

## Limites et Phase 6.3

Le MVP ne simule pas multi-symbole, short, levier, pyramiding, sortie partielle,
stop, take profit, trailing stop, minimum ou précision exchange. Il ne détecte
pas encore les gaps temporels à partir d'un timeframe : l'adaptateur Phase 6.3
devra fournir une suite contiguë ou une information explicite.

La Phase 6.3 devra adapter observation et bougie primaire vers
`PortfolioSimulationStep`, ajouter une configuration publique optionnelle et un
résumé additif, préserver les fingerprints/replays historiques et définir la
persistance/checkpoint. Elle ne devra jamais alimenter la stratégie avec un
`ForwardOutcome`.
