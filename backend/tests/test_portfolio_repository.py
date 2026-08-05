from __future__ import annotations

import asyncio
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.database.connection import Database
from app.database.schema import SCHEMA_VERSION
from app.domain.portfolio import (
    EquityPoint,
    PortfolioSimulationConfig,
    PortfolioSimulationStep,
    simulate_portfolio,
)
from app.models.backtest import BacktestConfig, BacktestJob
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.portfolio_repository import (
    PORTFOLIO_SCHEMA_VERSION,
    PortfolioPersistenceError,
    PortfolioRepository,
)
from tests.test_backtesting_domain import signal_config

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _steps(count: int = 6) -> list[PortfolioSimulationStep]:
    accepted = [True, False, False, True, True, True][:count]
    opens = ["90", "100", "110", "110", "110", "99"][:count]
    return [
        PortfolioSimulationStep(
            observation_id=f"observation-{index + 1:06d}",
            source_open_time=START + timedelta(hours=index),
            decision_time=START + timedelta(hours=index + 1),
            open_price=Decimal(opens[index]),
            close_price=Decimal(opens[index]),
            accepted=accepted[index],
        )
        for index in range(count)
    ]


def _result():
    return simulate_portfolio(
        symbol="BTC/USDC",
        steps=_steps(),
        config=PortfolioSimulationConfig(
            quote_asset="USDC",
            initial_capital=Decimal("1000.0000000000000000001"),
            fee_rate=Decimal("0.0000000000000000001"),
        ),
    )


def _job(job_id: str) -> BacktestJob:
    return BacktestJob(
        id=job_id,
        config=BacktestConfig(
            symbols=["BTC/USDC"],
            start=START,
            end=START + timedelta(hours=6),
            signal_config=signal_config(),
            portfolio_simulation={"quote_asset": "USDC"},
        ),
    )


@pytest.mark.asyncio
async def test_migration_8_is_idempotent_and_enables_real_foreign_keys() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "schema.sqlite3")
        await database.initialize()
        await database.initialize()
        async with database.connection() as connection:
            cursor = await connection.execute("""
                SELECT name, type FROM sqlite_master
                WHERE name LIKE 'backtest_portfolio_%'
                   OR name LIKE 'idx_portfolio_%'
                ORDER BY name
                """)
            objects = {(row["name"], row["type"]) for row in await cursor.fetchall()}
            version_cursor = await connection.execute("SELECT MAX(version) FROM schema_migrations")
            version = await version_cursor.fetchone()
            foreign_keys_cursor = await connection.execute("PRAGMA foreign_keys")
            foreign_keys = await foreign_keys_cursor.fetchone()
        assert SCHEMA_VERSION == 9
        assert version is not None and version[0] == 9
        assert foreign_keys is not None and foreign_keys[0] == 1
        assert {
            ("backtest_portfolio_runs", "table"),
            ("backtest_portfolio_orders", "table"),
            ("backtest_portfolio_executions", "table"),
            ("backtest_portfolio_trades", "table"),
            ("backtest_portfolio_equity", "table"),
            ("idx_portfolio_executions_order", "index"),
            ("idx_portfolio_equity_time", "index"),
        } <= objects


@pytest.mark.asyncio
async def test_replace_reconstructs_exactly_and_survives_new_repository() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "restart.sqlite3")
        await database.initialize()
        jobs = BacktestRepository(database)
        await jobs.save_job(_job("restart"))
        expected = _result()
        first = PortfolioRepository(database)
        await first.replace_simulation_result(
            job_id="restart",
            result=expected,
            config_fingerprint="sha256:test",
        )
        metadata = await first.get_run_metadata("restart")
        assert metadata is not None
        assert metadata.schema_version == PORTFOLIO_SCHEMA_VERSION
        assert metadata.order_count == len(expected.orders)
        assert metadata.execution_count == len(expected.executions)
        assert metadata.trade_count == len(expected.trades)
        assert metadata.equity_point_count == len(expected.equity_curve)
        restored = await PortfolioRepository(
            Database(Path(temporary) / "restart.sqlite3")
        ).load_portfolio_simulation_result("restart")
        assert restored == expected


@pytest.mark.asyncio
async def test_replace_is_idempotent_and_pages_are_stable() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "pages.sqlite3")
        await database.initialize()
        await BacktestRepository(database).save_job(_job("pages"))
        repository = PortfolioRepository(database)
        result = _result()
        for _ in range(2):
            await repository.replace_simulation_result(
                job_id="pages",
                result=result,
                config_fingerprint="sha256:test",
            )
        first = await repository.list_trades(job_id="pages", offset=0, limit=1)
        second = await repository.list_trades(job_id="pages", offset=1, limit=1)
        beyond = await repository.list_trades(job_id="pages", offset=999, limit=1)
        assert first.total == second.total == len(result.trades)
        assert [item.sequence for item in (*first.items, *second.items)] == [0, 1]
        assert beyond.items == ()
        equity = await repository.list_equity_points(job_id="pages", offset=1, limit=2)
        assert [item.sequence for item in equity.items] == [1, 2]
        assert equity.total == len(result.equity_curve)


@pytest.mark.asyncio
async def test_failed_replacement_rolls_back_and_preserves_previous_run() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "rollback.sqlite3")
        await database.initialize()
        await BacktestRepository(database).save_job(_job("rollback"))
        repository = PortfolioRepository(database)
        expected = _result()
        await repository.replace_simulation_result(
            job_id="rollback",
            result=expected,
            config_fingerprint="sha256:test",
        )
        invalid = replace(expected, orders=(expected.orders[0], expected.orders[0]))
        with pytest.raises(PortfolioPersistenceError):
            await repository.replace_simulation_result(
                job_id="rollback",
                result=invalid,
                config_fingerprint="sha256:invalid",
            )
        assert await repository.load_portfolio_simulation_result("rollback") == expected


@pytest.mark.asyncio
async def test_cancelled_batched_replacement_rolls_back_completely() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "cancelled-write.sqlite3")
        await database.initialize()
        await BacktestRepository(database).save_job(_job("cancelled-write"))
        repository = PortfolioRepository(database)
        expected = _result()
        await repository.replace_simulation_result(
            job_id="cancelled-write",
            result=expected,
            config_fingerprint="sha256:before-cancellation",
        )
        points = tuple(
            EquityPoint(
                timestamp=START + timedelta(minutes=sequence),
                cash=Decimal("1000"),
                position_value=Decimal("0"),
                equity=Decimal("1000"),
                realized_pnl_cumulative=Decimal("0"),
                unrealized_pnl=Decimal("0"),
                fees_cumulative=Decimal("0"),
                drawdown_ratio=Decimal("0"),
                exposed=False,
            )
            for sequence in range(2_001)
        )
        checks = 0

        def cancellation_requested() -> bool:
            nonlocal checks
            checks += 1
            return checks == 2

        with pytest.raises(asyncio.CancelledError):
            await repository.replace_simulation_result(
                job_id="cancelled-write",
                result=replace(expected, equity_curve=points),
                config_fingerprint="sha256:cancelled",
                cancellation_requested=cancellation_requested,
            )
        assert await repository.load_portfolio_simulation_result("cancelled-write") == expected


@pytest.mark.asyncio
async def test_sampling_preserves_real_extrema_and_is_deterministic() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "sample.sqlite3")
        await database.initialize()
        await BacktestRepository(database).save_job(_job("sample"))
        repository = PortfolioRepository(database)
        original = _result()
        points = []
        for sequence in range(100):
            equity = Decimal("2000") if sequence == 37 else Decimal(1000 + sequence)
            drawdown = Decimal("0.9") if sequence == 63 else Decimal(sequence) / Decimal("1000")
            points.append(
                EquityPoint(
                    timestamp=START + timedelta(minutes=sequence),
                    cash=equity,
                    position_value=Decimal("0"),
                    equity=equity,
                    realized_pnl_cumulative=equity - Decimal("1000"),
                    unrealized_pnl=Decimal("0"),
                    fees_cumulative=Decimal("0"),
                    drawdown_ratio=drawdown,
                    exposed=False,
                )
            )
        result = replace(original, equity_curve=tuple(points))
        await repository.replace_simulation_result(
            job_id="sample",
            result=result,
            config_fingerprint="sha256:test",
        )
        first = await repository.sample_equity_points(job_id="sample", max_points=12)
        second = await repository.sample_equity_points(job_id="sample", max_points=12)
        sequences = [item.sequence for item in first.items]
        assert first == second
        assert len(sequences) <= 12
        assert sequences == sorted(sequences)
        assert {0, 37, 63, 99} <= set(sequences)
        assert all(item.point == points[item.sequence] for item in first.items)


@pytest.mark.asyncio
async def test_large_equity_is_written_and_iterated_in_bounded_batches() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "batches.sqlite3")
        await database.initialize()
        await BacktestRepository(database).save_job(_job("batches"))
        repository = PortfolioRepository(database)
        original = _result()
        points = tuple(
            EquityPoint(
                timestamp=START + timedelta(minutes=sequence),
                cash=Decimal("1000"),
                position_value=Decimal("0"),
                equity=Decimal("1000"),
                realized_pnl_cumulative=Decimal("0"),
                unrealized_pnl=Decimal("0"),
                fees_cumulative=Decimal("0"),
                drawdown_ratio=Decimal("0"),
                exposed=False,
            )
            for sequence in range(2_501)
        )
        await repository.replace_simulation_result(
            job_id="batches",
            result=replace(original, equity_curve=points),
            config_fingerprint="sha256:test",
        )
        sizes = []
        async for batch in repository.iter_equity_points("batches"):
            sizes.append(len(batch))
        assert sizes == [1_000, 1_000, 501]


@pytest.mark.asyncio
async def test_job_delete_cascades_all_portfolio_rows() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "delete.sqlite3")
        await database.initialize()
        jobs = BacktestRepository(database)
        await jobs.save_job(_job("delete"))
        portfolio = PortfolioRepository(database)
        await portfolio.replace_simulation_result(
            job_id="delete",
            result=_result(),
            config_fingerprint="sha256:test",
        )
        assert await jobs.delete_job("delete")
        assert await portfolio.get_run_metadata("delete") is None
        async with database.connection() as connection:
            for table in (
                "backtest_portfolio_orders",
                "backtest_portfolio_executions",
                "backtest_portfolio_trades",
                "backtest_portfolio_equity",
            ):
                cursor = await connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE job_id=?", ("delete",)
                )
                row = await cursor.fetchone()
                assert row is not None and row[0] == 0
