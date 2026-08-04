"""Évaluation finale unique sur la partition de test réservée."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence, TypeAlias

import numpy as np
from numpy.typing import NDArray
from sklearn.dummy import DummyClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from app.ml.domain.ml_evaluation import (
    MLClassificationMetrics,
    evaluate_classification,
)
from app.ml.domain.ml_feature_policy import (
    MLFeaturePolicy,
    apply_ml_feature_policy,
    normalize_feature_policy,
)
from app.ml.domain.ml_preprocessing import (
    LABEL_ORDER,
    MLFeaturePreprocessor,
    MLPreprocessingError,
    encode_market_labels,
)
from app.ml.models.ml_dataset import MLDatasetRow

MLClassifier: TypeAlias = DummyClassifier | LogisticRegression

LabelCounts: TypeAlias = tuple[
    int,
    int,
    int,
]


class MLFinalEvaluationError(ValueError):
    """Signale qu'une évaluation finale ne peut pas être réalisée."""


@dataclass(frozen=True, slots=True)
class MLFinalModelEvaluation:
    """Métriques finales d'un modèle."""

    model_name: str

    development_metrics: MLClassificationMetrics
    test_metrics: MLClassificationMetrics

    development_predicted_label_counts: LabelCounts
    test_predicted_label_counts: LabelCounts

    def to_dict(self) -> dict[str, object]:
        """Retourne une représentation JSON-compatible."""
        return {
            "model_name": self.model_name,
            "development_predicted_label_counts": (
                _label_counts_to_dict(self.development_predicted_label_counts)
            ),
            "test_predicted_label_counts": (
                _label_counts_to_dict(self.test_predicted_label_counts)
            ),
            "development_metrics": (self.development_metrics.to_dict()),
            "test_metrics": (self.test_metrics.to_dict()),
        }


@dataclass(frozen=True, slots=True)
class MLFinalEvaluationResult:
    """Résultat complet de l'évaluation finale réservée."""

    policy: MLFeaturePolicy
    c_value: float
    evaluation_start: datetime

    preprocessor: MLFeaturePreprocessor
    dummy_model: DummyClassifier
    logistic_model: LogisticRegression

    source_row_count: int
    development_row_count: int
    test_row_count: int
    excluded_target_overlap_count: int

    development_shape: tuple[int, int]
    test_shape: tuple[int, int]

    development_label_counts: LabelCounts
    test_label_counts: LabelCounts

    excluded_present_feature_names: tuple[str, ...]
    logistic_iterations: int

    dummy_evaluation: MLFinalModelEvaluation
    logistic_evaluation: MLFinalModelEvaluation

    def to_dict(self) -> dict[str, object]:
        """Retourne le rapport final sérialisable."""
        schema = self.preprocessor.schema

        return {
            "selected_configuration": {
                "policy": self.policy.value,
                "c_value": self.c_value,
                "selection_method": ("expanding_walk_forward"),
            },
            "evaluation_start": (self.evaluation_start.isoformat()),
            "source_row_count": self.source_row_count,
            "development_row_count": (self.development_row_count),
            "test_row_count": self.test_row_count,
            "excluded_target_overlap_count": (self.excluded_target_overlap_count),
            "development_shape": list(self.development_shape),
            "test_shape": list(self.test_shape),
            "development_label_counts": (_label_counts_to_dict(self.development_label_counts)),
            "test_label_counts": (_label_counts_to_dict(self.test_label_counts)),
            "feature_policy": {
                "excluded_present_feature_count": (len(self.excluded_present_feature_names)),
                "excluded_present_feature_names": list(self.excluded_present_feature_names),
            },
            "preprocessing": {
                "input_feature_count": (schema.input_feature_count),
                "dropped_constant_feature_count": (len(schema.dropped_constant_feature_names)),
                "active_feature_count": (schema.active_feature_count),
                "output_feature_count": (schema.output_feature_count),
            },
            "logistic_iterations": (self.logistic_iterations),
            "models": [
                self.dummy_evaluation.to_dict(),
                self.logistic_evaluation.to_dict(),
            ],
        }


def _validate_evaluation_start(
    evaluation_start: datetime,
) -> None:
    """Vérifie que la frontière de test est en UTC."""
    if evaluation_start.tzinfo is None or evaluation_start.utcoffset() is None:
        raise MLFinalEvaluationError("evaluation_start doit être timezone-aware")

    if evaluation_start.utcoffset() != timedelta(0):
        raise MLFinalEvaluationError("evaluation_start doit être exprimé en UTC")


def _normalize_c_value(
    c_value: float,
) -> float:
    """Valide la force de régularisation."""
    if isinstance(c_value, bool):
        raise MLFinalEvaluationError("C ne peut pas être booléen")

    converted = float(c_value)

    if not math.isfinite(converted) or converted <= 0:
        raise MLFinalEvaluationError("C doit être fini et strictement positif")

    return converted


def _ordered_rows(
    rows: Sequence[MLDatasetRow],
) -> tuple[MLDatasetRow, ...]:
    """Trie les lignes et vérifie les observations."""
    ordered = tuple(
        sorted(
            rows,
            key=lambda row: (
                row.decision_time,
                row.observation_id,
            ),
        )
    )

    if not ordered:
        raise MLFinalEvaluationError("le dataset ne peut pas être vide")

    observation_ids: set[int] = set()

    for row in ordered:
        if row.observation_id in observation_ids:
            raise MLFinalEvaluationError(
                "plusieurs lignes utilisent l'observation " f"{row.observation_id}"
            )

        observation_ids.add(row.observation_id)

    return ordered


def _validate_dataset_contract(
    rows: tuple[MLDatasetRow, ...],
) -> None:
    """Vérifie les métadonnées communes du dataset."""
    job_ids = {row.job_id for row in rows}
    horizons = {row.horizon for row in rows}

    if len(job_ids) != 1:
        raise MLFinalEvaluationError("toutes les lignes doivent provenir du même job")

    if len(horizons) != 1:
        raise MLFinalEvaluationError("toutes les lignes doivent utiliser le même horizon")


def _label_counts(
    labels: Sequence[int],
) -> LabelCounts:
    """Compte les labels dans l'ordre DOWN, NEUTRAL, UP."""
    counts = [0 for _ in LABEL_ORDER]

    for label_index in labels:
        if label_index < 0 or label_index >= len(LABEL_ORDER):
            raise MLFinalEvaluationError(f"indice de label inconnu : {label_index}")

        counts[label_index] += 1

    return (
        counts[0],
        counts[1],
        counts[2],
    )


def _label_counts_to_dict(
    counts: LabelCounts,
) -> dict[str, int]:
    """Associe les comptes aux labels métier."""
    return {label.value: counts[index] for index, label in enumerate(LABEL_ORDER)}


def _validate_training_classes(
    labels: NDArray[np.int64],
) -> None:
    """Vérifie que le développement contient les trois classes."""
    observed = tuple(sorted({int(value) for value in labels}))
    expected = tuple(range(len(LABEL_ORDER)))

    if observed != expected:
        raise MLFinalEvaluationError("le développement doit contenir " "les trois classes")


def _validate_model_classes(
    model: MLClassifier,
    *,
    model_name: str,
) -> None:
    """Vérifie l'ordre des classes appris."""
    classes = tuple(int(value) for value in np.asarray(model.classes_).tolist())
    expected = tuple(range(len(LABEL_ORDER)))

    if classes != expected:
        raise MLFinalEvaluationError(
            f"{model_name} utilise un ordre " f"de classes inattendu : {classes}"
        )


def _predict_labels(
    model: MLClassifier,
    matrix: NDArray[np.float64],
    *,
    model_name: str,
) -> tuple[int, ...]:
    """Produit et valide les prédictions."""
    predictions = np.asarray(model.predict(matrix))

    if predictions.shape != (matrix.shape[0],):
        raise MLFinalEvaluationError(
            f"{model_name} produit une forme " f"inattendue : {predictions.shape}"
        )

    normalized = tuple(int(value) for value in predictions.tolist())

    _label_counts(normalized)

    return normalized


def _fit_logistic_regression(
    x_development: NDArray[np.float64],
    y_development: NDArray[np.int64],
    *,
    c_value: float,
) -> LogisticRegression:
    """Entraîne le candidat sélectionné sur le développement."""
    model = LogisticRegression(
        C=c_value,
        class_weight="balanced",
        solver="lbfgs",
        max_iter=5000,
        tol=1e-5,
    )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter(
                "error",
                ConvergenceWarning,
            )

            model.fit(
                x_development,
                y_development,
            )
    except ConvergenceWarning as exc:
        raise MLFinalEvaluationError("la régression logistique finale " "n'a pas convergé") from exc
    except ValueError as exc:
        raise MLFinalEvaluationError("échec de l'entraînement final") from exc

    return model


def _evaluate_model(
    model: MLClassifier,
    *,
    model_name: str,
    x_development: NDArray[np.float64],
    y_development: NDArray[np.int64],
    x_test: NDArray[np.float64],
    y_test: NDArray[np.int64],
) -> MLFinalModelEvaluation:
    """Évalue un modèle sur le développement et le test."""
    development_predictions = _predict_labels(
        model,
        x_development,
        model_name=model_name,
    )
    test_predictions = _predict_labels(
        model,
        x_test,
        model_name=model_name,
    )

    expected_development = tuple(int(value) for value in y_development.tolist())
    expected_test = tuple(int(value) for value in y_test.tolist())

    return MLFinalModelEvaluation(
        model_name=model_name,
        development_metrics=evaluate_classification(
            expected_development,
            development_predictions,
        ),
        test_metrics=evaluate_classification(
            expected_test,
            test_predictions,
        ),
        development_predicted_label_counts=(_label_counts(development_predictions)),
        test_predicted_label_counts=(_label_counts(test_predictions)),
    )


def evaluate_final_logistic_model(
    rows: Sequence[MLDatasetRow],
    *,
    evaluation_start: datetime,
    policy: MLFeaturePolicy | str,
    c_value: float,
) -> MLFinalEvaluationResult:
    """Réentraîne le candidat puis ouvre une seule fois le test."""
    _validate_evaluation_start(evaluation_start)
    normalized_policy = normalize_feature_policy(policy)
    normalized_c_value = _normalize_c_value(c_value)

    ordered = _ordered_rows(rows)
    _validate_dataset_contract(ordered)

    development_rows = tuple(
        row
        for row in ordered
        if (row.decision_time < evaluation_start and row.exit_time < evaluation_start)
    )
    excluded_target_overlap = tuple(
        row
        for row in ordered
        if (row.decision_time < evaluation_start and row.exit_time >= evaluation_start)
    )
    test_rows = tuple(row for row in ordered if row.decision_time >= evaluation_start)

    if not development_rows:
        raise MLFinalEvaluationError("la partition de développement est vide")

    if not test_rows:
        raise MLFinalEvaluationError("la partition de test est vide")

    development_application = apply_ml_feature_policy(
        development_rows,
        policy=normalized_policy,
    )
    test_application = apply_ml_feature_policy(
        test_rows,
        policy=normalized_policy,
    )

    preprocessor = MLFeaturePreprocessor()

    try:
        x_development = preprocessor.fit_transform(development_application.rows)
        x_test = preprocessor.transform(test_application.rows)
    except MLPreprocessingError as exc:
        raise MLFinalEvaluationError("échec du prétraitement final") from exc

    y_development = encode_market_labels(development_application.rows)
    y_test = encode_market_labels(test_application.rows)

    _validate_training_classes(y_development)

    dummy_model = DummyClassifier(strategy="most_frequent")
    dummy_model.fit(
        x_development,
        y_development,
    )

    logistic_model = _fit_logistic_regression(
        x_development,
        y_development,
        c_value=normalized_c_value,
    )

    _validate_model_classes(
        dummy_model,
        model_name="dummy_most_frequent",
    )
    _validate_model_classes(
        logistic_model,
        model_name=("logistic_regression_selected"),
    )

    dummy_evaluation = _evaluate_model(
        dummy_model,
        model_name="dummy_most_frequent",
        x_development=x_development,
        y_development=y_development,
        x_test=x_test,
        y_test=y_test,
    )
    logistic_evaluation = _evaluate_model(
        logistic_model,
        model_name=("logistic_regression_selected"),
        x_development=x_development,
        y_development=y_development,
        x_test=x_test,
        y_test=y_test,
    )

    iteration_values = np.asarray(logistic_model.n_iter_)

    if iteration_values.size == 0:
        raise MLFinalEvaluationError("nombre d'itérations final absent")

    development_labels = tuple(int(value) for value in y_development.tolist())
    test_labels = tuple(int(value) for value in y_test.tolist())

    return MLFinalEvaluationResult(
        policy=normalized_policy,
        c_value=normalized_c_value,
        evaluation_start=evaluation_start,
        preprocessor=preprocessor,
        dummy_model=dummy_model,
        logistic_model=logistic_model,
        source_row_count=len(ordered),
        development_row_count=len(development_rows),
        test_row_count=len(test_rows),
        excluded_target_overlap_count=len(excluded_target_overlap),
        development_shape=(
            int(x_development.shape[0]),
            int(x_development.shape[1]),
        ),
        test_shape=(
            int(x_test.shape[0]),
            int(x_test.shape[1]),
        ),
        development_label_counts=_label_counts(development_labels),
        test_label_counts=_label_counts(test_labels),
        excluded_present_feature_names=(development_application.excluded_present_feature_names),
        logistic_iterations=int(iteration_values.max()),
        dummy_evaluation=dummy_evaluation,
        logistic_evaluation=(logistic_evaluation),
    )
