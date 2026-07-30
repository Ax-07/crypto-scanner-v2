"""Audit reproductible, hors réseau, du portefeuille et de sa persistance SQLite."""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import math
import sys
import tempfile
import time
import tracemalloc
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.settings import ScanConfig
from app.database.connection import Database
from app.domain.portfolio import (
    EquityPoint,
    PortfolioSimulationConfig,
    PortfolioSimulationStep,
    simulate_portfolio,
)
from app.exporters.portfolio_csv import stream_equity_v1
from app.models.backtest import BacktestConfig, BacktestJob, BacktestStatus
from app.models.portfolio import PortfolioSimulationConfigV1
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.portfolio_repository import (
    PORTFOLIO_READ_BATCH_SIZE,
    PORTFOLIO_WRITE_BATCH_SIZE,
    PortfolioRepository,
)

START = datetime(2025, 1, 1, tzinfo=timezone.utc)
ZERO = Decimal("0")
CAPITAL = Decimal("10000")


def _steps(count: int) -> tuple[PortfolioSimulationStep, ...]:
    return tuple(
        PortfolioSimulationStep(
            observation_id=f"observation-{index:07d}",
            source_open_time=START + timedelta(minutes=index),
            decision_time=START + timedelta(minutes=index + 1),
            open_price=Decimal(10_000 + index % 170) / Decimal("100"),
            close_price=Decimal(10_005 + index % 170) / Decimal("100"),
            accepted=index % 4 in {1, 2},
        )
        for index in range(count)
    )


def _job(job_id: str, point_count: int) -> BacktestJob:
    return BacktestJob(
        id=job_id,
        status=BacktestStatus.COMPLETED,
        config=BacktestConfig(
            symbols=["BTC/USDC"],
            start=START,
            end=START + timedelta(minutes=max(2, point_count)),
            signal_config=ScanConfig(timeframe="1m"),
            portfolio_simulation=PortfolioSimulationConfigV1(quote_asset="USDC"),
        ),
    )


def _database_sizes(path: Path) -> dict[str, int]:
    return {
        "sqlite_bytes": path.stat().st_size if path.exists() else 0,
        "wal_bytes": (
            path.with_name(path.name + "-wal").stat().st_size
            if path.with_name(path.name + "-wal").exists()
            else 0
        ),
        "shm_bytes": (
            path.with_name(path.name + "-shm").stat().st_size
            if path.with_name(path.name + "-shm").exists()
            else 0
        ),
    }


async def _stream_equity_metrics(
    repository: PortfolioRepository,
    job_id: str,
    *,
    interrupt_after_first_batch: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    chunks = 0
    rows = 0
    byte_count = 0
    first_line = None
    last_line = None
    stream = stream_equity_v1(repository, job_id)
    try:
        async for chunk in stream:
            chunks += 1
            encoded = chunk.encode("utf-8")
            byte_count += len(encoded)
            lines = chunk.splitlines()
            rows += len(lines)
            if lines and first_line is None:
                first_line = lines[0]
            if lines:
                last_line = lines[-1]
            if interrupt_after_first_batch and chunks == 2:
                break
    finally:
        await cast(Any, stream).aclose()
    return {
        "seconds": round(time.perf_counter() - started, 3),
        "chunks": chunks,
        "csv_lines": rows,
        "bytes": byte_count,
        "first_line": first_line,
        "last_line": last_line,
    }


async def _persist_and_measure(
    *,
    database: Database,
    path: Path,
    job_id: str,
    result,
    export_full: bool,
) -> dict[str, Any]:
    jobs = BacktestRepository(database)
    await jobs.save_job(_job(job_id, len(result.equity_curve)))
    repository = PortfolioRepository(database)

    started = time.perf_counter()
    await repository.replace_simulation_result(
        job_id=job_id,
        result=result,
        config_fingerprint=f"sha256:{job_id}",
    )
    persistence_seconds = time.perf_counter() - started
    metadata = await repository.get_run_metadata(job_id)
    assert metadata is not None

    page_offset = min(123, max(0, metadata.equity_point_count - 1))
    started = time.perf_counter()
    raw_page = await repository.list_equity_points(
        job_id=job_id,
        offset=page_offset,
        limit=1_000,
    )
    page_seconds = time.perf_counter() - started
    started = time.perf_counter()
    sampled = await repository.sample_equity_points(job_id=job_id, max_points=1_000)
    sample_seconds = time.perf_counter() - started
    assert len(raw_page.items) <= 1_000
    assert len(sampled.items) <= 1_000
    assert sampled.items[0].sequence == 0
    assert sampled.items[-1].sequence == metadata.equity_point_count - 1

    interrupted = await _stream_equity_metrics(
        repository,
        job_id,
        interrupt_after_first_batch=True,
    )
    after_interrupt = await repository.list_equity_points(job_id=job_id, offset=0, limit=1)
    assert after_interrupt.total == metadata.equity_point_count
    export = await _stream_equity_metrics(repository, job_id) if export_full else {"skipped": True}

    restarted = PortfolioRepository(Database(path))
    restart_metadata = await restarted.get_run_metadata(job_id)
    restart_page = await restarted.list_equity_points(job_id=job_id, offset=0, limit=1)
    assert restart_metadata == metadata
    assert restart_page.items[0].point == result.equity_curve[0]

    async with database.connection() as connection:
        cursor = await connection.execute("PRAGMA journal_mode")
        journal_row = await cursor.fetchone()
    sizes_before_delete = _database_sizes(path)
    assert await jobs.delete_job(job_id)
    assert await repository.get_run_metadata(job_id) is None

    counts = (
        len(result.orders),
        len(result.executions),
        len(result.trades),
        len(result.equity_curve),
    )
    return {
        "orders": counts[0],
        "executions": counts[1],
        "trades": counts[2],
        "equity_points": counts[3],
        "write_batches": sum(
            math.ceil(count / PORTFOLIO_WRITE_BATCH_SIZE) for count in counts if count
        ),
        "read_batch_size": PORTFOLIO_READ_BATCH_SIZE,
        "persistence_seconds": round(persistence_seconds, 3),
        "raw_page_seconds": round(page_seconds, 3),
        "raw_page_items": len(raw_page.items),
        "sample_seconds": round(sample_seconds, 3),
        "sample_items": len(sampled.items),
        "interrupted_export": interrupted,
        "full_export": export,
        "journal_mode": str(journal_row[0]) if journal_row else "unknown",
        **sizes_before_delete,
        "deleted_without_vacuum": True,
    }


async def _simulation_case(
    database: Database,
    path: Path,
    *,
    name: str,
    point_count: int,
    export_full: bool,
) -> dict[str, Any]:
    tracemalloc.start()
    started = time.perf_counter()
    steps = _steps(point_count)
    result = simulate_portfolio(
        symbol="BTC/USDC",
        steps=steps,
        config=PortfolioSimulationConfig(
            quote_asset="USDC",
            initial_capital=CAPITAL,
            fee_rate=Decimal("0.001"),
            slippage_rate=Decimal("0.0005"),
        ),
    )
    simulation_seconds = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    persistence = await _persist_and_measure(
        database=database,
        path=path,
        job_id=name,
        result=result,
        export_full=export_full,
    )
    return {
        "kind": "engine_and_persistence",
        "candles": point_count,
        "simulation_seconds": round(simulation_seconds, 3),
        "simulation_peak_bytes_indicative": peak,
        **persistence,
    }


async def _large_persistence_case(
    database: Database,
    path: Path,
    *,
    point_count: int,
) -> dict[str, Any]:
    base = simulate_portfolio(
        symbol="BTC/USDC",
        steps=_steps(2),
        config=PortfolioSimulationConfig(quote_asset="USDC", initial_capital=CAPITAL),
    )
    tracemalloc.start()
    started = time.perf_counter()
    points = tuple(
        EquityPoint(
            timestamp=START + timedelta(minutes=sequence),
            cash=CAPITAL,
            position_value=ZERO,
            equity=CAPITAL,
            realized_pnl_cumulative=ZERO,
            unrealized_pnl=ZERO,
            fees_cumulative=ZERO,
            drawdown_ratio=ZERO,
            exposed=False,
        )
        for sequence in range(point_count)
    )
    generation_seconds = time.perf_counter() - started
    result = replace(base, equity_curve=points)
    persistence = await _persist_and_measure(
        database=database,
        path=path,
        job_id="large-persistence",
        result=result,
        export_full=True,
    )
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del points, result
    gc.collect()
    return {
        "kind": "synthetic_persistence_only",
        "candles": None,
        "generation_seconds": round(generation_seconds, 3),
        "generation_and_persistence_peak_bytes_indicative": peak,
        **persistence,
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="portfolio-audit-") as temporary:
        path = Path(temporary) / "portfolio-audit.sqlite3"
        database = Database(path)
        await database.initialize()
        started = time.perf_counter()
        small = await _simulation_case(
            database,
            path,
            name="small",
            point_count=args.small_points,
            export_full=True,
        )
        medium = await _simulation_case(
            database,
            path,
            name="medium",
            point_count=args.medium_points,
            export_full=True,
        )
        large = await _large_persistence_case(
            database,
            path,
            point_count=args.large_points,
        )
        await database.close()
        return {
            "environment": {
                "temporary_sqlite": True,
                "network": False,
                "write_batch_size": PORTFOLIO_WRITE_BATCH_SIZE,
                "read_batch_size": PORTFOLIO_READ_BATCH_SIZE,
            },
            "small": small,
            "medium": medium,
            "large": large,
            "total_seconds": round(time.perf_counter() - started, 3),
            "temporary_files_cleaned": True,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--small-points", type=int, default=300)
    parser.add_argument("--medium-points", type=int, default=10_000)
    parser.add_argument("--large-points", type=int, default=500_000)
    args = parser.parse_args()
    if args.small_points < 2 or args.medium_points < 2 or args.large_points < 4:
        parser.error("les volumes doivent être respectivement >= 2, >= 2 et >= 4")
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
