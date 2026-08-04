from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.ml.domain.ml_feature_policy import (
    MLFeaturePolicy,
)
from app.ml.domain.ml_walk_forward import (
    build_expanding_walk_forward_plan,
)
from app.ml.models.ml_dataset import (
    MLDatasetRow,
    MarketDirectionLabel,
)
from app.ml.services.ml_benchmark_builder import (
    MLBenchmarkBuildError,
    build_ml_benchmark_report,
)
from app.ml.services.ml_dataset_builder import (
    MLDatasetBuildReport,
    MLDatasetBuildResult,
)
from app.ml.services.ml_dataset_exporter import (
    MLDatasetExporter,
)
from app.ml.services.ml_dataset_loader import (
    MLDatasetLoader,
    MLDatasetLoadResult,
)
from app.ml.services.ml_final_evaluator import (
    MLFinalEvaluationResult,
    evaluate_final_logistic_model,
)
from app.ml.services.ml_walk_forward_evaluator import (
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

EVALUATION_START = BASE_TIME + timedelta(hours=120)

PARIS_TIMEZONE = timezone(timedelta(hours=1))

FeatureValue = bool | int | float | str | None

BenchmarkArtifacts = tuple[
    MLDatasetLoadResult,
    MLWalkForwardEvaluationResult,
    MLFinalEvaluationResult,
]


def dataset_row(
    observation_id: int,
    *,
    label: MarketDirectionLabel,
) -> MLDatasetRow:
    """Construit une ligne synthétique causalement valide."""
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
        job_id="benchmark-builder-test",
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
        future_return=(future_return_by_label[label]),
        label=label,
        features=features,
    )


def cyclic_rows(
    count: int,
) -> tuple[MLDatasetRow, ...]:
    """Construit une série équilibrée sur trois classes."""
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


def build_result(
    rows: tuple[MLDatasetRow, ...],
) -> MLDatasetBuildResult:
    """Construit un résultat d'export cohérent."""
    row_count = len(rows)

    report = MLDatasetBuildReport(
        source_rows=row_count,
        processed_rows=row_count,
        generated_rows=row_count,
        skipped_rows=0,
        censored_outcomes=0,
        invalid_outcomes=0,
        missing_natr=0,
        contract_rejections=0,
        batch_count=1,
        rejection_reasons={},
    )

    return MLDatasetBuildResult(
        job_id="benchmark-builder-test",
        horizon=6,
        natr_multiplier=1.0,
        rows=rows,
        report=report,
    )


@pytest.fixture(scope="module")
def benchmark_artifacts(
    tmp_path_factory: pytest.TempPathFactory,
) -> BenchmarkArtifacts:
    """Construit la chaîne réelle utilisée par le builder."""
    output_directory = tmp_path_factory.mktemp("ml-benchmark-builder")
    rows = cyclic_rows(150)

    export_result = MLDatasetExporter().export(
        build_result(rows),
        Path(output_directory),
        file_stem="benchmark-builder",
    )

    loaded = MLDatasetLoader().load(export_result.manifest_path)

    plan = build_expanding_walk_forward_plan(
        loaded.rows,
        evaluation_end=EVALUATION_START,
        fold_count=2,
        validation_window=18,
        minimum_train_window=60,
    )

    walk_forward_result = evaluate_logistic_walk_forward(
        plan,
        policies=(MLFeaturePolicy.NORMALIZED_DEDUPLICATED,),
        c_values=(0.03,),
    )

    final_result = evaluate_final_logistic_model(
        loaded.rows,
        evaluation_start=EVALUATION_START,
        policy=(MLFeaturePolicy.NORMALIZED_DEDUPLICATED),
        c_value=0.03,
    )

    return (
        loaded,
        walk_forward_result,
        final_result,
    )


def test_builds_report_from_verified_results(
    benchmark_artifacts: BenchmarkArtifacts,
) -> None:
    (
        loaded,
        walk_forward_result,
        final_result,
    ) = benchmark_artifacts

    report = build_ml_benchmark_report(
        loaded=loaded,
        walk_forward_result=(walk_forward_result),
        final_result=final_result,
        benchmark_name=("  synthetic-logistic-v1  "),
        created_at=datetime(
            2026,
            8,
            3,
            23,
            0,
            tzinfo=PARIS_TIMEZONE,
        ),
        status="rejected",
        decision_reasons=(
            "généralisation insuffisante",
            "test final consommé",
            "généralisation insuffisante",
        ),
    )

    assert report.benchmark_schema_version == "ml-benchmark-v1"
    assert report.benchmark_name == "synthetic-logistic-v1"
    assert report.status == "rejected"
    assert report.test_consumed is True

    assert report.created_at == datetime(
        2026,
        8,
        3,
        22,
        0,
        tzinfo=timezone.utc,
    )

    assert report.decision_reasons == (
        "généralisation insuffisante",
        "test final consommé",
    )

    assert report.source_manifest_file == ("benchmark-builder.manifest.json")
    assert report.source_data_file == ("benchmark-builder.jsonl")
    assert report.source_data_sha256 == loaded.manifest.data_sha256

    assert report.dataset_row_count == 150
    assert report.development_row_count == 114
    assert report.excluded_target_overlap_count == 6
    assert report.test_row_count == 30

    assert report.evaluation_start == EVALUATION_START

    assert report.selection.policy == ("normalized_deduplicated")
    assert report.selection.c_value == 0.03
    assert report.selection.fold_count == 2
    assert report.selection.validation_window == 18
    assert report.selection.minimum_train_window == 60
    assert report.selection.candidate_count == 1
    assert report.selection.total_validation_row_count == 36

    assert report.features.exported_feature_count == 4
    assert report.features.excluded_present_feature_names == (
        "candle.close",
        "price.close",
    )
    assert report.features.preprocessing_input_feature_count == 2
    assert report.features.active_feature_count == 2
    assert report.features.output_feature_count == 4

    assert report.dummy_test.row_count == 30
    assert report.selected_model_development.row_count == 114
    assert report.selected_model_test.row_count == 30

    assert report.selected_model_test.macro_f1 > 0.90
    assert report.selected_model_test.balanced_accuracy > 0.90


def test_rejects_final_policy_mismatch(
    benchmark_artifacts: BenchmarkArtifacts,
) -> None:
    (
        loaded,
        walk_forward_result,
        final_result,
    ) = benchmark_artifacts

    mismatched_final = replace(
        final_result,
        policy=(MLFeaturePolicy.WITHOUT_ABSOLUTE),
    )

    with pytest.raises(
        MLBenchmarkBuildError,
        match="politique finale",
    ):
        build_ml_benchmark_report(
            loaded=loaded,
            walk_forward_result=(walk_forward_result),
            final_result=mismatched_final,
            benchmark_name="benchmark",
            created_at=datetime.now(timezone.utc),
            status="rejected",
            decision_reasons=("raison",),
        )


def test_rejects_final_c_value_mismatch(
    benchmark_artifacts: BenchmarkArtifacts,
) -> None:
    (
        loaded,
        walk_forward_result,
        final_result,
    ) = benchmark_artifacts

    mismatched_final = replace(
        final_result,
        c_value=0.1,
    )

    with pytest.raises(
        MLBenchmarkBuildError,
        match="valeur de C finale",
    ):
        build_ml_benchmark_report(
            loaded=loaded,
            walk_forward_result=(walk_forward_result),
            final_result=mismatched_final,
            benchmark_name="benchmark",
            created_at=datetime.now(timezone.utc),
            status="rejected",
            decision_reasons=("raison",),
        )


def test_rejects_evaluation_boundary_mismatch(
    benchmark_artifacts: BenchmarkArtifacts,
) -> None:
    (
        loaded,
        walk_forward_result,
        final_result,
    ) = benchmark_artifacts

    mismatched_final = replace(
        final_result,
        evaluation_start=(final_result.evaluation_start + timedelta(hours=1)),
    )

    with pytest.raises(
        MLBenchmarkBuildError,
        match="frontière walk-forward",
    ):
        build_ml_benchmark_report(
            loaded=loaded,
            walk_forward_result=(walk_forward_result),
            final_result=mismatched_final,
            benchmark_name="benchmark",
            created_at=datetime.now(timezone.utc),
            status="rejected",
            decision_reasons=("raison",),
        )


def test_rejects_source_row_count_mismatch(
    benchmark_artifacts: BenchmarkArtifacts,
) -> None:
    (
        loaded,
        walk_forward_result,
        final_result,
    ) = benchmark_artifacts

    mismatched_final = replace(
        final_result,
        source_row_count=149,
    )

    with pytest.raises(
        MLBenchmarkBuildError,
        match="dataset chargé",
    ):
        build_ml_benchmark_report(
            loaded=loaded,
            walk_forward_result=(walk_forward_result),
            final_result=mismatched_final,
            benchmark_name="benchmark",
            created_at=datetime.now(timezone.utc),
            status="rejected",
            decision_reasons=("raison",),
        )


def test_rejects_incoherent_final_partitions(
    benchmark_artifacts: BenchmarkArtifacts,
) -> None:
    (
        loaded,
        walk_forward_result,
        final_result,
    ) = benchmark_artifacts

    mismatched_final = replace(
        final_result,
        development_row_count=113,
    )

    with pytest.raises(
        MLBenchmarkBuildError,
        match="partitions finales",
    ):
        build_ml_benchmark_report(
            loaded=loaded,
            walk_forward_result=(walk_forward_result),
            final_result=mismatched_final,
            benchmark_name="benchmark",
            created_at=datetime.now(timezone.utc),
            status="rejected",
            decision_reasons=("raison",),
        )


def test_rejects_empty_loaded_dataset(
    benchmark_artifacts: BenchmarkArtifacts,
) -> None:
    (
        loaded,
        walk_forward_result,
        final_result,
    ) = benchmark_artifacts

    empty_loaded = replace(
        loaded,
        rows=(),
    )

    with pytest.raises(
        MLBenchmarkBuildError,
        match="ne peut pas être vide",
    ):
        build_ml_benchmark_report(
            loaded=empty_loaded,
            walk_forward_result=(walk_forward_result),
            final_result=final_result,
            benchmark_name="benchmark",
            created_at=datetime.now(timezone.utc),
            status="rejected",
            decision_reasons=("raison",),
        )
