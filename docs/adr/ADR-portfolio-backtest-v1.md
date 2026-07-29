# ADR — Simulateur de portefeuille backtest v1

- Statut : **Proposé**
- Date : 2026-07-29
- Décision détaillée :
  [`../BACKTEST_PORTFOLIO_SIMULATION_DESIGN.md`](../BACKTEST_PORTFOLIO_SIMULATION_DESIGN.md)

## Contexte et problème

Le backtest actuel rejoue causalement des observations et mesure des
`ForwardOutcome` indépendants. Il ne simule ni ordre, position, trade, cash ou
equity. `accepted` est une décision de filtrage, pas une instruction d'achat.
Une simulation séquentielle doit être ajoutée sans changer le replay, ses
fingerprints, ses modèles historiques ou ses exports.

## Options considérées

1. Assimiler toute observation acceptée à un achat : simple, mais
   sémantiquement faux et sans stratégie de sortie.
2. Déduire entrée/sortie des directions techniques : leur agrégation n'est pas
   un contrat transactionnel et la confluence actuelle est orientée long.
3. Ajouter une stratégie dédiée et un moteur de portefeuille pur : davantage
   de modèles, mais séparation explicite, causalité et évolutivité.
4. Construire immédiatement un moteur multi-actifs/marge : non justifié par le
   produit et beaucoup plus risqué.

## Décision recommandée

Choisir l'option 3 avec un MVP :

- mono-symbole, spot, long-only, sans levier, une position;
- stratégie `accepted_state_transition_v1` produisant
  `enter_long/exit_long/hold`;
- `percent_cash` avec 100 % par défaut et frais inclus dans l'allocation;
- exécution `next_open`, frais et slippage fictifs configurables;
- sortie sur perte de validation, puis clôture forcée en fin de test;
- `Decimal` interne et equity à chaque clôture primaire;
- bloc de configuration, résultat, endpoints et exports optionnels,
  additifs et versionnés.

Les stops/take profit futurs utilisent une politique pessimiste lorsqu'une
bougie touche les deux niveaux, avec ambiguïté enregistrée.

## Conséquences

Positives : vocabulaire non ambigu, cash jamais négatif par convention,
résultats reproductibles, complexité linéaire, ancien replay inchangé et
interface capable de séparer outcomes et portefeuille.

Coûts : nouveaux événements et artefacts persistés, courbe potentiellement
volumineuse, checkpoint de portefeuille, conversions Decimal et tests
anti-look-ahead supplémentaires.

## Éléments reportés

Multi-actifs, short, levier/marge, pyramiding, remplissages partiels, données
exchange de précision, risk sizing, signal opposé contractuel, trailing stop,
Sharpe/Sortino et benchmark.

## Compatibilité

`portfolio_simulation` absent ou désactivé conserve strictement le comportement
historique. Les outcomes ne deviennent jamais des trades. Aucun champ, endpoint
ou CSV existant n'est supprimé. Un job ancien reste lisible sans résultat
portfolio et les fingerprints historiques restent inchangés.

