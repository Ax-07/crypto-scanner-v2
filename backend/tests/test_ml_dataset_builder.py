from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.ml_dataset import (
    MLDatasetBuildError,
    build_ml_dataset_row,
    classify_market_direction,
    extract_causal_features,
    extract_natr_percent,
)
from app.models.backtest import ForwardOutcome, SignalObservation
from app.models.ml_dataset import MarketDirectionLabel

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
