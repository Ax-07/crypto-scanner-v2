"""Évaluation walk-forward des configurations ML candidates."""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from datetime import datetime
from statistics import fmean, pstdev
from typing import Sequence

import numpy as np
from numpy.typing import NDArray
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from app.ml.domain.ml_evaluation import (
    MLClassificationMetrics,
    evaluate_classification,
)
from app.ml.domain.ml_feature_policy import (
    ML_FEATURE_POLICIES_V1,
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
from app.ml.domain.ml_walk_forward import (
    MLWalkForwardFold,
    MLWalkForwardPlan,
)

LabelCounts = tuple[
    int,
    int,
    int,
]


class MLWalkForwardEvaluationError(ValueError):
    """Signale qu'une configuration ne peut pas être évaluée."""


@dataclass(frozen=True, slots=True)
class MLWalkForwardFoldEvaluation:
    """Résultat d'une configuration sur un fold."""

    fold_index: int
    validation_start: datetime
    validation_end: datetime

    train_row_count: int
    validation_row_count: int
    output_feature_count: int

    logistic_iterations: int
    predicted_label_counts: LabelCounts

    train_metrics: MLClassificationMetrics
    validation_metrics: MLClassificationMetrics

    def to_dict(self) -> dict[str, object]:
        """Retourne une représentation JSON-compatible."""
        return {
            "fold_index": self.fold_index,
            "validation_start": (self.validation_start.isoformat()),
            "validation_end": (self.validation_end.isoformat()),
            "train_row_count": self.train_row_count,
            "validation_row_count": (self.validation_row_count),
            "output_feature_count": (self.output_feature_count),
            "logistic_iterations": (self.logistic_iterations),
            "predicted_label_counts": (_label_counts_to_dict(self.predicted_label_counts)),
            "train_metrics": (self.train_metrics.to_dict()),
            "validation_metrics": (self.validation_metrics.to_dict()),
        }


@dataclass(frozen=True, slots=True)
class MLWalkForwardCandidateEvaluation:
    """Agrégation d'une configuration sur tous les folds."""

    policy: MLFeaturePolicy
    c_value: float
    folds: tuple[
        MLWalkForwardFoldEvaluation,
        ...,
    ]

    pooled_validation_metrics: MLClassificationMetrics
    pooled_predicted_label_counts: LabelCounts

    mean_train_macro_f1: float
    mean_validation_macro_f1: float
    standard_deviation_validation_macro_f1: float
    minimum_validation_macro_f1: float

    mean_validation_balanced_accuracy: float
    standard_deviation_validation_balanced_accuracy: float

    mean_generalization_gap: float

    @property
    def fold_count(self) -> int:
        """Retourne le nombre de folds évalués."""
        return len(self.folds)

    @property
    def total_validation_row_count(self) -> int:
        """Retourne le nombre total de prédictions hors échantillon."""
        return sum(fold.validation_row_count for fold in self.folds)

    @property
    def output_feature_count_range(
        self,
    ) -> tuple[int, int]:
        """Retourne les dimensions minimale et maximale."""
        counts = tuple(fold.output_feature_count for fold in self.folds)

        return (
            min(counts),
            max(counts),
        )

    def to_dict(self) -> dict[str, object]:
        """Retourne une représentation JSON-compatible."""
        minimum_columns, maximum_columns = self.output_feature_count_range

        return {
            "policy": self.policy.value,
            "c_value": self.c_value,
            "fold_count": self.fold_count,
            "total_validation_row_count": (self.total_validation_row_count),
            "output_feature_count_range": {
                "minimum": minimum_columns,
                "maximum": maximum_columns,
            },
            "mean_train_macro_f1": (self.mean_train_macro_f1),
            "mean_validation_macro_f1": (self.mean_validation_macro_f1),
            ("standard_deviation_" "validation_macro_f1"): (
                self.standard_deviation_validation_macro_f1
            ),
            "minimum_validation_macro_f1": (self.minimum_validation_macro_f1),
            ("mean_validation_" "balanced_accuracy"): (self.mean_validation_balanced_accuracy),
            ("standard_deviation_validation_" "balanced_accuracy"): (
                self.standard_deviation_validation_balanced_accuracy
            ),
            "mean_generalization_gap": (self.mean_generalization_gap),
            "pooled_predicted_label_counts": (
                _label_counts_to_dict(self.pooled_predicted_label_counts)
            ),
            "pooled_validation_metrics": (self.pooled_validation_metrics.to_dict()),
            "folds": [fold.to_dict() for fold in self.folds],
        }


@dataclass(frozen=True, slots=True)
class MLWalkForwardEvaluationResult:
    """Résultat complet de la recherche walk-forward."""

    evaluation_end: datetime
    fold_count: int
    validation_window: int
    minimum_train_window: int

    candidates: tuple[
        MLWalkForwardCandidateEvaluation,
        ...,
    ]

    @property
    def ranked_candidates(
        self,
    ) -> tuple[
        MLWalkForwardCandidateEvaluation,
        ...,
    ]:
        """Classe les candidats selon une règle déterministe."""
        return tuple(
            sorted(
                self.candidates,
                key=_candidate_ranking_key,
            )
        )

    @property
    def best_candidate(
        self,
    ) -> MLWalkForwardCandidateEvaluation:
        """Retourne le candidat arrivé en tête."""
        ranked = self.ranked_candidates

        if not ranked:
            raise MLWalkForwardEvaluationError("aucun candidat n'a été évalué")

        return ranked[0]

    def to_dict(self) -> dict[str, object]:
        """Retourne le rapport classé et sérialisable."""
        return {
            "evaluation_end": (self.evaluation_end.isoformat()),
            "fold_count": self.fold_count,
            "validation_window": (self.validation_window),
            "minimum_train_window": (self.minimum_train_window),
            "candidate_count": len(self.candidates),
            "ranking_rule": [
                "mean_validation_macro_f1_desc",
                "minimum_validation_macro_f1_desc",
                "pooled_validation_macro_f1_desc",
                ("mean_validation_" "balanced_accuracy_desc"),
                "absolute_generalization_gap_asc",
                "c_value_asc",
                "policy_asc",
            ],
            "candidates": [
                {
                    "rank": rank,
                    **candidate.to_dict(),
                }
                for rank, candidate in enumerate(
                    self.ranked_candidates,
                    start=1,
                )
            ],
        }


def _normalize_c_values(
    c_values: Sequence[float],
) -> tuple[float, ...]:
    """Valide et déduplique les forces de régularisation."""
    normalized: list[float] = []
    seen: set[float] = set()

    for value in c_values:
        if isinstance(value, bool):
            raise MLWalkForwardEvaluationError("les valeurs de C ne peuvent pas " "être booléennes")

        converted = float(value)

        if not math.isfinite(converted) or converted <= 0:
            raise MLWalkForwardEvaluationError(
                "les valeurs de C doivent être finies " "et strictement positives"
            )

        if converted in seen:
            continue

        seen.add(converted)
        normalized.append(converted)

    if not normalized:
        raise MLWalkForwardEvaluationError("au moins une valeur de C est nécessaire")

    return tuple(normalized)


def _normalize_policies(
    policies: Sequence[MLFeaturePolicy | str],
) -> tuple[MLFeaturePolicy, ...]:
    """Valide et déduplique les politiques."""
    normalized: list[MLFeaturePolicy] = []
    seen: set[MLFeaturePolicy] = set()

    for policy in policies:
        converted = normalize_feature_policy(policy)

        if converted in seen:
            continue

        seen.add(converted)
        normalized.append(converted)

    if not normalized:
        raise MLWalkForwardEvaluationError("au moins une politique est nécessaire")

    return tuple(normalized)


def _label_counts(
    labels: Sequence[int],
) -> LabelCounts:
    """Compte les labels dans l'ordre métier."""
    counts = [0 for _ in LABEL_ORDER]

    for label_index in labels:
        if label_index < 0 or label_index >= len(LABEL_ORDER):
            raise MLWalkForwardEvaluationError(f"indice de label inconnu : {label_index}")

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
    *,
    fold_index: int,
) -> None:
    """Vérifie la présence des trois classes dans le train."""
    observed = tuple(sorted({int(value) for value in labels}))
    expected = tuple(range(len(LABEL_ORDER)))

    if observed != expected:
        raise MLWalkForwardEvaluationError(
            f"le train du fold {fold_index} " "doit contenir les trois classes"
        )


def _fit_logistic_regression(
    x_train: NDArray[np.float64],
    y_train: NDArray[np.int64],
    *,
    c_value: float,
    policy: MLFeaturePolicy,
    fold_index: int,
) -> LogisticRegression:
    """Entraîne une régression logistique déterministe."""
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
                x_train,
                y_train,
            )
    except ConvergenceWarning as exc:
        raise MLWalkForwardEvaluationError(
            "non-convergence pour " f"policy={policy.value}, " f"C={c_value}, " f"fold={fold_index}"
        ) from exc
    except ValueError as exc:
        raise MLWalkForwardEvaluationError(
            "échec de l'entraînement pour "
            f"policy={policy.value}, "
            f"C={c_value}, "
            f"fold={fold_index}"
        ) from exc

    classes = tuple(int(value) for value in np.asarray(model.classes_).tolist())
    expected_classes = tuple(range(len(LABEL_ORDER)))

    if classes != expected_classes:
        raise MLWalkForwardEvaluationError(
            "ordre de classes inattendu pour "
            f"policy={policy.value}, "
            f"C={c_value}, "
            f"fold={fold_index} : {classes}"
        )

    return model


def _predict_labels(
    model: LogisticRegression,
    matrix: NDArray[np.float64],
    *,
    policy: MLFeaturePolicy,
    c_value: float,
    fold_index: int,
) -> tuple[int, ...]:
    """Produit et vérifie les prédictions."""
    predictions = np.asarray(model.predict(matrix))

    if predictions.shape != (matrix.shape[0],):
        raise MLWalkForwardEvaluationError(
            "forme de prédiction inattendue pour "
            f"policy={policy.value}, "
            f"C={c_value}, "
            f"fold={fold_index}"
        )

    normalized = tuple(int(value) for value in predictions.tolist())

    _label_counts(normalized)

    return normalized


def _evaluate_fold(
    fold: MLWalkForwardFold,
    *,
    policy: MLFeaturePolicy,
    c_value: float,
) -> tuple[
    MLWalkForwardFoldEvaluation,
    tuple[int, ...],
    tuple[int, ...],
]:
    """Évalue une configuration sur un fold."""
    train_application = apply_ml_feature_policy(
        fold.train_rows,
        policy=policy,
    )
    validation_application = apply_ml_feature_policy(
        fold.validation_rows,
        policy=policy,
    )

    preprocessor = MLFeaturePreprocessor()

    try:
        x_train = preprocessor.fit_transform(train_application.rows)
        x_validation = preprocessor.transform(validation_application.rows)
    except MLPreprocessingError as exc:
        raise MLWalkForwardEvaluationError(
            "échec du prétraitement pour "
            f"policy={policy.value}, "
            f"C={c_value}, "
            f"fold={fold.fold_index}"
        ) from exc

    y_train = encode_market_labels(train_application.rows)
    y_validation = encode_market_labels(validation_application.rows)

    _validate_training_classes(
        y_train,
        fold_index=fold.fold_index,
    )

    model = _fit_logistic_regression(
        x_train,
        y_train,
        c_value=c_value,
        policy=policy,
        fold_index=fold.fold_index,
    )

    train_predictions = _predict_labels(
        model,
        x_train,
        policy=policy,
        c_value=c_value,
        fold_index=fold.fold_index,
    )
    validation_predictions = _predict_labels(
        model,
        x_validation,
        policy=policy,
        c_value=c_value,
        fold_index=fold.fold_index,
    )

    expected_validation = tuple(int(value) for value in y_validation.tolist())

    train_metrics = evaluate_classification(
        y_train,
        train_predictions,
    )
    validation_metrics = evaluate_classification(
        expected_validation,
        validation_predictions,
    )

    iteration_values = np.asarray(model.n_iter_)

    if iteration_values.size == 0:
        raise MLWalkForwardEvaluationError(
            "nombre d'itérations absent pour "
            f"policy={policy.value}, "
            f"C={c_value}, "
            f"fold={fold.fold_index}"
        )

    evaluation = MLWalkForwardFoldEvaluation(
        fold_index=fold.fold_index,
        validation_start=fold.validation_start,
        validation_end=fold.validation_end,
        train_row_count=len(train_application.rows),
        validation_row_count=len(validation_application.rows),
        output_feature_count=(preprocessor.schema.output_feature_count),
        logistic_iterations=int(iteration_values.max()),
        predicted_label_counts=_label_counts(validation_predictions),
        train_metrics=train_metrics,
        validation_metrics=validation_metrics,
    )

    return (
        evaluation,
        expected_validation,
        validation_predictions,
    )


def _evaluate_candidate(
    plan: MLWalkForwardPlan,
    *,
    policy: MLFeaturePolicy,
    c_value: float,
) -> MLWalkForwardCandidateEvaluation:
    """Agrège une configuration sur tous les folds."""
    fold_evaluations: list[MLWalkForwardFoldEvaluation] = []
    pooled_expected: list[int] = []
    pooled_predictions: list[int] = []

    for fold in plan.folds:
        (
            evaluation,
            expected,
            predictions,
        ) = _evaluate_fold(
            fold,
            policy=policy,
            c_value=c_value,
        )

        fold_evaluations.append(evaluation)
        pooled_expected.extend(expected)
        pooled_predictions.extend(predictions)

    if not fold_evaluations:
        raise MLWalkForwardEvaluationError("le plan ne contient aucun fold")

    train_macro_f1_values = tuple(fold.train_metrics.macro_f1 for fold in fold_evaluations)
    validation_macro_f1_values = tuple(
        fold.validation_metrics.macro_f1 for fold in fold_evaluations
    )
    validation_balanced_accuracy_values = tuple(
        fold.validation_metrics.balanced_accuracy for fold in fold_evaluations
    )

    mean_train_macro_f1 = fmean(train_macro_f1_values)
    mean_validation_macro_f1 = fmean(validation_macro_f1_values)

    calculated_values = (
        mean_train_macro_f1,
        mean_validation_macro_f1,
        pstdev(validation_macro_f1_values),
        min(validation_macro_f1_values),
        fmean(validation_balanced_accuracy_values),
        pstdev(validation_balanced_accuracy_values),
    )

    if not all(math.isfinite(value) for value in calculated_values):
        raise MLWalkForwardEvaluationError("les métriques agrégées doivent être finies")

    return MLWalkForwardCandidateEvaluation(
        policy=policy,
        c_value=c_value,
        folds=tuple(fold_evaluations),
        pooled_validation_metrics=(
            evaluate_classification(
                pooled_expected,
                pooled_predictions,
            )
        ),
        pooled_predicted_label_counts=(_label_counts(pooled_predictions)),
        mean_train_macro_f1=(mean_train_macro_f1),
        mean_validation_macro_f1=(mean_validation_macro_f1),
        standard_deviation_validation_macro_f1=(calculated_values[2]),
        minimum_validation_macro_f1=(calculated_values[3]),
        mean_validation_balanced_accuracy=(calculated_values[4]),
        standard_deviation_validation_balanced_accuracy=(calculated_values[5]),
        mean_generalization_gap=(mean_train_macro_f1 - mean_validation_macro_f1),
    )


def _candidate_ranking_key(
    candidate: MLWalkForwardCandidateEvaluation,
) -> tuple[
    float,
    float,
    float,
    float,
    float,
    float,
    str,
]:
    """Retourne la clé de classement déterministe."""
    return (
        -candidate.mean_validation_macro_f1,
        -candidate.minimum_validation_macro_f1,
        -candidate.pooled_validation_metrics.macro_f1,
        -candidate.mean_validation_balanced_accuracy,
        abs(candidate.mean_generalization_gap),
        candidate.c_value,
        candidate.policy.value,
    )


def evaluate_logistic_walk_forward(
    plan: MLWalkForwardPlan,
    *,
    policies: Sequence[MLFeaturePolicy | str] = ML_FEATURE_POLICIES_V1,
    c_values: Sequence[float] = (
        1.0,
        0.3,
        0.1,
        0.03,
        0.01,
        0.003,
    ),
) -> MLWalkForwardEvaluationResult:
    """Évalue les configurations sans accéder au test réservé."""
    if not plan.folds:
        raise MLWalkForwardEvaluationError("le plan walk-forward ne contient aucun fold")

    normalized_policies = _normalize_policies(policies)
    normalized_c_values = _normalize_c_values(c_values)

    candidates = tuple(
        _evaluate_candidate(
            plan,
            policy=policy,
            c_value=c_value,
        )
        for policy in normalized_policies
        for c_value in normalized_c_values
    )

    return MLWalkForwardEvaluationResult(
        evaluation_end=plan.evaluation_end,
        fold_count=plan.fold_count,
        validation_window=(plan.validation_window),
        minimum_train_window=(plan.minimum_train_window),
        candidates=candidates,
    )
