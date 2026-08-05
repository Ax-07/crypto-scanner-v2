"""CLI officielle de préparation du backtest source canonique ML v2."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal, Sequence, cast

from app.core.config import get_app_settings
from app.core.logging import configure_logging
from app.core.settings import PROJECT_TIMEFRAMES, Timeframe
from app.database.connection import Database
from app.ml.services.ml_v2_source import (
    MLV2SourceCoverageError,
    MLV2SourceService,
    build_ml_v2_source_config,
)
from app.models.backtest import BacktestStatus
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.candle_repository import CandleRepository
from app.services.backtest_manager import BacktestManager


def build_parser() -> argparse.ArgumentParser:
    settings = get_app_settings()
    parser = argparse.ArgumentParser(
        description="Crée, reprend ou retrouve le backtest source canonique ML v2."
    )
    parser.add_argument("symbol", help="Symbole BASE/QUOTE, par exemple BTC/USDC")
    parser.add_argument("--timeframe", required=True, choices=PROJECT_TIMEFRAMES)
    parser.add_argument("--start", required=True, help="Début ISO-8601 avec fuseau")
    parser.add_argument("--end", required=True, help="Fin ISO-8601 exclusive avec fuseau")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--market-type", default="spot", choices=("spot", "swap", "future"))
    parser.add_argument("--quote")
    parser.add_argument(
        "--database-path",
        type=Path,
        default=settings.database_path,
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Attend aussi un source déjà exécuté par un autre processus.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _datetime(value: str, option: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{option} doit être une date ISO-8601 valide") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{option} doit inclure un fuseau horaire")
    return parsed


def _human_output(payload: dict[str, object]) -> str:
    window = cast(dict[str, object], payload["window"])
    fingerprints = cast(dict[str, object], payload["fingerprints"])
    lines = [
        f"Action: {payload['action']}",
        f"Raison: {payload['reason']}",
        f"Job: {payload['job_id'] or '-'} ({payload['status'] or 'non créé'})",
        f"Source: {payload['symbol']} {payload['timeframe']}",
        f"Fenêtre: {window['start']} -> {window['end']}",
        f"Profil: {payload['signal_profile_id']}",
        f"Features: {payload['feature_schema_version']}",
        f"Horizons: {payload['horizons']}",
        f"Identité source: {fingerprints['source_identity']}",
        f"Fingerprint profil: {fingerprints['profile_fingerprint']}",
        f"Fingerprint portefeuille: {fingerprints['config_fingerprint'] or '-'}",
        f"Export immédiat: {'oui' if payload['can_export'] else 'non'}",
    ]
    return "\n".join(lines)


async def run_cli(args: argparse.Namespace) -> int:
    configure_logging()
    database_path = Path(args.database_path).resolve()
    if args.dry_run and not database_path.is_file():
        raise ValueError("--dry-run exige une base SQLite existante et ne la crée pas")

    config = build_ml_v2_source_config(
        symbol=str(args.symbol),
        timeframe=cast(Timeframe, args.timeframe),
        start=_datetime(str(args.start), "--start"),
        end=_datetime(str(args.end), "--end"),
        exchange_id=str(args.exchange),
        market_type=cast(Literal["spot", "swap", "future"], args.market_type),
        quote=str(args.quote) if args.quote else None,
    )
    database = Database(database_path)
    if not args.dry_run:
        await database.initialize()
    try:
        backtests = BacktestRepository(database)
        candles = CandleRepository(database)
        manager = BacktestManager(backtests, candles)
        result = await MLV2SourceService(backtests, candles, manager).prepare(
            config,
            dry_run=bool(args.dry_run),
            wait_for_running=bool(args.wait),
        )
    finally:
        await database.close()

    payload = result.as_dict()
    print(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
        if args.json_output
        else _human_output(payload)
    )
    if result.job is not None and result.job.status in {
        BacktestStatus.FAILED,
        BacktestStatus.CANCELLED,
        BacktestStatus.INTERRUPTED,
    }:
        if result.job.error:
            print(f"Erreur persistée: {result.job.error}", file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        return asyncio.run(run_cli(parser.parse_args(argv)))
    except KeyboardInterrupt:
        print("Préparation interrompue.", file=sys.stderr)
        return 130
    except MLV2SourceCoverageError as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        print(
            json.dumps(
                {"coverage": [item.as_dict() for item in exc.diagnostics]},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except (ValueError, OSError) as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Échec global: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
