"""CLI d'export reproductible d'un dataset ML causal."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from app.core.config import BACKEND_ROOT, get_app_settings
from app.core.logging import configure_logging
from app.database.connection import Database
from app.repositories.backtest_repository import BacktestRepository
from app.services.ml_dataset_builder import MLDatasetBuilder
from app.services.ml_dataset_exporter import MLDatasetExporter


@dataclass(frozen=True, slots=True)
class ExportMLDatasetOptions:
    """Options validées indépendantes d'argparse."""

    job_id: str
    database_path: Path
    output_directory: Path
    batch_size: int
    natr_multiplier: float
    file_stem: str | None


def build_parser() -> argparse.ArgumentParser:
    """Construit le contrat public de la commande."""
    settings = get_app_settings()

    parser = argparse.ArgumentParser(
        description=(
            "Construit et exporte un dataset ML causal depuis un " "backtest SQLite terminé."
        )
    )
    parser.add_argument(
        "job_id",
        help="Identifiant du backtest source terminé.",
    )
    parser.add_argument(
        "--database-path",
        default=str(settings.database_path),
        help=("Chemin de la base SQLite. Utilise la configuration " "de l'application par défaut."),
    )
    parser.add_argument(
        "--output-directory",
        default="artifacts/ml-datasets",
        help=(
            "Dossier de destination. Un chemin relatif est résolu " "depuis la racine du backend."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1_000,
        help="Nombre de couples observation/outcome chargés par lot.",
    )
    parser.add_argument(
        "--natr-multiplier",
        type=float,
        default=1.0,
        help=("Multiplicateur appliqué au NATR pour définir " "la zone neutre."),
    )
    parser.add_argument(
        "--file-stem",
        help=("Nom de base optionnel des fichiers, sans extension. " "Par défaut : <job_id>.h6."),
    )

    return parser


def _backend_path(value: str) -> Path:
    """Résout un chemin relatif depuis la racine du backend."""
    path = Path(value.strip())

    if not path.is_absolute():
        path = BACKEND_ROOT / path

    return path


def options_from_args(
    args: argparse.Namespace,
) -> ExportMLDatasetOptions:
    """Valide argparse et construit les options métier."""
    job_id = str(args.job_id).strip()

    if not job_id:
        raise ValueError("job_id ne peut pas être vide")

    database_value = str(args.database_path).strip()

    if not database_value:
        raise ValueError("--database-path ne peut pas être vide")

    database_path = _backend_path(database_value)

    if not database_path.exists():
        raise ValueError(f"Base SQLite introuvable : {database_path}")

    if not database_path.is_file():
        raise ValueError(f"Le chemin SQLite n'est pas un fichier : {database_path}")

    output_value = str(args.output_directory).strip()

    if not output_value:
        raise ValueError("--output-directory ne peut pas être vide")

    output_directory = _backend_path(output_value)

    batch_size = int(args.batch_size)

    if batch_size < 1 or batch_size > 100_000:
        raise ValueError("--batch-size doit être compris entre 1 et 100000")

    natr_multiplier = float(args.natr_multiplier)

    if not math.isfinite(natr_multiplier) or natr_multiplier <= 0 or natr_multiplier > 10:
        raise ValueError(
            "--natr-multiplier doit être fini, supérieur à zéro " "et inférieur ou égal à 10"
        )

    raw_file_stem = args.file_stem
    file_stem = str(raw_file_stem).strip() if raw_file_stem is not None else None

    if file_stem == "":
        raise ValueError("--file-stem ne peut pas être vide")

    return ExportMLDatasetOptions(
        job_id=job_id,
        database_path=database_path,
        output_directory=output_directory,
        batch_size=batch_size,
        natr_multiplier=natr_multiplier,
        file_stem=file_stem,
    )


async def run_cli(
    args: argparse.Namespace,
) -> int:
    """Construit le dataset, l'exporte et ferme SQLite."""
    configure_logging()
    options = options_from_args(args)

    database = Database(options.database_path)
    await database.initialize()

    try:
        repository = BacktestRepository(database)
        builder = MLDatasetBuilder(repository)

        build_result = await builder.build(
            options.job_id,
            batch_size=options.batch_size,
            natr_multiplier=options.natr_multiplier,
        )

        export_result = MLDatasetExporter().export(
            build_result,
            options.output_directory,
            file_stem=options.file_stem,
        )
    finally:
        await database.close()

    manifest = export_result.manifest

    console_payload = {
        "source_job_id": manifest.source_job_id,
        "horizon": manifest.horizon,
        "natr_multiplier": manifest.natr_multiplier,
        "data_path": str(export_result.data_path),
        "manifest_path": str(export_result.manifest_path),
        "data_sha256": manifest.data_sha256,
        "row_count": manifest.row_count,
        "first_decision_time": (
            manifest.first_decision_time.isoformat()
            if manifest.first_decision_time is not None
            else None
        ),
        "last_decision_time": (
            manifest.last_decision_time.isoformat()
            if manifest.last_decision_time is not None
            else None
        ),
        "feature_count": len(manifest.feature_names),
        "stats": manifest.stats.model_dump(mode="json"),
    }

    print(
        json.dumps(
            console_payload,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """Point d'entrée synchrone compatible avec ``python -m``."""
    parser = build_parser()

    try:
        return asyncio.run(run_cli(parser.parse_args(argv)))
    except KeyboardInterrupt:
        print(
            "\nExport interrompu.",
            file=sys.stderr,
        )
        return 130
    except (ValueError, OSError) as exc:
        print(
            f"Erreur : {exc}",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:
        print(
            f"Échec global : {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
