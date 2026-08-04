"""Export déterministe et immuable des benchmarks ML."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.ml.models.ml_benchmark import (
    MLBenchmarkReport,
)


class MLBenchmarkExportError(ValueError):
    """Signale qu'un benchmark ne peut pas être exporté."""


@dataclass(frozen=True, slots=True)
class MLBenchmarkExportResult:
    """Résultat de l'export d'un benchmark."""

    report_path: Path
    report_sha256: str
    byte_count: int
    reused_existing_file: bool

    def to_dict(self) -> dict[str, object]:
        """Retourne une représentation JSON-compatible."""
        return {
            "report_path": str(self.report_path),
            "report_sha256": (self.report_sha256),
            "byte_count": self.byte_count,
            "reused_existing_file": (self.reused_existing_file),
        }


def _validate_file_stem(
    file_stem: str,
) -> str:
    """Valide un nom de fichier sans extension."""
    if not isinstance(
        file_stem,
        str,
    ):
        raise MLBenchmarkExportError("file_stem doit être une chaîne")

    normalized = file_stem.strip()

    if not normalized:
        raise MLBenchmarkExportError("file_stem ne peut pas être vide")

    if normalized != file_stem:
        raise MLBenchmarkExportError("file_stem ne peut pas commencer " "ou finir par un espace")

    if (
        normalized
        in {
            ".",
            "..",
        }
        or Path(normalized).is_absolute()
        or Path(normalized).name != normalized
        or "/" in normalized
        or "\\" in normalized
    ):
        raise MLBenchmarkExportError("file_stem doit être un nom simple")

    if normalized.endswith("."):
        raise MLBenchmarkExportError("file_stem ne peut pas finir " "par un point")

    if any(ord(character) < 32 for character in normalized):
        raise MLBenchmarkExportError("file_stem contient un caractère " "de contrôle interdit")

    return normalized


def _canonical_report_bytes(
    report: MLBenchmarkReport,
) -> bytes:
    """Sérialise le benchmark dans un JSON canonique."""
    payload = report.model_dump(mode="json")

    try:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            allow_nan=False,
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise MLBenchmarkExportError(
            "le benchmark ne peut pas être " "sérialisé en JSON canonique"
        ) from exc

    return (serialized + "\n").encode("utf-8")


def _sha256(
    payload: bytes,
) -> str:
    """Calcule le SHA-256 avec son préfixe."""
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _ensure_output_directory(
    output_directory: Path,
) -> Path:
    """Crée et vérifie le dossier de destination."""
    resolved = Path(output_directory).resolve()

    try:
        resolved.mkdir(
            parents=True,
            exist_ok=True,
        )
    except OSError as exc:
        raise MLBenchmarkExportError(
            "impossible de créer le dossier " f"d'export : {resolved}"
        ) from exc

    if not resolved.is_dir():
        raise MLBenchmarkExportError("le chemin d'export n'est pas " f"un dossier : {resolved}")

    return resolved


def _read_existing_file(
    path: Path,
) -> bytes:
    """Lit un benchmark déjà présent."""
    try:
        return path.read_bytes()
    except OSError as exc:
        raise MLBenchmarkExportError(
            "impossible de lire le benchmark " f"existant : {path}"
        ) from exc


def _atomic_write(
    path: Path,
    payload: bytes,
) -> None:
    """Écrit un nouveau fichier via un fichier temporaire."""
    temporary_path: Path | None = None

    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)

        with os.fdopen(
            descriptor,
            "wb",
        ) as temporary_file:
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        if path.exists():
            existing_payload = _read_existing_file(path)

            if existing_payload == payload:
                return

            raise MLBenchmarkExportError(
                "le benchmark existe déjà avec " f"un contenu différent : {path}"
            )

        os.replace(
            temporary_path,
            path,
        )
        temporary_path = None

    except MLBenchmarkExportError:
        raise
    except OSError as exc:
        raise MLBenchmarkExportError("impossible d'écrire le benchmark : " f"{path}") from exc
    finally:
        if temporary_path is not None and temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass


class MLBenchmarkExporter:
    """Exporte un benchmark sous une forme déterministe."""

    def export(
        self,
        report: MLBenchmarkReport,
        output_directory: Path,
        *,
        file_stem: str,
    ) -> MLBenchmarkExportResult:
        """Écrit le benchmark sans écrasement silencieux."""
        normalized_file_stem = _validate_file_stem(file_stem)
        resolved_directory = _ensure_output_directory(output_directory)
        report_path = resolved_directory / (normalized_file_stem + ".benchmark.json")
        payload = _canonical_report_bytes(report)
        report_sha256 = _sha256(payload)

        reused_existing_file = False

        if report_path.exists():
            existing_payload = _read_existing_file(report_path)

            if existing_payload != payload:
                raise MLBenchmarkExportError(
                    "le benchmark existe déjà avec " "un contenu différent : " f"{report_path}"
                )

            reused_existing_file = True
        else:
            _atomic_write(
                report_path,
                payload,
            )

        return MLBenchmarkExportResult(
            report_path=report_path,
            report_sha256=report_sha256,
            byte_count=len(payload),
            reused_existing_file=(reused_existing_file),
        )
