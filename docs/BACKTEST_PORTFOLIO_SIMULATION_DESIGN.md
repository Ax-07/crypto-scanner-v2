# Simulation de portefeuille du backtest — conception Phase 6.1

Statut : **Phase 6.3 intégrée**, conception initiale auditée au commit `e61835b`.

La Phase 6.2 implémente le moteur de domaine pur sous
`backend/app/domain/portfolio/`. La Phase 6.3 le relie désormais aux jobs et à
un résumé public additif; les détails restent en mémoire et le frontend n'est
pas intégré. Voir [`backend/portfolio-simulation-engine-v1.md`](backend/portfolio-simulation-engine-v1.md)
et [`backend/portfolio-replay-integration-v1.md`](backend/portfolio-replay-integration-v1.md).

## 1. Résumé exécutif

Le backtest actuel est un replay causal d'observations techniques. Pour chaque
bougie de décision conservée, il produit une `SignalObservation`, puis plusieurs
`ForwardOutcome` indépendants. Il ne possède ni ordre, exécution, position,
trade, cash, P&L séquentiel, equity ou drawdown.

Le MVP recommandé ajoute, de manière optionnelle et versionnée, un simulateur
mono-symbole spot, long-only, sans levier, avec une position au maximum. Une
stratégie dédiée transforme les observations en `enter_long`, `exit_long` ou
`hold`; elle ne confond pas `accepted` avec acheter ni `rejected` avec vendre.
L'exécution par défaut est l'ouverture suivante, la taille est un pourcentage du
cash disponible, frais inclus dans l'allocation, et la position est forcée à la
clôture de la dernière bougie. Le replay et ses outcomes restent inchangés.

## 2. État actuel vérifié

### 2.1 Flux réel

```text
SQLite OHLCV fermé
  → BacktestEngine._load_primary / _load_trends
  → fenêtre primaire terminant à la bougie t
  → timeframes supérieurs filtrés sur close_time <= decision_time
  → evaluate_signal_snapshot
  → evaluate_information_set
  → indicateurs + IndicatorSignal + tendance multi-TF + confluence
  → filtres RSI → tendance → classes structurées/legacy → confluence
  → SignalObservation accepted/rejected
  → sélection every_bar/state_changes/filtered_signals
  → calculate_forward_outcomes, un calcul indépendant par horizon
  → persistance SQLite des observations/outcomes
  → build_analytics et artefacts statistiques
```

| Étape | Responsable | Entrées → sorties | Temps et causalité |
|---|---|---|---|
| Chargement | `BacktestEngine._load_primary` | bougies avant plage + plage + marge future → `LoadedSeries` | lecture locale, `closed_only=True`; la marge future sert uniquement aux outcomes |
| Décision | `BacktestEngine.run` | index `t` → `decision_ms` à la clôture | primaire `[..., t]`; aucune bougie `t+1` |
| Multi-TF | `_load_trends`, puis filtre dans `run` | historiques supérieurs → fenêtres éligibles | uniquement `close_time <= decision_ms` |
| Évaluation | `evaluate_signal_snapshot` → `evaluate_information_set` | fenêtres, profil → `SignalObservation` | rejette explicitement tout élément daté après la décision |
| Indicateurs | fonctions de `app.domain.indicators` et `build_indicator_signals` | OHLC clos → valeurs/classes/signaux | calculs sur l'information disponible au plus tard à `t` |
| Décision de filtre | fin de `evaluate_information_set` | RSI, tendance, signaux, confluence → trace + booléen | `accepted` si les quatre étages passent |
| Conservation | `BacktestEngine.run` | observation → persistée ou non | dépend de `replay_mode`, pas d'un ordre |
| Outcomes | `calculate_forward_outcomes` | observation, bougies futures, horizons → `ForwardOutcome[]` | exécuté après la décision; données futures limitées à la mesure |
| Statistiques | `build_analytics` | observations + outcomes → résumé/segments/corrélations/ablations | analyse a posteriori, sans influencer les décisions |

Les modèles publics réels sont `BacktestConfig`, `BacktestJob`,
`BacktestSummary`, `SignalObservation` et `ForwardOutcome`. `BacktestResult`
n'existe pas. Depuis la Phase 6.3,
`BacktestSummary.trade_simulation_included` vaut `true` seulement après une
simulation réussie, et `GET /api/backtests/capabilities` annonce
`trade_simulation: true`.

### 2.2 Ce que calcule un outcome

Pour un horizon `h`, `calculate_forward_outcomes` choisit un prix d'entrée
théorique, puis la clôture `h` bougies après l'index d'entrée. Il calcule
rendements brut/net, MFE, MAE, extrêmes et couverture. Les frais et le slippage
existants sont des hypothèses de rendement, sans quantité ni débit de cash.
Chaque observation et chaque horizon sont indépendants : des fenêtres peuvent
se chevaucher sans contrainte.

```text
ForwardOutcome ≠ intention d'ordre
ForwardOutcome ≠ ordre simulé
ForwardOutcome ≠ exécution simulée
ForwardOutcome ≠ position
ForwardOutcome ≠ trade
```

### 2.3 Limites du replay actuel

- pas de capital initial ou de devise de compte;
- pas de taille, quantité, cash disponible ou capital engagé;
- pas de règle d'exclusivité ou de chevauchement;
- pas de stratégie native `enter/exit/hold`;
- pas de réalisation séquentielle des gains et pertes;
- pas de position finale, equity curve, drawdown ou métriques de portefeuille;
- frais/slippage appliqués à des ratios, non à des exécutions comptables;
- page frontend orientée observations/outcomes, non portefeuille.

## 3. Chronologie exacte

Pour une bougie primaire `t` :

```text
ouverture t
  → évolution OHLCV t (inconnue tant que la bougie est ouverte)
  → clôture t = decision_time
  → indicateurs avec bougies closes <= t
  → observation et filtres à decision_time
  → outcome signal_close : entrée théorique à close(t)
  → outcome next_open : entrée théorique à open(t+1)
  → sortie d'outcome à close(entry_index + horizon)
```

`source_open_time` est l'ouverture de `t`; `decision_time` est sa fermeture;
`close` et `source_ohlcv` décrivent `t`. Ces trois notions ne doivent pas être
fusionnées.

### 3.1 `signal_close`

La décision utilise le high, low, close et volume définitifs de `t`; elle n'est
donc connue qu'à la clôture. Exécuter exactement à cette même clôture suppose
un calcul et un remplissage instantanés au prix officiel de clôture, sans
latence ni mouvement : hypothèse optimiste et généralement non tradable. Cette
politique reste utile comme scénario de recherche et pour préserver les
outcomes historiques, mais n'est pas le défaut du portefeuille.

Une stratégie calculée avant la clôture avec des données intrabar versionnées
pourrait rendre cette hypothèse défendable; ces données n'existent pas ici.
Employer le OHLC final tout en supposant une décision antérieure serait un
look-ahead intrabougie.

### 3.2 `next_open`

L'entrée utilise strictement `candles[decision_index + 1].open`. La bougie
suivante est actuellement la ligne suivante de la série. Si elle manque ou si
la sortie manque, l'outcome est censuré `fin_de_serie`. Si un intervalle attendu
manque, la politique de gap peut rejeter toute la plage, ignorer/censurer la
fenêtre affectée, ou autoriser avec avertissement. Pour le portefeuille, une
ligne suivante séparée par un trou ne doit pas être considérée comme « prochaine
ouverture » : l'ordre doit expirer avec `gap_before_execution`.

## 4. Vocabulaire métier

- **Observation** : état du marché, des données et des indicateurs à un instant
  historique.
- **Signal technique** : sortie structurée d'un indicateur; ce n'est pas une
  recommandation transactionnelle.
- **Décision de filtrage** : acceptation ou rejet selon les règles du scanner.
- **Décision de stratégie** : transformation causale en `enter_long`,
  `exit_long` ou `hold`.
- **Intention d'ordre** : action souhaitée, avant validation de portefeuille.
- **Ordre simulé** : objet horodaté avec côté, quantité/notionnel demandé,
  politique et observation source.
- **Exécution simulée** : remplissage d'un ordre à un prix avec slippage et
  frais.
- **Position** : quantité encore exposée avec son coût d'entrée.
- **Trade** : cycle économique réalisé entre entrée et sortie.
- **Portefeuille** : cash, position, valeur totale et historique.
- **Point d'equity** : valorisation du portefeuille à un instant.
- **Outcome** : mesure future indépendante produite par le replay actuel.

Un rejet signifie seulement « filtres non satisfaits ». Il ne signifie ni
`exit_long`, ni `sell`, ni signal opposé.

## 5. Périmètre recommandé du MVP

| Décision | Recommandation | Justification |
|---|---|---|
| Marché | spot, long-only | la confluence actuelle est orientée long et n'a pas de miroir short |
| Symboles | exactement un | évite allocation concurrente et synchronisation multi-timeframes |
| Positions | zéro ou une | rend sizing, cash et causalité inspectables |
| Levier/short/marge | interdits | aucune donnée de financement, liquidation ou marge |
| Entrées | une exécution, pas de pyramiding | pas de coût moyen ni lots partiels |
| Cotation | capital dans l'actif de cotation | aucune conversion monétaire inventée |
| Sizing | `percent_cash`, 100 % par défaut | simple, composé et sans cash négatif si frais inclus |
| Exécution | `next_open` | sépare décision et remplissage |
| Fin | `force_close` par défaut | résultat réalisé comparable et déterministe |
| Equity | une fois par bougie primaire close | courbe complète en O(n) |

L'actuel `BacktestConfig.symbols` accepte jusqu'à 500 symboles. La validation du
bloc portefeuille doit exiger `len(symbols) == 1` lorsqu'il est activé, sans
restreindre le replay historique.

## 6. Source de la décision d'entrée

| Option | Avantages | Inconvénients et données nécessaires |
|---|---|---|
| A. Toute observation acceptée | minimale, compatible avec `filtered_signals` | confond filtre et ordre; répétitions; aucun exit |
| B. Acceptée + direction globale | réduit les faux sens | « direction globale » n'existe pas comme contrat; tendance et confluence diffèrent |
| C. Stratégie dédiée | vocabulaire correct, extensible, testable | nouveau composant pur et versionné |
| D. Filtres comme entrée seule | réutilise l'existant sans changer ses règles | résout l'entrée, pas la sortie; risque de mauvaise terminologie |

**Décision : option C**, avec une stratégie MVP explicite
`accepted_state_transition_v1`. Elle utilise la décision de filtrage comme une
condition, mais produit son propre résultat :

```text
flat + accepted                  → enter_long
flat + rejected                  → hold
long + accepted                  → hold
long + première observation rejetée après l'entrée → exit_long(reason=validation_lost)
```

Ainsi `accepted` n'est pas universellement « acheter » : il n'ouvre que lorsque
la stratégie est à plat. `rejected` n'est pas universellement « vendre » : la
stratégie versionnée peut l'interpréter comme perte de validation uniquement
si une position existe. Le moteur doit aussi enregistrer la décision de
stratégie et sa raison.

## 7. Stratégies de sortie et priorité

| Politique | Données / intrabougie | MVP |
|---|---|---|
| Signal opposé | nécessite un signal opposé contractuel absent | reporté |
| Perte de validation | observation courante; exécution suivante | oui |
| Stop loss | high/low après activation; ordre intrabougie ambigu | option ultérieure |
| Take profit | idem | option ultérieure |
| Trailing stop | haut courant, niveau causal avant/après bougie à spécifier | reporté |
| Sortie temporelle | compteur de bougies depuis l'exécution | option simple ultérieure |
| Fin de données | dernière clôture et politique explicite | oui |

Le MVP minimal comprend `validation_lost` et `force_close`. Les stops, take
profits, trailing stops et durée maximale doivent être conçus dans les modèles
mais désactivés tant que leur sémantique OHLC n'est pas implémentée et testée.

Priorité future, évaluée sans réécrire le passé :

1. invalidation technique empêchant de valoriser;
2. stop loss;
3. take profit;
4. sortie de stratégie;
5. durée maximale;
6. fin de période.

Si high et low touchent stop et take profit dans la même bougie OHLC, l'ordre
réel est inconnu. Politiques possibles : pessimiste (stop), optimiste (take),
ordre OHLC supposé, exigence de données plus fines, ou résultat ambigu.
**Décision MVP future : pessimiste**, exécuter le stop et poser
`intrabar_ambiguous=true`. Ne jamais déduire un chemin intrabougie de OHLC.

## 8. Capital, unité et dimensionnement

### 8.1 Capital initial

`initial_capital` est fini, strictement positif, exprimé dans l'actif de
cotation, avec défaut `10000`. Pour `BTC/USDC`, l'unité est USDC; pour
`ETH/EUR`, EUR. Le backend dérive `quote_asset` du symbole canonique contenant
`/`, le stocke dans le résultat et vérifie sa cohérence. Il refuse un symbole
non décomposable au lieu d'inventer une devise.

### 8.2 Politiques comparées

- `fixed_notional`: `requested = value`; simple, mais refuse/ajuste lorsque le
  cash est insuffisant.
- `percent_cash`: `requested = cash × value / 100`; reproductible, composé,
  valeur dans `(0, 100]`.
- `percent_equity`: inclut la valeur d'une position; inutile avec une seule
  entrée sans pyramiding.
- `all_in`: équivaut à 100 % du cash, mais ajoute un mode redondant.
- `risk_per_trade`: `risk_budget / stop_distance`; exige un stop causal et des
  bornes, donc hors MVP.

**Décision : `percent_cash`, défaut 100 %.** `fixed_notional` peut suivre sans
changer le moteur. Une allocation insuffisante ou sous le minimum numérique
produit un ordre rejeté documenté, jamais un cash négatif.

### 8.3 Convention d'entrée, frais inclus

Le montant alloué est le débit cash maximal :

```text
requested_cash = cash_before × percent_cash / 100
allocated_cash = min(requested_cash, cash_before)
entry_reference_price = open de la bougie d'exécution
entry_execution_price = entry_reference_price × (1 + slippage_rate)
entry_notional = allocated_cash / (1 + fee_rate)
entry_fee = entry_notional × fee_rate
quantity = entry_notional / entry_execution_price
cash_after_entry = cash_before - entry_notional - entry_fee
```

Cette convention garantit `cash_after_entry >= 0` à la tolérance numérique.
L'alternative « frais ajoutés » calcule `quantity=requested/price` puis débite
`requested+fee`; elle exige une réserve ou réduit ensuite la quantité. Elle est
écartée car son libellé de taille est moins intuitif et peut rendre le cash
négatif.

### 8.4 Sortie et P&L

```text
exit_execution_price = exit_reference_price × (1 - slippage_rate)
gross_exit_proceeds = quantity × exit_execution_price
exit_fee = gross_exit_proceeds × fee_rate
net_exit_proceeds = gross_exit_proceeds - exit_fee
cash_after_exit = cash_before_exit + net_exit_proceeds

total_entry_cost = entry_notional + entry_fee
gross_pnl = gross_exit_proceeds - entry_notional
realized_pnl = net_exit_proceeds - total_entry_cost
trade_return = realized_pnl / total_entry_cost
```

Les frais sont fictifs, prélevés dans l'actif de cotation sur chaque exécution.
Un taux unique `fee_rate` suffit au MVP; `0 <= rate < 1`. `slippage_rate` est
également fini, `0 <= rate < 1`, défavorable dans les deux sens. Aucun tarif
exchange n'est implicite.

Prix nul/négatif/non fini, quantité nulle, calcul non fini ou résultat sous la
tolérance minimale : ordre non exécuté avec raison structurée. Une bougie
manquante avant exécution expire l'ordre. Aucun remplissage partiel dans le MVP.

## 9. Portefeuille, position et valorisation

```text
cash                 actif de cotation immédiatement disponible
reserved_cash        0 dans le MVP, faute d'ordres persistants
position_market_value = quantity × mark_price
equity               = cash + position_market_value
```

Le montant engagé initial est `total_entry_cost`; il ne doit pas être présenté
comme la valeur de marché courante. Le `mark_price` est la clôture de chaque
bougie primaire. Les événements à l'ouverture sont appliqués avant la
valorisation à la clôture de cette même bougie.

Une position contient quantité, temps/prix de référence et d'exécution,
notionnel, frais, coût total, observation/intention/exécution sources, plus haut
causal depuis l'entrée et nombre de bougies détenues. Un trade fermé copie les
deux exécutions, coûts, produits, P&L, rendement, durée et motif de sortie.

### 9.1 P&L latent

```text
unrealized_pnl = position_market_value - total_entry_cost
portfolio_realized_pnl = somme des realized_pnl
equity = initial_capital + realized_pnl_cumulative + unrealized_pnl
```

Le P&L latent n'inclut pas de frais de sortie hypothétiques; ce choix doit être
affiché. Une variante liquidative pourra être ajoutée plus tard sans remplacer
la valeur comptable.

## 10. Equity, drawdown et métriques

Un point est créé à chaque clôture primaire, après exécutions d'ouverture
éventuelles et après la valorisation. Un point final reflète la clôture forcée.
Champs : timestamp, cash, valeur de position, equity, P&L réalisé/latent, frais
cumulés, exposition et drawdown.

```text
running_peak_t = max(equity_0 ... equity_t)
drawdown_t = 0 si running_peak_t <= 0
             sinon (running_peak_t - equity_t) / running_peak_t
max_drawdown = max(drawdown_t)
```

Le drawdown est un ratio positif (0,12 = recul de 12 %), peak-to-trough sur les
points d'equity. Métriques MVP :

- `total_return = final_equity / initial_capital - 1`;
- `net_pnl = final_equity - initial_capital`;
- `realized_pnl`, `unrealized_pnl`, frais cumulés;
- nombre de trades, gains/pertes/nuls;
- `win_rate = winning_trades / closed_trades`, null si aucun;
- gain moyen, perte moyenne;
- `profit_factor = gross_profit / abs(gross_loss)`, null si aucune perte;
- max drawdown;
- exposition = nombre de points avec position / points valorisables;
- durée moyenne en bougies.

Sharpe, Sortino, annualisation, benchmark et alpha sont reportés : calendriers
et fréquence de rendement doivent d'abord être définis.

## 11. Fin de simulation et position ouverte

Politiques possibles :

- `force_close`: vente à la clôture de la dernière bougie, slippage et frais;
- `mark_to_market`: position conservée et valorisée, résultat séparant réalisé
  et latent;
- `discard`: interdit, car masque une exposition.

**Décision : `force_close` par défaut.** La référence est le dernier close
valide, avec `exit_reason=end_of_test`. C'est un événement administratif connu
à la fin du dataset, non un signal rétroactif. Si ce prix est invalide, la
position reste ouverte, le job termine avec avertissement et
`final_equity_valid=false`; elle n'est jamais supprimée silencieusement.

## 12. Précision numérique

Les OHLC actuels et contrats historiques utilisent `float`; les conserver
évite une rupture. Le nouveau moteur comptable doit convertir les valeurs depuis
leur représentation décimale vers `Decimal`, contexte 28 chiffres, interdire
NaN/infini, et n'arrondir qu'aux frontières de stockage/affichage avec
`ROUND_HALF_EVEN`. Sans métadonnées exchange fiables, il ne doit inventer ni
tick size ni step size. Les nouveaux montants décimaux sont sérialisés comme
chaînes dans les artefacts versionnés; les taux restent des nombres validés.
Tolérance de cash : `1e-12` unité de cotation, ramenée à zéro seulement si sa
valeur absolue est sous ce seuil.

## 13. Contraintes anti-look-ahead

- décisions sur bougies closes `<= decision_time`;
- timeframes supérieurs uniquement si leur propre clôture est passée;
- intention créée après l'observation, exécution `next_open` seulement;
- mutation de `t+1` ne change ni observation ni intention décidée à `t`;
- elle peut changer l'exécution et la performance, ce qui est attendu;
- un stop n'est actif qu'après son exécution d'entrée;
- le trailing high à l'ouverture d'une bougie est construit avec le passé; une
  mise à jour par le high courant ne peut pas déclencher rétroactivement;
- equity à `t` utilise au plus le close de `t`;
- métriques et outcomes ne rebouclent jamais dans la stratégie;
- trou temporel entre décision et exécution : expiration, pas saut silencieux.

`signal_close` reste autorisable comme option expérimentale clairement étiquetée
« hypothèse optimiste », mais n'est pas le défaut du portefeuille.

## 14. Cas limites

À couvrir explicitement : aucune observation acceptée; acceptations répétées;
sortie sans position; entrée avec position; capital trop faible; taux zéro;
prix/quantité non finis ou non positifs; dernière bougie sans ouverture
suivante; trous; bougies constantes; timeframe supérieur incomplet; annulation;
reprise idempotente; job historique; position impossible à liquider; zéro trade;
profit factor sans perte; equity non positive; collision stop/take; identifiants
dupliqués; points d'equity au même timestamp.

## 15. Modèles internes proposés

Ces esquisses ne sont pas encore des contrats publics :

```text
StrategyDecision(version, action, reason, observation_id, decision_time)
OrderIntent(id, action, created_at, execute_at_policy, requested_cash)
SimulatedOrder(id, intent_id, side, status, requested_quantity, reject_reason)
SimulatedExecution(id, order_id, time, reference_price, execution_price,
                   quantity, notional, fee, slippage_rate)
OpenPosition(symbol, quantity, entry_execution_id, total_entry_cost,
             entry_time, bars_held, highest_mark)
ClosedTrade(id, entry_execution_id, exit_execution_id, realized_pnl,
            return_rate, duration_bars, exit_reason, intrabar_ambiguous)
PortfolioState(cash, reserved_cash, open_position, realized_pnl, fees)
EquityPoint(timestamp, cash, position_value, equity, realized_pnl,
            unrealized_pnl, fees_cumulative, drawdown)
PortfolioSimulationResult(summary, trades, equity_curve, open_position, warnings)
```

Le moteur pur reçoit une séquence chronologique de bougies et d'observations et
émet des événements. Il ne dépend ni de FastAPI, SQLite, pandas, Zustand ou
CCXT.

## 16. Configuration publique intégrée en Phase 6.3

Bloc optionnel et additif :

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
    "slippage_rate": "0.0005",
    "end_of_test_policy": "force_close"
  }
}
```

L'absence du bloc suffit pour désactiver la simulation. Aucun champ `enabled`
n'est accepté en v1. Un bloc présent entre dans le fingerprint canonique; le
fingerprint historique du profil reste inchangé lorsque le bloc est absent.
La Phase 6.3 exige `replay_mode="every_bar"` afin de ne jamais interpréter une
observation non conservée comme un rejet.

`fee_bps` et `slippage_bps` historiques restent ceux des outcomes. Le bloc
portfolio utilise des taux explicites afin d'éviter de changer leur sens.
L'interface peut proposer de recopier les valeurs, jamais le faire
silencieusement.

## 17. Résultat Phase 6.3 et API futures

Le résumé du job contient désormais un aperçu borné. Les routes de détail
ci-dessous restent réservées à la Phase 6.4 :

```json
{
  "portfolio_simulation": {
    "version": 1,
    "summary": {
      "version": 1,
      "quote_asset": "USDC",
      "initial_capital": "10000",
      "final_equity": "1078.217821782178217821782178",
      "total_return_ratio": "0.078217821782178217821782178",
      "trade_count": 1
    },
    "has_trades": true,
    "has_equity_curve": true
  }
}
```

Trades et equity ne doivent pas gonfler le job. Routes cohérentes avec les
routes existantes (qui n'ont pas de segment `/jobs`) :

```text
GET /api/backtests/{job_id}/portfolio
GET /api/backtests/{job_id}/trades?offset=0&limit=100
GET /api/backtests/{job_id}/equity?offset=0&limit=1000
GET /api/backtests/{job_id}/trades/export.csv
GET /api/backtests/{job_id}/equity/export.csv
```

Réponses : `404` job absent; `409` job non terminé ou résultat indisponible;
`422` pagination/config invalide; job historique ou simulation désactivée :
`409` avec code `portfolio_simulation_not_enabled`; un job annulé ne publie
aucun résultat partiel en Phase 6.3. La Phase 6.4 conservera cette règle sauf
décision de contrat ultérieure explicite.
Les listes renvoient `items,total,offset,limit`. Les endpoints actuels et
`export.csv?dataset=...` restent inchangés.

## 18. Exports futurs

`trades-v1.csv` :

```text
trade_id,symbol,side,entry_time,exit_time,entry_reference_price,
entry_price,exit_reference_price,exit_price,quantity,entry_fee,exit_fee,
gross_pnl,net_pnl,return_pct,duration_bars,exit_reason,
entry_observation_id,exit_observation_id,intrabar_ambiguous
```

`equity-v1.csv` :

```text
timestamp,cash,position_value,equity,realized_pnl,unrealized_pnl,
fees_cumulative,drawdown,exposed
```

UTF-8, ordre stable, décimaux non localisés, timestamps UTC ISO 8601,
en-têtes versionnés et exportables séparément. Aucun export existant n'est
modifié.

## 19. Conception frontend future

Conserver les outcomes dans leur section « Rendements futurs indépendants » et
ajouter une section distincte « Simulation de portefeuille » :

- configuration activable : capital, unité dérivée, sizing, exécution, frais,
  slippage et fin;
- résumé : capital initial, equity finale, rendement, P&L net, drawdown, frais,
  trades et win rate;
- courbe : equity, cash et drawdown, avec valeurs textuelles;
- trades paginés et détail reliant observations/exécutions;
- position finale et P&L latent si non liquidée.

Responsive : formulaire compact, métriques en grille, graphique lisible, table
à scroll horizontal ou cartes, `Sheet` pleine largeur sur mobile. Accessibilité :
signe et texte en plus de la couleur, unités explicites, tables navigables,
focus clavier, résumé textuel du graphique, titres séparant outcomes et
portefeuille, hypothèses visibles.

Points d'insertion réels : `BacktestsPage.Results`, les cartes d'exports,
`backtestApi`, `backtest-store` et les types/schémas backtest. Ne pas surcharger
`BacktestObservationDetails`, qui reste une vue technique.

## 20. Scénarios manuels, oracles

Tous les montants sont en unités de l'actif de cotation.

### A. Sans frais

Capital 1 000, allocation 100 %, entrée 100, sortie 110 :
quantité 10, cash après entrée 0, sortie nette 1 100, P&L 100, rendement 10 %.

### B. Frais 1 %, allocation frais inclus

Capital 1 000, slippage 0, entrée 100, sortie 110 :

```text
entry_notional = 1000 / 1.01 = 990.0990099009900990099009901
entry_fee = 9.900990099009900990099009901
quantity = 9.900990099009900990099009901
gross_exit_proceeds = 1089.108910891089108910891089
exit_fee = 10.89108910891089108910891089
net_exit_proceeds = 1078.217821782178217821782178
realized_pnl = 78.217821782178217821782178
trade_return = 7.8217821782178217821782178 %
```

### C. Slippage 1 %, sans frais

Références 100 puis 110 : achat exécuté 101, quantité
`9.900990099009900990099009901`; vente exécutée 108,9; equity finale
`1078.217821782178217821782178`, soit P&L `78.217821782178...`.

### D. Trade perdant

Capital 1 000, sans friction, entrée 100, sortie 90 : quantité 10, equity finale
900, P&L -100, rendement -10 %, drawdown maximal 10 % si le pic était 1 000.

### E. Position ouverte

Cas B après l'entrée, mark close 105 : cash 0, valeur de position
`1039.603960396039603960396040`, P&L latent
`39.603960396039603960396040`; aucun frais de sortie hypothétique.

### F. Deux trades composés

Sans friction, all-in : 1 000 → achat 100/vente 110 = 1 100; achat 110/vente
99 = 990. Rendements trades +10 % puis -10 %, rendement total -1 % et non 0 %.

## 21. Plan de tests

### Unitaires

- sizing : cash suffisant/insuffisant, 1/25/100 %, fixe futur, frais inclus,
  invalides et minima;
- exécution : entrée/sortie, taux zéro, slippage défavorable, frais, prix
  invalide, trou, ordre expiré;
- portefeuille : ouvrir, valoriser, fermer, P&L/cash/equity, double entrée,
  sortie à plat, quantité nulle;
- métriques : rendement, win rate, profit factor, drawdown, exposition, aucun
  trade, position ouverte;
- collision intrabougie future : pessimiste + marqueur ambigu.

### Intégration

Entrée/sortie gagnante et perdante; plusieurs trades; frais retournant un petit
gain brut en perte nette; slippage; capital insuffisant; position finale;
`next_open`; `signal_close` expérimental; aucune acceptation; acceptations
répétées; trous; annulation/reprise; fingerprint; bloc absent; ancien job.

### Anti-look-ahead

Muter une bougie future et vérifier observation/intention inchangées; seule
l'exécution/performance postérieure change. Vérifier l'ouverture suivante
exacte, l'exclusion d'un timeframe supérieur ouvert, l'activation post-fill des
stops et l'equity de `t` indépendante du close `t+1`.

Les scénarios A à F deviennent des oracles décimaux. Les tests existants des
outcomes et la fixture golden restent inchangés.

## 22. Performance et persistance

Pour un symbole, une boucle avec état constant est `O(n + k)`, `n` bougies et
`k` trades; un point par bougie consomme `O(n)` mémoire/stockage. Le nombre de
trades est au plus approximativement `n/2` dans le modèle une entrée/une sortie.
La valorisation est O(1) par bougie.

Le projet ne conserve pas seulement les jobs en mémoire : `BacktestManager`
garde un cache et des tâches, mais `BacktestRepository` persiste jobs,
observations, outcomes, checkpoints et artefacts dans SQLite. Trades/equity
doivent suivre ce modèle. Une courbe longue rend les payloads intégrés
inadaptés : pagination et export en flux sont recommandés. Pas de migration vers
un autre moteur de base en Phase 6; mesurer d'abord taille, TTL, capacité et
temps d'export. Un redémarrage doit reprendre depuis un checkpoint incluant
l'état de portefeuille ou recalculer déterministement depuis le dernier
checkpoint vérifié.

## 23. Compatibilité

- bloc absent : JSON, comportement, outcomes et fingerprints historiques
  inchangés;
- bloc présent : replay/outcomes historiques plus résultat additif;
- ancien job : reste lisible, sans migration obligatoire du payload;
- aucun champ, endpoint, CSV ou modèle actuel supprimé;
- aucune position/trade ne doit être reconstruit heuristiquement depuis des
  outcomes historiques.

## 24. Risques

- confondre filtres et décisions transactionnelles;
- divergence entre la chronologie replay et portefeuille;
- ambiguïté intrabougie des stops;
- dérive float/Decimal et sérialisation;
- croissance SQLite de l'equity;
- reprise non idempotente créant des doubles trades;
- symbole ne révélant pas proprement l'actif de cotation;
- UI présentant un outcome comme preuve de performance de portefeuille;
- `signal_close` interprété comme exécution réaliste;
- changements de fingerprints legacy.

## 25. Décisions retenues

1. spot long-only, mono-symbole, une position;
2. `percent_cash`, 100 % par défaut, allocation frais inclus;
3. `next_open` par défaut, slippage défavorable symétrique;
4. taux de frais unique par côté, payé en actif de cotation;
5. stratégie dédiée `accepted_state_transition_v1`;
6. sortie MVP sur perte de validation et fin de test;
7. `force_close` par défaut;
8. `Decimal` interne, float historique intact;
9. equity à chaque clôture primaire;
10. métriques MVP définies en section 10;
11. modèles et résultats versionnés et additifs;
12. endpoints paginés dédiés et exports v1 séparés.

## 26. Questions ouvertes avant implémentation

| Question | Pourquoi / impact | Recommandation provisoire |
|---|---|---|
| Parsing des symboles autres que `BASE/QUOTE` | détermine l'unité et validation | exiger `/` pour le MVP |
| Stockage Decimal SQLite | type natif absent, tri/agrégats | chaînes canoniques + colonnes numériques de lecture si mesuré nécessaire |
| Annulation : résultat partiel public | état cohérent et reprise | ne publier qu'un checkpoint atomique marqué `partial` |
| `signal_close` dans le portefeuille | comparabilité vs réalisme | option avancée avec avertissement, jamais défaut |
| Stops/take profit du premier incrément | valeur produit mais ambiguïté OHLC | les reporter après le moteur de base |
| Pourcentage par défaut 100 ou 25 | dépend de l'usage produit réel | 100 pour oracle simple; rendre visible et modifiable |

## 27. Plan d'implémentation recommandé

- **Phase 6.2 — Modèles et moteur de portefeuille pur — implémentée** :
  Decimal, stratégie, événements, sizing, exécutions, position, métriques,
  scénarios manuels et garanties anti-look-ahead.
- **Phase 6.3 — Intégration au replay et contrats API** : bloc optionnel,
  causalité, fingerprint séparé, checkpoints et compatibilité.
- **Phase 6.4 — Trades, equity, métriques et exports** : persistance,
  pagination, drawdown, CSV versionnés.
- **Phase 6.5 — Interface frontend du portefeuille** : formulaire, résumé,
  courbe, table et accessibilité.
- **Phase 6.6 — Validation, performance et documentation finale** : matrice
  complète, benchmarks, reprise, volumes, OpenAPI et guides.

Chaque phase doit préserver les tests golden des outcomes et ne doit annoncer
la simulation comme disponible qu'après activation de ses contrats publics.
