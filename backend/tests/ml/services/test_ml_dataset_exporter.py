from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.domain.ohlcv_fingerprint import InputDataStreamFingerprint, aggregate_input_fingerprints
from app.models.backtest import BacktestConfig, BacktestJob, BacktestStatus
from app.ml.domain.ml_dataset_profile import (
    ML_DATASET_PROFILE_V2_ID,
    build_ml_dataset_profile_v2,
)
from app.ml.services.ml_v2_source import ml_v2_source_identity
from app.ml.models.ml_dataset import (
    ML_FEATURE_SCHEMA_VERSION,
    ML_FEATURE_SCHEMA_VERSION_V2,
    MLDatasetRow,
    MLFeatureSchemaVersion,
    MarketDirectionLabel,
)
from app.ml.services.ml_dataset_builder import (
    MLDatasetBuildReport,
    MLDatasetBuildResult,
)
from app.ml.services.ml_dataset_exporter import MLDatasetExporter

BASE_TIME = datetime(
    2026,
    1,
    1,
    12,
    0,
    tzinfo=timezone.utc,
)

EMPTY_SHA256 = "sha256:" "e3b0c44298fc1c149afbf4c8996fb924" "27ae41e4649b934ca495991b7852b855"
PROFILE_FINGERPRINT_A = "sha256:" + ("a" * 64)
PROFILE_FINGERPRINT_B = "sha256:" + ("b" * 64)


def dataset_row(
    observation_id: int,
    *,
    decision_time: datetime,
    future_return: float,
    feature_name: str,
    profile_id: str = "inline",
    profile_fingerprint: str | None = "sha256:profile",
    feature_schema_version: MLFeatureSchemaVersion = ML_FEATURE_SCHEMA_VERSION,
) -> MLDatasetRow:
    """Construit une ligne exportable avec un label cohérent."""
    threshold = 0.02

    if future_return > threshold:
        label = MarketDirectionLabel.UP
    elif future_return < -threshold:
        label = MarketDirectionLabel.DOWN
    else:
        label = MarketDirectionLabel.NEUTRAL

    return MLDatasetRow(
        observation_id=observation_id,
        job_id="export-test",
        symbol="BTC/USDC",
        timeframe="1h",
        decision_time=decision_time,
        source_open_time=decision_time - timedelta(hours=1),
        snapshot_status="confirmed",
        calculation_mode="canonical",
        source_algorithm_version="signal-evaluation-v3",
        source_dataset_version="binance-history-v1",
        profile_id=profile_id,
        profile_fingerprint=profile_fingerprint,
        horizon=6,
        entry_policy="signal_close",
        entry_time=decision_time,
        exit_time=decision_time + timedelta(hours=6),
        natr_percent=2.0,
        natr_multiplier=1.0,
        neutral_threshold_return=threshold,
        future_return=future_return,
        label=label,
        features={
            "price.close": 100.0 + observation_id,
            feature_name: float(observation_id),
        },
        feature_schema_version=feature_schema_version,
    )


def build_result(
    rows: tuple[MLDatasetRow, ...],
    *,
    report_generated_rows: int | None = None,
    feature_schema_version: MLFeatureSchemaVersion = ML_FEATURE_SCHEMA_VERSION,
) -> MLDatasetBuildResult:
    """Construit un résultat de service cohérent, sauf demande explicite."""
    generated_rows = len(rows) if report_generated_rows is None else report_generated_rows

    report = MLDatasetBuildReport(
        source_rows=generated_rows,
        processed_rows=generated_rows,
        generated_rows=generated_rows,
        skipped_rows=0,
        censored_outcomes=0,
        invalid_outcomes=0,
        missing_natr=0,
        contract_rejections=0,
        batch_count=1 if generated_rows else 0,
        rejection_reasons={},
    )

    source_job = None
    source_input = None
    if feature_schema_version == ML_FEATURE_SCHEMA_VERSION_V2:
        source_job = BacktestJob(
            id="export-test",
            status=BacktestStatus.COMPLETED,
            config=BacktestConfig(
                symbols=["BTC/USDC"],
                start=BASE_TIME - timedelta(days=2),
                end=BASE_TIME + timedelta(days=2),
                signal_config=build_ml_dataset_profile_v2(timeframe="1h"),
                signal_profile_id=ML_DATASET_PROFILE_V2_ID,
                horizons=[6],
            ),
        )
        stream = InputDataStreamFingerprint(
            role="primary",
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1h",
            requested_start_ms=1,
            requested_end_ms=2,
            effective_first_open_time_ms=1,
            effective_last_open_time_ms=1,
            candle_count=1,
            warmup_bars=0,
            future_bars=0,
            gaps_validated=True,
            fingerprint="sha256:" + "1" * 64,
        )
        source_input = aggregate_input_fingerprints(
            ml_v2_source_identity(source_job.config), (stream,)
        )

    return MLDatasetBuildResult(
        job_id="export-test",
        horizon=6,
        natr_multiplier=1.0,
        rows=rows,
        report=report,
        feature_schema_version=feature_schema_version,
        source_job=source_job,
        source_input=source_input,
    )


def test_export_writes_sorted_jsonl_and_manifest() -> None:
    early_row = dataset_row(
        1,
        decision_time=BASE_TIME,
        future_return=0.03,
        feature_name="feature.a",
    )
    late_row = dataset_row(
        2,
        decision_time=BASE_TIME + timedelta(hours=1),
        future_return=0.01,
        feature_name="feature.b",
        profile_fingerprint=None,
    )

    result = build_result(
        (
            late_row,
            early_row,
        )
    )

    with tempfile.TemporaryDirectory() as temporary:
        exported = MLDatasetExporter().export(
            result,
            Path(temporary),
            file_stem=" dataset export ",
        )

        assert exported.data_path.name == "dataset_export.jsonl"
        assert exported.manifest_path.name == "dataset_export.manifest.json"

        data_bytes = exported.data_path.read_bytes()

        assert data_bytes.endswith(b"\n")

        payloads = [json.loads(line) for line in data_bytes.decode("utf-8").splitlines()]

        assert [payload["observation_id"] for payload in payloads] == [
            1,
            2,
        ]

        expected_sha256 = "sha256:" + hashlib.sha256(data_bytes).hexdigest()

        manifest = exported.manifest

        assert manifest.data_sha256 == expected_sha256
        assert manifest.data_file == "dataset_export.jsonl"
        assert manifest.row_count == 2
        assert manifest.first_decision_time == BASE_TIME
        assert manifest.last_decision_time == BASE_TIME + timedelta(hours=1)
        assert manifest.feature_names == [
            "feature.a",
            "feature.b",
            "price.close",
        ]
        assert manifest.source_algorithm_versions == [
            "signal-evaluation-v3",
        ]
        assert manifest.source_dataset_versions == [
            "binance-history-v1",
        ]
        assert manifest.profile_ids == [
            "inline",
        ]
        assert manifest.profile_fingerprints == [
            "sha256:profile",
        ]

        manifest_payload = json.loads(exported.manifest_path.read_text(encoding="utf-8"))

        assert manifest_payload == manifest.model_dump(mode="json")
        assert exported.manifest_path.read_bytes().endswith(b"\n")


def test_export_is_deterministic_across_input_order() -> None:
    first_row = dataset_row(
        1,
        decision_time=BASE_TIME,
        future_return=0.03,
        feature_name="feature.a",
    )
    second_row = dataset_row(
        2,
        decision_time=BASE_TIME + timedelta(hours=1),
        future_return=-0.03,
        feature_name="feature.b",
    )

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)

        first_export = MLDatasetExporter().export(
            build_result(
                (
                    second_row,
                    first_row,
                )
            ),
            root / "first",
            file_stem="stable",
        )
        second_export = MLDatasetExporter().export(
            build_result(
                (
                    first_row,
                    second_row,
                )
            ),
            root / "second",
            file_stem="stable",
        )

        assert first_export.data_path.read_bytes() == second_export.data_path.read_bytes()
        assert first_export.manifest_path.read_bytes() == second_export.manifest_path.read_bytes()
        assert first_export.manifest.data_sha256 == second_export.manifest.data_sha256


def test_export_replaces_existing_files() -> None:
    initial_row = dataset_row(
        1,
        decision_time=BASE_TIME,
        future_return=0.03,
        feature_name="feature.a",
    )
    updated_row = dataset_row(
        1,
        decision_time=BASE_TIME,
        future_return=0.04,
        feature_name="feature.a",
    )

    with tempfile.TemporaryDirectory() as temporary:
        destination = Path(temporary)

        first_export = MLDatasetExporter().export(
            build_result((initial_row,)),
            destination,
            file_stem="replace",
        )
        initial_bytes = first_export.data_path.read_bytes()

        second_export = MLDatasetExporter().export(
            build_result((updated_row,)),
            destination,
            file_stem="replace",
        )
        updated_bytes = second_export.data_path.read_bytes()

        assert first_export.data_path == second_export.data_path
        assert first_export.manifest_path == second_export.manifest_path
        assert initial_bytes != updated_bytes
        assert second_export.manifest.data_sha256 == (
            "sha256:" + hashlib.sha256(updated_bytes).hexdigest()
        )

        temporary_files = [path for path in destination.iterdir() if path.name.endswith(".tmp")]

        assert temporary_files == []


def test_export_rejects_duplicate_observation_ids() -> None:
    first_row = dataset_row(
        1,
        decision_time=BASE_TIME,
        future_return=0.03,
        feature_name="feature.a",
    )
    duplicate_row = dataset_row(
        1,
        decision_time=BASE_TIME + timedelta(hours=1),
        future_return=0.01,
        feature_name="feature.b",
    )

    with tempfile.TemporaryDirectory() as temporary:
        with pytest.raises(
            ValueError,
            match="plusieurs lignes",
        ):
            MLDatasetExporter().export(
                build_result(
                    (
                        first_row,
                        duplicate_row,
                    )
                ),
                Path(temporary),
            )


def test_export_rejects_report_row_count_mismatch() -> None:
    rows = (
        dataset_row(
            1,
            decision_time=BASE_TIME,
            future_return=0.03,
            feature_name="feature.a",
        ),
        dataset_row(
            2,
            decision_time=BASE_TIME + timedelta(hours=1),
            future_return=0.01,
            feature_name="feature.b",
        ),
    )

    inconsistent_result = build_result(
        rows,
        report_generated_rows=3,
    )

    with tempfile.TemporaryDirectory() as temporary:
        with pytest.raises(
            ValueError,
            match="nombre de lignes",
        ):
            MLDatasetExporter().export(
                inconsistent_result,
                Path(temporary),
            )


@pytest.mark.parametrize(
    "file_stem",
    [
        "",
        "   ",
        ".",
        "..",
        "...",
    ],
)
def test_export_rejects_unusable_file_stem(
    file_stem: str,
) -> None:
    result = build_result(())

    with tempfile.TemporaryDirectory() as temporary:
        with pytest.raises(
            ValueError,
            match="file_stem",
        ):
            MLDatasetExporter().export(
                result,
                Path(temporary),
                file_stem=file_stem,
            )


def test_export_empty_dataset() -> None:
    result = build_result(())

    with tempfile.TemporaryDirectory() as temporary:
        exported = MLDatasetExporter().export(
            result,
            Path(temporary),
            file_stem="empty",
        )

        assert exported.data_path.read_bytes() == b""
        assert exported.manifest.data_sha256 == EMPTY_SHA256
        assert exported.manifest.row_count == 0
        assert exported.manifest.first_decision_time is None
        assert exported.manifest.last_decision_time is None
        assert exported.manifest.feature_names == []
        assert exported.manifest.stats.generated_rows == 0
        assert exported.manifest.stats.processed_rows == 0


def test_export_propagates_v2_feature_schema() -> None:
    row = dataset_row(
        1,
        decision_time=BASE_TIME,
        future_return=0.03,
        feature_name="feature.v2",
        profile_id=ML_DATASET_PROFILE_V2_ID,
        profile_fingerprint=PROFILE_FINGERPRINT_A,
        feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
    )

    result = build_result(
        (row,),
        feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
    )

    with tempfile.TemporaryDirectory() as temporary:
        exported = MLDatasetExporter().export(
            result,
            Path(temporary),
            file_stem="dataset-v2",
        )

        assert exported.manifest.feature_schema_version == ML_FEATURE_SCHEMA_VERSION_V2
        assert result.source_job is not None
        assert result.source_input is not None
        assert exported.manifest.manifest_schema_version == 2
        assert exported.manifest.backtest_config == result.source_job.config
        assert exported.manifest.source_identity == result.source_input.source_identity
        assert exported.manifest.input_data_fingerprint == (
            result.source_input.input_data_fingerprint
        )
        assert exported.manifest.input_streams == list(result.source_input.streams)
        assert set(exported.manifest.pipeline_versions) == {
            "backtest_algorithm",
            "builder",
            "exporter",
            "feature_schema",
            "label_schema",
            "loader_contract",
        }
        assert not any(
            Path(value).is_absolute() for value in exported.manifest.pipeline_versions.values()
        )

        assert exported.manifest.profile_ids == [
            ML_DATASET_PROFILE_V2_ID,
        ]
        assert exported.manifest.profile_fingerprints == [
            PROFILE_FINGERPRINT_A,
        ]

        payload = json.loads(
            exported.data_path.read_text(
                encoding="utf-8",
            )
        )

        assert payload["feature_schema_version"] == ML_FEATURE_SCHEMA_VERSION_V2


def test_export_rejects_v2_with_noncanonical_profile_id() -> None:
    row = dataset_row(
        1,
        decision_time=BASE_TIME,
        future_return=0.03,
        feature_name="feature.v2",
        profile_id="inline",
        profile_fingerprint=PROFILE_FINGERPRINT_A,
        feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
    )

    with tempfile.TemporaryDirectory() as temporary:
        with pytest.raises(
            ValueError,
            match="profile_id",
        ):
            MLDatasetExporter().export(
                build_result(
                    (row,),
                    feature_schema_version=(ML_FEATURE_SCHEMA_VERSION_V2),
                ),
                Path(temporary),
            )


@pytest.mark.parametrize(
    "profile_fingerprint",
    [
        None,
        "sha256:invalid",
    ],
)
def test_export_rejects_v2_with_invalid_profile_fingerprint(
    profile_fingerprint: str | None,
) -> None:
    row = dataset_row(
        1,
        decision_time=BASE_TIME,
        future_return=0.03,
        feature_name="feature.v2",
        profile_id=ML_DATASET_PROFILE_V2_ID,
        profile_fingerprint=profile_fingerprint,
        feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
    )

    with tempfile.TemporaryDirectory() as temporary:
        with pytest.raises(
            ValueError,
            match="profile_fingerprint",
        ):
            MLDatasetExporter().export(
                build_result(
                    (row,),
                    feature_schema_version=(ML_FEATURE_SCHEMA_VERSION_V2),
                ),
                Path(temporary),
            )


def test_export_rejects_v2_with_mixed_profile_fingerprints() -> None:
    first = dataset_row(
        1,
        decision_time=BASE_TIME,
        future_return=0.03,
        feature_name="feature.v2",
        profile_id=ML_DATASET_PROFILE_V2_ID,
        profile_fingerprint=PROFILE_FINGERPRINT_A,
        feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
    )
    second = dataset_row(
        2,
        decision_time=BASE_TIME + timedelta(hours=1),
        future_return=-0.03,
        feature_name="feature.v2",
        profile_id=ML_DATASET_PROFILE_V2_ID,
        profile_fingerprint=PROFILE_FINGERPRINT_B,
        feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
    )

    with tempfile.TemporaryDirectory() as temporary:
        with pytest.raises(
            ValueError,
            match="plusieurs profile_fingerprints",
        ):
            MLDatasetExporter().export(
                build_result(
                    (
                        first,
                        second,
                    ),
                    feature_schema_version=(ML_FEATURE_SCHEMA_VERSION_V2),
                ),
                Path(temporary),
            )


def test_export_rejects_empty_v2_dataset() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        with pytest.raises(
            ValueError,
            match="sans ligne ML",
        ):
            MLDatasetExporter().export(
                build_result(
                    (),
                    feature_schema_version=(ML_FEATURE_SCHEMA_VERSION_V2),
                ),
                Path(temporary),
            )


def test_export_rejects_feature_schema_mismatch() -> None:
    row = dataset_row(
        1,
        decision_time=BASE_TIME,
        future_return=0.03,
        feature_name="feature.v1",
    )

    result = build_result(
        (row,),
        feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
    )

    with tempfile.TemporaryDirectory() as temporary:
        with pytest.raises(
            ValueError,
            match="feature_schema_version",
        ):
            MLDatasetExporter().export(
                result,
                Path(temporary),
            )
