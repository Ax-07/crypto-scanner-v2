from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.database.connection import Database
from app.models.backtest import BacktestConfig, BacktestJob, BacktestStatus
from app.repositories.backtest_repository import BacktestRepository
from app.services.backtest_engine import BacktestEngine
from tests.fixtures.synthetic_backtest_v1 import candles
from tests.test_backtesting_domain import signal_config


class MemoryHistory:
    def __init__(self, rows):
        self.rows = rows

    async def before(self, symbol, timeframe, before_ms, limit, job):
        return [item for item in self.rows if item.open_time < before_ms][-limit:]

    async def range(self, symbol, timeframe, start_ms, end_ms, job):
        return [item for item in self.rows if start_ms <= item.open_time < end_ms]


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
