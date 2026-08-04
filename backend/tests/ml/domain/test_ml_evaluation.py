from __future__ import annotations

from typing import Any, cast

import numpy as np
import pytest

from app.ml.domain.ml_evaluation import (
    MLEvaluationError,
    evaluate_classification,
)
from app.ml.models.ml_dataset import (
    MarketDirectionLabel,
)


def test_evaluate_known_confusion_matrix_and_metrics() -> None:
    metrics = evaluate_classification(
        expected_labels=[
            0,
            0,
            1,
            1,
            1,
            2,
        ],
        predicted_labels=[
            1,
            1,
            1,
            1,
            1,
            1,
        ],
    )

    assert metrics.row_count == 6
    assert metrics.confusion_matrix == (
        (
            0,
            2,
            0,
        ),
        (
            0,
            3,
            0,
        ),
        (
            0,
            1,
            0,
        ),
    )

    assert metrics.accuracy == pytest.approx(0.5)
    assert metrics.balanced_accuracy == pytest.approx(1.0 / 3.0)
    assert metrics.macro_precision == pytest.approx(1.0 / 6.0)
    assert metrics.macro_recall == pytest.approx(1.0 / 3.0)
    assert metrics.macro_f1 == pytest.approx(2.0 / 9.0)
    assert metrics.weighted_f1 == pytest.approx(1.0 / 3.0)

    down = metrics.class_metrics(MarketDirectionLabel.DOWN)
    neutral = metrics.class_metrics(MarketDirectionLabel.NEUTRAL)
    up = metrics.class_metrics(MarketDirectionLabel.UP)

    assert down.support == 2
    assert down.prediction_count == 0
    assert down.true_positive_count == 0
    assert down.precision == 0.0
    assert down.recall == 0.0
    assert down.f1 == 0.0

    assert neutral.support == 3
    assert neutral.prediction_count == 6
    assert neutral.true_positive_count == 3
    assert neutral.precision == pytest.approx(0.5)
    assert neutral.recall == pytest.approx(1.0)
    assert neutral.f1 == pytest.approx(2.0 / 3.0)

    assert up.support == 1
    assert up.prediction_count == 0
    assert up.true_positive_count == 0
    assert up.precision == 0.0
    assert up.recall == 0.0
    assert up.f1 == 0.0


def test_evaluate_perfect_classification() -> None:
    metrics = evaluate_classification(
        expected_labels=[
            0,
            1,
            2,
            0,
            1,
            2,
        ],
        predicted_labels=[
            0,
            1,
            2,
            0,
            1,
            2,
        ],
    )

    assert metrics.confusion_matrix == (
        (
            2,
            0,
            0,
        ),
        (
            0,
            2,
            0,
        ),
        (
            0,
            0,
            2,
        ),
    )

    assert metrics.accuracy == 1.0
    assert metrics.balanced_accuracy == 1.0
    assert metrics.macro_precision == 1.0
    assert metrics.macro_recall == 1.0
    assert metrics.macro_f1 == 1.0
    assert metrics.weighted_f1 == 1.0

    for class_metrics in metrics.classes:
        assert class_metrics.support == 2
        assert class_metrics.prediction_count == 2
        assert class_metrics.true_positive_count == 2
        assert class_metrics.precision == 1.0
        assert class_metrics.recall == 1.0
        assert class_metrics.f1 == 1.0


def test_absent_class_receives_zero_recall() -> None:
    metrics = evaluate_classification(
        expected_labels=[
            0,
            0,
            1,
            1,
        ],
        predicted_labels=[
            0,
            0,
            1,
            1,
        ],
    )

    assert metrics.accuracy == 1.0

    assert metrics.class_metrics(MarketDirectionLabel.DOWN).recall == 1.0

    assert metrics.class_metrics(MarketDirectionLabel.NEUTRAL).recall == 1.0

    up_metrics = metrics.class_metrics(MarketDirectionLabel.UP)

    assert up_metrics.support == 0
    assert up_metrics.prediction_count == 0
    assert up_metrics.recall == 0.0
    assert up_metrics.precision == 0.0
    assert up_metrics.f1 == 0.0

    assert metrics.balanced_accuracy == pytest.approx(2.0 / 3.0)
    assert metrics.macro_recall == pytest.approx(2.0 / 3.0)
    assert metrics.macro_f1 == pytest.approx(2.0 / 3.0)
    assert metrics.weighted_f1 == 1.0


def test_to_dict_is_json_compatible_and_ordered() -> None:
    metrics = evaluate_classification(
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

    payload = metrics.to_dict()

    assert payload["row_count"] == 3
    assert payload["accuracy"] == 1.0
    assert payload["label_order"] == [
        "down",
        "neutral",
        "up",
    ]
    assert payload["confusion_matrix"] == [
        [
            1,
            0,
            0,
        ],
        [
            0,
            1,
            0,
        ],
        [
            0,
            0,
            1,
        ],
    ]

    classes = cast(
        list[dict[str, Any]],
        payload["classes"],
    )

    assert [class_payload["label"] for class_payload in classes] == [
        "down",
        "neutral",
        "up",
    ]

    assert [class_payload["label_index"] for class_payload in classes] == [
        0,
        1,
        2,
    ]


def test_evaluate_accepts_numpy_integer_labels() -> None:
    expected = np.asarray(
        [
            0,
            1,
            2,
        ],
        dtype=np.int64,
    )
    predicted = np.asarray(
        [
            0,
            1,
            2,
        ],
        dtype=np.int32,
    )

    metrics = evaluate_classification(
        expected,
        predicted,
    )

    assert metrics.accuracy == 1.0
    assert metrics.row_count == 3


def test_evaluate_accepts_generator_inputs() -> None:
    metrics = evaluate_classification(
        (
            label
            for label in [
                0,
                1,
                2,
            ]
        ),
        (
            label
            for label in [
                0,
                1,
                2,
            ]
        ),
    )

    assert metrics.row_count == 3
    assert metrics.accuracy == 1.0


def test_evaluate_rejects_empty_labels() -> None:
    with pytest.raises(
        MLEvaluationError,
        match="aucun label",
    ):
        evaluate_classification(
            [],
            [],
        )


def test_evaluate_rejects_different_lengths() -> None:
    with pytest.raises(
        MLEvaluationError,
        match="même longueur",
    ):
        evaluate_classification(
            [
                0,
                1,
            ],
            [
                0,
            ],
        )


@pytest.mark.parametrize(
    "invalid_argument",
    [
        "expected",
        "predicted",
    ],
)
def test_evaluate_rejects_boolean_labels(
    invalid_argument: str,
) -> None:
    expected: list[object] = [
        0,
        1,
    ]
    predicted: list[object] = [
        0,
        1,
    ]

    if invalid_argument == "expected":
        expected[0] = True
    else:
        predicted[0] = False

    with pytest.raises(
        MLEvaluationError,
        match="ne peut pas être booléen",
    ):
        evaluate_classification(
            expected,
            predicted,
        )


@pytest.mark.parametrize(
    "invalid_value",
    [
        1.5,
        "1",
        None,
    ],
)
def test_evaluate_rejects_non_integer_labels(
    invalid_value: object,
) -> None:
    with pytest.raises(
        MLEvaluationError,
        match="doit être un entier",
    ):
        evaluate_classification(
            [
                0,
                1,
            ],
            [
                0,
                invalid_value,
            ],
        )


@pytest.mark.parametrize(
    "invalid_value",
    [
        -1,
        3,
    ],
)
def test_evaluate_rejects_unknown_label_indexes(
    invalid_value: int,
) -> None:
    with pytest.raises(
        MLEvaluationError,
        match="indice inconnu",
    ):
        evaluate_classification(
            [
                0,
                1,
            ],
            [
                0,
                invalid_value,
            ],
        )
