"""Export déterministe et atomique des datasets ML au format JSONL."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.models.ml_dataset import MLDatasetRow
from app.models.ml_dataset_export import (
    MLDatasetExportManifest,
    MLDatasetExportStats,
)
from app.services.ml_dataset_builder import MLDatasetBuildResult


@dataclass(frozen=True, slots=True)
class MLDatasetExportResult:
    """Chemins et manifeste produits par un export."""

    data_path: Path
    manifest_path: Path
    manifest: MLDatasetExportManifest


def _canonical_json_bytes(
    payload: object,
) -> bytes:
    """Sérialise un objet en JSON canonique terminé par une nouvelle ligne."""
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return (serialized + "\n").encode("utf-8")


def _safe_file_stem(
    value: str,
) -> str:
    """Normalise un identifiant en nom de fichier portable."""
    normalized = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in value.strip()
    )
    normalized = normalized.strip("._")

    if not normalized:
        raise ValueError("file_stem doit contenir au moins un caractère utilisable")

    return normalized


def _ordered_rows(
    rows: tuple[MLDatasetRow, ...],
) -> tuple[MLDatasetRow, ...]:
    """Trie les lignes chronologiquement et refuse les doublons."""
    ordered = tuple(
        sorted(
            rows,
            key=lambda row: (
                row.decision_time,
                row.observation_id,
            ),
        )
    )

    seen_observations: set[int] = set()

    for row in ordered:
        if row.observation_id in seen_observations:
            raise ValueError(
                "le dataset contient plusieurs lignes pour " f"l'observation {row.observation_id}"
            )

        seen_observations.add(row.observation_id)

    return ordered


def _export_stats(
    result: MLDatasetBuildResult,
) -> MLDatasetExportStats:
    """Convertit le rapport interne en contrat public d'export."""
    report = result.report

    return MLDatasetExportStats(
        source_rows=report.source_rows,
        processed_rows=report.processed_rows,
        generated_rows=report.generated_rows,
        skipped_rows=report.skipped_rows,
        censored_outcomes=report.censored_outcomes,
        invalid_outcomes=report.invalid_outcomes,
        missing_natr=report.missing_natr,
        contract_rejections=report.contract_rejections,
        batch_count=report.batch_count,
        rejection_reasons=report.rejection_reasons,
    )


class MLDatasetExporter:
    """Écrit un dataset JSONL et son manifeste reproductible."""

    def export(
        self,
        result: MLDatasetBuildResult,
        output_directory: Path,
        *,
        file_stem: str | None = None,
    ) -> MLDatasetExportResult:
        """Exporte le résultat de construction dans deux fichiers.

        Chaque fichier est d'abord entièrement écrit dans un fichier
        temporaire situé dans le même répertoire, puis remplacé atomiquement.
        """
        ordered_rows = _ordered_rows(result.rows)

        if len(ordered_rows) != result.report.generated_rows:
            raise ValueError("le nombre de lignes ne correspond pas " "à report.generated_rows")

        destination = Path(output_directory)
        destination.mkdir(
            parents=True,
            exist_ok=True,
        )

        default_stem = f"{result.job_id}.h{result.horizon}"
        normalized_stem = _safe_file_stem(file_stem if file_stem is not None else default_stem)

        data_path = destination / (f"{normalized_stem}.jsonl")
        manifest_path = destination / (f"{normalized_stem}.manifest.json")

        temporary_token = uuid4().hex
        temporary_data_path = destination / (f".{data_path.name}.{temporary_token}.tmp")
        temporary_manifest_path = destination / (f".{manifest_path.name}.{temporary_token}.tmp")

        try:
            data_digest = hashlib.sha256()

            with temporary_data_path.open("xb") as data_file:
                for row in ordered_rows:
                    row_bytes = _canonical_json_bytes(
                        row.model_dump(
                            mode="json",
                        )
                    )
                    data_file.write(row_bytes)
                    data_digest.update(row_bytes)

            data_sha256 = "sha256:" + data_digest.hexdigest()

            feature_names = sorted(
                {feature_name for row in ordered_rows for feature_name in row.features}
            )

            source_algorithm_versions = sorted(
                {row.source_algorithm_version for row in ordered_rows}
            )
            source_dataset_versions = sorted({row.source_dataset_version for row in ordered_rows})
            profile_ids = sorted({row.profile_id for row in ordered_rows})
            profile_fingerprints = sorted(
                {
                    row.profile_fingerprint
                    for row in ordered_rows
                    if row.profile_fingerprint is not None
                }
            )

            first_decision_time = ordered_rows[0].decision_time if ordered_rows else None
            last_decision_time = ordered_rows[-1].decision_time if ordered_rows else None

            manifest = MLDatasetExportManifest(
                source_job_id=result.job_id,
                horizon=result.horizon,
                natr_multiplier=result.natr_multiplier,
                data_file=data_path.name,
                data_sha256=data_sha256,
                row_count=len(ordered_rows),
                first_decision_time=first_decision_time,
                last_decision_time=last_decision_time,
                feature_names=feature_names,
                source_algorithm_versions=(source_algorithm_versions),
                source_dataset_versions=(source_dataset_versions),
                profile_ids=profile_ids,
                profile_fingerprints=(profile_fingerprints),
                stats=_export_stats(result),
            )

            manifest_bytes = _canonical_json_bytes(
                manifest.model_dump(
                    mode="json",
                )
            )

            with temporary_manifest_path.open("xb") as manifest_file:
                manifest_file.write(manifest_bytes)

            temporary_data_path.replace(data_path)
            temporary_manifest_path.replace(manifest_path)

            return MLDatasetExportResult(
                data_path=data_path,
                manifest_path=manifest_path,
                manifest=manifest,
            )
        finally:
            temporary_data_path.unlink(missing_ok=True)
            temporary_manifest_path.unlink(missing_ok=True)
