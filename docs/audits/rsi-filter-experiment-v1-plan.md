# Manifeste préenregistré — expérience filtre RSI v1

## Identité et hypothèse

- version : `rsi-filter-experiment-v1`
- préenregistrement : 30 juillet 2026, avant toute exécution de R1/R2/R3
- HEAD initial Phase 7.2 : `3ac63df`
- baseline gelée : `signal-strategy-baseline-v1`, commit `770f002`
- fingerprint baseline : `sha256:7a35c7442778828cd207b6fbaee4a6d8390d6bb8fcb7d79751030d433b44a1b6`
- hypothèse : le prédicat strict de valeur `RSI < 35` limite trop fortement
  l'échantillon exploitable ; une relaxation mécanique peut augmenter les
  trades sans dégradation économique manifeste.

La période, la formule, le lissage, les statuts et le signal structuré RSI ne
changent pas. Les indicateurs, filtres non RSI, confluence, stratégie
`accepted_state_transition_v1`, exécution `next_open`, sizing, coûts et clôture
forcée restent ceux de la baseline.

## Manifeste machine lisible

Le bloc suivant est la source normative lue par le script. Les indices de fin
de segment sont exclusifs.

<!-- rsi-filter-experiment-v1-manifest -->
```json
{
  "baseline": {
    "commit": "770f002",
    "fingerprint": "sha256:7a35c7442778828cd207b6fbaee4a6d8390d6bb8fcb7d79751030d433b44a1b6",
    "version": "signal-strategy-baseline-v1"
  },
  "costs": {
    "end_of_test_policy": "force_close",
    "execution_policy": "next_open",
    "fee_rate": "0.001",
    "initial_capital": "10000",
    "position_sizing": {
      "mode": "percent_cash",
      "value": "100"
    },
    "slippage_rate": "0"
  },
  "datasets": [
    {
      "candles": 7381,
      "end": "2026-07-24T12:00:00Z",
      "segments": {
        "development": {"end_index": 4428, "start_index": 0},
        "test": {"end_index": 7381, "start_index": 5904},
        "validation": {"end_index": 5904, "start_index": 4428}
      },
      "start": "2023-03-12T08:00:00Z",
      "symbol": "BTC/USDC",
      "timeframe": "4h"
    },
    {
      "candles": 1384,
      "end": "2022-09-30T00:00:00Z",
      "segments": {
        "development": {"end_index": 830, "start_index": 0},
        "test": {"end_index": 1384, "start_index": 1107},
        "validation": {"end_index": 1107, "start_index": 830}
      },
      "start": "2018-12-16T00:00:00Z",
      "symbol": "BTC/USDC",
      "timeframe": "1d"
    },
    {
      "candles": 1208,
      "end": "2026-07-24T12:00:00Z",
      "segments": {
        "development": {"end_index": 724, "start_index": 0},
        "test": {"end_index": 1208, "start_index": 966},
        "validation": {"end_index": 966, "start_index": 724}
      },
      "start": "2026-01-04T04:00:00Z",
      "symbol": "LINK/USDC",
      "timeframe": "4h"
    },
    {
      "candles": 1500,
      "end": "2026-07-23T14:00:00Z",
      "segments": {
        "development": {"end_index": 900, "start_index": 0},
        "test": {"end_index": 1500, "start_index": 1200},
        "validation": {"end_index": 1200, "start_index": 900}
      },
      "start": "2026-05-22T02:00:00Z",
      "symbol": "ONDO/USDC",
      "timeframe": "1h"
    },
    {
      "candles": 1500,
      "end": "2026-07-24T15:00:00Z",
      "segments": {
        "development": {"end_index": 900, "start_index": 0},
        "test": {"end_index": 1500, "start_index": 1200},
        "validation": {"end_index": 1200, "start_index": 900}
      },
      "start": "2026-05-23T03:00:00Z",
      "symbol": "SUI/USDC",
      "timeframe": "1h"
    }
  ],
  "decision_rules": {
    "development": {
      "accepted_must_increase": true,
      "cost_to_gross_profit_max": "0.75",
      "drawdown_multiple_max": "2",
      "minimum_new_trade_datasets": 2,
      "top_5_profit_concentration_max": "0.80",
      "trade_count_formula": "max(30,2*baseline_development_trade_count)"
    },
    "final": {
      "drawdown_formula": "max(baseline+0.02,1.5*baseline)",
      "minimum_cumulative_trades": 15,
      "net_return_must_be_non_negative": true,
      "net_return_must_improve": true,
      "trade_count_must_increase": true
    },
    "selection_order": [
      "validation_trade_count_desc",
      "validation_net_return_desc",
      "validation_drawdown_asc",
      "relaxation_asc"
    ],
    "validation": {
      "drawdown_formula": "max(baseline+0.02,1.5*baseline)",
      "minimum_new_trade_datasets": 2,
      "profit_factor_not_below_baseline": true,
      "return_not_below_baseline": true,
      "trade_count_formula": "max(10,baseline_validation_trade_count)"
    }
  },
  "git_head_at_preregistration": "3ac63df",
  "primary_metric": "exploitable_trade_count",
  "rsi_rule": {
    "availability_policy": "available_and_finite_required_for_all_variants",
    "operator": "<",
    "period": 14,
    "threshold": "35"
  },
  "safety_metrics": [
    "net_return",
    "net_pnl",
    "max_drawdown",
    "profit_factor",
    "win_rate",
    "average_trade_return",
    "total_fees",
    "exposure_ratio",
    "top_5_profit_concentration",
    "markets_with_trades"
  ],
  "stage_order": ["reproduce", "development", "validation", "final-test"],
  "variants": [
    {"delta": "0", "id": "R0", "operator": "<", "threshold": "35", "type": "baseline"},
    {"delta": "5", "id": "R1", "operator": "<", "threshold": "40", "type": "relaxation"},
    {"delta": "10", "id": "R2", "operator": "<", "threshold": "45", "type": "relaxation"},
    {"delta": null, "id": "R3", "operator": null, "threshold": null, "type": "no_value_filter"}
  ],
  "version": "rsi-filter-experiment-v1"
}
```

## Ordre, élimination et ouverture du test final

1. `reproduce` exécute uniquement R0 et exige la parité complète.
2. `development` exécute R0/R1/R2/R3 sur le seul segment développement.
3. `validation` exécute R0 et les seules variantes survivantes.
4. Au maximum une candidate est sélectionnée selon l'ordre mécanique ci-dessus.
5. Le test final refuse tout manifeste modifié, sélection absente ou multiple,
   variante non préenregistrée, validation absente, datasets/segments divergents
   ou identifiant différent du fichier de sélection.

Une profit factor indéfinie avec zéro perte n'est pas défavorable. Lorsque R0
n'a aucun trade, une candidate de validation doit avoir au moins dix trades, un
rendement non négatif et un profit factor défini au moins égal à 1, sauf si elle
n'a également aucune perte. Aucun seuil ne sera ajusté après lecture des
résultats.

## Critères de conclusion

La conclusion appartient exactement à l'une des catégories suivantes :
`confirmed_for_production_candidate`, `promising_but_insufficient`,
`rejected_on_validation`, `rejected_on_final_test`,
`no_variant_increased_sample_enough` ou `experiment_invalidated`.

Une confirmation ne déploie rien : elle autorise seulement la proposition
d'une Phase 7.3 séparée. Une insuffisance ou un échec conserve la production
inchangée et n'autorise pas de relaxation supplémentaire improvisée.
