# Baseline signaux et stratégie v1

## Résumé exécutif

Baseline de mesure uniquement au commit `770f002`. Aucun indicateur,
filtre, contrat public, endpoint ou code frontend n'est modifié. Les comptes de
chaque marché sont indépendants : leurs P&L ne forment pas un portefeuille
multi-actifs.

- BTC/USDC 4h 2023-03-12–2026-07-24: 21 trades, rendement -0.027543023521176834967192241, drawdown 0.054849057241997849691262676, statut faible échantillon.
- BTC/USDC 1d 2018-12-16–2022-09-30: 0 trades, rendement 0, drawdown 0, statut faible échantillon.
- LINK/USDC 4h 2026-01-04–2026-07-24: 0 trades, rendement 0, drawdown 0, statut faible échantillon.
- ONDO/USDC 1h 2026-05-22–2026-07-23: 0 trades, rendement 0, drawdown 0, statut faible échantillon.
- SUI/USDC 1h 2026-05-23–2026-07-24: 1 trades, rendement -0.0015940616318382103595271431, drawdown 0.0015940616318382103595271431, statut faible échantillon.

## Objectif et protocole

- configuration actuelle figée avant lecture des performances ;
- replay causal `every_bar`, exécution `next_open`, stratégie
  `accepted_state_transition_v1` ;
- découpage chronologique 60 % développement, 20 % validation, 20 % test final ;
- test final consulté seulement après gel de la configuration ;
- aucune optimisation, permutation aléatoire ou requête réseau ;
- base historique ouverte en lecture seule, résultats dans une SQLite temporaire supprimée.

## Code et empreintes

- Version : `signal-strategy-baseline-v1`
- Généré : `2026-07-30T10:00:00Z`
- Git : `770f002`
- Empreinte d'audit : `sha256:7a35c7442778828cd207b6fbaee4a6d8390d6bb8fcb7d79751030d433b44a1b6`

## Inventaire des données

Combinaisons inventoriées : 851. Bougies locales :
127776. Les détails complets
restent produits par le script en mémoire ; le rapport suivi privilégie les séries
sélectionnées afin de rester compact.

L'inventaire ligne par ligne est publié dans
[`signal-strategy-baseline-v1-inventory.md`](signal-strategy-baseline-v1-inventory.md).

| Symbole | Timeframe | Début | Fin exclusive | Bougies | Continuité |
|---|---|---:|---:|---:|---:|
| BTC/USDC | 4h | 2023-03-12 | 2026-07-24 | 7381 | 1 |
| BTC/USDC | 1d | 2018-12-16 | 2022-09-30 | 1384 | 1 |
| LINK/USDC | 4h | 2026-01-04 | 2026-07-24 | 1208 | 1 |
| ONDO/USDC | 1h | 2026-05-22 | 2026-07-23 | 1500 | 1 |
| SUI/USDC | 1h | 2026-05-23 | 2026-07-24 | 1500 | 1 |

Seuils pré-définis : au moins 500 bougies, continuité de la plage
sélectionnée au moins 0.98, et au moins 30
trades pour éviter l'avertissement de faible échantillon.

## Configuration canonique

Capital 10 000 unités de cotation, sizing 100 % du cash, frais 0,1 %, slippage
nul, `next_open`, `force_close`, horizons 1/3/6/12/24 et paramètres
`ScanConfig` actuels. Les fingerprints par marché sont dans le résumé JSON.

## Résultats globaux et inter-marchés

| Symbole | TF | Observations | Accepted | Trades | Rendement | Drawdown | Win rate | Frais | Statut |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| BTC/USDC | 4h | 7381 | 32 | 21 | -0.027543023521176834967192241 | 0.054849057241997849691262676 | 0.6666666666666666666666666667 | 424.2919601656101726767897083 | faible échantillon |
| BTC/USDC | 1d | 1384 | 0 | 0 | 0 | 0 | None | 0 | faible échantillon |
| LINK/USDC | 4h | 1208 | 0 | 0 | 0 | 0 | None | 0 | faible échantillon |
| ONDO/USDC | 1h | 1500 | 0 | 0 | 0 | 0 | None | 0 | faible échantillon |
| SUI/USDC | 1h | 1500 | 1 | 1 | -0.0015940616318382103595271431 | 0.0015940616318382103595271431 | 0 | 19.98406342712872664302777632 | faible échantillon |

## Stabilité temporelle

| Symbole | TF | Segment | Trades | Rendement | Drawdown |
|---|---|---|---:|---:|---:|
| BTC/USDC | 4h | development | 19 | -0.0011728765885431462990787354 | 0.03695228234605015502447486436 |
| BTC/USDC | 4h | validation | 2 | -0.026401112179019962513301592 | 0.03470345341107547860420153794 |
| BTC/USDC | 4h | test | 0 | 0 | 0 |
| BTC/USDC | 1d | development | 0 | 0 | 0 |
| BTC/USDC | 1d | validation | 0 | 0 | 0 |
| BTC/USDC | 1d | test | 0 | 0 | 0 |
| LINK/USDC | 4h | development | 0 | 0 | 0 |
| LINK/USDC | 4h | validation | 0 | 0 | 0 |
| LINK/USDC | 4h | test | 0 | 0 | 0 |
| ONDO/USDC | 1h | development | 0 | 0 | 0 |
| ONDO/USDC | 1h | validation | 0 | 0 | 0 |
| ONDO/USDC | 1h | test | 0 | 0 | 0 |
| SUI/USDC | 1h | development | 0 | 0 | 0 |
| SUI/USDC | 1h | validation | 1 | -0.0015940616318382103595271431 | 0.0015940616318382103595271431 |
| SUI/USDC | 1h | test | 0 | 0 | 0 |

Chaque résultat avec moins de 30 trades est descriptif et non robuste.
Les bornes exactes, distributions, concentration des profits, ordres, sorties,
couverture des indicateurs, confluence, outcomes, sensibilités et ablations sont
conservés dans le calcul reproductible et synthétisés dans le JSON compact.

## Sensibilités et ablations

Les matrices sont fixées à l'avance : frais et slippage 0/0,05/0,1/0,2 %, sizing
25/50/100 %. Elles réutilisent exactement les mêmes observations et transitions.
Les ablations existantes de `build_analytics` sont rapportées comme analyses
d'outcomes ; elles ne sont pas assimilées à un P&L de portefeuille.

## Diagnostics détaillés par marché


### BTC/USDC — 4h

Période `2023-03-12T08:00:00+00:00` à `2026-07-24T12:00:00+00:00` (fin
exclusive), 7381 bougies.

#### Observations, transitions et ordres

- observations : 7381 ;
- accepted/rejected : 32/7349
  (taux 0.004335455900284514293456171251) ;
- transitions false→true / true→false :
  21/21 ;
- durées accepted : `{"count": 21, "minimum": "1", "q10": "1", "q25": "1", "median": "1", "q75": "2", "q90": "2", "maximum": "3", "mean": "1.523809523809523809523809524"}` ;
- durées rejected : `{"count": 22, "minimum": "2", "q10": "4", "q25": "65", "median": "115", "q75": "356", "q90": "666", "maximum": "1720", "mean": "334.0454545454545454545454545"}` ;
- stades de rejet : `{"confluence": 15, "none": 32, "rsi": 6688, "trend": 646}` ;
- ordres total/exécutés/rejetés/annulés :
  42/42/0/0 ;
- raisons opérationnelles : `{}`.

L'écart transitions/trades vient de `next_open`, des répétitions accepted, de
l'état de position, des ordres de fin de données et de `force_close`.

#### Sorties, distribution et concentration

Sorties : `{"validation_lost": {"average_duration_bars": "1.523809523809523809523809524", "average_return": "-0.001240989103347628945889026455", "total_pnl": "-275.430235211768349671922418", "total_return": "-0.02606077117030020786366955556", "trade_count": 21, "win_rate": "0.6666666666666666666666666667"}}`.

Distribution : `{"duration_bars": {"count": 21, "maximum": "3", "mean": "1.523809523809523809523809524", "median": "1", "minimum": "1", "q10": "1", "q25": "1", "q75": "2", "q90": "2"}, "fees": {"count": 21, "maximum": "20.54632231975684130758073558", "mean": "20.20437905550524631794236707", "median": "20.25954110593314221290487915", "minimum": "19.78835525337799756339346798", "q10": "19.9354861979598360351000248", "q25": "20.05247235629394542530142895", "q75": "20.33741511175722728515850471", "q90": "20.46189984740324035432569299"}, "maximum_losing_streak": 2, "maximum_winning_streak": 5, "pnl": {"count": 21, "maximum": "220.5307256264214213065685", "mean": "-13.11572548627468331771059133", "median": "9.95158110497169146835052", "minimum": "-339.53547091719808282257198", "q10": "-174.97993326201095027876018", "q25": "-41.28028040079820957528435", "q75": "68.399682580861657070517636", "q90": "132.46260178631747496420105"}, "return_ratio": {"count": 21, "maximum": "0.02194887841904449116468789281", "mean": "-0.001240989103347628945889026451", "median": "0.0009945618750483901197809180164", "minimum": "-0.03373727350471199707968003138", "q10": "-0.01722455328970568756251146595", "q25": "-0.004066853933747626374218023642", "q75": "0.00688575918318607094961488732", "q90": "0.01311199355478480750335663797"}, "seconds_between_trades": {"count": 20, "maximum": "15436800", "mean": "2984400", "median": "1353600", "minimum": "28800", "q10": "57600", "q25": "864000", "q75": "3297600", "q90": "6681600"}}`.

| Extrême | P&L | Part du total | Interprétation |
|---|---:|---:|---|
| meilleur | 220.5307256264214213065685 | -0.8006772584602533547655048306 | signed_against_non_positive_total |
| 3 meilleurs | 493.93465713627788422044693 | -1.793320391120130237553369969 | signed_against_non_positive_total |
| 5 meilleurs | 646.342503617657755931567894 | -2.346665038864409252014232441 | signed_against_non_positive_total |
| top 10 % | 493.93465713627788422044693 | -1.793320391120130237553369969 | signed_against_non_positive_total |
| 5 pires | -1084.198230198211795580180624 | 3.936380584232558838635322104 | signed_against_non_positive_total |

#### Couverture, directions, signaux et states

| Indicateur | Observations | Statuts | Entrées | Directions aux entrées |
|---|---:|---|---:|---|
| rsi | 7381 | {"available": 7381} | 21 | {"bullish": 21} |
| sma | 7381 | {"missing": 7381} | 21 | {} |
| ema | 7381 | {"missing": 7381} | 21 | {} |
| macd | 7381 | {"available": 7381} | 21 | {"bearish": 21} |
| bollinger | 7381 | {"available": 7381} | 21 | {"bullish": 16, "bearish": 5} |
| stochastic | 7381 | {"available": 7381} | 21 | {"bullish": 11, "neutral": 10} |

Les associations direction/signal/state avec rendement et P&L des trades
d'entrée sont descriptives et gardent leur effectif :

```json
{
  "bollinger": {
    "direction": {
      "bearish": {
        "average_return": "0.0001651339361392804632606808116",
        "total_pnl": "7.961559691389160346286708",
        "trade_count": 5
      },
      "bullish": {
        "average_return": "-0.001680402553187288136248309977",
        "total_pnl": "-283.391794903157510018209126",
        "trade_count": 16
      }
    },
    "signal": {
      "lower_band_breakout": {
        "average_return": "0.0001651339361392804632606808116",
        "total_pnl": "7.961559691389160346286708",
        "trade_count": 5
      },
      "near_oversold": {
        "average_return": "0.003383351603970045422473899953",
        "total_pnl": "101.826007485382211205042982",
        "trade_count": 3
      },
      "oversold": {
        "average_return": "-0.002848961204838980495953435345",
        "total_pnl": "-385.217802388539721223252108",
        "trade_count": 13
      }
    },
    "state": {
      "near_oversold": {
        "average_return": "0.003383351603970045422473899953",
        "total_pnl": "101.826007485382211205042982",
        "trade_count": 3
      },
      "oversold": {
        "average_return": "-0.002011712554567241340616180857",
        "total_pnl": "-377.2562426971505608769654",
        "trade_count": 18
      }
    }
  },
  "ema": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "macd": {
    "direction": {
      "bearish": {
        "average_return": "-0.001240989103347628945889026455",
        "total_pnl": "-275.430235211768349671922418",
        "trade_count": 21
      }
    },
    "signal": {
      "below_signal": {
        "average_return": "-0.001240989103347628945889026455",
        "total_pnl": "-275.430235211768349671922418",
        "trade_count": 21
      }
    },
    "state": {
      "below_signal/above_zero": {
        "average_return": "0.00533006749377365219421016001",
        "total_pnl": "108.09859175414144905867159",
        "trade_count": 2
      },
      "below_signal/below_zero": {
        "average_return": "-0.001932679271465658539583677662",
        "total_pnl": "-383.528826965909798730594008",
        "trade_count": 19
      }
    }
  },
  "rsi": {
    "direction": {
      "bullish": {
        "average_return": "-0.001240989103347628945889026455",
        "total_pnl": "-275.430235211768349671922418",
        "trade_count": 21
      }
    },
    "signal": {
      "near_oversold": {
        "average_return": "-0.0005331017462982287016783929825",
        "total_pnl": "-87.134584087698347660535302",
        "trade_count": 14
      },
      "oversold": {
        "average_return": "-0.0026567638174464294343102934",
        "total_pnl": "-188.295651124070002011387116",
        "trade_count": 7
      }
    },
    "state": {
      "near_oversold": {
        "average_return": "-0.0005331017462982287016783929825",
        "total_pnl": "-87.134584087698347660535302",
        "trade_count": 14
      },
      "oversold": {
        "average_return": "-0.0026567638174464294343102934",
        "total_pnl": "-188.295651124070002011387116",
        "trade_count": 7
      }
    }
  },
  "sma": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "stochastic": {
    "direction": {
      "bullish": {
        "average_return": "-0.004002411412220432615622387193",
        "total_pnl": "-452.970373263584343043530616",
        "trade_count": 11
      },
      "neutral": {
        "average_return": "0.001796575436412455090817670358",
        "total_pnl": "177.540138051815993371608198",
        "trade_count": 10
      }
    },
    "signal": {
      "bullish_cross": {
        "average_return": "0.004130865447968169866157929543",
        "total_pnl": "124.169019361900757149372636",
        "trade_count": 3
      },
      "neutral": {
        "average_return": "0.001796575436412455090817670358",
        "total_pnl": "177.540138051815993371608198",
        "trade_count": 10
      },
      "oversold": {
        "average_return": "-0.007052390234791158546290005969",
        "total_pnl": "-577.139392625485100192903252",
        "trade_count": 8
      }
    },
    "state": {
      "neutral": {
        "average_return": "0.001796575436412455090817670358",
        "total_pnl": "177.540138051815993371608198",
        "trade_count": 10
      },
      "oversold": {
        "average_return": "-0.004002411412220432615622387193",
        "total_pnl": "-452.970373263584343043530616",
        "trade_count": 11
      }
    }
  }
}
```

#### Confluence et tendance

Confluence (buckets fixés avant mesure) :

```json
{
  "all": {
    "grades": {
      "B": 15,
      "C": 390,
      "D": 1448,
      "F": 5528
    },
    "predefined_buckets": {
      "high:>=70": 15,
      "low:<40": 3012,
      "medium:40-69.999": 4354
    },
    "sample_size": 7381,
    "scores": {
      "count": 7381,
      "maximum": "78.33",
      "mean": "42.62427313372171792440048774",
      "median": "42.83",
      "minimum": "12.67",
      "q10": "28.92",
      "q25": "34.92",
      "q75": "50.25",
      "q90": "57.25"
    }
  },
  "entries": {
    "grades": {
      "B": 2,
      "C": 19
    },
    "predefined_buckets": {
      "high:>=70": 2,
      "medium:40-69.999": 19
    },
    "sample_size": 21,
    "scores": {
      "count": 21,
      "maximum": "75.83",
      "mean": "65.97380952380952380952380952",
      "median": "66.08",
      "minimum": "61.08",
      "q10": "61.08",
      "q25": "61.67",
      "q75": "69.33",
      "q90": "69.33"
    }
  },
  "exits": {
    "grades": {
      "B": 1,
      "C": 4,
      "D": 10,
      "F": 6
    },
    "predefined_buckets": {
      "high:>=70": 1,
      "low:<40": 3,
      "medium:40-69.999": 17
    },
    "sample_size": 21,
    "scores": {
      "count": 21,
      "maximum": "71.67",
      "mean": "54.43619047619047619047619048",
      "median": "56.83",
      "minimum": "34.92",
      "q10": "39.08",
      "q25": "48.5",
      "q75": "58.17",
      "q90": "66.67"
    }
  },
  "losing_entries": {
    "grades": {
      "B": 1,
      "C": 6
    },
    "predefined_buckets": {
      "high:>=70": 1,
      "medium:40-69.999": 6
    },
    "sample_size": 7,
    "scores": {
      "count": 7,
      "maximum": "74.33",
      "mean": "66.62857142857142857142857143",
      "median": "66.08",
      "minimum": "61.08",
      "q10": "61.08",
      "q25": "61.92",
      "q75": "69.33",
      "q90": "69.33"
    }
  },
  "winning_entries": {
    "grades": {
      "B": 1,
      "C": 13
    },
    "predefined_buckets": {
      "high:>=70": 1,
      "medium:40-69.999": 13
    },
    "sample_size": 14,
    "scores": {
      "count": 14,
      "maximum": "75.83",
      "mean": "65.64642857142857142857142857",
      "median": "65.955",
      "minimum": "61.08",
      "q10": "61.08",
      "q25": "61.08",
      "q75": "69.33",
      "q90": "69.33"
    }
  }
}
```

Tendance :

```json
{
  "entry_trade_performance": {
    "bearish,bullish": {
      "average_return": "0.005310299601407750692917833883",
      "total_pnl": "159.582003966380922459434336",
      "trade_count": 3
    },
    "bullish,neutral": {
      "average_return": "-0.002332870554140192219023503179",
      "total_pnl": "-435.012239178149272131356754",
      "trade_count": 18
    }
  },
  "observation_states": {
    "bearish": 177,
    "bearish,bullish": 342,
    "bearish,bullish,neutral": 1037,
    "bearish,neutral": 1705,
    "bullish": 932,
    "bullish,neutral": 2725,
    "neutral": 463
  },
  "provenance": "SignalObservation.trend_states (facteur historique multi-timeframe, distinct de SMA/EMA structurés)"
}
```

#### Outcomes et horizons

| Horizon | Outcomes | Censurés | Moyenne | Médiane | Taux positif | Moy. accepted | Moy. rejected |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 7381 | 2 | -0.001604805012481366038758639382 | -0.0016786732 | 0.408049871256267786963003117 | 0.0011762956125 | -0.00161691814981625153123723969 |
| 3 | 7381 | 4 | -0.001216772248759658397722651484 | -0.0016526559 | 0.4453029686864579097193981293 | 0.001550991684375 | -0.00122883058039482641252552757 |
| 6 | 7381 | 7 | -0.0006495457405478708977488473013 | -0.0011889419 | 0.4704366693788988337401681584 | 0.00594218511875 | -0.0006782757034323072732225551621 |
| 12 | 7381 | 13 | 0.0004187970265200868621064060803 | -0.00037557355 | 0.4917209554831704668838219327 | 0.008428037825 | 0.0003838603163849509269356597601 |
| 24 | 7381 | 25 | 0.002557708139233278955954323002 | -0.0000410322 | 0.4993202827623708537248504622 | 0.014128564265625 | 0.002507152787506826870562534134 |

Comparaison outcomes/portefeuille :
`{"accepted_observation_count": 32, "accepted_observations_without_distinct_entry": 11, "entry_trade_count": 21, "note": "les outcomes sont indépendants; le portefeuille ignore les répétitions accepted pendant une position et ne somme jamais les outcomes", "outcome_count": 36905}`.

#### Périodes calendaires

| Année | Observations | Trades | Rendement | Drawdown |
|---|---:|---:|---:|---:|
| 2023 | 1768 | 5 | 0.027737978823901681802478733 | 0.009137388803669975712410015702 |
| 2024 | 2196 | 13 | -0.0000266858172357790407750576 | 0.0358721567029550445118370002 |
| 2025 | 2190 | 3 | -0.053763753001157915024794899 | 0.053763753001157915024794899 |
| 2026 | 1227 | 0 | 0 | 0 |

#### Sensibilité aux coûts et au sizing

| Famille | Valeur | Trades | Rendement | Drawdown | Frais | Profit factor |
|---|---:|---:|---:|---:|---:|---:|
| fees | 0 | 21 | 0.014170025790814292335725281 | 0.04806926724719325066420615008 | 0 | 1.136927211055952790009551751 |
| fees | 0.0005 | 21 | -0.0069054791856523763347434468 | 0.05134057396409470782988674469 | 214.3878630359121871714514886 | 0.9364875283536046334703545442 |
| fees | 0.001 | 21 | -0.027543023521176834967192241 | 0.054849057241997849691262676 | 424.2919601656101726767897083 | 0.7587810239734805941881103335 |
| fees | 0.002 | 21 | -0.06754048372884894571350618 | 0.08652209896443518874569853424 | 831.0209457149773649021241756 | 0.4800636106317468725923044584 |
| slippage | 0 | 21 | -0.027543023521176834967192241 | 0.054849057241997849691262676 | 424.2919601656101726767897083 | 0.7587810239734805941881103335 |
| slippage | 0.0005 | 21 | -0.0477516880704942603396842937 | 0.07039418709250749969511389286 | 419.870254950139681605461164 | 0.6028060827171128848643143796 |
| slippage | 0.001 | 21 | -0.067540405402011308696771767 | 0.0865211215391691434265066992 | 415.5099190502605555243835354 | 0.4800640524185037517528940626 |
| slippage | 0.002 | 21 | -0.1058927607578652470397641092 | 0.1179412424488717561197978006 | 406.9695319521648202477403502 | 0.304593706761886731648951072 |
| sizing | 25 | 21 | -0.0066091543929711581603946841 | 0.013765069712369307827579324 | 105.2278884673137489406943372 | 0.7654484398477647407322904347 |
| sizing | 50 | 21 | -0.0134045009174399111015555514 | 0.02746308077193982371487971817 | 211.0305380369709801422337189 | 0.7631927664682795572071099344 |
| sizing | 100 | 21 | -0.027543023521176834967192241 | 0.054849057241997849691262676 | 424.2919601656101726767897083 | 0.7587810239734805941881103335 |

#### Ablations et corrélations existantes

| Ablation | Facteurs retirés | Accepted | Delta |
|---|---|---:|---:|
| bollinger | bollinger | 21 | -11 |
| group:confirmation | bollinger, macd | 46 | 14 |
| group:momentum | rsi, stochastic | 26 | -6 |
| group:trend | trend | 24 | -8 |
| macd | macd | 46 | 14 |
| rsi | rsi | 19 | -13 |
| stochastic | stochastic | 35 | 3 |
| trend | trend | 24 | -8 |

Les ablations ci-dessus recalculent descriptivement la confluence et ses outcomes,
pas le portefeuille. Corrélations disponibles par horizon :
`["1", "12", "24", "3", "6"]`.
Chaque matrice existante conserve ses `pair_counts`; aucune causalité n'est inférée.


### BTC/USDC — 1d

Période `2018-12-16T00:00:00+00:00` à `2022-09-30T00:00:00+00:00` (fin
exclusive), 1384 bougies.

#### Observations, transitions et ordres

- observations : 1384 ;
- accepted/rejected : 0/1384
  (taux 0) ;
- transitions false→true / true→false :
  0/0 ;
- durées accepted : `{"count": 0}` ;
- durées rejected : `{"count": 1, "minimum": "1384", "q10": "1384", "q25": "1384", "median": "1384", "q75": "1384", "q90": "1384", "maximum": "1384", "mean": "1384"}` ;
- stades de rejet : `{"rsi": 1269, "trend": 115}` ;
- ordres total/exécutés/rejetés/annulés :
  0/0/0/0 ;
- raisons opérationnelles : `{}`.

L'écart transitions/trades vient de `next_open`, des répétitions accepted, de
l'état de position, des ordres de fin de données et de `force_close`.

#### Sorties, distribution et concentration

Sorties : `{}`.

Distribution : `{"duration_bars": {"count": 0}, "fees": {"count": 0}, "maximum_losing_streak": 0, "maximum_winning_streak": 0, "pnl": {"count": 0}, "return_ratio": {"count": 0}, "seconds_between_trades": {"count": 0}}`.

| Extrême | P&L | Part du total | Interprétation |
|---|---:|---:|---|
| meilleur | 0 | None | undefined_zero_total |
| 3 meilleurs | 0 | None | undefined_zero_total |
| 5 meilleurs | 0 | None | undefined_zero_total |
| top 10 % | 0 | None | undefined_zero_total |
| 5 pires | 0 | None | undefined_zero_total |

#### Couverture, directions, signaux et states

| Indicateur | Observations | Statuts | Entrées | Directions aux entrées |
|---|---:|---|---:|---|
| rsi | 1384 | {"insufficient_data": 13, "available": 1371} | 0 | {} |
| sma | 1384 | {"missing": 1384} | 0 | {} |
| ema | 1384 | {"missing": 1384} | 0 | {} |
| macd | 1384 | {"insufficient_data": 32, "available": 1352} | 0 | {} |
| bollinger | 1384 | {"insufficient_data": 18, "available": 1366} | 0 | {} |
| stochastic | 1384 | {"insufficient_data": 15, "available": 1369} | 0 | {} |

Les associations direction/signal/state avec rendement et P&L des trades
d'entrée sont descriptives et gardent leur effectif :

```json
{
  "bollinger": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "ema": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "macd": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "rsi": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "sma": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "stochastic": {
    "direction": {},
    "signal": {},
    "state": {}
  }
}
```

#### Confluence et tendance

Confluence (buckets fixés avant mesure) :

```json
{
  "all": {
    "grades": {
      "A+": 6,
      "B": 1,
      "C": 72,
      "D": 240,
      "F": 1063,
      "None": 2
    },
    "predefined_buckets": {
      "high:>=70": 7,
      "low:<40": 551,
      "medium:40-69.999": 824
    },
    "sample_size": 1384,
    "scores": {
      "count": 1382,
      "maximum": "100",
      "mean": "42.02235166425470332850940666",
      "median": "42.83",
      "minimum": "0",
      "q10": "26.58",
      "q25": "33.08",
      "q75": "48.92",
      "q90": "54.92"
    }
  },
  "entries": {
    "grades": {},
    "predefined_buckets": {},
    "sample_size": 0,
    "scores": {
      "count": 0
    }
  },
  "exits": {
    "grades": {},
    "predefined_buckets": {},
    "sample_size": 0,
    "scores": {
      "count": 0
    }
  },
  "losing_entries": {
    "grades": {},
    "predefined_buckets": {},
    "sample_size": 0,
    "scores": {
      "count": 0
    }
  },
  "winning_entries": {
    "grades": {},
    "predefined_buckets": {},
    "sample_size": 0,
    "scores": {
      "count": 0
    }
  }
}
```

Tendance :

```json
{
  "entry_trade_performance": {},
  "observation_states": {
    "bearish": 59,
    "bearish,bullish": 36,
    "bearish,bullish,neutral": 147,
    "bearish,bullish,unavailable": 6,
    "bearish,neutral": 324,
    "bearish,neutral,unavailable": 20,
    "bearish,unavailable": 16,
    "bullish": 197,
    "bullish,neutral": 403,
    "bullish,neutral,unavailable": 29,
    "bullish,unavailable": 40,
    "neutral": 85,
    "neutral,unavailable": 20,
    "unavailable": 2
  },
  "provenance": "SignalObservation.trend_states (facteur historique multi-timeframe, distinct de SMA/EMA structurés)"
}
```

#### Outcomes et horizons

| Horizon | Outcomes | Censurés | Moyenne | Médiane | Taux positif | Moy. accepted | Moy. rejected |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1384 | 2 | 0.001951788597684515195369030391 | 0.00133943055 | 0.5151953690303907380607814761 | None | 0.001951788597684515195369030391 |
| 3 | 1384 | 4 | 0.005777380666811594202898550725 | 0.0032939757 | 0.5253623188405797101449275362 | None | 0.005777380666811594202898550725 |
| 6 | 1384 | 7 | 0.01159554710827886710239651416 | 0.0035992319 | 0.5170660856935366739288307916 | None | 0.01159554710827886710239651416 |
| 12 | 1384 | 13 | 0.02353076401699489423778264041 | 0.0100534607 | 0.5463165572574762946754194019 | None | 0.02353076401699489423778264041 |
| 24 | 1384 | 25 | 0.04977688016482707873436350258 | 0.0245644769 | 0.5526122148638704930095658572 | None | 0.04977688016482707873436350258 |

Comparaison outcomes/portefeuille :
`{"accepted_observation_count": 0, "accepted_observations_without_distinct_entry": 0, "entry_trade_count": 0, "note": "les outcomes sont indépendants; le portefeuille ignore les répétitions accepted pendant une position et ne somme jamais les outcomes", "outcome_count": 6920}`.

#### Périodes calendaires

| Année | Observations | Trades | Rendement | Drawdown |
|---|---:|---:|---:|---:|
| 2018 | 16 | 0 | 0 | 0 |
| 2019 | 365 | 0 | 0 | 0 |
| 2020 | 366 | 0 | 0 | 0 |
| 2021 | 365 | 0 | 0 | 0 |
| 2022 | 272 | 0 | 0 | 0 |

#### Sensibilité aux coûts et au sizing

| Famille | Valeur | Trades | Rendement | Drawdown | Frais | Profit factor |
|---|---:|---:|---:|---:|---:|---:|
| fees | 0 | 0 | 0 | 0 | 0 | None |
| fees | 0.0005 | 0 | 0 | 0 | 0 | None |
| fees | 0.001 | 0 | 0 | 0 | 0 | None |
| fees | 0.002 | 0 | 0 | 0 | 0 | None |
| slippage | 0 | 0 | 0 | 0 | 0 | None |
| slippage | 0.0005 | 0 | 0 | 0 | 0 | None |
| slippage | 0.001 | 0 | 0 | 0 | 0 | None |
| slippage | 0.002 | 0 | 0 | 0 | 0 | None |
| sizing | 25 | 0 | 0 | 0 | 0 | None |
| sizing | 50 | 0 | 0 | 0 | 0 | None |
| sizing | 100 | 0 | 0 | 0 | 0 | None |

#### Ablations et corrélations existantes

| Ablation | Facteurs retirés | Accepted | Delta |
|---|---|---:|---:|
| bollinger | bollinger | 0 | 0 |
| group:confirmation | bollinger, macd | 0 | 0 |
| group:momentum | rsi, stochastic | 0 | 0 |
| group:trend | trend | 0 | 0 |
| macd | macd | 0 | 0 |
| rsi | rsi | 0 | 0 |
| stochastic | stochastic | 0 | 0 |
| trend | trend | 0 | 0 |

Les ablations ci-dessus recalculent descriptivement la confluence et ses outcomes,
pas le portefeuille. Corrélations disponibles par horizon :
`["1", "12", "24", "3", "6"]`.
Chaque matrice existante conserve ses `pair_counts`; aucune causalité n'est inférée.


### LINK/USDC — 4h

Période `2026-01-04T04:00:00+00:00` à `2026-07-24T12:00:00+00:00` (fin
exclusive), 1208 bougies.

#### Observations, transitions et ordres

- observations : 1208 ;
- accepted/rejected : 0/1208
  (taux 0) ;
- transitions false→true / true→false :
  0/0 ;
- durées accepted : `{"count": 0}` ;
- durées rejected : `{"count": 1, "minimum": "1208", "q10": "1208", "q25": "1208", "median": "1208", "q75": "1208", "q90": "1208", "maximum": "1208", "mean": "1208"}` ;
- stades de rejet : `{"rsi": 1070, "trend": 138}` ;
- ordres total/exécutés/rejetés/annulés :
  0/0/0/0 ;
- raisons opérationnelles : `{}`.

L'écart transitions/trades vient de `next_open`, des répétitions accepted, de
l'état de position, des ordres de fin de données et de `force_close`.

#### Sorties, distribution et concentration

Sorties : `{}`.

Distribution : `{"duration_bars": {"count": 0}, "fees": {"count": 0}, "maximum_losing_streak": 0, "maximum_winning_streak": 0, "pnl": {"count": 0}, "return_ratio": {"count": 0}, "seconds_between_trades": {"count": 0}}`.

| Extrême | P&L | Part du total | Interprétation |
|---|---:|---:|---|
| meilleur | 0 | None | undefined_zero_total |
| 3 meilleurs | 0 | None | undefined_zero_total |
| 5 meilleurs | 0 | None | undefined_zero_total |
| top 10 % | 0 | None | undefined_zero_total |
| 5 pires | 0 | None | undefined_zero_total |

#### Couverture, directions, signaux et states

| Indicateur | Observations | Statuts | Entrées | Directions aux entrées |
|---|---:|---|---:|---|
| rsi | 1208 | {"insufficient_data": 13, "available": 1195} | 0 | {} |
| sma | 1208 | {"missing": 1208} | 0 | {} |
| ema | 1208 | {"missing": 1208} | 0 | {} |
| macd | 1208 | {"insufficient_data": 32, "available": 1176} | 0 | {} |
| bollinger | 1208 | {"insufficient_data": 18, "available": 1190} | 0 | {} |
| stochastic | 1208 | {"insufficient_data": 15, "available": 1193} | 0 | {} |

Les associations direction/signal/state avec rendement et P&L des trades
d'entrée sont descriptives et gardent leur effectif :

```json
{
  "bollinger": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "ema": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "macd": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "rsi": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "sma": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "stochastic": {
    "direction": {},
    "signal": {},
    "state": {}
  }
}
```

#### Confluence et tendance

Confluence (buckets fixés avant mesure) :

```json
{
  "all": {
    "grades": {
      "C": 7,
      "D": 80,
      "F": 1121
    },
    "predefined_buckets": {
      "low:<40": 817,
      "medium:40-69.999": 391
    },
    "sample_size": 1208,
    "scores": {
      "count": 1208,
      "maximum": "65",
      "mean": "35.01528973509933774834437086",
      "median": "36",
      "minimum": "0",
      "q10": "20.75",
      "q25": "27.75",
      "q75": "42.25",
      "q90": "48.25"
    }
  },
  "entries": {
    "grades": {},
    "predefined_buckets": {},
    "sample_size": 0,
    "scores": {
      "count": 0
    }
  },
  "exits": {
    "grades": {},
    "predefined_buckets": {},
    "sample_size": 0,
    "scores": {
      "count": 0
    }
  },
  "losing_entries": {
    "grades": {},
    "predefined_buckets": {},
    "sample_size": 0,
    "scores": {
      "count": 0
    }
  },
  "winning_entries": {
    "grades": {},
    "predefined_buckets": {},
    "sample_size": 0,
    "scores": {
      "count": 0
    }
  }
}
```

Tendance :

```json
{
  "entry_trade_performance": {},
  "observation_states": {
    "bearish": 52,
    "bearish,bullish": 37,
    "bearish,bullish,neutral": 74,
    "bearish,bullish,unavailable": 163,
    "bearish,neutral": 93,
    "bearish,neutral,unavailable": 413,
    "bearish,unavailable": 343,
    "bullish,neutral,unavailable": 12,
    "neutral,unavailable": 21
  },
  "provenance": "SignalObservation.trend_states (facteur historique multi-timeframe, distinct de SMA/EMA structurés)"
}
```

#### Outcomes et horizons

| Horizon | Outcomes | Censurés | Moyenne | Médiane | Taux positif | Moy. accepted | Moy. rejected |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1208 | 2 | -0.002619633060033167495854063018 | -0.001998002 | 0.4270315091210613598673300166 | None | -0.002619633060033167495854063018 |
| 3 | 1208 | 4 | -0.003218468629651162790697674419 | -0.00281436695 | 0.4526578073089700996677740864 | None | -0.003218468629651162790697674419 |
| 6 | 1208 | 7 | -0.004135376992089925062447960033 | -0.0031491 | 0.4487926727726894254787676936 | None | -0.004135376992089925062447960033 |
| 12 | 1208 | 13 | -0.006022323699079497907949790795 | -0.006226824 | 0.4368200836820083682008368201 | None | -0.006022323699079497907949790795 |
| 24 | 1208 | 25 | -0.01005374481141166525781910397 | -0.007696219 | 0.4497041420118343195266272189 | None | -0.01005374481141166525781910397 |

Comparaison outcomes/portefeuille :
`{"accepted_observation_count": 0, "accepted_observations_without_distinct_entry": 0, "entry_trade_count": 0, "note": "les outcomes sont indépendants; le portefeuille ignore les répétitions accepted pendant une position et ne somme jamais les outcomes", "outcome_count": 6040}`.

#### Périodes calendaires

| Année | Observations | Trades | Rendement | Drawdown |
|---|---:|---:|---:|---:|
| 2026 | 1208 | 0 | 0 | 0 |

#### Sensibilité aux coûts et au sizing

| Famille | Valeur | Trades | Rendement | Drawdown | Frais | Profit factor |
|---|---:|---:|---:|---:|---:|---:|
| fees | 0 | 0 | 0 | 0 | 0 | None |
| fees | 0.0005 | 0 | 0 | 0 | 0 | None |
| fees | 0.001 | 0 | 0 | 0 | 0 | None |
| fees | 0.002 | 0 | 0 | 0 | 0 | None |
| slippage | 0 | 0 | 0 | 0 | 0 | None |
| slippage | 0.0005 | 0 | 0 | 0 | 0 | None |
| slippage | 0.001 | 0 | 0 | 0 | 0 | None |
| slippage | 0.002 | 0 | 0 | 0 | 0 | None |
| sizing | 25 | 0 | 0 | 0 | 0 | None |
| sizing | 50 | 0 | 0 | 0 | 0 | None |
| sizing | 100 | 0 | 0 | 0 | 0 | None |

#### Ablations et corrélations existantes

| Ablation | Facteurs retirés | Accepted | Delta |
|---|---|---:|---:|
| bollinger | bollinger | 0 | 0 |
| group:confirmation | bollinger, macd | 0 | 0 |
| group:momentum | rsi, stochastic | 0 | 0 |
| group:trend | trend | 0 | 0 |
| macd | macd | 0 | 0 |
| rsi | rsi | 0 | 0 |
| stochastic | stochastic | 0 | 0 |
| trend | trend | 0 | 0 |

Les ablations ci-dessus recalculent descriptivement la confluence et ses outcomes,
pas le portefeuille. Corrélations disponibles par horizon :
`["1", "12", "24", "3", "6"]`.
Chaque matrice existante conserve ses `pair_counts`; aucune causalité n'est inférée.


### ONDO/USDC — 1h

Période `2026-05-22T02:00:00+00:00` à `2026-07-23T14:00:00+00:00` (fin
exclusive), 1500 bougies.

#### Observations, transitions et ordres

- observations : 1500 ;
- accepted/rejected : 0/1500
  (taux 0) ;
- transitions false→true / true→false :
  0/0 ;
- durées accepted : `{"count": 0}` ;
- durées rejected : `{"count": 1, "minimum": "1500", "q10": "1500", "q25": "1500", "median": "1500", "q75": "1500", "q90": "1500", "maximum": "1500", "mean": "1500"}` ;
- stades de rejet : `{"rsi": 1372, "trend": 128}` ;
- ordres total/exécutés/rejetés/annulés :
  0/0/0/0 ;
- raisons opérationnelles : `{}`.

L'écart transitions/trades vient de `next_open`, des répétitions accepted, de
l'état de position, des ordres de fin de données et de `force_close`.

#### Sorties, distribution et concentration

Sorties : `{}`.

Distribution : `{"duration_bars": {"count": 0}, "fees": {"count": 0}, "maximum_losing_streak": 0, "maximum_winning_streak": 0, "pnl": {"count": 0}, "return_ratio": {"count": 0}, "seconds_between_trades": {"count": 0}}`.

| Extrême | P&L | Part du total | Interprétation |
|---|---:|---:|---|
| meilleur | 0 | None | undefined_zero_total |
| 3 meilleurs | 0 | None | undefined_zero_total |
| 5 meilleurs | 0 | None | undefined_zero_total |
| top 10 % | 0 | None | undefined_zero_total |
| 5 pires | 0 | None | undefined_zero_total |

#### Couverture, directions, signaux et states

| Indicateur | Observations | Statuts | Entrées | Directions aux entrées |
|---|---:|---|---:|---|
| rsi | 1500 | {"insufficient_data": 13, "available": 1487} | 0 | {} |
| sma | 1500 | {"missing": 1500} | 0 | {} |
| ema | 1500 | {"missing": 1500} | 0 | {} |
| macd | 1500 | {"insufficient_data": 32, "available": 1468} | 0 | {} |
| bollinger | 1500 | {"insufficient_data": 18, "available": 1482} | 0 | {} |
| stochastic | 1500 | {"insufficient_data": 15, "available": 1485} | 0 | {} |

Les associations direction/signal/state avec rendement et P&L des trades
d'entrée sont descriptives et gardent leur effectif :

```json
{
  "bollinger": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "ema": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "macd": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "rsi": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "sma": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "stochastic": {
    "direction": {},
    "signal": {},
    "state": {}
  }
}
```

#### Confluence et tendance

Confluence (buckets fixés avant mesure) :

```json
{
  "all": {
    "grades": {
      "A": 4,
      "B": 20,
      "C": 84,
      "D": 278,
      "F": 1114
    },
    "predefined_buckets": {
      "high:>=70": 24,
      "low:<40": 607,
      "medium:40-69.999": 869
    },
    "sample_size": 1500,
    "scores": {
      "count": 1500,
      "maximum": "87.08",
      "mean": "42.44819333333333333333333333",
      "median": "42.42",
      "minimum": "16.42",
      "q10": "27.67",
      "q25": "34.5",
      "q75": "50.75",
      "q90": "56.33"
    }
  },
  "entries": {
    "grades": {},
    "predefined_buckets": {},
    "sample_size": 0,
    "scores": {
      "count": 0
    }
  },
  "exits": {
    "grades": {},
    "predefined_buckets": {},
    "sample_size": 0,
    "scores": {
      "count": 0
    }
  },
  "losing_entries": {
    "grades": {},
    "predefined_buckets": {},
    "sample_size": 0,
    "scores": {
      "count": 0
    }
  },
  "winning_entries": {
    "grades": {},
    "predefined_buckets": {},
    "sample_size": 0,
    "scores": {
      "count": 0
    }
  }
}
```

Tendance :

```json
{
  "entry_trade_performance": {},
  "observation_states": {
    "bearish,bullish,neutral": 76,
    "bearish,neutral": 288,
    "bullish,neutral": 167,
    "bullish,neutral,unavailable": 237,
    "neutral": 204,
    "neutral,unavailable": 528
  },
  "provenance": "SignalObservation.trend_states (facteur historique multi-timeframe, distinct de SMA/EMA structurés)"
}
```

#### Outcomes et horizons

| Horizon | Outcomes | Censurés | Moyenne | Médiane | Taux positif | Moy. accepted | Moy. rejected |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1500 | 2 | -0.001909822670827770360480640854 | -0.00260822235 | 0.4072096128170894526034712951 | None | -0.001909822670827770360480640854 |
| 3 | 1500 | 4 | -0.001810375083221925133689839572 | -0.00314663335 | 0.4224598930481283422459893048 | None | -0.001810375083221925133689839572 |
| 6 | 1500 | 7 | -0.001672353815070328198258539853 | -0.0022916184 | 0.4514400535833891493636972539 | None | -0.001672353815070328198258539853 |
| 12 | 1500 | 13 | -0.001656847359919300605245460659 | -0.0042313824 | 0.4384667114996637525218560861 | None | -0.001656847359919300605245460659 |
| 24 | 1500 | 25 | -0.0007231587047457627118644067797 | -0.0052030479 | 0.4535593220338983050847457627 | None | -0.0007231587047457627118644067797 |

Comparaison outcomes/portefeuille :
`{"accepted_observation_count": 0, "accepted_observations_without_distinct_entry": 0, "entry_trade_count": 0, "note": "les outcomes sont indépendants; le portefeuille ignore les répétitions accepted pendant une position et ne somme jamais les outcomes", "outcome_count": 7500}`.

#### Périodes calendaires

| Année | Observations | Trades | Rendement | Drawdown |
|---|---:|---:|---:|---:|
| 2026 | 1500 | 0 | 0 | 0 |

#### Sensibilité aux coûts et au sizing

| Famille | Valeur | Trades | Rendement | Drawdown | Frais | Profit factor |
|---|---:|---:|---:|---:|---:|---:|
| fees | 0 | 0 | 0 | 0 | 0 | None |
| fees | 0.0005 | 0 | 0 | 0 | 0 | None |
| fees | 0.001 | 0 | 0 | 0 | 0 | None |
| fees | 0.002 | 0 | 0 | 0 | 0 | None |
| slippage | 0 | 0 | 0 | 0 | 0 | None |
| slippage | 0.0005 | 0 | 0 | 0 | 0 | None |
| slippage | 0.001 | 0 | 0 | 0 | 0 | None |
| slippage | 0.002 | 0 | 0 | 0 | 0 | None |
| sizing | 25 | 0 | 0 | 0 | 0 | None |
| sizing | 50 | 0 | 0 | 0 | 0 | None |
| sizing | 100 | 0 | 0 | 0 | 0 | None |

#### Ablations et corrélations existantes

| Ablation | Facteurs retirés | Accepted | Delta |
|---|---|---:|---:|
| bollinger | bollinger | 0 | 0 |
| group:confirmation | bollinger, macd | 0 | 0 |
| group:momentum | rsi, stochastic | 0 | 0 |
| group:trend | trend | 0 | 0 |
| macd | macd | 0 | 0 |
| rsi | rsi | 0 | 0 |
| stochastic | stochastic | 0 | 0 |
| trend | trend | 0 | 0 |

Les ablations ci-dessus recalculent descriptivement la confluence et ses outcomes,
pas le portefeuille. Corrélations disponibles par horizon :
`["1", "12", "24", "3", "6"]`.
Chaque matrice existante conserve ses `pair_counts`; aucune causalité n'est inférée.


### SUI/USDC — 1h

Période `2026-05-23T03:00:00+00:00` à `2026-07-24T15:00:00+00:00` (fin
exclusive), 1500 bougies.

#### Observations, transitions et ordres

- observations : 1500 ;
- accepted/rejected : 1/1499
  (taux 0.0006666666666666666666666666667) ;
- transitions false→true / true→false :
  1/1 ;
- durées accepted : `{"count": 1, "minimum": "1", "q10": "1", "q25": "1", "median": "1", "q75": "1", "q90": "1", "maximum": "1", "mean": "1"}` ;
- durées rejected : `{"count": 2, "minimum": "468", "q10": "468", "q25": "468", "median": "749.5", "q75": "468", "q90": "468", "maximum": "1031", "mean": "749.5"}` ;
- stades de rejet : `{"none": 1, "rsi": 1364, "trend": 135}` ;
- ordres total/exécutés/rejetés/annulés :
  2/2/0/0 ;
- raisons opérationnelles : `{}`.

L'écart transitions/trades vient de `next_open`, des répétitions accepted, de
l'état de position, des ordres de fin de données et de `force_close`.

#### Sorties, distribution et concentration

Sorties : `{"validation_lost": {"average_duration_bars": "1", "average_return": "-0.0015940616318382103595271431", "total_pnl": "-15.940616318382103595271431", "total_return": "-0.0015940616318382103595271431", "trade_count": 1, "win_rate": "0"}}`.

Distribution : `{"duration_bars": {"count": 1, "maximum": "1", "mean": "1", "median": "1", "minimum": "1", "q10": "1", "q25": "1", "q75": "1", "q90": "1"}, "fees": {"count": 1, "maximum": "19.98406342712872664302777632", "mean": "19.98406342712872664302777632", "median": "19.98406342712872664302777632", "minimum": "19.98406342712872664302777632", "q10": "19.98406342712872664302777632", "q25": "19.98406342712872664302777632", "q75": "19.98406342712872664302777632", "q90": "19.98406342712872664302777632"}, "maximum_losing_streak": 1, "maximum_winning_streak": 0, "pnl": {"count": 1, "maximum": "-15.940616318382103595271431", "mean": "-15.940616318382103595271431", "median": "-15.940616318382103595271431", "minimum": "-15.940616318382103595271431", "q10": "-15.940616318382103595271431", "q25": "-15.940616318382103595271431", "q75": "-15.940616318382103595271431", "q90": "-15.940616318382103595271431"}, "return_ratio": {"count": 1, "maximum": "-0.0015940616318382103595271431", "mean": "-0.0015940616318382103595271431", "median": "-0.0015940616318382103595271431", "minimum": "-0.0015940616318382103595271431", "q10": "-0.0015940616318382103595271431", "q25": "-0.0015940616318382103595271431", "q75": "-0.0015940616318382103595271431", "q90": "-0.0015940616318382103595271431"}, "seconds_between_trades": {"count": 0}}`.

| Extrême | P&L | Part du total | Interprétation |
|---|---:|---:|---|
| meilleur | -15.940616318382103595271431 | 1 | signed_against_non_positive_total |
| 3 meilleurs | -15.940616318382103595271431 | 1 | signed_against_non_positive_total |
| 5 meilleurs | -15.940616318382103595271431 | 1 | signed_against_non_positive_total |
| top 10 % | -15.940616318382103595271431 | 1 | signed_against_non_positive_total |
| 5 pires | -15.940616318382103595271431 | 1 | signed_against_non_positive_total |

#### Couverture, directions, signaux et states

| Indicateur | Observations | Statuts | Entrées | Directions aux entrées |
|---|---:|---|---:|---|
| rsi | 1500 | {"insufficient_data": 13, "available": 1487} | 1 | {"bullish": 1} |
| sma | 1500 | {"missing": 1500} | 1 | {} |
| ema | 1500 | {"missing": 1500} | 1 | {} |
| macd | 1500 | {"insufficient_data": 32, "available": 1468} | 1 | {"bearish": 1} |
| bollinger | 1500 | {"insufficient_data": 18, "available": 1482} | 1 | {"bullish": 1} |
| stochastic | 1500 | {"insufficient_data": 15, "available": 1485} | 1 | {"bullish": 1} |

Les associations direction/signal/state avec rendement et P&L des trades
d'entrée sont descriptives et gardent leur effectif :

```json
{
  "bollinger": {
    "direction": {
      "bullish": {
        "average_return": "-0.0015940616318382103595271431",
        "total_pnl": "-15.940616318382103595271431",
        "trade_count": 1
      }
    },
    "signal": {
      "oversold": {
        "average_return": "-0.0015940616318382103595271431",
        "total_pnl": "-15.940616318382103595271431",
        "trade_count": 1
      }
    },
    "state": {
      "oversold": {
        "average_return": "-0.0015940616318382103595271431",
        "total_pnl": "-15.940616318382103595271431",
        "trade_count": 1
      }
    }
  },
  "ema": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "macd": {
    "direction": {
      "bearish": {
        "average_return": "-0.0015940616318382103595271431",
        "total_pnl": "-15.940616318382103595271431",
        "trade_count": 1
      }
    },
    "signal": {
      "below_signal": {
        "average_return": "-0.0015940616318382103595271431",
        "total_pnl": "-15.940616318382103595271431",
        "trade_count": 1
      }
    },
    "state": {
      "below_signal/below_zero": {
        "average_return": "-0.0015940616318382103595271431",
        "total_pnl": "-15.940616318382103595271431",
        "trade_count": 1
      }
    }
  },
  "rsi": {
    "direction": {
      "bullish": {
        "average_return": "-0.0015940616318382103595271431",
        "total_pnl": "-15.940616318382103595271431",
        "trade_count": 1
      }
    },
    "signal": {
      "near_oversold": {
        "average_return": "-0.0015940616318382103595271431",
        "total_pnl": "-15.940616318382103595271431",
        "trade_count": 1
      }
    },
    "state": {
      "near_oversold": {
        "average_return": "-0.0015940616318382103595271431",
        "total_pnl": "-15.940616318382103595271431",
        "trade_count": 1
      }
    }
  },
  "sma": {
    "direction": {},
    "signal": {},
    "state": {}
  },
  "stochastic": {
    "direction": {
      "bullish": {
        "average_return": "-0.0015940616318382103595271431",
        "total_pnl": "-15.940616318382103595271431",
        "trade_count": 1
      }
    },
    "signal": {
      "bullish_cross": {
        "average_return": "-0.0015940616318382103595271431",
        "total_pnl": "-15.940616318382103595271431",
        "trade_count": 1
      }
    },
    "state": {
      "oversold": {
        "average_return": "-0.0015940616318382103595271431",
        "total_pnl": "-15.940616318382103595271431",
        "trade_count": 1
      }
    }
  }
}
```

#### Confluence et tendance

Confluence (buckets fixés avant mesure) :

```json
{
  "all": {
    "grades": {
      "C": 13,
      "D": 65,
      "F": 1422
    },
    "predefined_buckets": {
      "low:<40": 1119,
      "medium:40-69.999": 381
    },
    "sample_size": 1500,
    "scores": {
      "count": 1500,
      "maximum": "68.58",
      "mean": "32.66523333333333333333333333",
      "median": "32.835",
      "minimum": "0",
      "q10": "18.25",
      "q25": "26.25",
      "q75": "40.25",
      "q90": "47.83"
    }
  },
  "entries": {
    "grades": {
      "C": 1
    },
    "predefined_buckets": {
      "medium:40-69.999": 1
    },
    "sample_size": 1,
    "scores": {
      "count": 1,
      "maximum": "66.67",
      "mean": "66.67",
      "median": "66.67",
      "minimum": "66.67",
      "q10": "66.67",
      "q25": "66.67",
      "q75": "66.67",
      "q90": "66.67"
    }
  },
  "exits": {
    "grades": {
      "F": 1
    },
    "predefined_buckets": {
      "medium:40-69.999": 1
    },
    "sample_size": 1,
    "scores": {
      "count": 1,
      "maximum": "47",
      "mean": "47",
      "median": "47",
      "minimum": "47",
      "q10": "47",
      "q25": "47",
      "q75": "47",
      "q90": "47"
    }
  },
  "losing_entries": {
    "grades": {
      "C": 1
    },
    "predefined_buckets": {
      "medium:40-69.999": 1
    },
    "sample_size": 1,
    "scores": {
      "count": 1,
      "maximum": "66.67",
      "mean": "66.67",
      "median": "66.67",
      "minimum": "66.67",
      "q10": "66.67",
      "q25": "66.67",
      "q75": "66.67",
      "q90": "66.67"
    }
  },
  "winning_entries": {
    "grades": {},
    "predefined_buckets": {},
    "sample_size": 0,
    "scores": {
      "count": 0
    }
  }
}
```

Tendance :

```json
{
  "entry_trade_performance": {
    "bearish,bullish": {
      "average_return": "-0.0015940616318382103595271431",
      "total_pnl": "-15.940616318382103595271431",
      "trade_count": 1
    }
  },
  "observation_states": {
    "bearish": 144,
    "bearish,bullish": 136,
    "bearish,bullish,neutral": 200,
    "bearish,neutral": 280,
    "bearish,unavailable": 740
  },
  "provenance": "SignalObservation.trend_states (facteur historique multi-timeframe, distinct de SMA/EMA structurés)"
}
```

#### Outcomes et horizons

| Horizon | Outcomes | Censurés | Moyenne | Médiane | Taux positif | Moy. accepted | Moy. rejected |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1500 | 2 | -0.002447438214085447263017356475 | -0.00239731085 | 0.3811748998664886515353805073 | -0.0002475937 | -0.00244890771609886439545758183 |
| 3 | 1500 | 4 | -0.002857485869050802139037433155 | -0.00269449425 | 0.403074866310160427807486631 | 0.0017721081 | -0.002860582587424749163879598662 |
| 6 | 1500 | 7 | -0.003408843792900200937709310114 | -0.0031879885 | 0.4226389819156061620897521768 | -0.0037484103 | -0.003408616201407506702412868633 |
| 12 | 1500 | 13 | -0.004567616081708137188971082717 | -0.0035945923 | 0.4236718224613315400134498991 | 0.0132170851 | -0.004579584252086137281292059219 |
| 24 | 1500 | 25 | -0.007218731308881355932203389831 | -0.0061529929 | 0.4108474576271186440677966102 | 0.00756192 | -0.007228758887788331071913161465 |

Comparaison outcomes/portefeuille :
`{"accepted_observation_count": 1, "accepted_observations_without_distinct_entry": 0, "entry_trade_count": 1, "note": "les outcomes sont indépendants; le portefeuille ignore les répétitions accepted pendant une position et ne somme jamais les outcomes", "outcome_count": 7500}`.

#### Périodes calendaires

| Année | Observations | Trades | Rendement | Drawdown |
|---|---:|---:|---:|---:|
| 2026 | 1500 | 1 | -0.0015940616318382103595271431 | 0.0015940616318382103595271431 |

#### Sensibilité aux coûts et au sizing

| Famille | Valeur | Trades | Rendement | Drawdown | Frais | Profit factor |
|---|---:|---:|---:|---:|---:|---:|
| fees | 0 | 1 | 0.00040474905558553696708041 | 0.0002696508022111365781313198437 | 0 | None |
| fees | 0.0005 | 1 | -0.0005951557410717199414324139 | 0.0007695159768100310098422543534 | 9.997025232661596886392205947 | 0 |
| fees | 0.001 | 1 | -0.0015940616318382103595271431 | 0.0015940616318382103595271431 | 19.98406342712872664302777632 | 0 |
| fees | 0.002 | 1 | -0.0035888826771712915238061384 | 0.0035888826771712915238061384 | 39.9282385041035037318778525 | 0 |
| slippage | 0 | 1 | -0.0015940616318382103595271431 | 0.0015940616318382103595271431 | 19.98406342712872664302777632 | 0 |
| slippage | 0.0005 | 1 | -0.0025919686167139342872037776 | 0.0025919686167139342872037776 | 19.97407436822106173884682903 | 0 |
| slippage | 0.001 | 1 | -0.0035888786915148572918757405 | 0.0035888786915148572918757405 | 19.96409528839322467173299557 | 0 |
| slippage | 0.002 | 1 | -0.0055797140804137065257565757 | 0.0055797140804137065257565757 | 19.94416700622206501974219642 | 0 |
| sizing | 25 | 1 | -0.0003985154079595525898817857 | 0.0003985154079595525898817857 | 4.996015856782181660756944083 | 0 |
| sizing | 50 | 1 | -0.0007970308159191051797635715 | 0.0007970308159191051797635715 | 9.992031713564363321513888163 | 0 |
| sizing | 100 | 1 | -0.0015940616318382103595271431 | 0.0015940616318382103595271431 | 19.98406342712872664302777632 | 0 |

#### Ablations et corrélations existantes

| Ablation | Facteurs retirés | Accepted | Delta |
|---|---|---:|---:|
| bollinger | bollinger | 0 | -1 |
| group:confirmation | bollinger, macd | 1 | 0 |
| group:momentum | rsi, stochastic | 0 | -1 |
| group:trend | trend | 1 | 0 |
| macd | macd | 1 | 0 |
| rsi | rsi | 1 | 0 |
| stochastic | stochastic | 1 | 0 |
| trend | trend | 1 | 0 |

Les ablations ci-dessus recalculent descriptivement la confluence et ses outcomes,
pas le portefeuille. Corrélations disponibles par horizon :
`["1", "12", "24", "3", "6"]`.
Chaque matrice existante conserve ses `pair_counts`; aucune causalité n'est inférée.


## Limites méthodologiques

- Les historiques hors BTC sont courts et presque tous cotés en USDC.
- Une majorité des 851 combinaisons locales est non évaluable.
- Les catégories rares, corrélations et ablations sont descriptives, non causales.
- Le moteur v1 est mono-symbole, spot long-only, sans stop ni short.
- Les résultats du test final ne doivent servir à aucun réglage de cette baseline.

## Faiblesses, points robustes et éléments non concluants

Les faiblesses sont limitées aux faits chiffrés ci-dessus. Les garanties robustes
sont la causalité, la déterminisme, la séparation outcomes/portefeuille et la
sensibilité monotone attendue aux coûts. Les indicateurs ou catégories à faible
effectif restent non concluants et ne doivent pas être modifiés faute de preuve.

## Proposition unique de Phase 7.2

Expérience proposée : **goulot d'acceptation `rsi`**. Preuve de sélection :
22 trades au total et 11763 rejets au stade `rsi`; l'échantillon économique est insuffisant. Hypothèse : une modification minimale du seul stade `rsi` peut produire un échantillon évaluable sans dégrader fortement le drawdown.

Métrique principale : rendement validation. Garde-fous : drawdown pas dégradé de
plus de 10 % relatif, nombre de trades au moins 80 % de la baseline, frais non
accrus, effet présent sur au moins deux marchés/périodes. Abandon : gain limité au
développement, test final consulté avant gel, ou dégradation d'un garde-fou.
Le test final demeure gelé jusqu'à la fin de cette future expérience. Cette
expérience n'est pas exécutée en Phase 7.1.

## État Git et périmètre final

État initial : branche `main`, HEAD `770f002`. L'arbre contenait déjà les
modifications et nouveaux fichiers de la Phase 6.6 portefeuille, dont
`backend/app/models/portfolio.py`, ses tests, la documentation portefeuille et
les fichiers frontend de simulation. Git exigeait `safe.directory` à cause du
propriétaire Windows ; chaque commande a utilisé `git -c safe.directory=...`
sans modifier la configuration globale.

Cette phase ajoute uniquement le module/CLI d'audit, deux fichiers de tests et
quatre documents de baseline, puis complète `CURRENT_APP_STATE_FOR_AI.md`.
Deux annotations de typage du script portefeuille préexistant ont été corrigées
pour satisfaire la nouvelle commande `mypy app scripts`, sans changement de
runtime. Aucun fichier de production des signaux, route, migration, contrat
public, dépendance, lockfile ou fichier frontend n'a été modifié par la Phase
7.1. Aucun commit ni `git add` n'a été exécuté.

## Reproductibilité quick et full

- quick injecté `2026-07-30T10:00:00Z` : 1 combinaison, 400 observations,
  0 accepted, 0 trade, 59,72 s ;
- full initial : 5 combinaisons, 12 973 observations, 22 trades, 1 793,20 s ;
- full détaillé répété avec le même timestamp : 5 combinaisons, 12 973
  observations, 22 trades, 1 805,89 s ;
- fingerprint d'audit :
  `sha256:7a35c7442778828cd207b6fbaee4a6d8390d6bb8fcb7d79751030d433b44a1b6` ;
- base historique ouverte en lecture seule, aucun réseau, SQLite temporaire
  supprimée ; les sorties quick temporaires et logs ont été nettoyés.

Le timestamp étant injecté, la sélection, les fingerprints, les métriques, le
classement et les conclusions sont déterministes. Le temps mural reste
dépendant de la machine.

## Validation

Backend ciblé :

```text
144 passed, 1 skipped in 10.04s
```

Il couvre les 17 tests propres à l'audit, le domaine portefeuille, replay,
repository et les tests de backtest ciblés.

Backend complet :

```text
678 passed, 1 skipped, 27 subtests passed in 24.45s
2 warnings pandas préexistants dans market_data.py
compileall app scripts : réussi
Black app tests scripts : 130 fichiers inchangés
Flake8 app tests scripts : réussi
mypy app scripts : 83 fichiers, aucun problème
```

Frontend non-régression :

```text
pnpm install --frozen-lockfile --offline : réussi
typecheck : réussi
lint : réussi
Vitest : 48 fichiers, 299 tests réussis
build : 2 065 modules transformés
```

Le lockfile est inchangé. `git diff --check` est vide. Aucun artefact SQLite,
CSV, equity brute, gros JSON, log ou export temporaire n'est suivi.

## Extraits de référence

Configuration canonique :

```python
PortfolioSimulationConfig(
    quote_asset="USDC",
    initial_capital=Decimal("10000"),
    position_size_percent=Decimal("100"),
    fee_rate=Decimal("0.001"),
    slippage_rate=Decimal("0"),
    execution_policy=ExecutionPolicy.NEXT_OPEN,
    end_of_test_policy=EndOfTestPolicy.FORCE_CLOSE,
)
```

Découpage chronologique :

```python
development_end = int(len(timestamps) * Decimal("0.60"))
validation_end = int(len(timestamps) * Decimal("0.80"))
development = timestamps[:development_end]
validation = timestamps[development_end:validation_end]
test_final = timestamps[validation_end:]
```

Concentration des profits :

```python
total = sum(pnls, Decimal("0"))
amount = sum(values, Decimal("0"))
share = amount / total if total != 0 else None
top_five = contribution(sorted(pnls, reverse=True)[:5])
```

Lancement reproductible :

```powershell
cd backend
.\venv\Scripts\python.exe scripts\audit_signal_strategy_baseline.py `
  --mode full `
  --generated-at 2026-07-30T10:00:00Z
```

Test anti-look-ahead :

```python
development, validation, test = chronological_segments(timestamps)
assert development.end_index == validation.start_index
assert validation.end_index == test.start_index
assert development.end < validation.start < test.start
```

## Plan précis de la Phase 7.2

- cible unique : stade d'acceptation RSI, responsable de 11 763 rejets ;
- hypothèse : une modification minimale de ce seul stade peut produire un
  échantillon évaluable sans dégrader fortement le drawdown ;
- développement : segment 60 % uniquement ;
- validation : segment 20 % suivant, paramètres gelés ;
- test final : dernier 20 %, non consulté avant sélection définitive ;
- métrique principale : rendement du portefeuille sur validation ;
- garde-fous : drawdown relatif dégradé de moins de 10 %, effectif de trades
  suffisant, frais non accrus, résultat visible sur plusieurs marchés/périodes,
  aucune fuite temporelle ;
- succès : amélioration développement confirmée sur validation avec tous les
  garde-fous ;
- abandon : gain limité au développement, moins de données économiques
  exploitables, dégradation d'un garde-fou ou sensibilité excessive ;
- risque principal : assouplir le RSI jusqu'à sélectionner a posteriori une
  période BTC favorable.

La Phase 7.2 n'est pas commencée.
