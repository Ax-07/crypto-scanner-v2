"""Évaluation déterministe des classifications directionnelles ML."""

from __future__ import annotations

import math
import operator
from dataclasses import dataclass
from typing import Iterable, SupportsIndex, cast

from app.ml.domain.ml_preprocessing import LABEL_ORDER
from app.ml.models.ml_dataset import MarketDirectionLabel


class MLEvaluationError(ValueError):
    """Signale des labels ou des prédictions impossibles à évaluer."""


@dataclass(frozen=True, slots=True)
class MLClassMetrics:
    """Métriques calculées pour une classe directionnelle."""

    label: MarketDirectionLabel
    label_index: int

    support: int
    prediction_count: int
    true_positive_count: int

    precision: float
    recall: float
    f1: float


@dataclass(frozen=True, slots=True)
class MLClassificationMetrics:
    """Métriques complètes d'une classification à trois classes."""

    row_count: int

    accuracy: float
    balanced_accuracy: float

    macro_precision: float
    macro_recall: float
    macro_f1: float
    weighted_f1: float

    confusion_matrix: tuple[
        tuple[int, ...],
        ...,
    ]
    classes: tuple[MLClassMetrics, ...]

    def class_metrics(
        self,
        label: MarketDirectionLabel,
    ) -> MLClassMetrics:
        """Retourne les métriques d'une classe précise."""
        for metrics in self.classes:
            if metrics.label == label:
                return metrics

        raise MLEvaluationError(f"métriques absentes pour la classe {label.value}")

    def to_dict(self) -> dict[str, object]:
        """Retourne une représentation JSON-compatible."""
        return {
            "row_count": self.row_count,
            "accuracy": self.accuracy,
            "balanced_accuracy": self.balanced_accuracy,
            "macro_precision": self.macro_precision,
            "macro_recall": self.macro_recall,
            "macro_f1": self.macro_f1,
            "weighted_f1": self.weighted_f1,
            "label_order": [label.value for label in LABEL_ORDER],
            "confusion_matrix": [list(row) for row in self.confusion_matrix],
            "classes": [
                {
                    "label": metrics.label.value,
                    "label_index": (metrics.label_index),
                    "support": metrics.support,
                    "prediction_count": (metrics.prediction_count),
                    "true_positive_count": (metrics.true_positive_count),
                    "precision": metrics.precision,
                    "recall": metrics.recall,
                    "f1": metrics.f1,
                }
                for metrics in self.classes
            ],
        }


def _normalize_labels(
    values: Iterable[object],
    *,
    name: str,
) -> tuple[int, ...]:
    """Convertit des indices entiers et vérifie leur domaine."""
    normalized: list[int] = []
    maximum_label = len(LABEL_ORDER) - 1

    for position, value in enumerate(values):
        if isinstance(value, bool):
            raise MLEvaluationError(f"{name}[{position}] ne peut pas être booléen")

        try:
            label_index = operator.index(cast(SupportsIndex, value))
        except TypeError as exc:
            raise MLEvaluationError(f"{name}[{position}] doit être un entier") from exc

        if label_index < 0 or label_index > maximum_label:
            raise MLEvaluationError(
                f"{name}[{position}] contient un indice " f"inconnu : {label_index}"
            )

        normalized.append(label_index)

    return tuple(normalized)


def _safe_ratio(
    numerator: int,
    denominator: int,
) -> float:
    """Calcule une proportion sans division par zéro."""
    if denominator == 0:
        return 0.0

    ratio = numerator / denominator

    if not math.isfinite(ratio):
        raise MLEvaluationError("une métrique calculée n'est pas finie")

    return ratio


def evaluate_classification(
    expected_labels: Iterable[object],
    predicted_labels: Iterable[object],
) -> MLClassificationMetrics:
    """Évalue des prédictions dans l'ordre DOWN, NEUTRAL, UP.

    La balanced accuracy correspond à la moyenne des rappels des trois
    classes métier. Une classe absente de la vérité reçoit donc un rappel
    nul afin de conserver une définition stable entre les partitions.
    """
    expected = _normalize_labels(
        expected_labels,
        name="expected_labels",
    )
    predicted = _normalize_labels(
        predicted_labels,
        name="predicted_labels",
    )

    if not expected:
        raise MLEvaluationError("aucun label n'est disponible pour l'évaluation")

    if len(expected) != len(predicted):
        raise MLEvaluationError(
            "expected_labels et predicted_labels " "doivent avoir la même longueur"
        )

    class_count = len(LABEL_ORDER)

    mutable_confusion_matrix = [[0 for _ in range(class_count)] for _ in range(class_count)]

    for expected_label, predicted_label in zip(
        expected,
        predicted,
        strict=True,
    ):
        mutable_confusion_matrix[expected_label][predicted_label] += 1

    confusion_matrix = tuple(tuple(row) for row in mutable_confusion_matrix)

    class_metrics: list[MLClassMetrics] = []

    for label_index, label in enumerate(LABEL_ORDER):
        support = sum(confusion_matrix[label_index])
        prediction_count = sum(row[label_index] for row in confusion_matrix)
        true_positive_count = confusion_matrix[label_index][label_index]

        precision = _safe_ratio(
            true_positive_count,
            prediction_count,
        )
        recall = _safe_ratio(
            true_positive_count,
            support,
        )

        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2.0 * precision * recall / (precision + recall)

        if not math.isfinite(f1):
            raise MLEvaluationError("une métrique F1 calculée n'est pas finie")

        class_metrics.append(
            MLClassMetrics(
                label=label,
                label_index=label_index,
                support=support,
                prediction_count=prediction_count,
                true_positive_count=(true_positive_count),
                precision=precision,
                recall=recall,
                f1=f1,
            )
        )

    row_count = len(expected)
    correct_count = sum(confusion_matrix[index][index] for index in range(class_count))

    accuracy = _safe_ratio(
        correct_count,
        row_count,
    )
    macro_precision = sum(metrics.precision for metrics in class_metrics) / class_count
    macro_recall = sum(metrics.recall for metrics in class_metrics) / class_count
    macro_f1 = sum(metrics.f1 for metrics in class_metrics) / class_count
    weighted_f1 = sum(metrics.f1 * metrics.support for metrics in class_metrics) / row_count

    calculated_metrics = (
        accuracy,
        macro_precision,
        macro_recall,
        macro_f1,
        weighted_f1,
    )

    if not all(math.isfinite(value) for value in calculated_metrics):
        raise MLEvaluationError("les métriques globales doivent être finies")

    return MLClassificationMetrics(
        row_count=row_count,
        accuracy=accuracy,
        balanced_accuracy=macro_recall,
        macro_precision=macro_precision,
        macro_recall=macro_recall,
        macro_f1=macro_f1,
        weighted_f1=weighted_f1,
        confusion_matrix=confusion_matrix,
        classes=tuple(class_metrics),
    )
