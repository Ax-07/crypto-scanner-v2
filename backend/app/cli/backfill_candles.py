"""CLI asynchrone de backfill et synchronisation OHLCV."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Sequence, cast

from app.core.config import BACKEND_ROOT, get_app_settings
from app.core.logging import configure_logging
from app.core.settings import PROJECT_TIMEFRAMES, ScanConfig
from app.database.connection import Database
from app.models.backfill import BackfillOptions, TargetResult
from app.repositories.backfill_repository import BackfillRepository
from app.repositories.candle_repository import CandleRepository
from app.repositories.market_repository import MarketRepository
from app.services.candle_backfill import CandleBackfillService
from app.services.candle_sync import CandleSyncService
from app.services.exchange import create_exchange
from app.services.market_catalog import MarketCatalogService


def build_parser() -> argparse.ArgumentParser:
    """Construit le contrat public de la commande."""
    settings = get_app_settings()
    parser = argparse.ArgumentParser(
        description=(
            "Backfill OHLCV SQLite. Simulation par défaut; --execute est requis "
            "pour télécharger et écrire des bougies."
        )
    )
    parser.add_argument("--exchange", default=settings.backfill_default_exchange)
    parser.add_argument("--market-type", default=settings.backfill_default_market_type)
    parser.add_argument("--quote", default=settings.backfill_default_quote)
    parser.add_argument("--symbols", default="all", choices=("all",))
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=list(settings.backfill_default_timeframes),
    )
    parser.add_argument("--timeframe", action="append", default=[])
    parser.add_argument("--from", dest="from_mode", default="earliest", choices=("earliest",))
    parser.add_argument("--from-date")
    parser.add_argument("--to-date")
    resume = parser.add_mutually_exclusive_group()
    resume.add_argument("--resume", action="store_true", default=True)
    resume.add_argument("--restart", action="store_true")
    parser.add_argument("--include-inactive", action="store_true")
    parser.add_argument("--max-concurrency", type=int, default=settings.backfill_max_concurrency)
    parser.add_argument("--page-limit", type=int, default=settings.backfill_page_limit)
    parser.add_argument("--max-retries", type=int, default=settings.backfill_max_retries)
    parser.add_argument("--retry-delay", type=float, default=settings.backfill_retry_delay_seconds)
    parser.add_argument(
        "--repair-gaps",
        action=argparse.BooleanOptionalAction,
        default=settings.backfill_repair_gaps,
    )
    parser.add_argument("--mode", choices=("backfill", "sync"), default="backfill")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--report-path")
    return parser


def _date_ms(value: str | None) -> int | None:
    """Convertit une date ISO en début de journée UTC."""
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1_000)


def options_from_args(args: argparse.Namespace) -> BackfillOptions:
    """Valide argparse et construit les options métier."""
    explicit = list(args.timeframe)
    if args.timeframes != ["all"]:
        explicit.extend(args.timeframes)
    timeframes = tuple(dict.fromkeys(explicit))
    unknown = set(timeframes) - set(PROJECT_TIMEFRAMES)
    if unknown:
        raise ValueError(f"Timeframes invalides: {sorted(unknown)}")
    if args.max_concurrency < 1 or args.max_concurrency > 20:
        raise ValueError("--max-concurrency doit être compris entre 1 et 20")
    if args.page_limit < 1 or args.page_limit > 1_500:
        raise ValueError("--page-limit doit être compris entre 1 et 1500")
    if args.max_retries < 0 or args.max_retries > 20:
        raise ValueError("--max-retries doit être compris entre 0 et 20")
    from_time = _date_ms(args.from_date)
    to_time = _date_ms(args.to_date)
    if from_time is not None and to_time is not None and from_time >= to_time:
        raise ValueError("--from-date doit précéder --to-date")
    return BackfillOptions(
        exchange_id=str(args.exchange).strip().lower(),
        market_type=str(args.market_type).strip().lower(),
        quote=str(args.quote).strip().upper(),
        symbols=tuple(str(item).strip().upper() for item in args.symbol),
        timeframes=timeframes,
        from_time=from_time,
        to_time=to_time,
        resume=not args.restart,
        restart=bool(args.restart),
        include_inactive=bool(args.include_inactive),
        max_concurrency=args.max_concurrency,
        page_limit=args.page_limit,
        max_retries=args.max_retries,
        retry_delay_seconds=args.retry_delay,
        progress_interval_seconds=get_app_settings().backfill_progress_interval_seconds,
        overlap_candles=get_app_settings().backfill_overlap_candles,
        repair_gaps=bool(args.repair_gaps),
        execute=bool(args.execute and not args.dry_run),
        mode=args.mode,
    )


async def _progress(done: int, total: int, result: TargetResult) -> None:
    """Affiche une ligne synthétique par cible, jamais par bougie."""
    print(
        f"[{done}/{total}] {result.symbol} {result.timeframe} | "
        f"{result.status.value} | {result.pages} pages | "
        f"{result.candles} bougies"
    )


async def run_cli(args: argparse.Namespace) -> int:
    """Initialise les dépendances, lance le service et ferme les ressources."""
    configure_logging()
    settings = get_app_settings()
    options = options_from_args(args)
    database = Database(settings.database_path)
    await database.initialize()
    candles = CandleRepository(database)
    states = BackfillRepository(database)
    catalog = MarketCatalogService(MarketRepository(database))
    sync = CandleSyncService(candles, settings)
    service = CandleBackfillService(candles, states, catalog, sync, settings.database_path)
    scan_config = ScanConfig(
        exchange_id=options.exchange_id,
        market_type=cast(Literal["spot", "swap", "future"], options.market_type),
        use_rsi=False,
        use_ma=False,
        use_macd=False,
        use_bollinger=False,
        use_stochastic=False,
        use_confluence_score=False,
    )
    exchange = create_exchange(scan_config)
    print(f"Base SQLite: {settings.database_path}")
    if settings.database_path.exists():
        print(f"Taille actuelle: {settings.database_path.stat().st_size} octets")
    free_space = shutil.disk_usage(settings.database_path.parent).free
    if free_space < 1024**3:
        print("AVERTISSEMENT: moins de 1 Gio d'espace disque disponible.")
    try:
        report = await service.run(exchange, options, _progress)
    finally:
        await exchange.close()
        await database.close()

    payload = report.as_dict()
    console_payload = {
        key: value for key, value in payload.items() if key not in {"results", "selected_symbols"}
    }
    console_payload["selected_symbol_count"] = len(report.selected_symbols)
    print(json.dumps(console_payload, ensure_ascii=True, indent=2))
    if args.report_path:
        report_path = Path(args.report_path)
        if not report_path.is_absolute():
            report_path = BACKEND_ROOT / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Rapport: {report_path}")
    if not options.execute:
        print("SIMULATION: aucune bougie OHLCV téléchargée ou modifiée.")
        print("Ajoutez --execute pour lancer le téléchargement réel.")
    failed_value = payload["failed_targets"]
    failed = failed_value if isinstance(failed_value, int) else 0
    return 1 if report.total_targets and failed == report.total_targets else 0


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée synchrone compatible avec ``python -m``."""
    parser = build_parser()
    try:
        return asyncio.run(run_cli(parser.parse_args(argv)))
    except KeyboardInterrupt:
        print(
            "\nInterruption propre. Reprendre avec "
            "python -m app.cli.backfill_candles --resume --execute",
            file=sys.stderr,
        )
        return 130
    except (ValueError, OSError) as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Échec global: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
