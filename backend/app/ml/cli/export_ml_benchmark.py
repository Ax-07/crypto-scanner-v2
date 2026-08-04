"""Construit et exporte un benchmark ML final immuable."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence, cast

from app.ml.domain.ml_feature_policy import (
    MLFeaturePolicy,
)
from app.ml.domain.ml_temporal_split import (
    split_ml_dataset_chronologically,
)
from app.ml.domain.ml_walk_forward import (
    build_expanding_walk_forward_plan,
)
from app.ml.models.ml_benchmark import (
    MLBenchmarkStatus,
)
from app.ml.services.ml_benchmark_builder import (
    build_ml_benchmark_report,
)
from app.ml.services.ml_benchmark_exporter import (
    MLBenchmarkExporter,
)
from app.ml.services.ml_dataset_loader import (
    MLDatasetLoader,
)
from app.ml.services.ml_final_evaluator import (
    evaluate_final_logistic_model,
)
from app.ml.services.ml_walk_forward_evaluator import (
    evaluate_logistic_walk_forward,
)

DEFAULT_C_VALUES = (
    1.0,
    0.3,
    0.1,
    0.03,
    0.01,
    0.003,
)


def _parse_utc_datetime(
    value: str,
) -> datetime:
    """Parse une date ISO 8601 et la normalise en UTC."""
    normalized = value.strip()

    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "created-at doit être une date " "ISO 8601 valide"
        ) from exc

    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("created-at doit inclure " "un fuseau horaire")

    return parsed.astimezone(timezone.utc)


def _build_parser() -> argparse.ArgumentParser:
    """Construit le parseur de la commande."""
    parser = argparse.ArgumentParser(
        description=(
            "Reconstruit la sélection walk-forward, "
            "évalue la configuration finale et exporte "
            "un benchmark ML immuable."
        )
    )

    parser.add_argument(
        "manifest_path",
        type=Path,
        help=("Chemin du manifeste du dataset ML."),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("artifacts/ml-benchmarks"),
        help=("Dossier de destination du benchmark."),
    )

    parser.add_argument(
        "--benchmark-name",
        required=True,
        help=("Identifiant métier du benchmark."),
    )

    parser.add_argument(
        "--file-stem",
        required=True,
        help=("Nom du fichier sans extension."),
    )

    parser.add_argument(
        "--created-at",
        type=_parse_utc_datetime,
        required=True,
        help=("Date immuable de création du benchmark " "au format ISO 8601 avec fuseau horaire."),
    )

    parser.add_argument(
        "--selected-policy",
        choices=[policy.value for policy in MLFeaturePolicy],
        required=True,
        help=("Politique sélectionnée avant " "l'ouverture du test."),
    )

    parser.add_argument(
        "--selected-c-value",
        type=float,
        required=True,
        help=("Valeur de C sélectionnée avant " "l'ouverture du test."),
    )

    parser.add_argument(
        "--fold-count",
        type=int,
        default=4,
        help=("Nombre de folds walk-forward."),
    )

    parser.add_argument(
        "--validation-window",
        type=int,
        default=72,
        help=("Nombre de temps de décision " "par fenêtre de validation."),
    )

    parser.add_argument(
        "--minimum-train-window",
        type=int,
        default=200,
        help=("Nombre minimal de temps de décision " "dans le premier historique."),
    )

    parser.add_argument(
        "--candidate-c-values",
        type=float,
        nargs="+",
        default=list(DEFAULT_C_VALUES),
        help=("Valeurs de C comparées pendant " "le walk-forward."),
    )

    parser.add_argument(
        "--status",
        choices=[
            "accepted",
            "rejected",
        ],
        default="rejected",
        help=("Décision finale associée au benchmark."),
    )

    parser.add_argument(
        "--decision-reason",
        action="append",
        default=[],
        help=("Raison de décision. L'option peut " "être répétée."),
    )

    return parser


def _validate_selected_candidate(
    *,
    selected_policy: MLFeaturePolicy,
    selected_c_value: float,
    best_policy: MLFeaturePolicy,
    best_c_value: float,
) -> None:
    """Vérifie que la configuration finale correspond au classement."""
    if selected_policy != best_policy:
        raise ValueError(
            "la politique sélectionnée ne correspond "
            "pas au meilleur candidat walk-forward : "
            f"{selected_policy.value} != "
            f"{best_policy.value}"
        )

    if abs(selected_c_value - best_c_value) > 1e-12:
        raise ValueError(
            "la valeur de C sélectionnée ne correspond "
            "pas au meilleur candidat walk-forward : "
            f"{selected_c_value} != {best_c_value}"
        )


def run(
    argv: Sequence[str] | None = None,
) -> dict[str, object]:
    """Exécute la construction complète du benchmark."""
    parser = _build_parser()
    arguments = parser.parse_args(argv)

    manifest_path = cast(
        Path,
        arguments.manifest_path,
    )
    output_directory = cast(
        Path,
        arguments.output_directory,
    )
    benchmark_name = cast(
        str,
        arguments.benchmark_name,
    )
    file_stem = cast(
        str,
        arguments.file_stem,
    )
    created_at = cast(
        datetime,
        arguments.created_at,
    )
    selected_policy = MLFeaturePolicy(
        cast(
            str,
            arguments.selected_policy,
        )
    )
    selected_c_value = float(arguments.selected_c_value)
    candidate_c_values = tuple(
        float(value)
        for value in cast(
            list[float],
            arguments.candidate_c_values,
        )
    )
    decision_reasons = tuple(
        cast(
            list[str],
            arguments.decision_reason,
        )
    )
    status = cast(
        MLBenchmarkStatus,
        arguments.status,
    )

    loaded = MLDatasetLoader().load(manifest_path)

    reserved_split = split_ml_dataset_chronologically(loaded.rows)

    walk_forward_plan = build_expanding_walk_forward_plan(
        loaded.rows,
        evaluation_end=(reserved_split.test_start),
        fold_count=int(arguments.fold_count),
        validation_window=int(arguments.validation_window),
        minimum_train_window=int(arguments.minimum_train_window),
    )

    walk_forward_result = evaluate_logistic_walk_forward(
        walk_forward_plan,
        policies=tuple(MLFeaturePolicy),
        c_values=candidate_c_values,
    )

    best_candidate = walk_forward_result.best_candidate

    _validate_selected_candidate(
        selected_policy=selected_policy,
        selected_c_value=(selected_c_value),
        best_policy=best_candidate.policy,
        best_c_value=best_candidate.c_value,
    )

    final_result = evaluate_final_logistic_model(
        loaded.rows,
        evaluation_start=(reserved_split.test_start),
        policy=selected_policy,
        c_value=selected_c_value,
    )

    report = build_ml_benchmark_report(
        loaded=loaded,
        walk_forward_result=(walk_forward_result),
        final_result=final_result,
        benchmark_name=benchmark_name,
        created_at=created_at,
        status=status,
        decision_reasons=(decision_reasons),
    )

    export_result = MLBenchmarkExporter().export(
        report,
        output_directory,
        file_stem=file_stem,
    )

    return {
        "benchmark_schema_version": (report.benchmark_schema_version),
        "benchmark_name": (report.benchmark_name),
        "status": report.status,
        "test_consumed": (report.test_consumed),
        "source_data_sha256": (report.source_data_sha256),
        "evaluation_start": (report.evaluation_start.isoformat()),
        "selected_configuration": {
            "policy": (report.selection.policy),
            "c_value": (report.selection.c_value),
        },
        "walk_forward": {
            "candidate_count": (report.selection.candidate_count),
            "mean_validation_macro_f1": (report.selection.mean_validation_macro_f1),
            "minimum_validation_macro_f1": (report.selection.minimum_validation_macro_f1),
            "pooled_validation_macro_f1": (report.selection.pooled_validation_macro_f1),
        },
        "final_test": {
            "row_count": (report.selected_model_test.row_count),
            "accuracy": (report.selected_model_test.accuracy),
            "balanced_accuracy": (report.selected_model_test.balanced_accuracy),
            "macro_f1": (report.selected_model_test.macro_f1),
            "weighted_f1": (report.selected_model_test.weighted_f1),
            "predicted_label_counts": (
                report.selected_model_test.predicted_label_counts.model_dump(mode="json")
            ),
        },
        **export_result.to_dict(),
    }


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """Point d'entrée de la commande."""
    try:
        payload = run(argv)
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
