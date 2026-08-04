from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ml.domain.ml_evaluation import (
    evaluate_classification,
)
from app.ml.domain.ml_feature_policy import (
    MLFeaturePolicy,
    MLFeaturePolicyError,
)
from app.ml.domain.ml_walk_forward import (
    MLWalkForwardPlan,
    build_expanding_walk_forward_plan,
)
from app.ml.models.ml_dataset import (
    MLDatasetRow,
    MarketDirectionLabel,
)
from app.ml.services.ml_walk_forward_evaluator import (
    MLWalkForwardCandidateEvaluation,
    MLWalkForwardEvaluationError,
    MLWalkForwardEvaluationResult,
    evaluate_logistic_walk_forward,
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
) -> MLDatasetRow:
    """Construit une ligne causalement valide et facilement séparable."""
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
        job_id="walk-forward-evaluation-test",
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
    """Construit un dataset équilibré à trois classes."""
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
    """Construit un dataset ne contenant qu'une seule classe."""
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


def evaluation_plan(
    rows: tuple[MLDatasetRow, ...] | None = None,
) -> MLWalkForwardPlan:
    """Construit un petit plan walk-forward déterministe."""
    selected_rows = rows if rows is not None else cyclic_rows(150)

    return build_expanding_walk_forward_plan(
        selected_rows,
        evaluation_end=(BASE_TIME + timedelta(hours=140)),
        fold_count=2,
        validation_window=24,
        minimum_train_window=60,
    )


def test_evaluates_and_deduplicates_candidates() -> None:
    result = evaluate_logistic_walk_forward(
        evaluation_plan(),
        policies=(
            MLFeaturePolicy.WITHOUT_ABSOLUTE,
            "without_absolute",
        ),
        c_values=(
            1.0,
            1.0,
        ),
    )

    assert len(result.candidates) == 1
    assert len(result.ranked_candidates) == 1

    candidate = result.best_candidate

    assert candidate.policy == MLFeaturePolicy.WITHOUT_ABSOLUTE
    assert candidate.c_value == 1.0
    assert candidate.fold_count == 2
    assert candidate.total_validation_row_count == 48

    assert sum(candidate.pooled_predicted_label_counts) == 48

    assert candidate.pooled_validation_metrics.row_count == 48

    assert candidate.mean_validation_macro_f1 > 0.90
    assert candidate.pooled_validation_metrics.macro_f1 > 0.90

    minimum_columns, maximum_columns = candidate.output_feature_count_range

    assert minimum_columns > 0
    assert maximum_columns >= minimum_columns

    assert all(
        fold.train_row_count > 0
        and fold.validation_row_count == 24
        and fold.output_feature_count > 0
        and fold.logistic_iterations > 0
        for fold in candidate.folds
    )

    payload = result.to_dict()

    assert payload["candidate_count"] == 1
    assert payload["fold_count"] == 2

    candidates_payload = payload["candidates"]

    assert isinstance(
        candidates_payload,
        list,
    )
    assert candidates_payload[0]["rank"] == 1
    assert candidates_payload[0]["policy"] == "without_absolute"


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
def test_rejects_invalid_c_values(
    invalid_c_value: float,
) -> None:
    with pytest.raises(
        MLWalkForwardEvaluationError,
        match="valeurs de C",
    ):
        evaluate_logistic_walk_forward(
            evaluation_plan(),
            policies=(MLFeaturePolicy.WITHOUT_ABSOLUTE,),
            c_values=(invalid_c_value,),
        )


def test_rejects_empty_c_values() -> None:
    with pytest.raises(
        MLWalkForwardEvaluationError,
        match="au moins une valeur de C",
    ):
        evaluate_logistic_walk_forward(
            evaluation_plan(),
            policies=(MLFeaturePolicy.WITHOUT_ABSOLUTE,),
            c_values=(),
        )


def test_rejects_empty_policies() -> None:
    with pytest.raises(
        MLWalkForwardEvaluationError,
        match="au moins une politique",
    ):
        evaluate_logistic_walk_forward(
            evaluation_plan(),
            policies=(),
            c_values=(1.0,),
        )


def test_rejects_unknown_policy() -> None:
    with pytest.raises(
        MLFeaturePolicyError,
        match="politique de features inconnue",
    ):
        evaluate_logistic_walk_forward(
            evaluation_plan(),
            policies=("unknown-policy",),
            c_values=(1.0,),
        )


def test_rejects_train_without_three_classes() -> None:
    with pytest.raises(
        MLWalkForwardEvaluationError,
        match="doit contenir les trois classes",
    ):
        evaluate_logistic_walk_forward(
            evaluation_plan(neutral_rows(150)),
            policies=(MLFeaturePolicy.WITHOUT_ABSOLUTE,),
            c_values=(1.0,),
        )


def test_rejects_plan_without_folds() -> None:
    empty_plan = MLWalkForwardPlan(
        folds=(),
        evaluation_end=(BASE_TIME + timedelta(hours=100)),
        validation_window=24,
        minimum_train_window=60,
        source_row_count=0,
        eligible_row_count=0,
        excluded_at_or_after_evaluation_end=0,
        excluded_target_overlap_count=0,
    )

    with pytest.raises(
        MLWalkForwardEvaluationError,
        match="ne contient aucun fold",
    ):
        evaluate_logistic_walk_forward(empty_plan)


def test_ranking_uses_lower_c_after_exact_tie() -> None:
    perfect_metrics = evaluate_classification(
        expected_labels=[
            0,
            1,
            2,
        ],
        predicted_labels=[
            0,
            1,
            2,
        ],
    )

    higher_c = MLWalkForwardCandidateEvaluation(
        policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
        c_value=1.0,
        folds=(),
        pooled_validation_metrics=perfect_metrics,
        pooled_predicted_label_counts=(
            1,
            1,
            1,
        ),
        mean_train_macro_f1=1.0,
        mean_validation_macro_f1=1.0,
        standard_deviation_validation_macro_f1=0.0,
        minimum_validation_macro_f1=1.0,
        mean_validation_balanced_accuracy=1.0,
        standard_deviation_validation_balanced_accuracy=0.0,
        mean_generalization_gap=0.0,
    )
    lower_c = MLWalkForwardCandidateEvaluation(
        policy=MLFeaturePolicy.WITHOUT_ABSOLUTE,
        c_value=0.1,
        folds=(),
        pooled_validation_metrics=perfect_metrics,
        pooled_predicted_label_counts=(
            1,
            1,
            1,
        ),
        mean_train_macro_f1=1.0,
        mean_validation_macro_f1=1.0,
        standard_deviation_validation_macro_f1=0.0,
        minimum_validation_macro_f1=1.0,
        mean_validation_balanced_accuracy=1.0,
        standard_deviation_validation_balanced_accuracy=0.0,
        mean_generalization_gap=0.0,
    )

    result = MLWalkForwardEvaluationResult(
        evaluation_end=(BASE_TIME + timedelta(hours=100)),
        fold_count=2,
        validation_window=24,
        minimum_train_window=60,
        candidates=(
            higher_c,
            lower_c,
        ),
    )

    assert result.best_candidate.c_value == 0.1
    assert result.ranked_candidates == (
        lower_c,
        higher_c,
    )
