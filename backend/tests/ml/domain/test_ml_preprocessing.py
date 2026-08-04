from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.ml.domain.ml_preprocessing import (
    LABEL_ORDER,
    MLFeaturePreprocessor,
    MLPreprocessingError,
    decode_market_labels,
    encode_market_labels,
)
from app.ml.models.ml_dataset import (
    MLDatasetRow,
    MarketDirectionLabel,
)

FeatureValue = bool | int | float | str | None

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
    features: dict[str, FeatureValue],
    label: MarketDirectionLabel = (MarketDirectionLabel.NEUTRAL),
) -> MLDatasetRow:
    """Construit une ligne ML valide pour le prétraitement."""
    decision_time = BASE_TIME + timedelta(hours=observation_id)

    future_return_by_label = {
        MarketDirectionLabel.DOWN: -0.03,
        MarketDirectionLabel.NEUTRAL: 0.0,
        MarketDirectionLabel.UP: 0.03,
    }

    return MLDatasetRow(
        observation_id=observation_id,
        job_id="preprocessing-test",
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
        future_return=future_return_by_label[label],
        label=label,
        features=features,
    )


def test_label_encoding_uses_stable_business_order() -> None:
    rows = (
        dataset_row(
            1,
            features={"value": 1.0},
            label=MarketDirectionLabel.UP,
        ),
        dataset_row(
            2,
            features={"value": 2.0},
            label=MarketDirectionLabel.DOWN,
        ),
        dataset_row(
            3,
            features={"value": 3.0},
            label=MarketDirectionLabel.NEUTRAL,
        ),
    )

    encoded = encode_market_labels(rows)

    assert encoded.dtype == np.int64
    assert encoded.tolist() == [
        2,
        0,
        1,
    ]
    assert LABEL_ORDER == (
        MarketDirectionLabel.DOWN,
        MarketDirectionLabel.NEUTRAL,
        MarketDirectionLabel.UP,
    )
    assert decode_market_labels([int(value) for value in encoded]) == (
        MarketDirectionLabel.UP,
        MarketDirectionLabel.DOWN,
        MarketDirectionLabel.NEUTRAL,
    )


def test_decode_rejects_unknown_label_index() -> None:
    with pytest.raises(
        MLPreprocessingError,
        match="indice de label inconnu",
    ):
        decode_market_labels(
            [
                0,
                3,
            ]
        )


def test_preprocessor_removes_constants_and_encodes_types() -> None:
    rows = (
        dataset_row(
            1,
            features={
                "constant.value": 5.0,
                "metric.value": 1.0,
                "flag.enabled": False,
                "state.value": "bearish",
            },
        ),
        dataset_row(
            2,
            features={
                "constant.value": 5.0,
                "metric.value": 2.0,
                "flag.enabled": True,
                "state.value": "bullish",
            },
        ),
        dataset_row(
            3,
            features={
                "constant.value": 5.0,
                "metric.value": 3.0,
                "flag.enabled": False,
                "state.value": "neutral",
            },
        ),
    )

    preprocessor = MLFeaturePreprocessor()
    matrix = preprocessor.fit_transform(rows)
    schema = preprocessor.schema

    assert schema.input_feature_names == (
        "constant.value",
        "flag.enabled",
        "metric.value",
        "state.value",
    )
    assert schema.dropped_constant_feature_names == ("constant.value",)
    assert schema.active_feature_names == (
        "flag.enabled",
        "metric.value",
        "state.value",
    )
    assert schema.numeric_feature_names == ("metric.value",)
    assert schema.boolean_feature_names == ("flag.enabled",)
    assert schema.categorical_feature_names == ("state.value",)
    assert matrix.shape == (
        3,
        5,
    )
    assert np.isfinite(matrix).all()


def test_event_absence_is_equivalent_to_zero() -> None:
    train_rows = (
        dataset_row(
            1,
            features={
                "support.value": 1.0,
            },
        ),
        dataset_row(
            2,
            features={
                "support.value": 2.0,
                "event.rsi.enter.count": 2,
            },
        ),
        dataset_row(
            3,
            features={
                "support.value": 3.0,
                "event.rsi.enter.count": 1,
            },
        ),
    )

    preprocessor = MLFeaturePreprocessor()
    preprocessor.fit(train_rows)

    missing_event = dataset_row(
        10,
        features={
            "support.value": 2.5,
        },
    )
    explicit_zero = dataset_row(
        11,
        features={
            "support.value": 2.5,
            "event.rsi.enter.count": 0,
        },
    )

    transformed = preprocessor.transform(
        (
            missing_event,
            explicit_zero,
        )
    )

    np.testing.assert_allclose(
        transformed[0],
        transformed[1],
    )


def test_numeric_missing_value_creates_indicator() -> None:
    train_rows = (
        dataset_row(
            1,
            features={
                "metric.value": 10.0,
                "support.value": 1.0,
            },
        ),
        dataset_row(
            2,
            features={
                "support.value": 2.0,
            },
        ),
        dataset_row(
            3,
            features={
                "metric.value": 10.0,
                "support.value": 3.0,
            },
        ),
    )

    preprocessor = MLFeaturePreprocessor()
    preprocessor.fit(train_rows)

    assert "metric.value" in preprocessor.schema.active_feature_names
    assert any(
        "missingindicator_metric.value" in feature_name
        for feature_name in preprocessor.schema.output_feature_names
    )

    present = dataset_row(
        10,
        features={
            "metric.value": 10.0,
            "support.value": 2.0,
        },
    )
    missing = dataset_row(
        11,
        features={
            "support.value": 2.0,
        },
    )

    transformed = preprocessor.transform(
        (
            present,
            missing,
        )
    )

    assert not np.array_equal(
        transformed[0],
        transformed[1],
    )


def test_unknown_category_is_ignored() -> None:
    train_rows = (
        dataset_row(
            1,
            features={
                "metric.value": 1.0,
                "state.value": "bearish",
            },
        ),
        dataset_row(
            2,
            features={
                "metric.value": 2.0,
                "state.value": "bullish",
            },
        ),
    )

    preprocessor = MLFeaturePreprocessor()
    preprocessor.fit(train_rows)

    unknown = dataset_row(
        10,
        features={
            "metric.value": 1.5,
            "state.value": "sideways",
        },
    )

    transformed = preprocessor.transform((unknown,))

    categorical_indexes = [
        index
        for index, feature_name in enumerate(preprocessor.schema.output_feature_names)
        if feature_name.startswith("categorical__state.value_")
    ]

    assert categorical_indexes
    assert transformed.shape == (
        1,
        preprocessor.schema.output_feature_count,
    )
    assert np.isfinite(transformed).all()
    assert transformed[
        0,
        categorical_indexes,
    ].tolist() == [0.0 for _ in categorical_indexes]


def test_transform_ignores_features_unknown_to_train() -> None:
    train_rows = (
        dataset_row(
            1,
            features={
                "metric.value": 1.0,
            },
        ),
        dataset_row(
            2,
            features={
                "metric.value": 2.0,
            },
        ),
    )

    preprocessor = MLFeaturePreprocessor()
    preprocessor.fit(train_rows)

    regular = dataset_row(
        10,
        features={
            "metric.value": 1.5,
        },
    )
    with_extra_feature = dataset_row(
        11,
        features={
            "metric.value": 1.5,
            "new.validation.feature": 999.0,
        },
    )

    transformed = preprocessor.transform(
        (
            regular,
            with_extra_feature,
        )
    )

    np.testing.assert_allclose(
        transformed[0],
        transformed[1],
    )


def test_schema_is_deterministic() -> None:
    first_rows = (
        dataset_row(
            1,
            features={
                "state.value": "bearish",
                "metric.value": 1.0,
                "flag.enabled": False,
            },
        ),
        dataset_row(
            2,
            features={
                "state.value": "bullish",
                "metric.value": 2.0,
                "flag.enabled": True,
            },
        ),
    )

    second_rows = (
        dataset_row(
            2,
            features={
                "flag.enabled": True,
                "metric.value": 2.0,
                "state.value": "bullish",
            },
        ),
        dataset_row(
            1,
            features={
                "flag.enabled": False,
                "metric.value": 1.0,
                "state.value": "bearish",
            },
        ),
    )

    first = MLFeaturePreprocessor()
    second = MLFeaturePreprocessor()

    first.fit(first_rows)
    second.fit(second_rows)

    assert first.schema.active_feature_names == second.schema.active_feature_names
    assert first.schema.output_feature_names == second.schema.output_feature_names

    sample = dataset_row(
        10,
        features={
            "metric.value": 1.5,
            "flag.enabled": True,
            "state.value": "bullish",
        },
    )

    np.testing.assert_allclose(
        first.transform((sample,)),
        second.transform((sample,)),
    )


def test_fit_rejects_empty_train() -> None:
    with pytest.raises(
        MLPreprocessingError,
        match="train ne peut pas être vide",
    ):
        MLFeaturePreprocessor().fit(())


def test_transform_rejects_unfitted_preprocessor() -> None:
    with pytest.raises(
        MLPreprocessingError,
        match="n'est pas entraîné",
    ):
        MLFeaturePreprocessor().transform(
            (
                dataset_row(
                    1,
                    features={
                        "metric.value": 1.0,
                    },
                ),
            )
        )


def test_fit_rejects_only_constant_features() -> None:
    rows = (
        dataset_row(
            1,
            features={
                "constant.value": 1.0,
            },
        ),
        dataset_row(
            2,
            features={
                "constant.value": 1.0,
            },
        ),
    )

    with pytest.raises(
        MLPreprocessingError,
        match="toutes les features",
    ):
        MLFeaturePreprocessor().fit(rows)


def test_fit_rejects_unsupported_feature_type() -> None:
    valid = dataset_row(
        1,
        features={
            "metric.value": 1.0,
        },
    )
    invalid = valid.model_copy(
        update={
            "observation_id": 2,
            "features": {
                "metric.value": [
                    1,
                    2,
                ],
            },
        }
    )

    with pytest.raises(
        MLPreprocessingError,
        match="type non pris en charge",
    ):
        MLFeaturePreprocessor().fit(
            (
                valid,
                invalid,
            )
        )


def test_fit_rejects_incompatible_feature_types() -> None:
    rows = (
        dataset_row(
            1,
            features={
                "mixed.value": 1.0,
            },
        ),
        dataset_row(
            2,
            features={
                "mixed.value": "bullish",
            },
        ),
    )

    with pytest.raises(
        MLPreprocessingError,
        match="plusieurs types incompatibles",
    ):
        MLFeaturePreprocessor().fit(rows)


def test_fit_rejects_non_finite_numeric_value() -> None:
    valid = dataset_row(
        1,
        features={
            "metric.value": 1.0,
        },
    )
    invalid = valid.model_copy(
        update={
            "observation_id": 2,
            "features": {
                "metric.value": float("nan"),
            },
        }
    )

    with pytest.raises(
        MLPreprocessingError,
        match="doit être fini",
    ):
        MLFeaturePreprocessor().fit(
            (
                valid,
                invalid,
            )
        )


def test_transform_empty_rows_preserves_column_count() -> None:
    rows = (
        dataset_row(
            1,
            features={
                "metric.value": 1.0,
            },
        ),
        dataset_row(
            2,
            features={
                "metric.value": 2.0,
            },
        ),
    )

    preprocessor = MLFeaturePreprocessor()
    preprocessor.fit(rows)

    transformed = preprocessor.transform(())

    assert transformed.dtype == np.float64
    assert transformed.shape == (
        0,
        preprocessor.schema.output_feature_count,
    )
