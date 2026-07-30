from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.backtests import (
    export_portfolio_equity,
    export_portfolio_trades,
    get_portfolio,
    get_portfolio_equity,
    get_portfolio_trades,
    router,
)
from app.database.connection import Database
from app.models.backtest import BacktestStatus, BacktestSummary
from app.repositories.backtest_repository import BacktestRepository
from app.repositories.candle_repository import CandleRepository
from app.services.backtest_manager import BacktestManager
from app.services.portfolio_replay import to_public_portfolio_result
from tests.test_portfolio_repository import _job, _result


def _request(manager: BacktestManager) -> Request:
    application = FastAPI()
    application.state.backtest_manager = manager
    application.include_router(router)
    return Request({"type": "http", "app": application, "headers": []})


async def _completed(manager: BacktestManager, job_id: str = "portfolio-api"):
    job = _job(job_id)
    result = _result()
    job.status = BacktestStatus.COMPLETED
    job.summary = BacktestSummary(
        trade_simulation_included=True,
        portfolio_simulation=to_public_portfolio_result(result),
    )
    await manager.repository.save_job(job)
    await manager.portfolio_repository.replace_simulation_result(
        job_id=job.id,
        result=result,
        config_fingerprint="sha256:test",
    )
    return job, result


@pytest.mark.asyncio
async def test_metadata_and_paginated_endpoints_read_sqlite() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "api.sqlite3")
        await database.initialize()
        manager = BacktestManager(BacktestRepository(database), CandleRepository(database))
        job, result = await _completed(manager)
        request = _request(manager)
        metadata = await get_portfolio(job.id, request)
        assert metadata.details_status == "complete"
        assert metadata.trade_count == len(result.trades)
        assert metadata.equity_point_count == len(result.equity_curve)
        assert metadata.available_after_restart

        first = await get_portfolio_trades(job.id, request, offset=0, limit=1)
        last = await get_portfolio_trades(job.id, request, offset=1, limit=1)
        assert first.total == 2 and first.has_more
        assert first.items[0].sequence == 0
        assert last.items[0].sequence == 1
        assert not last.has_more
        assert first.model_dump(mode="json")["items"][0]["entry_price"].count(".") <= 1

        raw = await get_portfolio_equity(
            job.id,
            request,
            offset=1,
            limit=2,
            mode="raw",
            max_points=1_000,
        )
        assert not raw.sampled
        assert [item.sequence for item in raw.items] == [1, 2]
        sampled = await get_portfolio_equity(
            job.id,
            request,
            offset=0,
            limit=100,
            mode="sampled",
            max_points=4,
        )
        assert sampled.sampled
        assert sampled.source_point_count == len(result.equity_curve)
        assert sampled.items[0].sequence == 0
        assert sampled.items[-1].sequence == len(result.equity_curve) - 1


@pytest.mark.asyncio
async def test_legacy_absent_and_non_completed_states_are_explicit() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "errors.sqlite3")
        await database.initialize()
        repository = BacktestRepository(database)
        manager = BacktestManager(repository, CandleRepository(database))
        request = _request(manager)

        absent = _job("absent")
        absent.config.portfolio_simulation = None
        absent.status = BacktestStatus.COMPLETED
        await repository.save_job(absent)
        with pytest.raises(HTTPException) as absent_error:
            await get_portfolio(absent.id, request)
        assert absent_error.value.status_code == 404
        assert absent_error.value.detail["code"] == "portfolio_not_requested"

        legacy = _job("legacy")
        legacy.status = BacktestStatus.COMPLETED
        legacy.summary = BacktestSummary(
            trade_simulation_included=True,
            portfolio_simulation=to_public_portfolio_result(_result()),
        )
        await repository.save_job(legacy)
        with pytest.raises(HTTPException) as legacy_error:
            await get_portfolio_trades(legacy.id, request, offset=0, limit=10)
        assert legacy_error.value.status_code == 409
        assert legacy_error.value.detail["code"] == "portfolio_details_legacy_unavailable"

        running = _job("running")
        running.status = BacktestStatus.RUNNING
        await repository.save_job(running)
        with pytest.raises(HTTPException) as running_error:
            await get_portfolio_equity(
                running.id,
                request,
                offset=0,
                limit=10,
                mode="raw",
                max_points=100,
            )
        assert running_error.value.detail["code"] == "portfolio_job_not_completed"


async def _stream_text(response) -> str:
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    return "".join(chunks)


@pytest.mark.asyncio
async def test_versioned_csv_exports_are_streamed_with_stable_columns() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Database(Path(temporary) / "exports.sqlite3")
        await database.initialize()
        manager = BacktestManager(BacktestRepository(database), CandleRepository(database))
        job, result = await _completed(manager, "csv")
        request = _request(manager)

        trades = await export_portfolio_trades(job.id, request)
        trades_text = await _stream_text(trades)
        assert trades.media_type == "text/csv; charset=utf-8"
        assert 'filename="csv-trades-v1.csv"' in trades.headers["content-disposition"]
        trade_lines = trades_text.splitlines()
        assert trade_lines[0].startswith("schema_version,job_id,trade_sequence")
        assert len(trade_lines) == len(result.trades) + 1
        assert ",,2026-" in trades_text

        equity = await export_portfolio_equity(job.id, request)
        equity_text = await _stream_text(equity)
        assert 'filename="csv-equity-v1.csv"' in equity.headers["content-disposition"]
        equity_lines = equity_text.splitlines()
        assert equity_lines[0] == (
            "schema_version,job_id,sequence,timestamp,cash,position_value,"
            "equity,realized_pnl_cumulative,unrealized_pnl,fees_cumulative,"
            "drawdown_ratio"
        )
        assert len(equity_lines) == len(result.equity_curve) + 1


def test_openapi_exposes_portfolio_v1_routes() -> None:
    application = FastAPI()
    application.include_router(router)
    paths = application.openapi()["paths"]
    assert "/api/backtests/{job_id}/portfolio" in paths
    assert "/api/backtests/{job_id}/trades" in paths
    assert "/api/backtests/{job_id}/equity" in paths
    assert "/api/backtests/{job_id}/trades/export.csv" in paths
    assert "/api/backtests/{job_id}/equity/export.csv" in paths


def test_route_validation_rejects_invalid_pagination_before_repository_access() -> None:
    application = FastAPI()
    application.include_router(router)
    with TestClient(application) as client:
        assert client.get("/api/backtests/x/trades?offset=-1").status_code == 422
        assert client.get("/api/backtests/x/trades?limit=0").status_code == 422
        assert client.get("/api/backtests/x/trades?limit=501").status_code == 422
        assert client.get("/api/backtests/x/equity?limit=1001").status_code == 422
        assert client.get("/api/backtests/x/equity?mode=sampled&max_points=3").status_code == 422
