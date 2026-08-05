"""Construction vérifiée des rapports de benchmark ML."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Sequence, cast

from app.ml.models.ml_benchmark import (
    MLBenchmarkFeatureSnapshot,
    MLBenchmarkLabelCounts,
    MLBenchmarkMetricSnapshot,
    MLBenchmarkReport,
    MLBenchmarkSelectionSnapshot,
    MLBenchmarkStatus,
    MLBenchmarkFeaturePolicy,
)
from app.ml.domain.ml_feature_policy import (
    ML_FEATURE_POLICIES_V1,
    MLFeaturePolicy,
)
from app.ml.models.ml_dataset_export import (
    MLDatasetExportManifest,
)
from app.ml.services.ml_dataset_loader import (
    MLDatasetLoadResult,
)
from app.ml.services.ml_final_evaluator import (
    MLFinalEvaluationResult,
)
from app.ml.services.ml_walk_forward_evaluator import (
    MLWalkForwardCandidateEvaluation,
    MLWalkForwardEvaluationResult,
)
from app.ml.models.ml_dataset import (
    ML_FEATURE_SCHEMA_VERSION_V1,
)


class MLBenchmarkBuildError(ValueError):
    """Signale des résultats incompatibles avec le benchmark."""


def _benchmark_v1_policy(
    policy: MLFeaturePolicy,
) -> MLBenchmarkFeaturePolicy:
    """Valide et convertit une politique compatible avec le benchmark v1."""
    if policy not in ML_FEATURE_POLICIES_V1:
        raise MLBenchmarkBuildError("le benchmark v1 accepte uniquement les politiques ML v1")

    return cast(
        MLBenchmarkFeaturePolicy,
        policy.value,
    )


def _manifest_payload(
    manifest: MLDatasetExportManifest,
) -> dict[str, object]:
    """Retourne le manifeste sous forme de dictionnaire Python."""
    return manifest.model_dump(mode="python")


def _required_manifest_integer(
    manifest: MLDatasetExportManifest,
    *,
    field_name: str,
) -> int:
    """Lit un entier obligatoire du manifeste."""
    value = _manifest_payload(manifest).get(field_name)

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MLBenchmarkBuildError(
            f"{field_name} doit être un entier " "strictement positif dans le manifeste"
        )

    return value


def _required_manifest_string(
    manifest: MLDatasetExportManifest,
    *,
    field_name: str,
) -> str:
    """Lit une chaîne obligatoire du manifeste."""
    value = _manifest_payload(manifest).get(field_name)

    if not isinstance(value, str):
        raise MLBenchmarkBuildError(f"{field_name} doit être une chaîne " "dans le manifeste")

    normalized = value.strip()

    if not normalized:
        raise MLBenchmarkBuildError(f"{field_name} ne peut pas être vide " "dans le manifeste")

    return normalized


def _label_counts(
    counts: tuple[
        int,
        int,
        int,
    ],
) -> MLBenchmarkLabelCounts:
    """Convertit les comptes DOWN, NEUTRAL et UP."""
    return MLBenchmarkLabelCounts(
        down=counts[0],
        neutral=counts[1],
        up=counts[2],
    )


def _metric_snapshot(
    *,
    metrics: object,
    predicted_label_counts: tuple[
        int,
        int,
        int,
    ],
) -> MLBenchmarkMetricSnapshot:
    """Construit un résumé stable depuis des métriques calculées."""
    required_attributes = (
        "row_count",
        "accuracy",
        "balanced_accuracy",
        "macro_f1",
        "weighted_f1",
    )

    if not all(
        hasattr(
            metrics,
            attribute_name,
        )
        for attribute_name in required_attributes
    ):
        raise MLBenchmarkBuildError("objet de métriques incompatible")

    row_count = getattr(
        metrics,
        "row_count",
    )
    accuracy = getattr(
        metrics,
        "accuracy",
    )
    balanced_accuracy = getattr(
        metrics,
        "balanced_accuracy",
    )
    macro_f1 = getattr(
        metrics,
        "macro_f1",
    )
    weighted_f1 = getattr(
        metrics,
        "weighted_f1",
    )

    if isinstance(row_count, bool) or not isinstance(row_count, int):
        raise MLBenchmarkBuildError("row_count des métriques doit être entier")

    numeric_values = (
        accuracy,
        balanced_accuracy,
        macro_f1,
        weighted_f1,
    )

    if not all(
        isinstance(
            value,
            (
                int,
                float,
            ),
        )
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        for value in numeric_values
    ):
        raise MLBenchmarkBuildError("les métriques doivent être numériques et finies")

    return MLBenchmarkMetricSnapshot(
        row_count=row_count,
        accuracy=float(accuracy),
        balanced_accuracy=float(balanced_accuracy),
        macro_f1=float(macro_f1),
        weighted_f1=float(weighted_f1),
        predicted_label_counts=_label_counts(predicted_label_counts),
    )


def _validate_selected_candidate(
    walk_forward_result: MLWalkForwardEvaluationResult,
    final_result: MLFinalEvaluationResult,
) -> MLWalkForwardCandidateEvaluation:
    """Vérifie que le test utilise le candidat walk-forward choisi."""
    candidate = walk_forward_result.best_candidate

    if candidate.policy != final_result.policy:
        raise MLBenchmarkBuildError(
            "la politique finale ne correspond pas " "au meilleur candidat walk-forward"
        )

    if not math.isclose(
        candidate.c_value,
        final_result.c_value,
        rel_tol=0,
        abs_tol=1e-12,
    ):
        raise MLBenchmarkBuildError(
            "la valeur de C finale ne correspond pas " "au meilleur candidat walk-forward"
        )

    if walk_forward_result.evaluation_end != final_result.evaluation_start:
        raise MLBenchmarkBuildError(
            "la frontière walk-forward ne correspond pas " "au début du test final"
        )

    return candidate


def _validate_source_consistency(
    loaded: MLDatasetLoadResult,
    final_result: MLFinalEvaluationResult,
) -> None:
    """Vérifie les volumes et identifiants du dataset source."""
    if loaded.manifest.feature_schema_version != ML_FEATURE_SCHEMA_VERSION_V1:
        raise MLBenchmarkBuildError("le benchmark v1 exige le contrat " "causal-features-v1")
    if not loaded.rows:
        raise MLBenchmarkBuildError("le dataset chargé ne peut pas être vide")

    if len(loaded.rows) != loaded.manifest.row_count:
        raise MLBenchmarkBuildError(
            "le manifeste et les lignes chargées " "n'ont pas le même effectif"
        )

    if final_result.source_row_count != loaded.manifest.row_count:
        raise MLBenchmarkBuildError("l'évaluation finale ne correspond pas " "au dataset chargé")

    expected_partition_count = (
        final_result.development_row_count
        + final_result.excluded_target_overlap_count
        + final_result.test_row_count
    )

    if expected_partition_count != final_result.source_row_count:
        raise MLBenchmarkBuildError(
            "les partitions finales ne reconstituent pas " "le dataset source"
        )

    if any(row.job_id != loaded.manifest.source_job_id for row in loaded.rows):
        raise MLBenchmarkBuildError(
            "les lignes ne correspondent pas " "au job déclaré par le manifeste"
        )


def build_ml_benchmark_report(
    *,
    loaded: MLDatasetLoadResult,
    walk_forward_result: MLWalkForwardEvaluationResult,
    final_result: MLFinalEvaluationResult,
    benchmark_name: str,
    created_at: datetime,
    status: MLBenchmarkStatus,
    decision_reasons: Sequence[str],
) -> MLBenchmarkReport:
    """Construit un benchmark depuis les résultats vérifiés."""
    _validate_source_consistency(
        loaded,
        final_result,
    )

    candidate = _validate_selected_candidate(
        walk_forward_result,
        final_result,
    )

    manifest = loaded.manifest
    preprocessor_schema = final_result.preprocessor.schema

    minimum_columns, maximum_columns = candidate.output_feature_count_range

    selection = MLBenchmarkSelectionSnapshot(
        policy=_benchmark_v1_policy(candidate.policy),
        c_value=candidate.c_value,
        fold_count=(walk_forward_result.fold_count),
        validation_window=(walk_forward_result.validation_window),
        minimum_train_window=(walk_forward_result.minimum_train_window),
        candidate_count=len(walk_forward_result.candidates),
        total_validation_row_count=(candidate.total_validation_row_count),
        output_feature_count_minimum=(minimum_columns),
        output_feature_count_maximum=(maximum_columns),
        mean_train_macro_f1=(candidate.mean_train_macro_f1),
        mean_validation_macro_f1=(candidate.mean_validation_macro_f1),
        standard_deviation_validation_macro_f1=(candidate.standard_deviation_validation_macro_f1),
        minimum_validation_macro_f1=(candidate.minimum_validation_macro_f1),
        pooled_validation_macro_f1=(candidate.pooled_validation_metrics.macro_f1),
        mean_validation_balanced_accuracy=(candidate.mean_validation_balanced_accuracy),
        mean_generalization_gap=(candidate.mean_generalization_gap),
        pooled_predicted_label_counts=_label_counts(candidate.pooled_predicted_label_counts),
    )

    features = MLBenchmarkFeatureSnapshot(
        exported_feature_count=len(manifest.feature_names),
        excluded_present_feature_names=(final_result.excluded_present_feature_names),
        preprocessing_input_feature_count=(preprocessor_schema.input_feature_count),
        dropped_constant_feature_names=(preprocessor_schema.dropped_constant_feature_names),
        active_feature_count=(preprocessor_schema.active_feature_count),
        output_feature_count=(preprocessor_schema.output_feature_count),
    )

    dummy_test = _metric_snapshot(
        metrics=(final_result.dummy_evaluation.test_metrics),
        predicted_label_counts=(final_result.dummy_evaluation.test_predicted_label_counts),
    )

    selected_model_development = _metric_snapshot(
        metrics=(final_result.logistic_evaluation.development_metrics),
        predicted_label_counts=(
            final_result.logistic_evaluation.development_predicted_label_counts
        ),
    )

    selected_model_test = _metric_snapshot(
        metrics=(final_result.logistic_evaluation.test_metrics),
        predicted_label_counts=(final_result.logistic_evaluation.test_predicted_label_counts),
    )

    return MLBenchmarkReport(
        benchmark_name=benchmark_name,
        created_at=created_at,
        status=status,
        decision_reasons=tuple(decision_reasons),
        source_manifest_file=(loaded.manifest_path.name),
        source_data_file=(loaded.data_path.name),
        source_data_sha256=(manifest.data_sha256),
        source_job_id=(manifest.source_job_id),
        manifest_schema_version=(
            _required_manifest_integer(
                manifest,
                field_name=("manifest_schema_version"),
            )
        ),
        dataset_schema_version=(
            _required_manifest_integer(
                manifest,
                field_name=("dataset_schema_version"),
            )
        ),
        feature_schema_version=(
            _required_manifest_string(
                manifest,
                field_name=("feature_schema_version"),
            )
        ),
        label_schema_version=(
            _required_manifest_string(
                manifest,
                field_name=("label_schema_version"),
            )
        ),
        horizon=manifest.horizon,
        natr_multiplier=(manifest.natr_multiplier),
        dataset_row_count=(manifest.row_count),
        first_decision_time=(loaded.rows[0].decision_time),
        last_decision_time=(loaded.rows[-1].decision_time),
        evaluation_start=(final_result.evaluation_start),
        development_row_count=(final_result.development_row_count),
        excluded_target_overlap_count=(final_result.excluded_target_overlap_count),
        test_row_count=(final_result.test_row_count),
        selection=selection,
        features=features,
        dummy_test=dummy_test,
        selected_model_development=(selected_model_development),
        selected_model_test=(selected_model_test),
    )
