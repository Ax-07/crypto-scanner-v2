"""Entraînement des modèles de référence du pipeline ML."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import TypeAlias

import numpy as np
from numpy.typing import NDArray
from sklearn.dummy import DummyClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from app.ml.domain.ml_evaluation import (
    MLClassificationMetrics,
    evaluate_classification,
)
from app.ml.domain.ml_preprocessing import (
    LABEL_ORDER,
    MLFeaturePreprocessor,
    encode_market_labels,
)
from app.ml.domain.ml_temporal_split import (
    MLTemporalSplit,
)

MLClassifier: TypeAlias = DummyClassifier | LogisticRegression

LabelCounts: TypeAlias = tuple[
    int,
    int,
    int,
]


class MLBaselineTrainingError(ValueError):
    """Signale qu'un modèle baseline ne peut pas être entraîné."""


@dataclass(frozen=True, slots=True)
class MLModelEvaluation:
    """Résultats d'un modèle sur le train et la validation."""

    model_name: str
    train_metrics: MLClassificationMetrics
    validation_metrics: MLClassificationMetrics

    def to_dict(self) -> dict[str, object]:
        """Retourne une représentation JSON-compatible."""
        return {
            "model_name": self.model_name,
            "train_metrics": (self.train_metrics.to_dict()),
            "validation_metrics": (self.validation_metrics.to_dict()),
        }


@dataclass(frozen=True, slots=True)
class MLBaselineTrainingResult:
    """Résultat complet de l'entraînement des baselines."""

    preprocessor: MLFeaturePreprocessor

    dummy_model: DummyClassifier
    logistic_model: LogisticRegression

    dummy_evaluation: MLModelEvaluation
    logistic_evaluation: MLModelEvaluation

    train_shape: tuple[int, int]
    validation_shape: tuple[int, int]

    train_label_counts: LabelCounts
    validation_label_counts: LabelCounts

    reserved_test_row_count: int
    logistic_iterations: tuple[int, ...]

    def to_dict(self) -> dict[str, object]:
        """Retourne le rapport d'entraînement sérialisable."""
        schema = self.preprocessor.schema

        return {
            "train_shape": list(self.train_shape),
            "validation_shape": list(self.validation_shape),
            "reserved_test_row_count": (self.reserved_test_row_count),
            "train_label_counts": (_label_counts_to_dict(self.train_label_counts)),
            "validation_label_counts": (_label_counts_to_dict(self.validation_label_counts)),
            "preprocessing": {
                "input_feature_count": (schema.input_feature_count),
                "dropped_constant_feature_count": (len(schema.dropped_constant_feature_names)),
                "active_feature_count": (schema.active_feature_count),
                "output_feature_count": (schema.output_feature_count),
            },
            "logistic_iterations": list(self.logistic_iterations),
            "models": [
                self.dummy_evaluation.to_dict(),
                self.logistic_evaluation.to_dict(),
            ],
        }


def _label_counts(
    encoded_labels: NDArray[np.int64],
) -> LabelCounts:
    """Compte les labels dans l'ordre DOWN, NEUTRAL, UP."""
    counts = np.bincount(
        encoded_labels,
        minlength=len(LABEL_ORDER),
    )

    if counts.shape != (len(LABEL_ORDER),):
        raise MLBaselineTrainingError("forme inattendue des comptes de labels")

    return (
        int(counts[0]),
        int(counts[1]),
        int(counts[2]),
    )


def _label_counts_to_dict(
    counts: LabelCounts,
) -> dict[str, int]:
    """Associe les comptes aux labels métier."""
    return {label.value: counts[index] for index, label in enumerate(LABEL_ORDER)}


def _validate_training_labels(
    encoded_labels: NDArray[np.int64],
) -> None:
    """Vérifie que les trois classes existent dans le train."""
    observed_labels = tuple(sorted({int(value) for value in encoded_labels}))
    expected_labels = tuple(range(len(LABEL_ORDER)))

    if observed_labels != expected_labels:
        raise MLBaselineTrainingError(
            "le train doit contenir les trois classes " "DOWN, NEUTRAL et UP"
        )


def _validate_model_classes(
    model: MLClassifier,
    *,
    model_name: str,
) -> None:
    """Vérifie l'ordre des classes appris par scikit-learn."""
    classes = np.asarray(model.classes_)

    if classes.ndim != 1:
        raise MLBaselineTrainingError(f"{model_name} utilise une cible multi-sortie")

    normalized_classes = tuple(int(value) for value in classes.tolist())
    expected_classes = tuple(range(len(LABEL_ORDER)))

    if normalized_classes != expected_classes:
        raise MLBaselineTrainingError(
            f"{model_name} utilise un ordre de classes " f"inattendu : {normalized_classes}"
        )


def _predict_labels(
    model: MLClassifier,
    matrix: NDArray[np.float64],
    *,
    model_name: str,
) -> tuple[int, ...]:
    """Produit et valide les prédictions d'un modèle."""
    predictions = np.asarray(model.predict(matrix))

    if predictions.shape != (matrix.shape[0],):
        raise MLBaselineTrainingError(
            f"{model_name} produit une forme " f"inattendue : {predictions.shape}"
        )

    normalized: list[int] = []

    for position, value in enumerate(predictions.tolist()):
        label_index = int(value)

        if label_index < 0 or label_index >= len(LABEL_ORDER):
            raise MLBaselineTrainingError(
                f"{model_name} produit un label "
                f"inconnu à la position {position} : "
                f"{label_index}"
            )

        normalized.append(label_index)

    return tuple(normalized)


def _evaluate_model(
    model: MLClassifier,
    *,
    model_name: str,
    x_train: NDArray[np.float64],
    y_train: NDArray[np.int64],
    x_validation: NDArray[np.float64],
    y_validation: NDArray[np.int64],
) -> MLModelEvaluation:
    """Évalue un modèle sans utiliser la partition de test."""
    train_predictions = _predict_labels(
        model,
        x_train,
        model_name=model_name,
    )
    validation_predictions = _predict_labels(
        model,
        x_validation,
        model_name=model_name,
    )

    return MLModelEvaluation(
        model_name=model_name,
        train_metrics=evaluate_classification(
            y_train,
            train_predictions,
        ),
        validation_metrics=(
            evaluate_classification(
                y_validation,
                validation_predictions,
            )
        ),
    )


def _fit_logistic_regression(
    x_train: NDArray[np.float64],
    y_train: NDArray[np.int64],
) -> LogisticRegression:
    """Entraîne la régression logistique pondérée."""
    model = LogisticRegression(
        C=1.0,
        class_weight="balanced",
        solver="lbfgs",
        max_iter=2000,
        tol=1e-5,
    )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter(
                "error",
                ConvergenceWarning,
            )
            model.fit(
                x_train,
                y_train,
            )
    except ConvergenceWarning as exc:
        raise MLBaselineTrainingError("la régression logistique " "n'a pas convergé") from exc
    except ValueError as exc:
        raise MLBaselineTrainingError(
            "échec de l'entraînement de la " "régression logistique"
        ) from exc

    return model


def train_ml_baselines(
    split: MLTemporalSplit,
) -> MLBaselineTrainingResult:
    """Entraîne les baselines uniquement sur train/validation."""
    if not split.train_rows:
        raise MLBaselineTrainingError("la partition d'entraînement est vide")

    if not split.validation_rows:
        raise MLBaselineTrainingError("la partition de validation est vide")

    preprocessor = MLFeaturePreprocessor()

    x_train = preprocessor.fit_transform(split.train_rows)
    x_validation = preprocessor.transform(split.validation_rows)

    y_train = encode_market_labels(split.train_rows)
    y_validation = encode_market_labels(split.validation_rows)

    _validate_training_labels(y_train)

    dummy_model = DummyClassifier(strategy="most_frequent")
    dummy_model.fit(
        x_train,
        y_train,
    )

    logistic_model = _fit_logistic_regression(
        x_train,
        y_train,
    )

    _validate_model_classes(
        dummy_model,
        model_name="dummy_most_frequent",
    )
    _validate_model_classes(
        logistic_model,
        model_name=("logistic_regression_balanced"),
    )

    dummy_evaluation = _evaluate_model(
        dummy_model,
        model_name="dummy_most_frequent",
        x_train=x_train,
        y_train=y_train,
        x_validation=x_validation,
        y_validation=y_validation,
    )
    logistic_evaluation = _evaluate_model(
        logistic_model,
        model_name=("logistic_regression_balanced"),
        x_train=x_train,
        y_train=y_train,
        x_validation=x_validation,
        y_validation=y_validation,
    )

    logistic_iterations = tuple(int(value) for value in np.asarray(logistic_model.n_iter_).tolist())

    return MLBaselineTrainingResult(
        preprocessor=preprocessor,
        dummy_model=dummy_model,
        logistic_model=logistic_model,
        dummy_evaluation=dummy_evaluation,
        logistic_evaluation=(logistic_evaluation),
        train_shape=(
            int(x_train.shape[0]),
            int(x_train.shape[1]),
        ),
        validation_shape=(
            int(x_validation.shape[0]),
            int(x_validation.shape[1]),
        ),
        train_label_counts=_label_counts(y_train),
        validation_label_counts=_label_counts(y_validation),
        reserved_test_row_count=len(split.test_rows),
        logistic_iterations=(logistic_iterations),
    )
