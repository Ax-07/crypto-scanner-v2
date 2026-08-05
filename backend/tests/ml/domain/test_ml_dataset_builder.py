from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ml.domain.ml_dataset import (
    MLDatasetBuildError,
    build_ml_dataset_row,
    classify_market_direction,
    extract_causal_features,
    extract_natr_percent,
)
from app.models.backtest import ForwardOutcome, SignalObservation
from app.ml.models.ml_dataset import (
    ML_FEATURE_SCHEMA_VERSION,
    ML_FEATURE_SCHEMA_VERSION_V2,
    MarketDirectionLabel,
)

DECISION_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def valid_observation(**changes: object) -> SignalObservation:
    """Construit une observation causale persistée avec un NATR disponible."""
    values: dict[str, object] = {
        "id": 42,
        "job_id": "backtest-ml",
        "symbol": "BTC/USDC",
        "timeframe": "1h",
        "decision_time": DECISION_TIME,
        "source_open_time": DECISION_TIME - timedelta(hours=1),
        "snapshot_status": "confirmed",
        "accepted": True,
        "close": 100.0,
        "trend_score": 2,
        "trend_net_score": 1,
        "trend_states": {
            "1h": "bullish",
            "4h": "neutral",
        },
        "confluence_score": 0.75,
        "confluence_grade": "A",
        "confluence_factors": {
            "trend": 0.8,
            "rsi": None,
        },
        "availability": {
            "atr": "available",
            "ema": "available",
        },
        "indicator_signals": {
            "atr": {
                "status": "available",
                "direction": "neutral",
                "signal": "volatility_expansion",
                "state": "expanding",
                "strength": 0.4,
                "reason": "NATR en expansion",
                "raw_value": 2.0,
                "components": {
                    "atr": {
                        "value": 2.0,
                        "normalized_value": None,
                        "unit": "price",
                    },
                    "natr": {
                        "value": 2.0,
                        "normalized_value": 0.02,
                        "unit": "percent",
                    },
                },
            },
            "ema": {
                "status": "available",
                "direction": "bullish",
                "signal": "bullish_cross",
                "state": None,
                "strength": 0.8,
                "reason": "Croisement EMA",
                "raw_value": None,
                "components": {
                    "fast": {
                        "value": 101.0,
                        "normalized_value": None,
                        "unit": "price",
                    },
                    "slow": {
                        "value": 99.0,
                        "normalized_value": None,
                        "unit": "price",
                    },
                },
            },
        },
        "indicator_events": [
            {
                "indicator": "ema",
                "position": 100,
                "direction": "bullish",
                "event": "bullish_cross",
                "kind": "cross",
                "strength": 0.8,
                "metadata": {
                    "fast": 101.0,
                    "slow": 99.0,
                },
            },
        ],
        "source_ohlcv": {
            "open": 98.0,
            "high": 102.0,
            "low": 97.0,
            "close": 100.0,
            "volume": 1_000.0,
        },
        "divergences": [
            {
                "source": "rsi",
                "divergence_type": "bullish_regular",
                "pivot_time": DECISION_TIME - timedelta(hours=3),
                "confirmation_time": DECISION_TIME,
            },
        ],
        "quality": {
            "gap_free": True,
            "available_bars": 250,
        },
        "algorithm_version": "signal-evaluation-v3",
        "dataset_version": "binance-history-v1",
        "profile_id": "ml-profile",
        "profile_fingerprint": "sha256:test-profile",
    }
    values.update(changes)
    return SignalObservation.model_validate(values)


def valid_outcome(**changes: object) -> ForwardOutcome:
    """Construit un outcome valide à six bougies."""
    values: dict[str, object] = {
        "observation_id": 42,
        "horizon": 6,
        "entry_policy": "signal_close",
        "entry_time": DECISION_TIME,
        "entry_price": 100.0,
        "exit_time": DECISION_TIME + timedelta(hours=6),
        "exit_price": 103.0,
        "gross_return": 0.03,
        "net_return": 0.029,
        "mfe": 0.05,
        "mae": -0.01,
        "censored": False,
        "available_bars": 6,
        "valid": True,
    }
    values.update(changes)
    return ForwardOutcome.model_validate(values)


def test_extract_natr_percent_prefers_component_value() -> None:
    observation = valid_observation()

    assert extract_natr_percent(observation) == pytest.approx(2.0)


def test_extract_natr_percent_can_use_normalized_component() -> None:
    observation = valid_observation(
        indicator_signals={
            "atr": {
                "status": "available",
                "direction": "neutral",
                "signal": None,
                "state": "stable",
                "strength": 0.0,
                "reason": None,
                "raw_value": None,
                "components": {
                    "natr": {
                        "value": None,
                        "normalized_value": 0.025,
                        "unit": "percent",
                    },
                },
            },
        },
    )

    assert extract_natr_percent(observation) == pytest.approx(2.5)


def test_extract_causal_features_flattens_signals_and_events() -> None:
    features = extract_causal_features(valid_observation())

    assert features["price.close"] == pytest.approx(100.0)
    assert features["candle.volume"] == pytest.approx(1_000.0)
    assert features["trend.state.1h"] == "bullish"
    assert features["availability.atr"] == "available"

    assert features["indicator.atr.status"] == "available"
    assert features["indicator.atr.direction"] == "neutral"
    assert features["indicator.atr.raw_value"] == pytest.approx(2.0)
    assert features["indicator.atr.component.natr.value"] == pytest.approx(2.0)
    assert features["indicator.atr.component.natr.normalized_value"] == pytest.approx(0.02)
    assert features["indicator.atr.component.natr.unit"] == "percent"

    assert features["event.total_count"] == 1
    assert features["event.direction.bullish.count"] == 1
    assert features["event.indicator.ema.count"] == 1
    assert features["event.kind.cross.count"] == 1
    assert features["event.ema.bullish_cross.count"] == 1
    assert features["event.ema.bullish_cross.max_strength"] == pytest.approx(0.8)

    assert features["divergence.total_count"] == 1
    assert features["divergence.source.rsi.count"] == 1
    assert features["divergence.type.bullish_regular.count"] == 1
    assert features["divergence.rsi.bullish_regular.count"] == 1

    assert features["quality.gap_free"] is True
    assert features["quality.available_bars"] == 250


def test_extract_causal_features_flattens_atr_components() -> None:
    observation = valid_observation(
        indicator_signals={
            **valid_observation().indicator_signals,
            "atr": {
                "status": "available",
                "direction": "neutral",
                "signal": None,
                "state": "expanding",
                "strength": 0.25,
                "reason": "NATR expanding",
                "raw_value": 1.5,
                "components": {
                    "true_range": {
                        "value": 2.0,
                        "normalized_value": 0.02,
                        "unit": "price",
                    },
                    "atr": {
                        "value": 1.5,
                        "normalized_value": 0.015,
                        "unit": "price",
                    },
                    "natr": {
                        "value": 1.5,
                        "normalized_value": 0.015,
                        "unit": "percent",
                    },
                    "previous_natr": {
                        "value": 1.2,
                        "normalized_value": 0.012,
                        "unit": "percent",
                    },
                    "natr_change": {
                        "value": 0.3,
                        "normalized_value": 0.003,
                        "unit": "percent",
                    },
                    "relative_natr_change": {
                        "value": 0.25,
                        "normalized_value": 0.25,
                        "unit": "ratio",
                    },
                },
            },
        },
    )

    features = extract_causal_features(observation)

    assert features["indicator.atr.raw_value"] == pytest.approx(1.5)

    assert features["indicator.atr.component.true_range.normalized_value"] == pytest.approx(0.02)

    assert features["indicator.atr.component.atr.normalized_value"] == pytest.approx(0.015)

    assert features["indicator.atr.component.previous_natr.value"] == pytest.approx(1.2)

    assert features["indicator.atr.component.natr_change.normalized_value"] == pytest.approx(0.003)

    assert features["indicator.atr.component.relative_natr_change.value"] == pytest.approx(0.25)


def test_extract_causal_features_flattens_adx_components() -> None:
    observation = valid_observation(
        indicator_signals={
            **valid_observation().indicator_signals,
            "adx": {
                "status": "available",
                "direction": "bullish",
                "signal": "bullish_cross",
                "state": "strong_trend",
                "strength": 0.6,
                "reason": "ADX strong_trend",
                "raw_value": 30.0,
                "components": {
                    "adx": {
                        "value": 30.0,
                        "normalized_value": 0.3,
                        "unit": "index",
                    },
                    "plus_di": {
                        "value": 40.0,
                        "normalized_value": 0.4,
                        "unit": "index",
                    },
                    "minus_di": {
                        "value": 20.0,
                        "normalized_value": 0.2,
                        "unit": "index",
                    },
                    "di_spread": {
                        "value": 20.0,
                        "normalized_value": 0.2,
                        "unit": "index",
                    },
                    "di_balance": {
                        "value": 20 / 60,
                        "normalized_value": 20 / 60,
                        "unit": "ratio",
                    },
                    "adx_change": {
                        "value": 12.0,
                        "normalized_value": 0.12,
                        "unit": "index",
                    },
                },
            },
        },
    )

    features = extract_causal_features(observation)

    assert features["indicator.adx.raw_value"] == pytest.approx(30.0)

    assert features["indicator.adx.component.adx.normalized_value"] == pytest.approx(0.3)

    assert features["indicator.adx.component.plus_di.value"] == pytest.approx(40.0)

    assert features["indicator.adx.component.di_spread.normalized_value"] == pytest.approx(0.2)

    assert features["indicator.adx.component.di_balance.value"] == pytest.approx(20 / 60)

    assert features["indicator.adx.component.adx_change.normalized_value"] == pytest.approx(0.12)


def test_extract_causal_features_flattens_supertrend_components() -> None:
    observation = valid_observation(
        indicator_signals={
            **valid_observation().indicator_signals,
            "supertrend": {
                "status": "available",
                "direction": "bullish",
                "signal": "bullish_flip",
                "state": "uptrend",
                "strength": 1.0,
                "reason": "Supertrend uptrend",
                "raw_value": 100.0,
                "components": {
                    "supertrend": {
                        "value": 100.0,
                        "normalized_value": 100 / 110,
                        "unit": "price",
                    },
                    "distance_ratio": {
                        "value": 10 / 110,
                        "normalized_value": 10 / 110,
                        "unit": "ratio",
                    },
                    "distance_atr": {
                        "value": 2.0,
                        "normalized_value": 2.0,
                        "unit": "ratio",
                    },
                    "band_position": {
                        "value": 15 / 20,
                        "normalized_value": 15 / 20,
                        "unit": "ratio",
                    },
                    "supertrend_change": {
                        "value": 5.0,
                        "normalized_value": 5 / 195,
                        "unit": "price",
                    },
                },
            },
        },
    )

    features = extract_causal_features(observation)

    assert features["indicator.supertrend.raw_value"] == pytest.approx(100.0)

    assert features["indicator.supertrend.component.supertrend.normalized_value"] == pytest.approx(
        100 / 110
    )

    assert features["indicator.supertrend.component.distance_ratio.value"] == pytest.approx(
        10 / 110
    )

    assert features[
        "indicator.supertrend.component.distance_atr.normalized_value"
    ] == pytest.approx(2.0)

    assert features["indicator.supertrend.component.band_position.value"] == pytest.approx(15 / 20)

    assert features[
        "indicator.supertrend.component.supertrend_change.normalized_value"
    ] == pytest.approx(5 / 195)


def test_extract_causal_features_flattens_donchian_components() -> None:
    observation = valid_observation(
        indicator_signals={
            **valid_observation().indicator_signals,
            "donchian": {
                "status": "available",
                "direction": "bullish",
                "signal": "breakout_up",
                "state": "above_channel",
                "strength": 0.15,
                "reason": "Cassure haussière du canal Donchian",
                "raw_value": 0.8,
                "components": {
                    "upper_channel": {
                        "value": 14.0,
                        "normalized_value": 14 / 13,
                        "unit": "price",
                    },
                    "channel_width_percent": {
                        "value": 100 * 5 / 11.5,
                        "normalized_value": 5 / 11.5,
                        "unit": "percent",
                    },
                    "channel_position": {
                        "value": 0.8,
                        "normalized_value": 0.8,
                        "unit": "ratio",
                    },
                    "price_to_previous_upper_distance": {
                        "value": 2.0,
                        "normalized_value": 2 / 13,
                        "unit": "price",
                    },
                    "channel_width_percent_change": {
                        "value": ((100 * 5 / 11.5) - (100 * 3 / 9.5)),
                        "normalized_value": ((5 / 11.5) - (3 / 9.5)),
                        "unit": "percent",
                    },
                    "channel_position_change": {
                        "value": 0.8 - (2 / 3),
                        "normalized_value": 0.8 - (2 / 3),
                        "unit": "ratio",
                    },
                },
            },
        },
    )

    features = extract_causal_features(observation)

    assert features["indicator.donchian.raw_value"] == pytest.approx(0.8)

    assert features["indicator.donchian.component.upper_channel.normalized_value"] == pytest.approx(
        14 / 13
    )

    assert features[
        "indicator.donchian.component.channel_width_percent.normalized_value"
    ] == pytest.approx(5 / 11.5)

    assert features["indicator.donchian.component.channel_position.value"] == pytest.approx(0.8)

    assert features[
        "indicator.donchian.component." "price_to_previous_upper_distance.normalized_value"
    ] == pytest.approx(2 / 13)

    assert features[
        "indicator.donchian.component." "channel_width_percent_change.normalized_value"
    ] == pytest.approx((5 / 11.5) - (3 / 9.5))

    assert features[
        "indicator.donchian.component." "channel_position_change.value"
    ] == pytest.approx(0.8 - (2 / 3))


def test_extract_causal_features_flattens_keltner_components() -> None:
    observation = valid_observation(
        indicator_signals={
            **valid_observation().indicator_signals,
            "keltner": {
                "status": "available",
                "direction": "bullish",
                "signal": "breakout_up",
                "state": "above_channel",
                "strength": 1.0,
                "reason": "Cassure haussière du canal Keltner",
                "raw_value": 1.25,
                "components": {
                    "middle_line": {
                        "value": 10.5,
                        "normalized_value": 10.5 / 12,
                        "unit": "price",
                    },
                    "atr": {
                        "value": 1.0,
                        "normalized_value": 1 / 12,
                        "unit": "price",
                    },
                    "channel_width_percent": {
                        "value": 100 * 2 / 10.5,
                        "normalized_value": 2 / 10.5,
                        "unit": "percent",
                    },
                    "channel_position": {
                        "value": 1.25,
                        "normalized_value": 1.25,
                        "unit": "ratio",
                    },
                    "price_to_previous_upper_atr": {
                        "value": 1.0,
                        "normalized_value": 1.0,
                        "unit": "ratio",
                    },
                    "middle_line_change": {
                        "value": 0.5,
                        "normalized_value": 0.5 / 20.5,
                        "unit": "price",
                    },
                    "channel_position_change": {
                        "value": 0.75,
                        "normalized_value": 0.75,
                        "unit": "ratio",
                    },
                },
            },
        },
    )

    features = extract_causal_features(observation)

    assert features["indicator.keltner.raw_value"] == pytest.approx(1.25)

    assert features["indicator.keltner.component.middle_line.normalized_value"] == pytest.approx(
        10.5 / 12
    )

    assert features["indicator.keltner.component.atr.normalized_value"] == pytest.approx(1 / 12)

    assert features[
        "indicator.keltner.component." "channel_width_percent.normalized_value"
    ] == pytest.approx(2 / 10.5)

    assert features["indicator.keltner.component.channel_position.value"] == pytest.approx(1.25)

    assert features[
        "indicator.keltner.component." "price_to_previous_upper_atr.value"
    ] == pytest.approx(1.0)

    assert features[
        "indicator.keltner.component." "middle_line_change.normalized_value"
    ] == pytest.approx(0.5 / 20.5)

    assert features[
        "indicator.keltner.component." "channel_position_change.value"
    ] == pytest.approx(0.75)


def test_extract_causal_features_flattens_rsi_components() -> None:
    observation = valid_observation(
        indicator_signals={
            **valid_observation().indicator_signals,
            "rsi": {
                "status": "available",
                "direction": "neutral",
                "signal": "neutral",
                "state": "neutral",
                "strength": 0.0,
                "reason": "RSI en zone neutral",
                "raw_value": 55.0,
                "components": {
                    "rsi": {
                        "value": 55.0,
                        "normalized_value": 0.55,
                        "unit": "index",
                    },
                    "previous_value": {
                        "value": 50.0,
                        "normalized_value": 0.5,
                        "unit": "index",
                    },
                    "change": {
                        "value": 5.0,
                        "normalized_value": 0.05,
                        "unit": "index",
                    },
                    "distance_from_midpoint": {
                        "value": 5.0,
                        "normalized_value": 0.05,
                        "unit": "index",
                    },
                },
            },
        },
    )

    features = extract_causal_features(observation)

    assert features["indicator.rsi.raw_value"] == pytest.approx(55.0)
    assert features["indicator.rsi.component.rsi.value"] == pytest.approx(55.0)
    assert features["indicator.rsi.component.rsi.normalized_value"] == pytest.approx(0.55)
    assert features["indicator.rsi.component.previous_value.value"] == pytest.approx(50.0)
    assert features["indicator.rsi.component.change.value"] == pytest.approx(5.0)
    assert features["indicator.rsi.component.change.normalized_value"] == pytest.approx(0.05)


def test_extract_causal_features_flattens_macd_components() -> None:
    observation = valid_observation(
        indicator_signals={
            **valid_observation().indicator_signals,
            "macd": {
                "status": "available",
                "direction": "bullish",
                "signal": "above_signal",
                "state": "above_signal/above_zero",
                "strength": 0.6,
                "reason": "MACD maintenu au-dessus de sa ligne de signal",
                "raw_value": 2.0,
                "components": {
                    "macd": {
                        "value": 2.0,
                        "normalized_value": 2 / 3,
                        "unit": "price",
                    },
                    "signal_line": {
                        "value": 1.0,
                        "normalized_value": 1 / 3,
                        "unit": "price",
                    },
                    "histogram": {
                        "value": 1.0,
                        "normalized_value": 1 / 3,
                        "unit": "price",
                    },
                    "relative_distance": {
                        "value": 1 / 3,
                        "normalized_value": 1 / 3,
                        "unit": "ratio",
                    },
                    "histogram_change": {
                        "value": 0.5,
                        "normalized_value": 1 / 3,
                        "unit": "price",
                    },
                },
            },
        },
    )

    features = extract_causal_features(observation)

    assert features["indicator.macd.raw_value"] == pytest.approx(2.0)
    assert features["indicator.macd.component.macd.value"] == pytest.approx(2.0)
    assert features["indicator.macd.component.macd.normalized_value"] == pytest.approx(2 / 3)
    assert features["indicator.macd.component.signal_line.value"] == pytest.approx(1.0)
    assert features["indicator.macd.component.histogram.value"] == pytest.approx(1.0)
    assert features["indicator.macd.component.relative_distance.value"] == pytest.approx(1 / 3)
    assert features["indicator.macd.component.histogram_change.normalized_value"] == pytest.approx(
        1 / 3
    )


def test_extract_causal_features_flattens_stochastic_components() -> None:
    observation = valid_observation(
        indicator_signals={
            **valid_observation().indicator_signals,
            "stochastic": {
                "status": "available",
                "direction": "bullish",
                "signal": "bullish_cross",
                "state": "neutral",
                "strength": 0.6,
                "reason": "Croisement haussier du stochastique",
                "raw_value": 30.0,
                "components": {
                    "k": {
                        "value": 30.0,
                        "normalized_value": 0.3,
                        "unit": "index",
                    },
                    "d": {
                        "value": 25.0,
                        "normalized_value": 0.25,
                        "unit": "index",
                    },
                    "spread": {
                        "value": 5.0,
                        "normalized_value": 0.05,
                        "unit": "index",
                    },
                    "k_change": {
                        "value": 20.0,
                        "normalized_value": 0.2,
                        "unit": "index",
                    },
                    "spread_change": {
                        "value": 15.0,
                        "normalized_value": 0.15,
                        "unit": "index",
                    },
                },
            },
        },
    )

    features = extract_causal_features(observation)

    assert features["indicator.stochastic.raw_value"] == pytest.approx(30.0)
    assert features["indicator.stochastic.component.k.value"] == pytest.approx(30.0)
    assert features["indicator.stochastic.component.k.normalized_value"] == pytest.approx(0.3)
    assert features["indicator.stochastic.component.d.value"] == pytest.approx(25.0)
    assert features["indicator.stochastic.component.spread.value"] == pytest.approx(5.0)
    assert features["indicator.stochastic.component.k_change.normalized_value"] == pytest.approx(
        0.2
    )
    assert features[
        "indicator.stochastic.component.spread_change.normalized_value"
    ] == pytest.approx(0.15)


def test_extract_causal_features_flattens_moving_average_components() -> None:
    observation = valid_observation(
        indicator_signals={
            **valid_observation().indicator_signals,
            "ema": {
                "status": "available",
                "direction": "bullish",
                "signal": "bullish_alignment",
                "state": None,
                "strength": 0.5,
                "reason": "EMA: alignement haussier",
                "raw_value": 100.0,
                "components": {
                    "fast": {
                        "value": 100.0,
                        "normalized_value": 100 / 110,
                        "unit": "price",
                    },
                    "slow": {
                        "value": 95.0,
                        "normalized_value": 95 / 110,
                        "unit": "price",
                    },
                    "price_to_fast_distance": {
                        "value": 10.0,
                        "normalized_value": 10 / 210,
                        "unit": "price",
                    },
                    "fast_to_slow_distance": {
                        "value": 5.0,
                        "normalized_value": 5 / 195,
                        "unit": "price",
                    },
                },
            },
        },
    )

    features = extract_causal_features(observation)

    assert features["indicator.ema.raw_value"] == pytest.approx(100.0)
    assert features["indicator.ema.component.fast.value"] == pytest.approx(100.0)
    assert features["indicator.ema.component.fast.normalized_value"] == pytest.approx(100 / 110)
    assert features[
        "indicator.ema.component.price_to_fast_distance.normalized_value"
    ] == pytest.approx(10 / 210)
    assert features["indicator.ema.component.fast_to_slow_distance.value"] == pytest.approx(5.0)


def test_extract_causal_features_flattens_bollinger_components() -> None:
    observation = valid_observation(
        indicator_signals={
            **valid_observation().indicator_signals,
            "bollinger": {
                "status": "available",
                "direction": "neutral",
                "signal": "neutral",
                "state": "neutral",
                "strength": 0.0,
                "reason": "Position Bollinger courante: neutral",
                "raw_value": 110.0,
                "components": {
                    "band_width_percent": {
                        "value": 100 * 30 / 105,
                        "normalized_value": 30 / 105,
                        "unit": "percent",
                    },
                    "band_position": {
                        "value": 20 / 30,
                        "normalized_value": 20 / 30,
                        "unit": "ratio",
                    },
                    "price_to_middle_distance": {
                        "value": 5.0,
                        "normalized_value": 5 / 215,
                        "unit": "price",
                    },
                    "band_position_change": {
                        "value": (20 / 30) - 0.5,
                        "normalized_value": (20 / 30) - 0.5,
                        "unit": "ratio",
                    },
                },
            },
        },
    )

    features = extract_causal_features(observation)

    assert features["indicator.bollinger.raw_value"] == pytest.approx(110.0)
    assert features[
        "indicator.bollinger.component.band_width_percent.normalized_value"
    ] == pytest.approx(30 / 105)
    assert features["indicator.bollinger.component.band_position.value"] == pytest.approx(20 / 30)
    assert features[
        "indicator.bollinger.component.price_to_middle_distance.normalized_value"
    ] == pytest.approx(5 / 215)
    assert features["indicator.bollinger.component.band_position_change.value"] == pytest.approx(
        (20 / 30) - 0.5
    )


def test_build_ml_dataset_row_creates_up_label() -> None:
    row = build_ml_dataset_row(
        valid_observation(),
        valid_outcome(),
    )

    assert row.observation_id == 42
    assert row.horizon == 6
    assert row.future_return == pytest.approx(0.03)
    assert row.natr_percent == pytest.approx(2.0)
    assert row.neutral_threshold_return == pytest.approx(0.02)
    assert row.label is MarketDirectionLabel.UP
    assert row.features["volatility.natr_percent"] == pytest.approx(2.0)
    assert row.feature_schema_version == ML_FEATURE_SCHEMA_VERSION


def test_build_ml_dataset_row_accepts_explicit_v2_schema() -> None:
    row = build_ml_dataset_row(
        valid_observation(),
        valid_outcome(),
        feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
    )

    assert row.feature_schema_version == ML_FEATURE_SCHEMA_VERSION_V2


def test_builder_uses_configured_natr_multiplier() -> None:
    row = build_ml_dataset_row(
        valid_observation(),
        valid_outcome(
            gross_return=0.025,
        ),
        natr_multiplier=1.5,
    )

    assert row.neutral_threshold_return == pytest.approx(0.03)
    assert row.label is MarketDirectionLabel.NEUTRAL


def test_outcome_values_do_not_leak_into_features() -> None:
    row = build_ml_dataset_row(
        valid_observation(),
        valid_outcome(),
    )

    forbidden_names = {
        "gross_return",
        "net_return",
        "mfe",
        "mae",
        "entry_price",
        "exit_price",
        "highest_price",
        "lowest_price",
    }

    assert forbidden_names.isdisjoint(row.features)
    assert not any(name.startswith(("future.", "outcome.", "target.")) for name in row.features)


@pytest.mark.parametrize(
    ("future_return", "expected"),
    [
        (0.020001, MarketDirectionLabel.UP),
        (0.02, MarketDirectionLabel.NEUTRAL),
        (0.0, MarketDirectionLabel.NEUTRAL),
        (-0.02, MarketDirectionLabel.NEUTRAL),
        (-0.020001, MarketDirectionLabel.DOWN),
    ],
)
def test_classify_market_direction_boundaries(
    future_return: float,
    expected: MarketDirectionLabel,
) -> None:
    assert (
        classify_market_direction(
            future_return,
            neutral_threshold_return=0.02,
        )
        is expected
    )


def test_builder_rejects_unpersisted_observation() -> None:
    with pytest.raises(
        MLDatasetBuildError,
        match="posséder un identifiant",
    ):
        build_ml_dataset_row(
            valid_observation(id=None),
            valid_outcome(),
        )


def test_builder_rejects_provisional_observation() -> None:
    with pytest.raises(
        MLDatasetBuildError,
        match="observations confirmées",
    ):
        build_ml_dataset_row(
            valid_observation(snapshot_status="provisional"),
            valid_outcome(),
        )


def test_builder_rejects_outcome_from_another_observation() -> None:
    with pytest.raises(
        MLDatasetBuildError,
        match="n'appartient pas",
    ):
        build_ml_dataset_row(
            valid_observation(),
            valid_outcome(observation_id=999),
        )


def test_builder_rejects_wrong_horizon() -> None:
    with pytest.raises(
        MLDatasetBuildError,
        match="horizon doit être égal à 6",
    ):
        build_ml_dataset_row(
            valid_observation(),
            valid_outcome(horizon=12),
        )


def test_builder_rejects_censored_outcome() -> None:
    with pytest.raises(
        MLDatasetBuildError,
        match="outcome censuré",
    ):
        build_ml_dataset_row(
            valid_observation(),
            valid_outcome(
                censored=True,
                censor_reason="end_of_history",
            ),
        )


def test_builder_rejects_invalid_outcome() -> None:
    with pytest.raises(
        MLDatasetBuildError,
        match="outcome invalide",
    ):
        build_ml_dataset_row(
            valid_observation(),
            valid_outcome(valid=False),
        )


def test_builder_rejects_missing_gross_return() -> None:
    with pytest.raises(
        MLDatasetBuildError,
        match="gross_return est requis",
    ):
        build_ml_dataset_row(
            valid_observation(),
            valid_outcome(gross_return=None),
        )


def test_builder_rejects_missing_natr() -> None:
    with pytest.raises(
        MLDatasetBuildError,
        match="NATR indisponible",
    ):
        build_ml_dataset_row(
            valid_observation(indicator_signals={}),
            valid_outcome(),
        )


@pytest.mark.parametrize(
    "multiplier",
    [
        0.0,
        -1.0,
        10.1,
        float("inf"),
        float("nan"),
    ],
)
def test_builder_rejects_invalid_natr_multiplier(
    multiplier: float,
) -> None:
    with pytest.raises(
        MLDatasetBuildError,
        match="natr_multiplier",
    ):
        build_ml_dataset_row(
            valid_observation(),
            valid_outcome(),
            natr_multiplier=multiplier,
        )
