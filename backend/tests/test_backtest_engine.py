from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.database.connection import Database
from app.models.backtest import BacktestConfig, BacktestJob, BacktestStatus
from app.repositories.backtest_repository import BacktestRepository
from app.services.backtest_engine import BacktestEngine
from app.services.portfolio_replay import PortfolioReplayError
from tests.fixtures.synthetic_backtest_v1 import candles
from tests.test_backtesting_domain import signal_config


class MemoryHistory:
    def __init__(self, rows):
        self.rows = rows

    async def before(self, symbol, timeframe, before_ms, limit, job):
        return [item for item in self.rows if item.open_time < before_ms][-limit:]

    async def range(self, symbol, timeframe, start_ms, end_ms, job):
        return [item for item in self.rows if start_ms <= item.open_time < end_ms]


class CountingMemoryHistory(MemoryHistory):
    def __init__(self, rows):
        super().__init__(rows)
        self.before_calls = 0
        self.range_calls = 0

    async def before(self, symbol, timeframe, before_ms, limit, job):
        self.before_calls += 1
        return await super().before(symbol, timeframe, before_ms, limit, job)

    async def range(self, symbol, timeframe, start_ms, end_ms, job):
        self.range_calls += 1
        return await super().range(symbol, timeframe, start_ms, end_ms, job)


@pytest.mark.asyncio
async def test_full_synthetic_replay_persists_and_survives_restart() -> None:
    rows = candles()
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "backtest.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        config = BacktestConfig(
            symbols=["SYN/USDC"],
            start=datetime.fromtimestamp(rows[80].open_time / 1_000, tz=timezone.utc),
            end=datetime.fromtimestamp(rows[100].open_time / 1_000, tz=timezone.utc),
            signal_config=signal_config(),
            horizons=[1, 3, 6],
        )
        job = BacktestJob(id="golden-v1", config=config)
        await repository.save_job(job)
        await BacktestEngine(MemoryHistory(rows), repository, yield_every=2).run(job)
        await repository.save_job(job)
        restored = await BacktestRepository(database).get_job(job.id)
        observations = await repository.all_observations(job.id)
        outcomes = await repository.all_outcomes(job.id)
        assert restored is not None and restored.summary is not None
        assert restored.summary.observation_count == 20
        assert len(observations) == 20
        assert len(outcomes) == 60
        assert all(item.snapshot_status == "confirmed" for item in observations)
        assert not restored.summary.trade_simulation_included
        await database.close()


@pytest.mark.asyncio
async def test_gap_policy_rejects_range() -> None:
    rows = candles()
    rows.pop(90)
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "gap.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        config = BacktestConfig(
            symbols=["SYN/USDC"],
            start=datetime.fromtimestamp(rows[79].open_time / 1_000, tz=timezone.utc),
            end=datetime.fromtimestamp(rows[99].open_time / 1_000, tz=timezone.utc),
            signal_config=signal_config(),
            horizons=[1],
            gap_policy="reject_range",
        )
        job = BacktestJob(id="gap", config=config)
        with pytest.raises(ValueError, match="discontinue"):
            await BacktestEngine(MemoryHistory(rows), repository).run(job)
        await database.close()


@pytest.mark.asyncio
async def test_checkpoint_resume_is_idempotent() -> None:
    rows = candles()
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "resume.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        config = BacktestConfig(
            symbols=["SYN/USDC"],
            start=datetime.fromtimestamp(rows[80].open_time / 1_000, tz=timezone.utc),
            end=datetime.fromtimestamp(rows[100].open_time / 1_000, tz=timezone.utc),
            signal_config=signal_config(),
            horizons=[1, 3],
        )
        job = BacktestJob(id="resume-v1", config=config)
        await repository.save_job(job)

        async def interrupt(progress) -> None:
            if progress.processed >= 5:
                raise RuntimeError("controlled interruption")

        engine = BacktestEngine(MemoryHistory(rows), repository, yield_every=1)
        with pytest.raises(RuntimeError, match="controlled"):
            await engine.run(job, interrupt)
        checkpoint = await repository.get_checkpoint(job.id)
        assert checkpoint is not None and checkpoint["processed"] == 5
        job.status = BacktestStatus.INTERRUPTED
        await repository.save_job(job)

        restored = await repository.get_job(job.id)
        assert restored is not None
        await engine.run(restored)
        observations = await repository.all_observations(job.id)
        outcomes = await repository.all_outcomes(job.id)
        assert restored.progress.processed == 20
        assert len(observations) == 20
        assert len(outcomes) == 40
        assert len({item.id for item in observations}) == 20
        await database.close()


@pytest.mark.asyncio
async def test_portfolio_replay_is_additive_and_resume_is_deterministic() -> None:
    rows = candles()
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "portfolio-resume.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        config = BacktestConfig(
            symbols=["SYN/USDC"],
            start=datetime.fromtimestamp(rows[80].open_time / 1_000, tz=timezone.utc),
            end=datetime.fromtimestamp(rows[100].open_time / 1_000, tz=timezone.utc),
            signal_config=signal_config(),
            horizons=[1, 3],
            portfolio_simulation={
                "quote_asset": "USDC",
                "initial_capital": "10000",
                "fee_rate": "0.001",
            },
        )
        uninterrupted = BacktestJob(id="portfolio-full", config=config)
        await repository.save_job(uninterrupted)
        engine = BacktestEngine(MemoryHistory(rows), repository, yield_every=1)
        await engine.run(uninterrupted)
        full_result = await engine.portfolios.load_portfolio_simulation_result(uninterrupted.id)
        full_outcomes = await repository.all_outcomes(uninterrupted.id)
        assert full_result is not None
        assert uninterrupted.portfolio_result is None
        assert uninterrupted.summary is not None
        assert uninterrupted.summary.trade_simulation_included
        assert uninterrupted.summary.portfolio_simulation is not None
        assert uninterrupted.summary.portfolio_simulation.summary.open_position_count == 0

        resumed = BacktestJob(id="portfolio-resumed", config=config)
        await repository.save_job(resumed)

        async def interrupt(progress) -> None:
            if progress.processed >= 5:
                raise RuntimeError("controlled portfolio interruption")

        with pytest.raises(RuntimeError, match="controlled portfolio interruption"):
            await engine.run(resumed, interrupt)
        resumed.status = BacktestStatus.INTERRUPTED
        await repository.save_job(resumed)
        restored = await repository.get_job(resumed.id)
        assert restored is not None
        await engine.run(restored)
        resumed_result = await engine.portfolios.load_portfolio_simulation_result(restored.id)
        resumed_outcomes = await repository.all_outcomes(restored.id)
        assert resumed_result is not None
        assert restored.portfolio_result is None
        assert resumed_result.metrics == full_result.metrics
        assert [item.id for item in resumed_result.orders] == [
            item.id for item in full_result.orders
        ]
        assert [item.id for item in resumed_result.executions] == [
            item.id for item in full_result.executions
        ]
        assert [item.id for item in resumed_result.trades] == [
            item.id for item in full_result.trades
        ]
        assert [item.model_dump(exclude={"observation_id"}) for item in resumed_outcomes] == [
            item.model_dump(exclude={"observation_id"}) for item in full_outcomes
        ]
        assert restored.config_fingerprint == uninterrupted.config_fingerprint
        assert restored.checkpoint is not None
        assert restored.checkpoint["config_fingerprint"] == restored.config_fingerprint
        checkpoint_result = resumed_result
        await engine.run(restored)
        assert (
            await engine.portfolios.load_portfolio_simulation_result(restored.id)
            == checkpoint_result
        )
        await database.close()


@pytest.mark.asyncio
async def test_portfolio_does_not_add_historical_data_loads() -> None:
    rows = candles()
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "portfolio-loads.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        common = {
            "symbols": ["SYN/USDC"],
            "start": datetime.fromtimestamp(rows[80].open_time / 1_000, tz=timezone.utc),
            "end": datetime.fromtimestamp(rows[85].open_time / 1_000, tz=timezone.utc),
            "signal_config": signal_config(),
            "horizons": [1],
        }
        legacy_history = CountingMemoryHistory(rows)
        legacy = BacktestJob(id="legacy-loads", config=BacktestConfig(**common))
        await repository.save_job(legacy)
        await BacktestEngine(legacy_history, repository).run(legacy)

        portfolio_history = CountingMemoryHistory(rows)
        portfolio = BacktestJob(
            id="portfolio-loads",
            config=BacktestConfig(
                **common,
                portfolio_simulation={"quote_asset": "USDC"},
            ),
        )
        await repository.save_job(portfolio)
        await BacktestEngine(portfolio_history, repository).run(portfolio)
        assert (portfolio_history.before_calls, portfolio_history.range_calls) == (
            legacy_history.before_calls,
            legacy_history.range_calls,
        )
        await database.close()


@pytest.mark.asyncio
async def test_requested_portfolio_fails_explicitly_on_primary_gap() -> None:
    rows = candles()
    start = rows[80].open_time
    end = rows[100].open_time
    rows.pop(90)
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "portfolio-gap.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        config = BacktestConfig(
            symbols=["SYN/USDC"],
            start=datetime.fromtimestamp(start / 1_000, tz=timezone.utc),
            end=datetime.fromtimestamp(end / 1_000, tz=timezone.utc),
            signal_config=signal_config(),
            horizons=[1],
            gap_policy="allow_with_warning",
            portfolio_simulation={"quote_asset": "USDC"},
        )
        job = BacktestJob(id="portfolio-gap", config=config)
        await repository.save_job(job)
        with pytest.raises(PortfolioReplayError) as raised:
            await BacktestEngine(MemoryHistory(rows), repository).run(job)
        assert raised.value.code == "portfolio_time_gap"
        assert job.summary is None
        assert job.portfolio_result is None
        await database.close()
