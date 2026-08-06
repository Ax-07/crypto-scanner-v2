from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.domain.ohlcv_fingerprint import (
    aggregate_input_fingerprints,
    InputDataStreamFingerprint,
)
from app.ml.models.ml_dataset import MLDatasetRow
from app.ml.models.ml_dataset_audit import MLDatasetAuditReport
from app.ml.services.ml_dataset_auditor import (
    MLDatasetAuditor,
    audit_json_bytes,
    write_audit_artifact,
)
from app.ml.services.ml_dataset_builder import MLDatasetBuildReport, MLDatasetBuildResult
from app.ml.services.ml_dataset_exporter import MLDatasetExporter
from app.ml.services.ml_dataset_loader import MLDatasetLoadError, MLDatasetLoader
from app.ml.services.ml_v2_source import build_ml_v2_source_config, ml_v2_source_identity
from app.models.backtest import BacktestJob, BacktestStatus

BASE = datetime(2021, 1, 1, tzinfo=timezone.utc)


def row(index: int, future_return: float, *, constant: float = 1.0) -> MLDatasetRow:
    decision = BASE + timedelta(hours=4 * index)
    threshold = 0.01
    label = (
        "up" if future_return > threshold else "down" if future_return < -threshold else "neutral"
    )
    return MLDatasetRow(
        feature_schema_version="causal-features-v2",
        observation_id=index + 1,
        job_id="audit-source",
        symbol="BTC/USDC",
        timeframe="4h",
        decision_time=decision,
        source_open_time=decision - timedelta(hours=4),
        source_algorithm_version="signal-evaluation-v3",
        source_dataset_version="legacy-compatible",
        profile_id="ml-dataset-v2",
        profile_fingerprint="sha256:" + "a" * 64,
        horizon=6,
        entry_policy="signal_close",
        entry_time=decision,
        exit_time=decision + timedelta(hours=24),
        natr_percent=1.0,
        neutral_threshold_return=threshold,
        future_return=future_return,
        label=label,
        features={
            "price.close": 100.0 + index,
            "candle.open": 99.0 + index,
            "candle.high": 101.0 + index,
            "candle.low": 98.0 + index,
            "candle.close": 100.0 + index,
            "candle.volume": 1_000.0 + index,
            "volatility.natr_percent": 1.0,
            "test.constant": constant,
            "test.linear": float(index),
            "test.inverse": float(-index),
        },
    )


def export_fixture(root: Path, *, rows: tuple[MLDatasetRow, ...] | None = None):
    dataset_rows = rows or tuple(row(index, (0.02, -0.02, 0.0)[index % 3]) for index in range(30))
    config = build_ml_v2_source_config(
        symbol="BTC/USDC",
        timeframe="4h",
        start=BASE,
        end=BASE + timedelta(hours=4 * 30),
    )
    job = BacktestJob(id="audit-source", config=config, status=BacktestStatus.COMPLETED)
    stream = InputDataStreamFingerprint(
        role="primary",
        exchange_id="binance",
        market_type="spot",
        symbol="BTC/USDC",
        timeframe="4h",
        requested_start_ms=1,
        requested_end_ms=2,
        effective_first_open_time_ms=1,
        effective_last_open_time_ms=1,
        candle_count=1,
        closed_only=True,
        warmup_bars=200,
        future_bars=7,
        gaps_validated=True,
        fingerprint="sha256:" + "b" * 64,
    )
    source_input = aggregate_input_fingerprints(ml_v2_source_identity(config), [stream])
    report = MLDatasetBuildReport(
        source_rows=len(dataset_rows),
        processed_rows=len(dataset_rows),
        generated_rows=len(dataset_rows),
        skipped_rows=0,
        censored_outcomes=0,
        invalid_outcomes=0,
        missing_natr=0,
        contract_rejections=0,
        batch_count=1,
        rejection_reasons={},
    )
    result = MLDatasetBuildResult(
        job_id=job.id,
        horizon=6,
        natr_multiplier=1.0,
        rows=dataset_rows,
        report=report,
        feature_schema_version="causal-features-v2",
        source_job=job,
        source_input=source_input,
    )
    exported = MLDatasetExporter().export(result, root, file_stem="audit")
    return exported, MLDatasetLoader().load(exported.manifest_path)


@pytest.mark.asyncio
async def test_valid_dataset_audit_is_deterministic_and_reports_statistics(tmp_path: Path) -> None:
    _, loaded = export_fixture(tmp_path)
    auditor = MLDatasetAuditor(minimum_rows=1, recommended_source_rows=1)

    first = await auditor.audit(loaded)
    second = await auditor.audit(loaded)

    assert audit_json_bytes(first) == audit_json_bytes(second)
    assert first.conclusion == "accepted_with_reservations"
    assert first.funnel["reconciled"] is True
    assert first.labels["counts"] == {"down": 10, "neutral": 10, "up": 10}
    assert "test.constant" in first.features["constant_features"]
    pairs = {(item["left"], item["right"]) for item in first.correlations["alerts"]}
    assert ("test.inverse", "test.linear") in pairs
    assert first.temporal["largest_observation_gap_seconds"] == 4 * 3_600


def test_loader_rejects_hash_and_row_count_mutations(tmp_path: Path) -> None:
    exported, _ = export_fixture(tmp_path)
    data = exported.data_path.read_bytes()
    exported.data_path.write_bytes(
        data.replace(b'"future_return":0.02', b'"future_return":0.03', 1)
    )
    with pytest.raises(MLDatasetLoadError, match="SHA-256"):
        MLDatasetLoader().load(exported.manifest_path)

    exported.data_path.write_bytes(data)
    payload = json.loads(exported.manifest_path.read_text(encoding="utf-8"))
    payload["row_count"] += 1
    exported.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MLDatasetLoadError, match="manifeste ML invalide"):
        MLDatasetLoader().load(exported.manifest_path)


def test_unknown_audit_version_and_inconsistent_conclusion_are_rejected(tmp_path: Path) -> None:
    _, loaded = export_fixture(tmp_path)
    payload = {
        "audit_schema_version": "ml-dataset-audit-v0",
        "dataset_identity": "sha256:" + "0" * 64,
        "dataset": {},
        "source": {},
        "funnel": {},
        "structure": {},
        "temporal": {},
        "labels": {},
        "features": {},
        "correlations": {},
        "outliers": {},
        "regimes": {},
        "stability": {},
        "causal_audit": {},
        "leak_audit": {},
        "conclusion": "accepted_for_experiment_design",
    }
    del loaded
    with pytest.raises(ValidationError):
        MLDatasetAuditReport.model_validate(payload)


def test_atomic_audit_artifact_reuses_identical_and_refuses_divergent(tmp_path: Path) -> None:
    destination = tmp_path / "audit.json"
    first = write_audit_artifact(destination, b"same\n")
    second = write_audit_artifact(destination, b"same\n")
    assert first == second
    with pytest.raises(ValueError, match="divergent"):
        write_audit_artifact(destination, b"different\n")
