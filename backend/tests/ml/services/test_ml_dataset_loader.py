from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import pytest

from app.ml.domain.ml_dataset_profile import ML_DATASET_PROFILE_V2_ID
from app.ml.models.ml_dataset import (
    MLDatasetRow,
    MarketDirectionLabel,
    ML_FEATURE_SCHEMA_VERSION,
    ML_FEATURE_SCHEMA_VERSION_V2,
    MLFeatureSchemaVersion,
)
from app.ml.services.ml_dataset_builder import (
    MLDatasetBuildReport,
    MLDatasetBuildResult,
)
from app.ml.services.ml_dataset_exporter import (
    MLDatasetExporter,
)
from app.ml.services.ml_dataset_loader import (
    MLDatasetLoadError,
    MLDatasetLoader,
)

BASE_TIME = datetime(
    2026,
    1,
    1,
    12,
    0,
    tzinfo=timezone.utc,
)
V2_PROFILE_FINGERPRINT = "sha256:" + "a" * 64


def dataset_row(
    observation_id: int,
    *,
    decision_time: datetime,
    feature_name: str = "feature.value",
    feature_schema_version: MLFeatureSchemaVersion = ML_FEATURE_SCHEMA_VERSION,
    profile_id: str = "inline",
    profile_fingerprint: str | None = "sha256:profile",
) -> MLDatasetRow:
    """Construit une ligne ML neutre valide."""
    return MLDatasetRow(
        observation_id=observation_id,
        job_id="loader-test",
        symbol="BTC/USDC",
        timeframe="1h",
        decision_time=decision_time,
        source_open_time=(decision_time - timedelta(hours=1)),
        snapshot_status="confirmed",
        calculation_mode="canonical",
        source_algorithm_version=("signal-evaluation-v3"),
        source_dataset_version=("binance-history-v1"),
        profile_id=profile_id,
        profile_fingerprint=profile_fingerprint,
        horizon=6,
        entry_policy="signal_close",
        entry_time=decision_time,
        exit_time=(decision_time + timedelta(hours=6)),
        natr_percent=2.0,
        natr_multiplier=1.0,
        neutral_threshold_return=0.02,
        future_return=0.0,
        label=MarketDirectionLabel.NEUTRAL,
        features={
            "price.close": (100.0 + observation_id),
            feature_name: float(observation_id),
        },
        feature_schema_version=feature_schema_version,
    )


def build_result(
    rows: tuple[MLDatasetRow, ...],
    *,
    feature_schema_version: MLFeatureSchemaVersion = ML_FEATURE_SCHEMA_VERSION,
) -> MLDatasetBuildResult:
    """Construit un résultat de génération cohérent."""
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
        batch_count=1 if row_count else 0,
        rejection_reasons={},
    )

    return MLDatasetBuildResult(
        job_id="loader-test",
        horizon=6,
        natr_multiplier=1.0,
        rows=rows,
        report=report,
        feature_schema_version=feature_schema_version,
    )


def export_valid_dataset(
    directory: Path,
    *,
    rows: tuple[MLDatasetRow, ...] | None = None,
) -> tuple[Path, Path]:
    """Exporte un dataset valide et retourne ses deux chemins."""
    selected_rows = (
        rows
        if rows is not None
        else (
            dataset_row(
                1,
                decision_time=BASE_TIME,
            ),
            dataset_row(
                2,
                decision_time=(BASE_TIME + timedelta(hours=1)),
                feature_name="feature.other",
            ),
        )
    )

    result = MLDatasetExporter().export(
        build_result(selected_rows),
        directory,
        file_stem="loader-test",
    )

    return (
        result.manifest_path,
        result.data_path,
    )


def manifest_payload(
    manifest_path: Path,
) -> dict[str, Any]:
    """Charge le manifeste sous forme de dictionnaire mutable."""
    return cast(
        dict[str, Any],
        json.loads(manifest_path.read_text(encoding="utf-8")),
    )


def write_manifest(
    manifest_path: Path,
    payload: dict[str, Any],
) -> None:
    """Écrit un manifeste JSON lisible."""
    manifest_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def update_manifest_sha256(
    manifest_path: Path,
    data_path: Path,
) -> None:
    """Met à jour le hash déclaré après une mutation contrôlée."""
    payload = manifest_payload(manifest_path)
    payload["data_sha256"] = "sha256:" + hashlib.sha256(data_path.read_bytes()).hexdigest()
    write_manifest(
        manifest_path,
        payload,
    )


def canonical_json_line(
    payload: dict[str, Any],
) -> bytes:
    """Sérialise une ligne JSONL canonique."""
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def test_loader_accepts_valid_export() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest_path, data_path = export_valid_dataset(root)

        result = MLDatasetLoader().load(manifest_path)

        assert result.manifest_path == (manifest_path.resolve())
        assert result.data_path == (data_path.resolve())
        assert len(result.rows) == 2
        assert [row.observation_id for row in result.rows] == [
            1,
            2,
        ]
        assert result.manifest.row_count == 2


def test_loader_accepts_empty_export() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest_path, data_path = export_valid_dataset(
            root,
            rows=(),
        )

        result = MLDatasetLoader().load(manifest_path)

        assert result.rows == ()
        assert result.data_path == (data_path.resolve())
        assert result.manifest.row_count == 0


def test_loader_rejects_missing_manifest() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        missing_path = Path(temporary) / "missing.manifest.json"

        with pytest.raises(
            MLDatasetLoadError,
            match="manifeste ML introuvable",
        ):
            MLDatasetLoader().load(missing_path)


def test_loader_rejects_invalid_manifest() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        manifest_path = Path(temporary) / "invalid.manifest.json"
        manifest_path.write_text(
            "{not-json",
            encoding="utf-8",
        )

        with pytest.raises(
            MLDatasetLoadError,
            match="manifeste ML invalide",
        ):
            MLDatasetLoader().load(manifest_path)


def test_loader_rejects_missing_data_file() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest_path, data_path = export_valid_dataset(root)
        data_path.unlink()

        with pytest.raises(
            MLDatasetLoadError,
            match="JSONL introuvable",
        ):
            MLDatasetLoader().load(manifest_path)


def test_loader_rejects_unsafe_data_file() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest_path, _ = export_valid_dataset(root)

        payload = manifest_payload(manifest_path)
        payload["data_file"] = "../outside.jsonl"
        write_manifest(
            manifest_path,
            payload,
        )

        with pytest.raises(
            MLDatasetLoadError,
            match="nom de fichier simple",
        ):
            MLDatasetLoader().load(manifest_path)


def test_loader_rejects_sha256_mismatch() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest_path, data_path = export_valid_dataset(root)

        data = data_path.read_bytes()
        data_path.write_bytes(
            data.replace(
                b"\n",
                b" \n",
                1,
            )
        )

        with pytest.raises(
            MLDatasetLoadError,
            match="SHA-256",
        ):
            MLDatasetLoader().load(manifest_path)


def test_loader_rejects_blank_jsonl_line() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest_path, data_path = export_valid_dataset(root)

        first_line, remainder = data_path.read_bytes().split(
            b"\n",
            1,
        )
        data_path.write_bytes(first_line + b"\n\n" + remainder)

        with pytest.raises(
            MLDatasetLoadError,
            match="ligne JSONL vide",
        ):
            MLDatasetLoader().load(manifest_path)


def test_loader_rejects_missing_final_newline() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest_path, data_path = export_valid_dataset(root)

        data = data_path.read_bytes()
        assert data.endswith(b"\n")
        data_path.write_bytes(data[:-1])

        with pytest.raises(
            MLDatasetLoadError,
            match="saut de ligne",
        ):
            MLDatasetLoader().load(manifest_path)


def test_loader_rejects_invalid_dataset_row() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest_path, data_path = export_valid_dataset(root)

        lines = data_path.read_bytes().splitlines(keepends=True)
        lines[0] = b"{}\n"
        data_path.write_bytes(b"".join(lines))

        with pytest.raises(
            MLDatasetLoadError,
            match="ligne ML invalide",
        ):
            MLDatasetLoader().load(manifest_path)


def test_loader_rejects_unsorted_rows() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest_path, data_path = export_valid_dataset(root)

        lines = data_path.read_bytes().splitlines(keepends=True)
        data_path.write_bytes(b"".join(reversed(lines)))
        update_manifest_sha256(
            manifest_path,
            data_path,
        )

        with pytest.raises(
            MLDatasetLoadError,
            match="ne sont pas triées",
        ):
            MLDatasetLoader().load(manifest_path)


def test_loader_rejects_duplicate_observations() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest_path, data_path = export_valid_dataset(root)

        lines = data_path.read_bytes().splitlines(keepends=True)
        first_payload = cast(
            dict[str, Any],
            json.loads(lines[0]),
        )
        second_payload = cast(
            dict[str, Any],
            json.loads(lines[1]),
        )
        second_payload["observation_id"] = first_payload["observation_id"]

        lines[1] = canonical_json_line(second_payload)
        data_path.write_bytes(b"".join(lines))
        update_manifest_sha256(
            manifest_path,
            data_path,
        )

        with pytest.raises(
            MLDatasetLoadError,
            match="plusieurs lignes",
        ):
            MLDatasetLoader().load(manifest_path)


def test_loader_rejects_source_job_mismatch() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest_path, data_path = export_valid_dataset(root)

        lines = data_path.read_bytes().splitlines(keepends=True)
        first_payload = cast(
            dict[str, Any],
            json.loads(lines[0]),
        )
        first_payload["job_id"] = "other-job"
        lines[0] = canonical_json_line(first_payload)

        data_path.write_bytes(b"".join(lines))
        update_manifest_sha256(
            manifest_path,
            data_path,
        )

        with pytest.raises(
            MLDatasetLoadError,
            match="source_job_id",
        ):
            MLDatasetLoader().load(manifest_path)


def test_loader_rejects_feature_names_mismatch() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest_path, _ = export_valid_dataset(root)

        payload = manifest_payload(manifest_path)
        payload["feature_names"] = [
            "unexpected.feature",
        ]
        write_manifest(
            manifest_path,
            payload,
        )

        with pytest.raises(
            MLDatasetLoadError,
            match="feature_names",
        ):
            MLDatasetLoader().load(manifest_path)


def test_loader_rejects_row_count_mismatch() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest_path, _ = export_valid_dataset(root)

        payload = manifest_payload(manifest_path)
        payload["row_count"] = 3

        stats = cast(
            dict[str, Any],
            payload["stats"],
        )
        stats.update(
            {
                "source_rows": 3,
                "processed_rows": 3,
                "generated_rows": 3,
                "skipped_rows": 0,
                "censored_outcomes": 0,
                "invalid_outcomes": 0,
                "missing_natr": 0,
                "contract_rejections": 0,
                "rejection_reasons": {},
            }
        )

        write_manifest(
            manifest_path,
            payload,
        )

        with pytest.raises(
            MLDatasetLoadError,
            match="row_count",
        ):
            MLDatasetLoader().load(manifest_path)


def test_loader_accepts_v2_export() -> None:
    rows = (
        dataset_row(
            1,
            decision_time=BASE_TIME,
            feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
            profile_id=ML_DATASET_PROFILE_V2_ID,
            profile_fingerprint=V2_PROFILE_FINGERPRINT,
        ),
        dataset_row(
            2,
            decision_time=BASE_TIME + timedelta(hours=1),
            feature_name="feature.other",
            feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
            profile_id=ML_DATASET_PROFILE_V2_ID,
            profile_fingerprint=V2_PROFILE_FINGERPRINT,
        ),
    )

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)

        exported = MLDatasetExporter().export(
            build_result(
                rows,
                feature_schema_version=ML_FEATURE_SCHEMA_VERSION_V2,
            ),
            root,
            file_stem="loader-v2",
        )

        result = MLDatasetLoader().load(
            exported.manifest_path,
        )

        assert result.manifest.feature_schema_version == ML_FEATURE_SCHEMA_VERSION_V2
        assert result.manifest.profile_ids == [ML_DATASET_PROFILE_V2_ID]
        assert result.manifest.profile_fingerprints == [V2_PROFILE_FINGERPRINT]
        assert all(
            row.feature_schema_version == ML_FEATURE_SCHEMA_VERSION_V2 for row in result.rows
        )
        assert all(row.profile_id == ML_DATASET_PROFILE_V2_ID for row in result.rows)
        assert all(row.profile_fingerprint == V2_PROFILE_FINGERPRINT for row in result.rows)


def test_loader_rejects_feature_schema_mismatch() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest_path, _ = export_valid_dataset(root)

        payload = manifest_payload(manifest_path)
        payload["feature_schema_version"] = ML_FEATURE_SCHEMA_VERSION_V2
        write_manifest(
            manifest_path,
            payload,
        )

        with pytest.raises(
            MLDatasetLoadError,
            match="feature_schema_version",
        ):
            MLDatasetLoader().load(manifest_path)
