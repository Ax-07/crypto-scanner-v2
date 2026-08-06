"""CLI read-only d'audit structurel, statistique et causal d'un dataset ML v2."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Sequence

from app.core.config import BACKEND_ROOT, get_app_settings
from app.database.connection import Database
from app.ml.services.ml_dataset_auditor import (
    MLDatasetAuditor,
    audit_json_bytes,
    render_audit_markdown,
    write_audit_artifact,
)
from app.ml.services.ml_dataset_loader import MLDatasetLoader
from app.ml.services.ml_v2_source_verifier import MLV2SourceVerifier
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.candle_repository import CandleRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audite un manifeste de dataset ML v2.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--database-path", default=str(get_app_settings().database_path))
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    parser.add_argument("--minimum-rows", type=int, default=5_000)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BACKEND_ROOT / path


def _logical(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(BACKEND_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


async def run_cli(args: argparse.Namespace) -> int:
    manifest_path = _path(args.manifest)
    database_path = _path(args.database_path)
    output_json = _path(args.output_json)
    output_markdown = _path(args.output_markdown)
    minimum_rows = int(args.minimum_rows)
    if minimum_rows < 1:
        raise ValueError("--minimum-rows doit être positif")
    loaded = MLDatasetLoader().load(manifest_path)
    database = Database(database_path)
    backtests = BacktestRepository(database)
    candles = CandleRepository(database)
    try:
        verification = await MLV2SourceVerifier(backtests, candles).verify(loaded.manifest)
        report = await MLDatasetAuditor(minimum_rows=minimum_rows).audit(
            loaded,
            verification=verification,
            backtests=backtests,
            candles=candles,
        )
    finally:
        await database.close()
    json_bytes = audit_json_bytes(report)
    config = loaded.manifest.backtest_config
    assert config is not None
    symbol = config.symbols[0]
    timeframe = config.signal_config.timeframe
    start = config.start.isoformat().replace("+00:00", "Z")
    end = config.end.isoformat().replace("+00:00", "Z")
    artifact_directory = _logical(manifest_path.parent)
    commands = [
        "python -m app.ml.cli.inspect_ml_v2_history "
        f"{symbol} --database-path {_logical(database_path)} --output-json "
        f"{artifact_directory}/history-inventory.json",
        "python -m app.ml.cli.prepare_ml_v2_source "
        f"{symbol} --timeframe {timeframe} --start {start} --end {end} "
        f"--database-path {_logical(database_path)} --json",
        "python -m app.ml.cli.export_ml_dataset "
        f"{loaded.manifest.source_job_id} --feature-schema-version causal-features-v2 "
        f"--database-path {_logical(database_path)} --output-directory "
        f"{artifact_directory} --file-stem dataset",
        "python -m app.ml.cli.verify_ml_v2_source "
        f"{_logical(manifest_path)} --database-path {_logical(database_path)} --json",
        "python -m app.ml.cli.audit_ml_v2_dataset "
        f"{_logical(manifest_path)} --database-path {_logical(database_path)} "
        f"--output-json {_logical(output_json)} "
        f"--output-markdown {_logical(output_markdown)} --json",
    ]
    markdown_bytes = render_audit_markdown(report, commands).encode("utf-8")
    audit_sha256 = write_audit_artifact(output_json, json_bytes)
    markdown_sha256 = write_audit_artifact(output_markdown, markdown_bytes)
    payload = {
        "audit_json": _logical(output_json),
        "audit_json_sha256": audit_sha256,
        "audit_markdown": _logical(output_markdown),
        "audit_markdown_sha256": markdown_sha256,
        "blocking_failures": report.blocking_failures,
        "warnings": report.warnings,
        "conclusion": report.conclusion,
        "row_count": report.dataset["row_count"],
    }
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(f"Conclusion: {report.conclusion}")
        print(f"Audit JSON: {payload['audit_json']} ({audit_sha256})")
        print(f"Rapport: {payload['audit_markdown']} ({markdown_sha256})")
    if report.conclusion == "rejected":
        return 2
    if report.conclusion == "accepted_with_reservations":
        return 3
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return asyncio.run(run_cli(build_parser().parse_args(argv)))
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError) as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Échec global: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
