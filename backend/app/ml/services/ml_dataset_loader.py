"""Chargement vérifié des exports de datasets ML."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.ml.models.ml_dataset import MLDatasetRow
from app.ml.models.ml_dataset_export import MLDatasetExportManifest


class MLDatasetLoadError(ValueError):
    """Signale qu'un export ML est absent, corrompu ou incohérent."""


@dataclass(frozen=True, slots=True)
class MLDatasetLoadResult:
    """Dataset ML chargé avec son manifeste vérifié."""

    manifest_path: Path
    data_path: Path
    manifest: MLDatasetExportManifest
    rows: tuple[MLDatasetRow, ...]


def _load_manifest(
    manifest_path: Path,
) -> MLDatasetExportManifest:
    """Charge et valide le manifeste JSON."""
    try:
        payload = manifest_path.read_bytes()
    except OSError as exc:
        raise MLDatasetLoadError(f"impossible de lire le manifeste : {manifest_path}") from exc

    try:
        return MLDatasetExportManifest.model_validate_json(payload)
    except ValidationError as exc:
        raise MLDatasetLoadError(f"manifeste ML invalide : {manifest_path}") from exc


def _resolve_data_path(
    manifest_path: Path,
    data_file: str,
) -> Path:
    """Résout le JSONL sans autoriser de traversée de répertoire."""
    if (
        not data_file
        or data_file in {".", ".."}
        or "/" in data_file
        or "\\" in data_file
        or Path(data_file).is_absolute()
    ):
        raise MLDatasetLoadError("data_file doit être un nom de fichier simple")

    root = manifest_path.parent.resolve()
    data_path = (root / data_file).resolve()

    if data_path.parent != root:
        raise MLDatasetLoadError("data_file sort du dossier du manifeste")

    if not data_path.is_file():
        raise MLDatasetLoadError(f"fichier JSONL introuvable : {data_path}")

    return data_path


def _load_rows(
    data_path: Path,
) -> tuple[tuple[MLDatasetRow, ...], str]:
    """Charge les lignes et calcule le SHA-256 sur les octets exacts."""
    rows: list[MLDatasetRow] = []
    digest = hashlib.sha256()

    try:
        with data_path.open("rb") as data_file:
            for line_number, raw_line in enumerate(
                data_file,
                start=1,
            ):
                digest.update(raw_line)

                if not raw_line.strip():
                    raise MLDatasetLoadError("ligne JSONL vide à la ligne " f"{line_number}")

                if not raw_line.endswith(b"\n"):
                    raise MLDatasetLoadError(
                        "chaque ligne JSONL doit se terminer "
                        f"par un saut de ligne : ligne {line_number}"
                    )

                try:
                    row = MLDatasetRow.model_validate_json(raw_line)
                except ValidationError as exc:
                    raise MLDatasetLoadError(
                        "ligne ML invalide à la ligne " f"{line_number}"
                    ) from exc

                rows.append(row)
    except MLDatasetLoadError:
        raise
    except OSError as exc:
        raise MLDatasetLoadError(f"impossible de lire le JSONL : {data_path}") from exc

    return (
        tuple(rows),
        "sha256:" + digest.hexdigest(),
    )


def _validate_order(
    rows: tuple[MLDatasetRow, ...],
) -> None:
    """Vérifie l'ordre déterministe et l'unicité des observations."""
    previous_key: tuple[object, int] | None = None
    observation_ids: set[int] = set()

    for row in rows:
        key = (
            row.decision_time,
            row.observation_id,
        )

        if previous_key is not None and key < previous_key:
            raise MLDatasetLoadError(
                "les lignes JSONL ne sont pas triées par " "decision_time puis observation_id"
            )

        if row.observation_id in observation_ids:
            raise MLDatasetLoadError(
                "plusieurs lignes utilisent l'observation " f"{row.observation_id}"
            )

        observation_ids.add(row.observation_id)
        previous_key = key


def _validate_manifest_metadata(
    manifest: MLDatasetExportManifest,
    rows: tuple[MLDatasetRow, ...],
) -> None:
    """Compare les métadonnées calculées au manifeste."""
    if len(rows) != manifest.row_count:
        raise MLDatasetLoadError("row_count ne correspond pas au nombre de lignes JSONL")

    if any(row.feature_schema_version != manifest.feature_schema_version for row in rows):
        raise MLDatasetLoadError(
            "feature_schema_version du manifeste ne correspond pas " "à toutes les lignes JSONL"
        )

    if not rows:
        return

    if rows[0].decision_time != manifest.first_decision_time:
        raise MLDatasetLoadError("first_decision_time ne correspond pas au JSONL")

    if rows[-1].decision_time != manifest.last_decision_time:
        raise MLDatasetLoadError("last_decision_time ne correspond pas au JSONL")

    if any(row.job_id != manifest.source_job_id for row in rows):
        raise MLDatasetLoadError("source_job_id ne correspond pas à toutes les lignes")

    if any(row.horizon != manifest.horizon for row in rows):
        raise MLDatasetLoadError("horizon ne correspond pas à toutes les lignes")

    if any(
        not math.isclose(
            row.natr_multiplier,
            manifest.natr_multiplier,
            rel_tol=0,
            abs_tol=1e-12,
        )
        for row in rows
    ):
        raise MLDatasetLoadError("natr_multiplier ne correspond pas à toutes les lignes")

    feature_names = sorted({feature_name for row in rows for feature_name in row.features})
    algorithm_versions = sorted({row.source_algorithm_version for row in rows})
    dataset_versions = sorted({row.source_dataset_version for row in rows})
    profile_ids = sorted({row.profile_id for row in rows})
    profile_fingerprints = sorted(
        {row.profile_fingerprint for row in rows if row.profile_fingerprint is not None}
    )

    comparisons = (
        (
            "feature_names",
            feature_names,
            manifest.feature_names,
        ),
        (
            "source_algorithm_versions",
            algorithm_versions,
            manifest.source_algorithm_versions,
        ),
        (
            "source_dataset_versions",
            dataset_versions,
            manifest.source_dataset_versions,
        ),
        (
            "profile_ids",
            profile_ids,
            manifest.profile_ids,
        ),
        (
            "profile_fingerprints",
            profile_fingerprints,
            manifest.profile_fingerprints,
        ),
    )

    for name, calculated, declared in comparisons:
        if calculated != declared:
            raise MLDatasetLoadError(f"{name} ne correspond pas au contenu JSONL")


class MLDatasetLoader:
    """Charge un export ML et vérifie son intégrité complète."""

    def load(
        self,
        manifest_path: Path,
    ) -> MLDatasetLoadResult:
        """Charge le manifeste et le JSONL associé."""
        resolved_manifest_path = Path(manifest_path).resolve()

        if not resolved_manifest_path.is_file():
            raise MLDatasetLoadError("manifeste ML introuvable : " f"{resolved_manifest_path}")

        manifest = _load_manifest(resolved_manifest_path)
        data_path = _resolve_data_path(
            resolved_manifest_path,
            manifest.data_file,
        )
        rows, calculated_sha256 = _load_rows(data_path)

        if calculated_sha256 != manifest.data_sha256:
            raise MLDatasetLoadError("le SHA-256 du JSONL ne correspond pas au manifeste")

        _validate_order(rows)
        _validate_manifest_metadata(
            manifest,
            rows,
        )

        return MLDatasetLoadResult(
            manifest_path=resolved_manifest_path,
            data_path=data_path,
            manifest=manifest,
            rows=rows,
        )
