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
from app.models.backtest import (
    BacktestConfig,
    BacktestJob,
    BacktestStatus,
    BacktestSummary,
)
from app.models.portfolio import (
    PortfolioSimulationPublicResult,
    PortfolioSimulationSummary,
)
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


class PartialPortfolioEngine(SlowEngine):
    async def run(self, job, callback) -> None:
        job.set_portfolio_result(object())
        summary = PortfolioSimulationSummary(
            quote_asset="USDC",
            initial_capital="1000",
            final_cash="1000",
            final_equity="1000",
            net_profit="0",
            total_return_ratio="0",
            realized_pnl="0",
            unrealized_pnl="0",
            total_fees="0",
            trade_count=0,
            winning_trade_count=0,
            losing_trade_count=0,
            breakeven_trade_count=0,
            win_rate=None,
            average_trade_return=None,
            max_drawdown_ratio="0",
            exposure_ratio="0",
            open_position_count=0,
        )
        job.summary = BacktestSummary(
            trade_simulation_included=True,
            portfolio_simulation=PortfolioSimulationPublicResult(
                quote_asset="USDC",
                summary=summary,
                has_trades=False,
                has_equity_curve=True,
            ),
        )
        await super().run(job, callback)


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
async def test_portfolio_cancellation_discards_internal_and_public_partial_result() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "portfolio-cancel.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        manager = BacktestManager(repository, CandleRepository(database))
        partial = PartialPortfolioEngine()
        manager.engine = partial  # type: ignore[assignment]
        payload = config_payload()
        payload["portfolio_simulation"] = {"quote_asset": "USDC"}
        job = await manager.create_job(BacktestConfig.model_validate(payload))
        await partial.started.wait()
        cancelled = await manager.cancel(job.id)
        assert cancelled is not None
        assert cancelled.status == BacktestStatus.CANCELLED
        assert cancelled.portfolio_result is None
        assert cancelled.summary is not None
        assert cancelled.summary.portfolio_simulation is None
        assert not cancelled.summary.trade_simulation_included
        assert "portfolio_simulation" not in cancelled.public_payload()["summary"]
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


@pytest.mark.asyncio
async def test_portfolio_job_exposes_only_summary_and_legacy_payload_stays_clean() -> None:
    rows = candles()
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "portfolio-api.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        manager = BacktestManager(repository, CandleRepository(database))
        manager.engine = BacktestEngine(MemoryHistory(rows), repository, yield_every=1)
        application = FastAPI()
        application.state.backtest_manager = manager
        request = Request({"type": "http", "app": application, "headers": []})

        legacy_config = BacktestConfig.model_validate(config_payload())
        legacy = await create_backtest(legacy_config, request)
        assert "portfolio_simulation" not in legacy["config"]
        assert "signal_profile_id" not in legacy["config"]
        assert "config_fingerprint" not in legacy
        await manager._tasks[legacy["id"]]
        legacy_done = await get_backtest(legacy["id"], request)
        assert "portfolio_simulation" not in legacy_done["summary"]

        portfolio_payload = config_payload()
        portfolio_payload["portfolio_simulation"] = {
            "quote_asset": "USDC",
            "initial_capital": "1000",
            "fee_rate": "0",
        }
        created = await create_backtest(
            BacktestConfig.model_validate(portfolio_payload),
            request,
        )
        job_id = created["id"]
        assert created["config"]["portfolio_simulation"]["initial_capital"] == "1000"
        await manager._tasks[job_id]
        snapshot = await get_backtest(job_id, request)
        portfolio = snapshot["summary"]["portfolio_simulation"]
        assert snapshot["status"] == "completed"
        assert snapshot["config_fingerprint"].startswith("sha256:")
        assert portfolio["version"] == 1
        assert portfolio["summary"]["quote_asset"] == "USDC"
        assert "orders" not in portfolio
        assert "trades" not in portfolio
        assert "equity_curve" not in portfolio
        await database.close()


def test_signal_profile_id_is_normalized_and_exposed_only_when_explicit() -> None:
    inline = BacktestJob(
        id="inline-profile",
        config=BacktestConfig.model_validate(config_payload()),
    )

    assert inline.config.signal_profile_id == "inline"
    assert "signal_profile_id" not in inline.public_payload()["config"]

    payload = config_payload()
    payload["signal_profile_id"] = "  ml-dataset-v2  "

    explicit = BacktestJob(
        id="explicit-profile",
        config=BacktestConfig.model_validate(payload),
    )

    assert explicit.config.signal_profile_id == "ml-dataset-v2"
    assert explicit.public_payload()["config"]["signal_profile_id"] == "ml-dataset-v2"

    payload["signal_profile_id"] = "   "

    with pytest.raises(
        ValueError,
        match="signal_profile_id",
    ):
        BacktestConfig.model_validate(payload)
