from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ml.domain.ml_feature_policy import (
    MLFeaturePolicy,
)
from app.ml.models.ml_dataset import (
    MLDatasetRow,
    MarketDirectionLabel,
)
from app.ml.services.ml_final_evaluator import (
    MLFinalEvaluationError,
    evaluate_final_logistic_model,
)

BASE_TIME = datetime(
    2026,
    1,
    1,
    0,
    0,
    tzinfo=timezone.utc,
)


FeatureValue = bool | int | float | str | None


def dataset_row(
    observation_id: int,
    *,
    label: MarketDirectionLabel,
    job_id: str = "final-evaluation-test",
) -> MLDatasetRow:
    """Construit une ligne ML valide et facilement séparable."""
    decision_time = BASE_TIME + timedelta(hours=observation_id - 1)

    future_return_by_label = {
        MarketDirectionLabel.DOWN: -0.03,
        MarketDirectionLabel.NEUTRAL: 0.0,
        MarketDirectionLabel.UP: 0.03,
    }
    signal_by_label = {
        MarketDirectionLabel.DOWN: -1.0,
        MarketDirectionLabel.NEUTRAL: 0.0,
        MarketDirectionLabel.UP: 1.0,
    }

    features: dict[str, FeatureValue] = {
        "signal.value": (signal_by_label[label] + (observation_id % 5) * 0.001),
        "state.value": label.value,
        "candle.close": (100.0 + observation_id),
        "price.close": (100.0 + observation_id),
    }

    return MLDatasetRow(
        observation_id=observation_id,
        job_id=job_id,
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


def cyclic_rows(
    count: int,
) -> tuple[MLDatasetRow, ...]:
    """Construit une série équilibrée sur les trois classes."""
    labels = (
        MarketDirectionLabel.DOWN,
        MarketDirectionLabel.NEUTRAL,
        MarketDirectionLabel.UP,
    )

    return tuple(
        dataset_row(
            observation_id,
            label=labels[(observation_id - 1) % len(labels)],
        )
        for observation_id in range(
            1,
            count + 1,
        )
    )


def neutral_rows(
    count: int,
) -> tuple[MLDatasetRow, ...]:
    """Construit une série ne contenant que NEUTRAL."""
    return tuple(
        dataset_row(
            observation_id,
            label=MarketDirectionLabel.NEUTRAL,
        )
        for observation_id in range(
            1,
            count + 1,
        )
    )


def test_evaluates_reserved_test_and_purges_overlap() -> None:
    rows = cyclic_rows(150)

    result = evaluate_final_logistic_model(
        rows,
        evaluation_start=(BASE_TIME + timedelta(hours=120)),
        policy=(MLFeaturePolicy.NORMALIZED_DEDUPLICATED),
        c_value=0.03,
    )

    assert result.source_row_count == 150
    assert result.development_row_count == 114
    assert result.excluded_target_overlap_count == 6
    assert result.test_row_count == 30

    assert result.development_shape[0] == 114
    assert result.test_shape[0] == 30

    assert result.development_shape[1] == result.test_shape[1]

    assert result.development_label_counts == (
        38,
        38,
        38,
    )
    assert result.test_label_counts == (
        10,
        10,
        10,
    )

    assert result.excluded_present_feature_names == (
        "candle.close",
        "price.close",
    )

    assert result.preprocessor.schema.input_feature_count == 2
    assert result.preprocessor.schema.output_feature_count == 4

    assert result.logistic_iterations > 0

    assert result.logistic_evaluation.test_metrics.macro_f1 > 0.90
    assert result.logistic_evaluation.test_metrics.balanced_accuracy > 0.90

    assert result.logistic_evaluation.test_metrics.row_count == 30

    assert sum(result.logistic_evaluation.test_predicted_label_counts) == 30

    payload = result.to_dict()

    selected_configuration = payload["selected_configuration"]

    assert isinstance(
        selected_configuration,
        dict,
    )
    assert selected_configuration["policy"] == "normalized_deduplicated"
    assert selected_configuration["c_value"] == 0.03
    assert selected_configuration["selection_method"] == "expanding_walk_forward"


def test_sorts_reversed_source_rows() -> None:
    rows = cyclic_rows(150)
    evaluation_start = BASE_TIME + timedelta(hours=120)

    ordered_result = evaluate_final_logistic_model(
        rows,
        evaluation_start=evaluation_start,
        policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
        c_value=0.03,
    )
    reversed_result = evaluate_final_logistic_model(
        tuple(reversed(rows)),
        evaluation_start=evaluation_start,
        policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
        c_value=0.03,
    )

    assert ordered_result.development_label_counts == reversed_result.development_label_counts
    assert ordered_result.test_label_counts == reversed_result.test_label_counts
    assert (
        ordered_result.logistic_evaluation.test_metrics
        == reversed_result.logistic_evaluation.test_metrics
    )
    assert (
        ordered_result.logistic_evaluation.test_predicted_label_counts
        == reversed_result.logistic_evaluation.test_predicted_label_counts
    )


@pytest.mark.parametrize(
    "invalid_c_value",
    [
        0.0,
        -1.0,
        float("nan"),
        float("inf"),
        True,
    ],
)
def test_rejects_invalid_c_value(
    invalid_c_value: float,
) -> None:
    with pytest.raises(
        MLFinalEvaluationError,
        match="C",
    ):
        evaluate_final_logistic_model(
            cyclic_rows(150),
            evaluation_start=(BASE_TIME + timedelta(hours=120)),
            policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
            c_value=invalid_c_value,
        )


def test_rejects_naive_evaluation_start() -> None:
    with pytest.raises(
        MLFinalEvaluationError,
        match="timezone-aware",
    ):
        evaluate_final_logistic_model(
            cyclic_rows(150),
            evaluation_start=datetime(
                2026,
                1,
                6,
                0,
                0,
            ),
            policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
            c_value=0.03,
        )


def test_rejects_non_utc_evaluation_start() -> None:
    non_utc_timezone = timezone(timedelta(hours=1))

    with pytest.raises(
        MLFinalEvaluationError,
        match="exprimé en UTC",
    ):
        evaluate_final_logistic_model(
            cyclic_rows(150),
            evaluation_start=datetime(
                2026,
                1,
                6,
                0,
                0,
                tzinfo=non_utc_timezone,
            ),
            policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
            c_value=0.03,
        )


def test_rejects_empty_dataset() -> None:
    with pytest.raises(
        MLFinalEvaluationError,
        match="ne peut pas être vide",
    ):
        evaluate_final_logistic_model(
            (),
            evaluation_start=(BASE_TIME + timedelta(hours=120)),
            policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
            c_value=0.03,
        )


def test_rejects_duplicate_observations() -> None:
    rows = list(cyclic_rows(150))
    rows[-1] = rows[-1].model_copy(
        update={
            "observation_id": 1,
        }
    )

    with pytest.raises(
        MLFinalEvaluationError,
        match="plusieurs lignes",
    ):
        evaluate_final_logistic_model(
            tuple(rows),
            evaluation_start=(BASE_TIME + timedelta(hours=120)),
            policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
            c_value=0.03,
        )


def test_rejects_multiple_jobs() -> None:
    rows = list(cyclic_rows(150))
    rows[-1] = rows[-1].model_copy(
        update={
            "job_id": "other-job",
        }
    )

    with pytest.raises(
        MLFinalEvaluationError,
        match="même job",
    ):
        evaluate_final_logistic_model(
            tuple(rows),
            evaluation_start=(BASE_TIME + timedelta(hours=120)),
            policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
            c_value=0.03,
        )


def test_rejects_multiple_horizons() -> None:
    rows = list(cyclic_rows(150))
    rows[-1] = rows[-1].model_copy(
        update={
            "horizon": 12,
        }
    )

    with pytest.raises(
        MLFinalEvaluationError,
        match="même horizon",
    ):
        evaluate_final_logistic_model(
            tuple(rows),
            evaluation_start=(BASE_TIME + timedelta(hours=120)),
            policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
            c_value=0.03,
        )


def test_rejects_empty_development_partition() -> None:
    with pytest.raises(
        MLFinalEvaluationError,
        match="développement est vide",
    ):
        evaluate_final_logistic_model(
            cyclic_rows(150),
            evaluation_start=BASE_TIME,
            policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
            c_value=0.03,
        )


def test_rejects_empty_test_partition() -> None:
    with pytest.raises(
        MLFinalEvaluationError,
        match="test est vide",
    ):
        evaluate_final_logistic_model(
            cyclic_rows(150),
            evaluation_start=(BASE_TIME + timedelta(hours=200)),
            policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
            c_value=0.03,
        )


def test_rejects_development_without_three_classes() -> None:
    with pytest.raises(
        MLFinalEvaluationError,
        match="trois classes",
    ):
        evaluate_final_logistic_model(
            neutral_rows(150),
            evaluation_start=(BASE_TIME + timedelta(hours=120)),
            policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
            c_value=0.03,
        )
