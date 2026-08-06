# Audit du dataset ML v2 réel

## Résumé exécutif

Conclusion calculée : `accepted_with_reservations`.
Ce rapport évalue uniquement la qualité technique et causale des données. Aucun modèle
n'a été entraîné et aucune période terminale de test ML v2 n'a été définie.

## Identification

- Dataset : `sha256:b580dbfc68d462649a4d06e493375533d8045ec0b7b9f8f189f810cbcad9fb57`
- Job source : `ebf1e0328c4346d69b02a0d1de802303`
- Source identity : `sha256:b864504e19dfe40070942469d3849241d585cf4a1a54ad48c633efdb9c3952df`
- Input fingerprint : `sha256:7e162fa7341ece55c141affd6dcb142f499e5e2bcb528f7ad1fbbdced4bd5f85`
- Symbole / timeframe : `BTC/USDC` / `4h`
- Bornes : `2020-04-01T04:00:00+00:00` à `2022-09-28T00:00:00+00:00`
- Lignes : `5460`
- SHA-256 JSONL : `sha256:d1d673c4fe96486891aa689de58dde3ac2f181b2459387def4214d109cadf205`
- SHA-256 manifeste : `sha256:1ccfe4dfb0a9b1dda8fab0971dc6cdba6f37ce73b2ebef9fc3bf257c3358ecc2`

## Commandes de reproduction

```text
python -m app.ml.cli.inspect_ml_v2_history BTC/USDC --database-path data/scanner_crypto.sqlite3 --output-json artifacts/ml-v2/btc-usdc-4h-20200401-20220928-causal-v2-7e162fa7/history-inventory.json
```
```text
python -m app.ml.cli.prepare_ml_v2_source BTC/USDC --timeframe 4h --start 2020-04-01T00:00:00Z --end 2022-09-28T00:00:00Z --database-path data/scanner_crypto.sqlite3 --json
```
```text
python -m app.ml.cli.export_ml_dataset ebf1e0328c4346d69b02a0d1de802303 --feature-schema-version causal-features-v2 --database-path data/scanner_crypto.sqlite3 --output-directory artifacts/ml-v2/btc-usdc-4h-20200401-20220928-causal-v2-7e162fa7 --file-stem dataset
```
```text
python -m app.ml.cli.verify_ml_v2_source artifacts/ml-v2/btc-usdc-4h-20200401-20220928-causal-v2-7e162fa7/dataset.manifest.json --database-path data/scanner_crypto.sqlite3 --json
```
```text
python -m app.ml.cli.audit_ml_v2_dataset artifacts/ml-v2/btc-usdc-4h-20200401-20220928-causal-v2-7e162fa7/dataset.manifest.json --database-path data/scanner_crypto.sqlite3 --output-json artifacts/ml-v2/btc-usdc-4h-20200401-20220928-causal-v2-7e162fa7/dataset-audit.json --output-markdown artifacts/ml-v2/btc-usdc-4h-20200401-20220928-causal-v2-7e162fa7/dataset-audit.md --json
```

## Couverture et provenance

Vérification source : `reproducible`.
Flux consommés : `3`.
La fenêtre est une fenêtre de développement et d'audit, choisie pour sa continuité,
ses warmups complets et sa couverture des régimes 2020-2022. Elle s'arrête avant le
trou OHLCV observé à partir du 29 septembre 2022.

```json
[
  {
    "candle_count": 5667,
    "closed_only": true,
    "effective_first_open_time_ms": 1582819200000,
    "effective_last_open_time_ms": 1664409600000,
    "exchange_id": "binance",
    "fingerprint": "sha256:538f049650b79176c491b17234be422cb193cc3bc20ddd651a30a282a8d6139d",
    "fingerprint_version": "ohlcv-content-sha256-v1",
    "future_bars": 7,
    "gaps_validated": true,
    "market_type": "spot",
    "requested_end_ms": 1664424000000,
    "requested_start_ms": 1582819200000,
    "role": "primary",
    "symbol": "BTC/USDC",
    "timeframe": "4h",
    "warmup_bars": 200
  },
  {
    "candle_count": 972,
    "closed_only": true,
    "effective_first_open_time_ms": 1580515200000,
    "effective_last_open_time_ms": 1664409600000,
    "exchange_id": "binance",
    "fingerprint": "sha256:bd2a15066c07c4bce330ca42824349b573f046218e6183b813ce76dff453c6da",
    "fingerprint_version": "ohlcv-content-sha256-v1",
    "future_bars": 0,
    "gaps_validated": true,
    "market_type": "spot",
    "requested_end_ms": 1664424000000,
    "requested_start_ms": 1580515200000,
    "role": "trend:1d",
    "symbol": "BTC/USDC",
    "timeframe": "1d",
    "warmup_bars": 60
  },
  {
    "candle_count": 190,
    "closed_only": true,
    "effective_first_open_time_ms": 1549843200000,
    "effective_last_open_time_ms": 1664150400000,
    "exchange_id": "binance",
    "fingerprint": "sha256:3c11c08ac1c1f1296253737b3cb9b055235d909ddff997d64761b5f8a44b3cba",
    "fingerprint_version": "ohlcv-content-sha256-v1",
    "future_bars": 0,
    "gaps_validated": true,
    "market_type": "spot",
    "requested_end_ms": 1664424000000,
    "requested_start_ms": 1549411200000,
    "role": "trend:1w",
    "symbol": "BTC/USDC",
    "timeframe": "1w",
    "warmup_bars": 60
  }
]
```

## Funnel

```json
{
  "candidate_observations_with_h6": 5460,
  "contract_rejection_reasons": {},
  "excluded_rows": 0,
  "exclusions": {
    "censored_outcomes": {
      "count": 0,
      "percent_of_candidates": 0.0
    },
    "contract_rejections": {
      "count": 0,
      "percent_of_candidates": 0.0
    },
    "invalid_outcomes": {
      "count": 0,
      "percent_of_candidates": 0.0
    },
    "missing_natr": {
      "count": 0,
      "percent_of_candidates": 0.0
    }
  },
  "exclusions_priority": [
    "censored_outcomes",
    "invalid_outcomes",
    "missing_natr",
    "contract_rejections"
  ],
  "final_percent_of_candidates": 100.0,
  "final_rows": 5460,
  "processed_rows": 5460,
  "reconciled": true
}
```

## Audit structurel

```json
{
  "actual_feature_count": 675,
  "declared_feature_count": 675,
  "duplicate_decision_time_count": 0,
  "duplicate_observation_id_count": 0,
  "missing_required_features": [],
  "profile_fingerprints": [
    "sha256:858e94686f66c838356598b6b3beeb9f330e8f17177863c44ff6180c2777564c"
  ],
  "profiles": [
    "ml-dataset-v2"
  ],
  "strict_chronological_order": true,
  "symbols": [
    "BTC/USDC"
  ],
  "timeframes": [
    "4h"
  ],
  "valid": true
}
```

## Labels

Distribution : `{"down": 1145, "neutral": 3005, "up": 1310}`.
Pourcentages : `{"down": 20.97069597069597, "neutral": 55.036630036630044, "up": 23.992673992673993}`.
Par année : `{"2020": {"down": 272, "neutral": 931, "up": 446}, "2021": {"down": 472, "neutral": 1170, "up": 548}, "2022": {"down": 401, "neutral": 904, "up": 316}}`.
Plus longues séquences : `{"down": 16, "neutral": 22, "up": 20}`.

## Audit temporel

```json
{
  "by_hour_utc": {
    "00": 910,
    "04": 910,
    "08": 910,
    "12": 910,
    "16": 910,
    "20": 910
  },
  "by_month": {
    "2020-04": 179,
    "2020-05": 186,
    "2020-06": 180,
    "2020-07": 186,
    "2020-08": 186,
    "2020-09": 180,
    "2020-10": 186,
    "2020-11": 180,
    "2020-12": 186,
    "2021-01": 186,
    "2021-02": 168,
    "2021-03": 186,
    "2021-04": 180,
    "2021-05": 186,
    "2021-06": 180,
    "2021-07": 186,
    "2021-08": 186,
    "2021-09": 180,
    "2021-10": 186,
    "2021-11": 180,
    "2021-12": 186,
    "2022-01": 186,
    "2022-02": 168,
    "2022-03": 186,
    "2022-04": 180,
    "2022-05": 186,
    "2022-06": 180,
    "2022-07": 186,
    "2022-08": 186,
    "2022-09": 163
  },
  "by_quarter": {
    "2020-Q2": 545,
    "2020-Q3": 552,
    "2020-Q4": 552,
    "2021-Q1": 540,
    "2021-Q2": 546,
    "2021-Q3": 552,
    "2021-Q4": 552,
    "2022-Q1": 540,
    "2022-Q2": 546,
    "2022-Q3": 535
  },
  "by_weekday_utc": {
    "0": 780,
    "1": 780,
    "2": 780,
    "3": 780,
    "4": 780,
    "5": 780,
    "6": 780
  },
  "by_year": {
    "2020": 1649,
    "2021": 2190,
    "2022": 1621
  },
  "duration_seconds": 78609600,
  "largest_observation_gap_seconds": 14400
}
```

## Features, redondances et valeurs extrêmes

Features constantes : `["availability.adx", "availability.atr", "availability.bollinger", "availability.donchian", "availability.keltner", "availability.macd", "availability.rsi", "availability.stochastic", "availability.supertrend", "availability.trend", "indicator.adx.component.adx.unit", "indicator.adx.component.adx_change.unit", "indicator.adx.component.di_balance.unit", "indicator.adx.component.di_spread.unit", "indicator.adx.component.di_spread_change.unit", "indicator.adx.component.distance_from_strong_threshold.unit", "indicator.adx.component.distance_from_weak_threshold.unit", "indicator.adx.component.dx.unit", "indicator.adx.component.dx_change.unit", "indicator.adx.component.minus_di.unit", "indicator.adx.component.minus_di_change.unit", "indicator.adx.component.plus_di.unit", "indicator.adx.component.plus_di_change.unit", "indicator.adx.component.previous_adx.unit", "indicator.adx.component.previous_di_balance.unit", "indicator.adx.component.previous_di_spread.unit", "indicator.adx.component.previous_dx.unit", "indicator.adx.component.previous_minus_di.unit", "indicator.adx.component.previous_plus_di.unit", "indicator.adx.status", "indicator.atr.component.atr.unit", "indicator.atr.component.atr_change.unit", "indicator.atr.component.natr.unit", "indicator.atr.component.natr_change.unit", "indicator.atr.component.previous_atr.unit", "indicator.atr.component.previous_natr.unit", "indicator.atr.component.previous_true_range.unit", "indicator.atr.component.relative_natr_change.unit", "indicator.atr.component.true_range.unit", "indicator.atr.component.true_range_change.unit", "indicator.atr.direction", "indicator.atr.status", "indicator.bollinger.component.band_position.unit", "indicator.bollinger.component.band_position_change.unit", "indicator.bollinger.component.band_width.unit", "indicator.bollinger.component.band_width_percent.unit", "indicator.bollinger.component.band_width_percent_change.unit", "indicator.bollinger.component.lower_band.unit", "indicator.bollinger.component.middle_band.unit", "indicator.bollinger.component.middle_band_change.unit", "indicator.bollinger.component.previous_band_position.unit", "indicator.bollinger.component.previous_band_width_percent.unit", "indicator.bollinger.component.price_to_lower_distance.unit", "indicator.bollinger.component.price_to_middle_distance.unit", "indicator.bollinger.component.price_to_upper_distance.unit", "indicator.bollinger.component.upper_band.unit", "indicator.bollinger.status", "indicator.donchian.component.channel_position.unit", "indicator.donchian.component.channel_position_change.unit", "indicator.donchian.component.channel_width.unit", "indicator.donchian.component.channel_width_percent.unit", "indicator.donchian.component.channel_width_percent_change.unit", "indicator.donchian.component.lower_channel.unit", "indicator.donchian.component.lower_channel_change.unit", "indicator.donchian.component.middle_channel.unit", "indicator.donchian.component.middle_channel_change.unit", "indicator.donchian.component.previous_channel_position.unit", "indicator.donchian.component.previous_channel_width.unit", "indicator.donchian.component.previous_channel_width_percent.unit", "indicator.donchian.component.previous_lower_channel.unit", "indicator.donchian.component.previous_middle_channel.unit", "indicator.donchian.component.previous_upper_channel.unit", "indicator.donchian.component.price_to_lower_distance.unit", "indicator.donchian.component.price_to_middle_distance.unit", "indicator.donchian.component.price_to_previous_lower_distance.unit", "indicator.donchian.component.price_to_previous_upper_distance.unit", "indicator.donchian.component.price_to_upper_distance.unit", "indicator.donchian.component.upper_channel.unit", "indicator.donchian.component.upper_channel_change.unit", "indicator.donchian.status", "indicator.ema.component.fast.unit", "indicator.ema.component.fast_change.unit", "indicator.ema.component.fast_to_slow_distance.unit", "indicator.ema.component.previous_fast.unit", "indicator.ema.component.previous_slow.unit", "indicator.ema.component.price.normalized_value", "indicator.ema.component.price.unit", "indicator.ema.component.price_to_fast_distance.unit", "indicator.ema.component.price_to_slow_distance.unit", "indicator.ema.component.slow.unit", "indicator.ema.component.slow_change.unit", "indicator.ema.status", "indicator.keltner.component.atr.unit", "indicator.keltner.component.atr_change.unit", "indicator.keltner.component.channel_position.unit", "indicator.keltner.component.channel_position_change.unit", "indicator.keltner.component.channel_width.unit", "indicator.keltner.component.channel_width_change.unit", "indicator.keltner.component.channel_width_percent.unit", "indicator.keltner.component.channel_width_percent_change.unit", "indicator.keltner.component.lower_channel.unit", "indicator.keltner.component.lower_channel_change.unit", "indicator.keltner.component.middle_line.unit", "indicator.keltner.component.middle_line_change.unit", "indicator.keltner.component.previous_atr.unit", "indicator.keltner.component.previous_channel_position.unit", "indicator.keltner.component.previous_channel_width.unit", "indicator.keltner.component.previous_channel_width_percent.unit", "indicator.keltner.component.previous_lower_channel.unit", "indicator.keltner.component.previous_middle_line.unit", "indicator.keltner.component.previous_upper_channel.unit", "indicator.keltner.component.price_to_lower_atr.unit", "indicator.keltner.component.price_to_lower_distance.unit", "indicator.keltner.component.price_to_middle_atr.unit", "indicator.keltner.component.price_to_middle_distance.unit", "indicator.keltner.component.price_to_previous_lower_atr.unit", "indicator.keltner.component.price_to_previous_lower_distance.unit", "indicator.keltner.component.price_to_previous_upper_atr.unit", "indicator.keltner.component.price_to_previous_upper_distance.unit", "indicator.keltner.component.price_to_upper_atr.unit", "indicator.keltner.component.price_to_upper_distance.unit", "indicator.keltner.component.upper_channel.unit", "indicator.keltner.component.upper_channel_change.unit", "indicator.keltner.status", "indicator.macd.component.histogram.unit", "indicator.macd.component.histogram_change.unit", "indicator.macd.component.macd.unit", "indicator.macd.component.macd_change.unit", "indicator.macd.component.previous_histogram.unit", "indicator.macd.component.previous_macd.unit", "indicator.macd.component.previous_signal_line.unit", "indicator.macd.component.relative_distance.unit", "indicator.macd.component.signal_change.unit", "indicator.macd.component.signal_line.unit", "indicator.macd.status", "indicator.rsi.component.change.unit", "indicator.rsi.component.distance_from_midpoint.unit", "indicator.rsi.component.distance_from_overbought.unit", "indicator.rsi.component.distance_from_oversold.unit", "indicator.rsi.component.previous_value.unit", "indicator.rsi.component.rsi.unit", "indicator.rsi.status", "indicator.sma.component.fast.unit", "indicator.sma.component.fast_change.unit", "indicator.sma.component.fast_to_slow_distance.unit", "indicator.sma.component.previous_fast.unit", "indicator.sma.component.previous_slow.unit", "indicator.sma.component.price.normalized_value", "indicator.sma.component.price.unit", "indicator.sma.component.price_to_fast_distance.unit", "indicator.sma.component.price_to_slow_distance.unit", "indicator.sma.component.slow.unit", "indicator.sma.component.slow_change.unit", "indicator.sma.status", "indicator.stochastic.component.d.unit", "indicator.stochastic.component.d_change.unit", "indicator.stochastic.component.k.unit", "indicator.stochastic.component.k_change.unit", "indicator.stochastic.component.previous_d.unit", "indicator.stochastic.component.previous_k.unit", "indicator.stochastic.component.previous_spread.unit", "indicator.stochastic.component.spread.unit", "indicator.stochastic.component.spread_change.unit", "indicator.stochastic.status", "indicator.supertrend.component.atr.unit", "indicator.supertrend.component.atr_change.unit", "indicator.supertrend.component.band_position.unit", "indicator.supertrend.component.band_position_change.unit", "indicator.supertrend.component.band_width.unit", "indicator.supertrend.component.band_width_change.unit", "indicator.supertrend.component.distance_atr.unit", "indicator.supertrend.component.distance_atr_change.unit", "indicator.supertrend.component.distance_ratio.unit", "indicator.supertrend.component.distance_ratio_change.unit", "indicator.supertrend.component.lower_band.unit", "indicator.supertrend.component.lower_band_change.unit", "indicator.supertrend.component.previous_atr.unit", "indicator.supertrend.component.previous_band_position.unit", "indicator.supertrend.component.previous_band_width.unit", "indicator.supertrend.component.previous_distance_atr.unit", "indicator.supertrend.component.previous_distance_ratio.unit", "indicator.supertrend.component.previous_lower_band.unit", "indicator.supertrend.component.previous_supertrend.unit", "indicator.supertrend.component.previous_upper_band.unit", "indicator.supertrend.component.price_to_lower_distance.unit", "indicator.supertrend.component.price_to_supertrend_distance.unit", "indicator.supertrend.component.price_to_upper_distance.unit", "indicator.supertrend.component.supertrend.unit", "indicator.supertrend.component.supertrend_change.unit", "indicator.supertrend.component.upper_band.unit", "indicator.supertrend.component.upper_band_change.unit", "indicator.supertrend.status", "quality.available_bars", "quality.constant_candle_ratio", "quality.zero_volume_ratio"]`.
Features quasi constantes : `["divergence.macd.hidden_bearish.count", "divergence.macd.hidden_bullish.count", "divergence.macd.regular_bearish.count", "divergence.macd.regular_bullish.count", "divergence.rsi.hidden_bearish.count", "divergence.rsi.hidden_bullish.count", "divergence.rsi.regular_bearish.count", "divergence.rsi.regular_bullish.count", "divergence.source.macd.count", "divergence.source.rsi.count", "event.adx.bearish_cross.count", "event.adx.bullish_cross.count", "event.atr.volatility_contraction.count", "event.atr.volatility_expansion.count", "event.bollinger.lower_band_reentry.count", "event.bollinger.lower_band_reentry.max_strength", "event.bollinger.upper_band_reentry.count", "event.bollinger.upper_band_reentry.max_strength", "event.direction.neutral.count", "event.donchian.breakout_down.count", "event.donchian.breakout_up.count", "event.ema.bearish_cross.count", "event.ema.bearish_cross.max_strength", "event.ema.bullish_cross.count", "event.ema.bullish_cross.max_strength", "event.indicator.adx.count", "event.indicator.atr.count", "event.indicator.bollinger.count", "event.indicator.donchian.count", "event.indicator.ema.count", "event.indicator.keltner.count", "event.indicator.macd.count", "event.indicator.rsi.count", "event.indicator.stochastic.count", "event.indicator.supertrend.count", "event.keltner.breakout_down.count", "event.keltner.breakout_up.count", "event.kind.reentry.count", "event.kind.threshold_exit.count", "event.kind.trend_change.count", "event.kind.volatility_regime.count", "event.macd.bearish_cross.count", "event.macd.bullish_cross.count", "event.rsi.exit_overbought.count", "event.rsi.exit_overbought.max_strength", "event.rsi.exit_oversold.count", "event.rsi.exit_oversold.max_strength", "event.stochastic.bearish_cross.count", "event.stochastic.bearish_cross.max_strength", "event.stochastic.bullish_cross.count", "event.stochastic.bullish_cross.max_strength", "event.supertrend.bearish_flip.count", "event.supertrend.bullish_flip.count", "observation.accepted"]`.
Paires fortement corrélées : `1490`.
Exemples extrêmes : `100`.
Les statistiques exhaustives des 675 features, les corrélations et les timestamps
extrêmes sont conservés dans `dataset-audit.json`.
Les seuils extrêmes sont des alertes descriptives ; aucune ligne n'est supprimée.

## Régimes et stabilité temporelle

Les régimes sont des terciles NATR descriptifs calculés sur cette fenêtre de
développement. Ils ne servent ni à sélectionner un modèle ni à optimiser une stratégie.
Segments : `{"high": {"labels": {"down": 315, "neutral": 1085, "up": 420}, "row_count": 1820}, "low": {"labels": {"down": 419, "neutral": 924, "up": 477}, "row_count": 1820}, "medium": {"labels": {"down": 411, "neutral": 996, "up": 413}, "row_count": 1820}}`.
Alertes de dérive annuelle : `49`.

## Audit causal

```json
{
  "method": "deterministic_raw_ohlcv_recalculation",
  "mismatch_count": 0,
  "mismatches": [],
  "numeric_tolerance": "model_contract_and_math_isclose_defaults",
  "observation_ids": [
    4712,
    4725,
    4726,
    4761,
    4762,
    4763,
    4764,
    4765,
    4766,
    4778,
    4779,
    4781,
    4782,
    4793,
    4794,
    4795
  ],
  "sample_size": 16,
  "selection_rule": "boundaries_quartiles_years_labels_natr_extremes",
  "status": "passed"
}
```

## Leak audit

Conclusion : `no_leak_detected_by_defined_checks`.
Cette conclusion est limitée aux contrôles définis et ne signifie pas qu'une fuite
future impossible à concevoir est exclue absolument.

## Contrôles bloquants

- Aucun.

## Alertes non bloquantes

- `constant_features:195`
- `high_feature_correlations:1490`
- `quasi_constant_features:54`
- `source_rows_below_recommended:5460<10000`
- `temporal_drift_alerts:49`

## Limites et Phase 4

Le JSONL n'est pas une période terminale et aucune mesure de performance de modèle
n'a été calculée. La Phase 4 devra figer les partitions chronologiques avant tout
entraînement, preprocessing appris, sélection de features ou benchmark.
