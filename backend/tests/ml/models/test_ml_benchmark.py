from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from app.ml.models.ml_benchmark import (
    ML_BENCHMARK_SCHEMA_VERSION,
    MLBenchmarkLabelCounts,
    MLBenchmarkMetricSnapshot,
    MLBenchmarkReport,
)

UTC = timezone.utc
PARIS_TIMEZONE = timezone(timedelta(hours=2))


def valid_payload() -> dict[str, Any]:
    """Construit un benchmark rejeté cohérent."""
    return {
        "benchmark_schema_version": (ML_BENCHMARK_SCHEMA_VERSION),
        "benchmark_name": ("  btc-usdc-1h-h6-logistic-v1  "),
        "created_at": datetime(
            2026,
            8,
            3,
            22,
            30,
            tzinfo=PARIS_TIMEZONE,
        ),
        "status": "rejected",
        "decision_reasons": [
            "balanced accuracy proche du hasard",
            "généralisation temporelle insuffisante",
            "balanced accuracy proche du hasard",
        ],
        "source_manifest_file": ("btc-usdc-1h-h6-v1.manifest.json"),
        "source_data_file": ("btc-usdc-1h-h6-v1.jsonl"),
        "source_data_sha256": (
            "sha256:" "a94660d07503b9494ac646ad948d0738" "d7b6a6941b1893c40a3a671484e4b2a4"
        ),
        "source_job_id": ("cc776c29c7e74f74a7910d91fc3b92cc"),
        "manifest_schema_version": 1,
        "dataset_schema_version": 1,
        "feature_schema_version": ("ml-features-v1"),
        "label_schema_version": ("ml-direction-label-v1"),
        "horizon": 6,
        "natr_multiplier": 1.0,
        "dataset_row_count": 713,
        "first_decision_time": datetime(
            2026,
            7,
            4,
            15,
            0,
            tzinfo=UTC,
        ),
        "last_decision_time": datetime(
            2026,
            8,
            3,
            7,
            0,
            tzinfo=UTC,
        ),
        "evaluation_start": datetime(
            2026,
            7,
            28,
            9,
            0,
            tzinfo=UTC,
        ),
        "test_consumed": True,
        "development_row_count": 564,
        "excluded_target_overlap_count": 6,
        "test_row_count": 143,
        "selection": {
            "selection_method": ("expanding_walk_forward"),
            "policy": ("normalized_deduplicated"),
            "c_value": 0.03,
            "fold_count": 4,
            "validation_window": 72,
            "minimum_train_window": 200,
            "candidate_count": 24,
            "total_validation_row_count": 288,
            "output_feature_count_minimum": 136,
            "output_feature_count_maximum": 137,
            "mean_train_macro_f1": (0.5799),
            "mean_validation_macro_f1": (0.3018),
            ("standard_deviation_" "validation_macro_f1"): 0.0581,
            "minimum_validation_macro_f1": (0.2327),
            "pooled_validation_macro_f1": (0.3373),
            ("mean_validation_" "balanced_accuracy"): 0.3795,
            "mean_generalization_gap": (0.2781),
            "pooled_predicted_label_counts": {
                "down": 112,
                "neutral": 104,
                "up": 72,
            },
        },
        "features": {
            "exported_feature_count": 136,
            "excluded_present_feature_names": [
                "price.close",
                "candle.close",
                "indicator.atr.raw_value",
                "price.close",
                "candle.high",
                "candle.low",
                "candle.open",
                "candle.volume",
                ("indicator.atr.component." "atr.value"),
                ("indicator.atr.component." "natr.normalized_value"),
                ("indicator.atr.component." "natr.value"),
                ("indicator.atr.component." "true_range.value"),
                ("indicator.bollinger.component." "band_position.normalized_value"),
                ("indicator.bollinger.component." "band_width.value"),
                ("indicator.bollinger.component." "band_width_percent." "normalized_value"),
                ("indicator.bollinger.component." "lower_band.value"),
                ("indicator.bollinger.component." "middle_band.value"),
                ("indicator.bollinger.component." "upper_band.value"),
                "quality.quote_volume_median",
            ],
            "preprocessing_input_feature_count": 118,
            "dropped_constant_feature_names": [f"constant.feature.{index}" for index in range(28)],
            "active_feature_count": 90,
            "output_feature_count": 139,
        },
        "dummy_test": {
            "row_count": 143,
            "accuracy": 0.48951048951048953,
            "balanced_accuracy": (0.3333333333333333),
            "macro_f1": 0.21909233176838813,
            "weighted_f1": 0.3217439837158147,
            "predicted_label_counts": {
                "down": 0,
                "neutral": 143,
                "up": 0,
            },
        },
        "selected_model_development": {
            "row_count": 564,
            "accuracy": 0.5531914893617021,
            "balanced_accuracy": (0.5602526629976115),
            "macro_f1": 0.5353527184834586,
            "weighted_f1": 0.5638752853007666,
            "predicted_label_counts": {
                "down": 175,
                "neutral": 218,
                "up": 171,
            },
        },
        "selected_model_test": {
            "row_count": 143,
            "accuracy": 0.3006993006993007,
            "balanced_accuracy": (0.33577961672473866),
            "macro_f1": 0.2897876037111493,
            "weighted_f1": 0.2896566294578771,
            "predicted_label_counts": {
                "down": 20,
                "neutral": 42,
                "up": 81,
            },
        },
    }


def test_accepts_and_normalizes_valid_report() -> None:
    report = MLBenchmarkReport.model_validate(valid_payload())

    assert report.benchmark_schema_version == "ml-benchmark-v1"
    assert report.benchmark_name == "btc-usdc-1h-h6-logistic-v1"
    assert report.status == "rejected"
    assert report.test_consumed is True

    assert report.created_at == datetime(
        2026,
        8,
        3,
        20,
        30,
        tzinfo=UTC,
    )

    assert report.decision_reasons == (
        "balanced accuracy proche du hasard",
        "généralisation temporelle insuffisante",
    )

    assert len(report.features.excluded_present_feature_names) == 18

    assert report.features.excluded_present_feature_names == tuple(
        sorted(report.features.excluded_present_feature_names)
    )

    assert report.selection.pooled_predicted_label_counts.total == 288
    assert report.selected_model_test.predicted_label_counts.total == 143


def test_report_is_frozen() -> None:
    report = MLBenchmarkReport.model_validate(valid_payload())

    with pytest.raises(
        ValidationError,
        match="frozen",
    ):
        setattr(
            report,
            "status",
            "accepted",
        )


def test_accepted_report_can_have_no_reason() -> None:
    payload = valid_payload()
    payload["status"] = "accepted"
    payload["decision_reasons"] = []

    report = MLBenchmarkReport.model_validate(payload)

    assert report.status == "accepted"
    assert report.decision_reasons == ()


def test_rejected_report_requires_reason() -> None:
    payload = valid_payload()
    payload["decision_reasons"] = []

    with pytest.raises(
        ValidationError,
        match="benchmark rejeté",
    ):
        MLBenchmarkReport.model_validate(payload)


def test_rejects_partition_count_mismatch() -> None:
    payload = valid_payload()
    payload["development_row_count"] = 563

    with pytest.raises(
        ValidationError,
        match="reconstituer dataset_row_count",
    ):
        MLBenchmarkReport.model_validate(payload)


def test_rejects_dummy_test_row_count_mismatch() -> None:
    payload = valid_payload()
    payload["dummy_test"]["row_count"] = 142
    payload["dummy_test"]["predicted_label_counts"] = {
        "down": 0,
        "neutral": 142,
        "up": 0,
    }

    with pytest.raises(
        ValidationError,
        match="dummy_test.row_count",
    ):
        MLBenchmarkReport.model_validate(payload)


def test_rejects_development_metric_row_mismatch() -> None:
    payload = valid_payload()
    payload["selected_model_development"]["row_count"] = 563
    payload["selected_model_development"]["predicted_label_counts"] = {
        "down": 175,
        "neutral": 217,
        "up": 171,
    }

    with pytest.raises(
        ValidationError,
        match="selected_model_development",
    ):
        MLBenchmarkReport.model_validate(payload)


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "../benchmark.json",
        "folder/benchmark.json",
        r"folder\benchmark.json",
        ".",
        "..",
    ],
)
def test_rejects_unsafe_source_file_names(
    unsafe_name: str,
) -> None:
    payload = valid_payload()
    payload["source_data_file"] = unsafe_name

    with pytest.raises(
        ValidationError,
        match="nom de fichier simple",
    ):
        MLBenchmarkReport.model_validate(payload)


def test_rejects_invalid_sha256() -> None:
    payload = valid_payload()
    payload["source_data_sha256"] = "sha256:not-a-valid-hash"

    with pytest.raises(
        ValidationError,
        match="source_data_sha256",
    ):
        MLBenchmarkReport.model_validate(payload)


def test_rejects_walk_forward_prediction_count_mismatch() -> None:
    payload = valid_payload()
    payload["selection"]["pooled_predicted_label_counts"]["up"] = 71

    with pytest.raises(
        ValidationError,
        match="totaliser total_validation_row_count",
    ):
        MLBenchmarkReport.model_validate(payload)


def test_rejects_invalid_output_feature_range() -> None:
    payload = valid_payload()
    payload["selection"]["output_feature_count_minimum"] = 138
    payload["selection"]["output_feature_count_maximum"] = 137

    with pytest.raises(
        ValidationError,
        match="ne peut pas dépasser",
    ):
        MLBenchmarkReport.model_validate(payload)


def test_rejects_feature_filter_count_mismatch() -> None:
    payload = valid_payload()
    payload["features"]["preprocessing_input_feature_count"] = 117

    with pytest.raises(
        ValidationError,
        match="reconstituer exported_feature_count",
    ):
        MLBenchmarkReport.model_validate(payload)


def test_rejects_constant_feature_count_mismatch() -> None:
    payload = valid_payload()
    payload["features"]["active_feature_count"] = 89

    with pytest.raises(
        ValidationError,
        match=("reconstituer " "preprocessing_input_feature_count"),
    ):
        MLBenchmarkReport.model_validate(payload)


def test_rejects_output_smaller_than_active_features() -> None:
    payload = valid_payload()
    payload["features"]["output_feature_count"] = 89

    with pytest.raises(
        ValidationError,
        match="inférieur à active_feature_count",
    ):
        MLBenchmarkReport.model_validate(payload)


def test_rejects_evaluation_start_outside_dataset() -> None:
    payload = valid_payload()
    payload["evaluation_start"] = datetime(
        2026,
        8,
        4,
        0,
        0,
        tzinfo=UTC,
    )

    with pytest.raises(
        ValidationError,
        match="appartenir à la période",
    ):
        MLBenchmarkReport.model_validate(payload)


def test_rejects_naive_datetime() -> None:
    payload = valid_payload()
    payload["created_at"] = datetime(
        2026,
        8,
        3,
        20,
        30,
    )

    with pytest.raises(
        ValidationError,
        match="inclure un fuseau horaire",
    ):
        MLBenchmarkReport.model_validate(payload)


def test_metric_snapshot_rejects_prediction_mismatch() -> None:
    with pytest.raises(
        ValidationError,
        match="totaliser row_count",
    ):
        MLBenchmarkMetricSnapshot(
            row_count=10,
            accuracy=0.5,
            balanced_accuracy=0.5,
            macro_f1=0.5,
            weighted_f1=0.5,
            predicted_label_counts=(
                MLBenchmarkLabelCounts(
                    down=3,
                    neutral=3,
                    up=3,
                )
            ),
        )


def test_rejects_extra_fields() -> None:
    payload = valid_payload()
    payload["unexpected_field"] = True

    with pytest.raises(
        ValidationError,
        match="unexpected_field",
    ):
        MLBenchmarkReport.model_validate(payload)
