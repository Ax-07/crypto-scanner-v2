from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest

from app.ml.models.ml_benchmark import (
    MLBenchmarkReport,
)
from app.ml.services.ml_benchmark_exporter import (
    MLBenchmarkExportError,
    MLBenchmarkExporter,
)

UTC = timezone.utc


def valid_report(
    *,
    benchmark_name: str = "benchmark-v1",
) -> MLBenchmarkReport:
    """Construit un rapport de benchmark cohérent."""
    payload: dict[str, Any] = {
        "benchmark_name": benchmark_name,
        "created_at": datetime(
            2026,
            8,
            3,
            21,
            0,
            tzinfo=UTC,
        ),
        "status": "rejected",
        "decision_reasons": ("généralisation insuffisante",),
        "source_manifest_file": ("dataset.manifest.json"),
        "source_data_file": "dataset.jsonl",
        "source_data_sha256": (
            "sha256:" "a94660d07503b9494ac646ad948d0738" "d7b6a6941b1893c40a3a671484e4b2a4"
        ),
        "source_job_id": "job-benchmark",
        "manifest_schema_version": 1,
        "dataset_schema_version": 1,
        "feature_schema_version": ("ml-features-v1"),
        "label_schema_version": ("ml-direction-label-v1"),
        "horizon": 6,
        "natr_multiplier": 1.0,
        "dataset_row_count": 100,
        "first_decision_time": datetime(
            2026,
            1,
            1,
            0,
            0,
            tzinfo=UTC,
        ),
        "last_decision_time": datetime(
            2026,
            1,
            10,
            0,
            0,
            tzinfo=UTC,
        ),
        "evaluation_start": datetime(
            2026,
            1,
            8,
            0,
            0,
            tzinfo=UTC,
        ),
        "test_consumed": True,
        "development_row_count": 70,
        "excluded_target_overlap_count": 6,
        "test_row_count": 24,
        "selection": {
            "selection_method": ("expanding_walk_forward"),
            "policy": ("normalized_deduplicated"),
            "c_value": 0.03,
            "fold_count": 4,
            "validation_window": 5,
            "minimum_train_window": 30,
            "candidate_count": 24,
            "total_validation_row_count": 20,
            "output_feature_count_minimum": 8,
            "output_feature_count_maximum": 9,
            "mean_train_macro_f1": 0.55,
            "mean_validation_macro_f1": 0.31,
            ("standard_deviation_" "validation_macro_f1"): 0.04,
            "minimum_validation_macro_f1": 0.25,
            "pooled_validation_macro_f1": 0.32,
            ("mean_validation_" "balanced_accuracy"): 0.38,
            "mean_generalization_gap": 0.24,
            "pooled_predicted_label_counts": {
                "down": 7,
                "neutral": 6,
                "up": 7,
            },
        },
        "features": {
            "exported_feature_count": 10,
            "excluded_present_feature_names": (
                "candle.close",
                "price.close",
            ),
            "preprocessing_input_feature_count": 8,
            "dropped_constant_feature_names": (
                "constant.first",
                "constant.second",
            ),
            "active_feature_count": 6,
            "output_feature_count": 9,
        },
        "dummy_test": {
            "row_count": 24,
            "accuracy": 0.50,
            "balanced_accuracy": (1.0 / 3.0),
            "macro_f1": 0.22,
            "weighted_f1": 0.33,
            "predicted_label_counts": {
                "down": 0,
                "neutral": 24,
                "up": 0,
            },
        },
        "selected_model_development": {
            "row_count": 70,
            "accuracy": 0.56,
            "balanced_accuracy": 0.57,
            "macro_f1": 0.55,
            "weighted_f1": 0.56,
            "predicted_label_counts": {
                "down": 20,
                "neutral": 30,
                "up": 20,
            },
        },
        "selected_model_test": {
            "row_count": 24,
            "accuracy": 0.31,
            "balanced_accuracy": 0.34,
            "macro_f1": 0.29,
            "weighted_f1": 0.30,
            "predicted_label_counts": {
                "down": 8,
                "neutral": 8,
                "up": 8,
            },
        },
    }

    return MLBenchmarkReport.model_validate(payload)


def canonical_bytes(
    report: MLBenchmarkReport,
) -> bytes:
    """Reproduit la sérialisation canonique attendue."""
    return (
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def test_exports_canonical_json_and_sha256(
    tmp_path: Path,
) -> None:
    report = valid_report()

    result = MLBenchmarkExporter().export(
        report,
        tmp_path,
        file_stem="benchmark-v1",
    )

    expected_payload = canonical_bytes(report)
    written_payload = result.report_path.read_bytes()

    assert result.report_path == (tmp_path.resolve() / "benchmark-v1.benchmark.json")
    assert result.report_path.is_file()

    assert written_payload == expected_payload
    assert written_payload.endswith(b"\n")
    assert not written_payload.endswith(b"\n\n")

    expected_sha256 = "sha256:" + hashlib.sha256(expected_payload).hexdigest()

    assert result.report_sha256 == expected_sha256
    assert result.byte_count == len(expected_payload)
    assert result.reused_existing_file is False

    parsed = json.loads(written_payload)

    assert parsed == report.model_dump(mode="json")


def test_second_identical_export_reuses_file(
    tmp_path: Path,
) -> None:
    report = valid_report()
    exporter = MLBenchmarkExporter()

    first = exporter.export(
        report,
        tmp_path,
        file_stem="benchmark-v1",
    )
    original_payload = first.report_path.read_bytes()

    second = exporter.export(
        report,
        tmp_path,
        file_stem="benchmark-v1",
    )

    assert second.report_path == (first.report_path)
    assert second.report_sha256 == (first.report_sha256)
    assert second.byte_count == (first.byte_count)
    assert second.reused_existing_file is True

    assert second.report_path.read_bytes() == original_payload


def test_rejects_different_existing_content(
    tmp_path: Path,
) -> None:
    exporter = MLBenchmarkExporter()

    first = exporter.export(
        valid_report(benchmark_name="benchmark-first"),
        tmp_path,
        file_stem="benchmark",
    )
    original_payload = first.report_path.read_bytes()

    with pytest.raises(
        MLBenchmarkExportError,
        match="contenu différent",
    ):
        exporter.export(
            valid_report(benchmark_name=("benchmark-second")),
            tmp_path,
            file_stem="benchmark",
        )

    assert first.report_path.read_bytes() == original_payload

    temporary_files = list(tmp_path.glob(".benchmark.benchmark.json.*.tmp"))

    assert temporary_files == []


@pytest.mark.parametrize(
    "invalid_file_stem",
    [
        "",
        " ",
        " benchmark",
        "benchmark ",
        ".",
        "..",
        "folder/benchmark",
        r"folder\benchmark",
        "benchmark.",
        "bad\nname",
    ],
)
def test_rejects_invalid_file_stems(
    tmp_path: Path,
    invalid_file_stem: str,
) -> None:
    with pytest.raises(
        MLBenchmarkExportError,
        match="file_stem",
    ):
        MLBenchmarkExporter().export(
            valid_report(),
            tmp_path,
            file_stem=invalid_file_stem,
        )


def test_rejects_non_string_file_stem(
    tmp_path: Path,
) -> None:
    invalid_file_stem = cast(
        str,
        123,
    )

    with pytest.raises(
        MLBenchmarkExportError,
        match="doit être une chaîne",
    ):
        MLBenchmarkExporter().export(
            valid_report(),
            tmp_path,
            file_stem=invalid_file_stem,
        )


def test_creates_nested_output_directory(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "artifacts" / "ml-benchmarks"

    assert not output_directory.exists()

    result = MLBenchmarkExporter().export(
        valid_report(),
        output_directory,
        file_stem="nested-benchmark",
    )

    assert output_directory.is_dir()
    assert result.report_path.is_file()
    assert result.report_path.parent == (output_directory.resolve())


def test_rejects_output_path_that_is_file(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "not-a-directory"
    output_path.write_text(
        "existing file",
        encoding="utf-8",
    )

    with pytest.raises(
        MLBenchmarkExportError,
        match="dossier",
    ):
        MLBenchmarkExporter().export(
            valid_report(),
            output_path,
            file_stem="benchmark",
        )


def test_result_to_dict_is_json_compatible(
    tmp_path: Path,
) -> None:
    result = MLBenchmarkExporter().export(
        valid_report(),
        tmp_path,
        file_stem="benchmark",
    )

    payload = result.to_dict()

    assert payload == {
        "report_path": str(result.report_path),
        "report_sha256": (result.report_sha256),
        "byte_count": result.byte_count,
        "reused_existing_file": False,
    }

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
    )

    assert isinstance(
        serialized,
        str,
    )
