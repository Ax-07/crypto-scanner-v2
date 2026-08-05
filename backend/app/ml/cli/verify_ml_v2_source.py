"""CLI sans écriture de vérification d'un manifeste ML v2."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Sequence

from app.core.config import get_app_settings
from app.core.logging import configure_logging
from app.database.connection import Database
from app.ml.services.ml_dataset_loader import MLDatasetLoader
from app.ml.services.ml_v2_source_verifier import MLV2SourceVerifier
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.candle_repository import CandleRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Vérifie un manifeste ML v2 et ses entrées OHLCV sans écriture."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--database-path", type=Path, default=get_app_settings().database_path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


async def run_cli(args: argparse.Namespace) -> int:
    configure_logging()
    database_path = Path(args.database_path).resolve()
    if not database_path.is_file():
        raise ValueError("la base SQLite candidate est introuvable")
    loaded = MLDatasetLoader().load(Path(args.manifest))
    database = Database(database_path)
    try:
        result = await MLV2SourceVerifier(
            BacktestRepository(database), CandleRepository(database)
        ).verify(loaded.manifest)
    finally:
        await database.close()
    payload = result.as_dict()
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(f"Statut: {payload['status']}")
        print(f"Raison: {payload['reason']}")
        print(f"Attendu: {payload['expected_input_data_fingerprint']}")
        print(f"Calculé: {payload['calculated_input_data_fingerprint']}")
        for stream in payload["divergent_streams"]:
            print(f"- {stream['role']} {stream['timeframe']}: {stream['type']}")
    return 0 if result.reproducible else 2


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return asyncio.run(run_cli(build_parser().parse_args(argv)))
    except KeyboardInterrupt:
        print("Vérification interrompue.", file=sys.stderr)
        return 130
    except (ValueError, OSError) as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Échec global: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
