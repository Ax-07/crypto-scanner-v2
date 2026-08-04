from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ml.domain.ml_feature_policy import (
    ABSOLUTE_FEATURE_NAMES,
    DUPLICATE_FEATURE_NAMES,
    MLFeaturePolicy,
    MLFeaturePolicyError,
    apply_ml_feature_policy,
    feature_policy_exclusions,
    normalize_feature_policy,
)
from app.ml.models.ml_dataset import (
    MLDatasetRow,
    MarketDirectionLabel,
)

BASE_TIME = datetime(
    2026,
    1,
    1,
    0,
    0,
    tzinfo=timezone.utc,
)


def dataset_row(
    observation_id: int,
    *,
    features: dict[str, bool | int | float | str | None],
) -> MLDatasetRow:
    """Construit une ligne ML neutre valide."""
    decision_time = BASE_TIME + timedelta(hours=observation_id)

    return MLDatasetRow(
        observation_id=observation_id,
        job_id="feature-policy-test",
        symbol="BTC/USDC",
        timeframe="1h",
        decision_time=decision_time,
        source_open_time=(decision_time - timedelta(hours=1)),
        snapshot_status="confirmed",
        calculation_mode="canonical",
        source_algorithm_version=("signal-evaluation-v3"),
        source_dataset_version=("binance-history-v1"),
        profile_id="inline",
        profile_fingerprint="sha256:profile",
        horizon=6,
        entry_policy="signal_close",
        entry_time=decision_time,
        exit_time=(decision_time + timedelta(hours=6)),
        natr_percent=2.0,
        natr_multiplier=1.0,
        neutral_threshold_return=0.02,
        future_return=0.0,
        label=MarketDirectionLabel.NEUTRAL,
        features=features,
    )


def test_normalize_accepts_enum_and_string() -> None:
    assert (
        normalize_feature_policy(MLFeaturePolicy.WITHOUT_ABSOLUTE)
        == MLFeaturePolicy.WITHOUT_ABSOLUTE
    )

    assert normalize_feature_policy("without_absolute") == MLFeaturePolicy.WITHOUT_ABSOLUTE


def test_normalize_rejects_unknown_policy() -> None:
    with pytest.raises(
        MLFeaturePolicyError,
        match="politique de features inconnue",
    ):
        normalize_feature_policy("unknown-policy")


def test_all_policy_has_no_exclusions() -> None:
    assert feature_policy_exclusions(MLFeaturePolicy.ALL) == frozenset()


def test_without_absolute_returns_absolute_features() -> None:
    assert feature_policy_exclusions(MLFeaturePolicy.WITHOUT_ABSOLUTE) == ABSOLUTE_FEATURE_NAMES


def test_without_duplicates_returns_duplicate_features() -> None:
    assert feature_policy_exclusions(MLFeaturePolicy.WITHOUT_DUPLICATES) == DUPLICATE_FEATURE_NAMES


def test_normalized_deduplicated_returns_union() -> None:
    assert feature_policy_exclusions(MLFeaturePolicy.NORMALIZED_DEDUPLICATED) == (
        ABSOLUTE_FEATURE_NAMES | DUPLICATE_FEATURE_NAMES
    )


def test_all_policy_preserves_all_features() -> None:
    row = dataset_row(
        1,
        features={
            "candle.close": 100.0,
            "price.close": 100.0,
            "indicator.rsi.raw_value": 55.0,
        },
    )

    application = apply_ml_feature_policy(
        (row,),
        policy=MLFeaturePolicy.ALL,
    )

    assert application.policy == MLFeaturePolicy.ALL
    assert application.source_feature_names == (
        "candle.close",
        "indicator.rsi.raw_value",
        "price.close",
    )
    assert application.excluded_feature_names == ()
    assert application.excluded_present_feature_names == ()
    assert application.retained_feature_names == (
        "candle.close",
        "indicator.rsi.raw_value",
        "price.close",
    )
    assert application.rows[0].features == (row.features)


def test_without_absolute_removes_only_present_absolute_features() -> None:
    row = dataset_row(
        1,
        features={
            "candle.close": 100.0,
            "candle.volume": 50.0,
            "indicator.rsi.raw_value": 55.0,
            "volatility.natr_percent": 0.5,
        },
    )

    application = apply_ml_feature_policy(
        (row,),
        policy="without_absolute",
    )

    assert application.excluded_present_feature_names == (
        "candle.close",
        "candle.volume",
    )
    assert application.retained_feature_names == (
        "indicator.rsi.raw_value",
        "volatility.natr_percent",
    )
    assert application.rows[0].features == {
        "indicator.rsi.raw_value": 55.0,
        "volatility.natr_percent": 0.5,
    }

    assert row.features == {
        "candle.close": 100.0,
        "candle.volume": 50.0,
        "indicator.rsi.raw_value": 55.0,
        "volatility.natr_percent": 0.5,
    }


def test_without_duplicates_removes_only_duplicate_features() -> None:
    row = dataset_row(
        1,
        features={
            "price.close": 100.0,
            "volatility.natr_percent": 0.5,
            "indicator.atr.raw_value": 0.5,
            "indicator.rsi.raw_value": 55.0,
        },
    )

    application = apply_ml_feature_policy(
        (row,),
        policy=MLFeaturePolicy.WITHOUT_DUPLICATES,
    )

    assert application.excluded_present_feature_names == (
        "indicator.atr.raw_value",
        "price.close",
    )
    assert application.rows[0].features == {
        "volatility.natr_percent": 0.5,
        "indicator.rsi.raw_value": 55.0,
    }


def test_normalized_deduplicated_removes_union() -> None:
    row = dataset_row(
        1,
        features={
            "candle.close": 100.0,
            "price.close": 100.0,
            "indicator.atr.raw_value": 0.5,
            "volatility.natr_percent": 0.5,
            "indicator.rsi.raw_value": 55.0,
        },
    )

    application = apply_ml_feature_policy(
        (row,),
        policy=(MLFeaturePolicy.NORMALIZED_DEDUPLICATED),
    )

    assert application.excluded_present_feature_names == (
        "candle.close",
        "indicator.atr.raw_value",
        "price.close",
    )
    assert application.rows[0].features == {
        "volatility.natr_percent": 0.5,
        "indicator.rsi.raw_value": 55.0,
    }


def test_application_collects_features_across_all_rows() -> None:
    rows = (
        dataset_row(
            1,
            features={
                "candle.close": 100.0,
                "feature.first": 1.0,
            },
        ),
        dataset_row(
            2,
            features={
                "feature.second": 2.0,
                "price.close": 101.0,
            },
        ),
    )

    application = apply_ml_feature_policy(
        rows,
        policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
    )

    assert application.source_feature_names == (
        "candle.close",
        "feature.first",
        "feature.second",
        "price.close",
    )
    assert application.excluded_present_feature_names == (
        "candle.close",
        "price.close",
    )
    assert application.retained_feature_names == (
        "feature.first",
        "feature.second",
    )

    assert application.rows[0].features == {
        "feature.first": 1.0,
    }
    assert application.rows[1].features == {
        "feature.second": 2.0,
    }

    assert application.source_feature_count == 4
    assert application.excluded_present_feature_count == 2
    assert application.retained_feature_count == 2


def test_application_preserves_row_metadata_and_targets() -> None:
    row = dataset_row(
        1,
        features={
            "candle.close": 100.0,
            "indicator.rsi.raw_value": 55.0,
        },
    )

    application = apply_ml_feature_policy(
        (row,),
        policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
    )
    filtered = application.rows[0]

    assert filtered.observation_id == row.observation_id
    assert filtered.job_id == row.job_id
    assert filtered.symbol == row.symbol
    assert filtered.timeframe == row.timeframe
    assert filtered.decision_time == row.decision_time
    assert filtered.entry_time == row.entry_time
    assert filtered.exit_time == row.exit_time
    assert filtered.future_return == row.future_return
    assert filtered.label == row.label

    assert filtered is not row
    assert filtered.features == {
        "indicator.rsi.raw_value": 55.0,
    }


def test_application_accepts_empty_rows() -> None:
    application = apply_ml_feature_policy(
        (),
        policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
    )

    assert application.rows == ()
    assert application.source_feature_names == ()
    assert application.excluded_present_feature_names == ()
    assert application.retained_feature_names == ()
    assert application.source_feature_count == 0
    assert application.retained_feature_count == 0
