from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.ml_dataset import (
    MLDatasetRow,
    MarketDirectionLabel,
)

DECISION_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def valid_row(**changes: object) -> MLDatasetRow:
    """Construit une ligne ML valide pouvant être adaptée par chaque test."""
    values: dict[str, object] = {
        "observation_id": 1,
        "job_id": "ml-test",
        "symbol": "BTC/USDC",
        "timeframe": "1h",
        "decision_time": DECISION_TIME,
        "source_open_time": DECISION_TIME - timedelta(hours=1),
        "source_algorithm_version": "signal-evaluation-v3",
        "source_dataset_version": "synthetic-v1",
        "profile_id": "inline",
        "profile_fingerprint": "sha256:test",
        "entry_policy": "signal_close",
        "entry_time": DECISION_TIME,
        "exit_time": DECISION_TIME + timedelta(hours=6),
        "natr_percent": 2.0,
        "natr_multiplier": 1.0,
        "neutral_threshold_return": 0.02,
        "future_return": 0.03,
        "label": "up",
        "features": {
            "price.close": 100.0,
            "rsi.raw_value": 35.0,
            "macd.direction": "bullish",
            "event.ema.bullish_cross": True,
        },
    }
    values.update(changes)
    return MLDatasetRow.model_validate(values)


def test_up_label_is_valid_above_positive_threshold() -> None:
    row = valid_row(
        future_return=0.0200001,
        label="up",
    )

    assert row.label is MarketDirectionLabel.UP
    assert row.neutral_threshold_return == pytest.approx(0.02)


def test_down_label_is_valid_below_negative_threshold() -> None:
    row = valid_row(
        future_return=-0.0200001,
        label="down",
    )

    assert row.label is MarketDirectionLabel.DOWN


@pytest.mark.parametrize(
    "future_return",
    [
        -0.02,
        -0.01,
        0.0,
        0.01,
        0.02,
    ],
)
def test_neutral_label_includes_threshold_boundaries(
    future_return: float,
) -> None:
    row = valid_row(
        future_return=future_return,
        label="neutral",
    )

    assert row.label is MarketDirectionLabel.NEUTRAL


def test_label_must_match_future_return() -> None:
    with pytest.raises(
        ValidationError,
        match="label incohérent",
    ):
        valid_row(
            future_return=0.03,
            label="down",
        )


def test_threshold_must_match_natr_and_multiplier() -> None:
    with pytest.raises(
        ValidationError,
        match="neutral_threshold_return",
    ):
        valid_row(
            natr_percent=2.0,
            natr_multiplier=1.5,
            neutral_threshold_return=0.02,
        )


def test_entry_time_cannot_precede_decision_time() -> None:
    with pytest.raises(
        ValidationError,
        match="entry_time ne peut pas être antérieur",
    ):
        valid_row(
            entry_time=DECISION_TIME - timedelta(seconds=1),
        )


def test_exit_time_must_follow_entry_time() -> None:
    with pytest.raises(
        ValidationError,
        match="exit_time doit être postérieur",
    ):
        valid_row(
            exit_time=DECISION_TIME,
        )


def test_source_open_time_cannot_follow_decision_time() -> None:
    with pytest.raises(
        ValidationError,
        match="source_open_time ne peut pas être postérieur",
    ):
        valid_row(
            source_open_time=DECISION_TIME + timedelta(seconds=1),
        )


@pytest.mark.parametrize(
    "feature_name",
    [
        "label",
        "future_return",
        "net_return",
        "mfe",
        "mae",
        "exit_price",
        "target.direction",
        "outcome.net_return",
        "future.highest_price",
    ],
)
def test_future_or_reserved_features_are_rejected(
    feature_name: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match="feature future ou réservée",
    ):
        valid_row(
            features={
                feature_name: 1.0,
            },
        )


@pytest.mark.parametrize(
    "invalid_value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_non_finite_feature_values_are_rejected(
    invalid_value: float,
) -> None:
    with pytest.raises(ValidationError):
        valid_row(
            features={
                "indicator.value": invalid_value,
            },
        )


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(
        ValidationError,
        match="fuseau horaire",
    ):
        valid_row(
            decision_time=DECISION_TIME.replace(tzinfo=None),
        )


def test_datetimes_are_normalized_to_utc() -> None:
    local_timezone = timezone(timedelta(hours=2))

    row = valid_row(
        decision_time=DECISION_TIME.astimezone(local_timezone),
        source_open_time=(DECISION_TIME - timedelta(hours=1)).astimezone(local_timezone),
        entry_time=DECISION_TIME.astimezone(local_timezone),
        exit_time=(DECISION_TIME + timedelta(hours=6)).astimezone(local_timezone),
    )

    assert row.decision_time.tzinfo is timezone.utc
    assert row.entry_time.tzinfo is timezone.utc
    assert row.exit_time.tzinfo is timezone.utc
