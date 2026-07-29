from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from app.api.backtests import (
    create_backtest,
    export_csv,
    export_summary_json,
    get_ablations,
    get_backtest,
    get_correlations,
    get_observations,
    get_summary,
    router,
)
from app.database.connection import Database
from app.models.backtest import BacktestConfig, BacktestStatus
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.candle_repository import CandleRepository
from app.services.backtest_engine import BacktestEngine
from app.services.backtest_manager import BacktestManager
from tests.fixtures.synthetic_backtest_v1 import candles
from tests.test_backtest_engine import MemoryHistory
from tests.test_backtesting_domain import signal_config


def config_payload() -> dict:
    rows = candles()
    return BacktestConfig(
        symbols=["SYN/USDC"],
        start=datetime.fromtimestamp(rows[80].open_time / 1_000, tz=timezone.utc),
        end=datetime.fromtimestamp(rows[85].open_time / 1_000, tz=timezone.utc),
        signal_config=signal_config(),
        horizons=[1, 3],
    ).model_dump(mode="json")


@pytest.mark.asyncio
async def test_rest_backtest_lifecycle_pagination_and_exports() -> None:
    rows = candles()
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "api.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        manager = BacktestManager(repository, CandleRepository(database))
        manager.engine = BacktestEngine(MemoryHistory(rows), repository, yield_every=1)
        application = FastAPI()
        application.state.backtest_manager = manager
        application.include_router(router)
        request = Request({"type": "http", "app": application, "headers": []})
        created = await create_backtest(BacktestConfig.model_validate(config_payload()), request)
        job_id = created["id"]
        await manager._tasks[job_id]
        snapshot = await get_backtest(job_id, request)
        assert snapshot["status"] == "completed", snapshot
        summary = await get_summary(job_id, request)
        assert summary["observation_count"] == 5
        page = await get_observations(
            job_id, request, offset=0, limit=2, accepted=None, symbol=None
        )
        assert page["total"] == 5
        assert len(page["items"]) == 2
        assert await get_correlations(job_id, request)
        assert await get_ablations(job_id, request)
        for dataset in ("observations", "outcomes", "correlations", "ablations"):
            exported = await export_csv(job_id, request, dataset=dataset)
            assert exported.status_code == 200
            assert exported.media_type == "text/csv; charset=utf-8"
        assert (await export_summary_json(job_id, request)).status_code == 200
        paths = {getattr(route, "path", None) for route in router.routes}
        assert "/api/backtests/{job_id}/ws" in paths
        await database.close()


class SlowEngine:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def run(self, job, callback) -> None:
        self.started.set()
        await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_cancellation_is_persisted() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "cancel.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        manager = BacktestManager(repository, CandleRepository(database))
        slow = SlowEngine()
        manager.engine = slow  # type: ignore[assignment]
        job = await manager.create_job(BacktestConfig.model_validate(config_payload()))
        await slow.started.wait()
        cancelled = await manager.cancel(job.id)
        restored = await repository.get_job(job.id)
        assert cancelled is not None and cancelled.status == BacktestStatus.CANCELLED
        assert restored is not None and restored.status == BacktestStatus.CANCELLED
        await database.close()


@pytest.mark.asyncio
async def test_restart_marks_interrupted_job_and_keeps_it_readable() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "restart.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        manager = BacktestManager(repository, CandleRepository(database))
        slow = SlowEngine()
        manager.engine = slow  # type: ignore[assignment]
        job = await manager.create_job(BacktestConfig.model_validate(config_payload()))
        await slow.started.wait()
        # Simule le traitement de reprise d'un nouveau processus.
        assert await repository.recover_interrupted() == 1
        restored = await repository.get_job(job.id)
        assert restored is not None and restored.status == BacktestStatus.INTERRUPTED
        assert "redémarrage" in (restored.error or "")
        await manager.cancel(job.id)
        await database.close()
