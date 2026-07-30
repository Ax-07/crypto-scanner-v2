"""API REST/WebSocket de validation historique persistante."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Literal

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import StreamingResponse

from app.exporters.portfolio_csv import stream_equity_v1, stream_trades_v1
from app.models.backtest import BacktestConfig, BacktestStatus
from app.models.portfolio import (
    PortfolioDetailsStatus,
    PortfolioEquityPage,
    PortfolioEquityPointV1,
    PortfolioRunMetadataV1,
    PortfolioTradePage,
    PortfolioTradeV1,
)
from app.repositories.portfolio_repository import StoredPortfolioRun
from app.services.backtest_manager import BacktestManager

router = APIRouter(prefix="/api/backtests", tags=["backtests"])


def _manager(request: Request) -> BacktestManager:
    return request.app.state.backtest_manager


async def _job_or_404(manager: BacktestManager, job_id: str):
    job = await manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Backtest introuvable")
    return job


def _portfolio_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _portfolio_run_or_error(
    manager: BacktestManager, job_id: str
) -> tuple[Any, StoredPortfolioRun]:
    job = await _job_or_404(manager, job_id)
    if job.config.portfolio_simulation is None:
        raise _portfolio_error(
            404,
            "portfolio_not_requested",
            "La simulation de portefeuille n'a pas été demandée.",
        )
    if job.status is not BacktestStatus.COMPLETED:
        raise _portfolio_error(
            409,
            "portfolio_job_not_completed",
            f"Les détails ne sont pas disponibles pour un job {job.status.value}.",
        )
    run = await manager.portfolio_repository.get_run_metadata(job_id)
    if run is None:
        if job.summary is not None and job.summary.portfolio_simulation is not None:
            raise _portfolio_error(
                409,
                "portfolio_details_legacy_unavailable",
                "Ce job Phase 6.3 possède un résumé mais aucun détail persistant.",
            )
        raise _portfolio_error(
            409,
            "portfolio_details_unavailable",
            "Les détails du portefeuille sont indisponibles.",
        )
    return job, run


def _public_trade(item) -> PortfolioTradeV1:
    trade = item.trade
    return PortfolioTradeV1(
        sequence=item.sequence,
        trade_id=trade.id,
        position_id=trade.position_id,
        symbol=trade.symbol,
        quote_asset=trade.quote_asset,
        entry_observation_id=trade.entry_observation_id,
        exit_observation_id=trade.exit_observation_id,
        entry_time=trade.entry_time,
        exit_time=trade.exit_time,
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        quantity=trade.quantity,
        entry_fee=trade.entry_fee,
        exit_fee=trade.exit_fee,
        gross_exit_proceeds=trade.gross_exit_proceeds,
        net_exit_proceeds=trade.net_exit_proceeds,
        realized_pnl=trade.realized_pnl,
        return_ratio=trade.return_ratio,
        duration_bars=trade.duration_bars,
        exit_reason=trade.exit_reason.value,
    )


def _public_equity(item) -> PortfolioEquityPointV1:
    point = item.point
    return PortfolioEquityPointV1(
        sequence=item.sequence,
        timestamp=point.timestamp,
        cash=point.cash,
        position_value=point.position_value,
        equity=point.equity,
        realized_pnl_cumulative=point.realized_pnl_cumulative,
        unrealized_pnl=point.unrealized_pnl,
        fees_cumulative=point.fees_cumulative,
        drawdown_ratio=point.drawdown_ratio,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_backtest(config: BacktestConfig, request: Request) -> dict[str, Any]:
    job = await _manager(request).create_job(config)
    return job.public_payload()


@router.get("")
async def list_backtests(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    items, total = await _manager(request).repository.list_jobs(offset=offset, limit=limit)
    return {
        "items": [item.public_payload() for item in items],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/capabilities")
async def backtest_capabilities() -> dict[str, Any]:
    return {
        "snapshot_status": {
            "confirmed": {"available": True, "source": "closed_ohlcv"},
            "provisional": {
                "available": False,
                "source": None,
                "reason": (
                    "Aucune source intrabar historisée n'est configurée; "
                    "le mode provisional ne peut pas être reconstruit fidèlement."
                ),
            },
        },
        "resume": True,
        "checkpoint_schema_version": 1,
        "trade_simulation": True,
    }


@router.get("/{job_id}")
async def get_backtest(job_id: str, request: Request) -> dict[str, Any]:
    return (await _job_or_404(_manager(request), job_id)).public_payload()


@router.post("/{job_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_backtest(job_id: str, request: Request) -> dict[str, Any]:
    manager = _manager(request)
    await _job_or_404(manager, job_id)
    try:
        job = await manager.resume(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    assert job is not None
    return job.public_payload()


@router.delete("/{job_id}", response_model=None)
async def cancel_or_delete_backtest(job_id: str, request: Request) -> Response | dict[str, Any]:
    manager = _manager(request)
    job = await _job_or_404(manager, job_id)
    if job.status in {BacktestStatus.PENDING, BacktestStatus.RUNNING}:
        cancelled = await manager.cancel(job_id)
        return cancelled.public_payload() if cancelled else {}
    await manager.delete(job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{job_id}/summary")
async def get_summary(job_id: str, request: Request) -> dict[str, Any]:
    job = await _job_or_404(_manager(request), job_id)
    if job.summary is None:
        raise HTTPException(status_code=409, detail="Résumé indisponible avant la fin du backtest")
    return job.summary.public_payload()


@router.get("/{job_id}/portfolio", response_model=PortfolioRunMetadataV1)
async def get_portfolio(job_id: str, request: Request) -> PortfolioRunMetadataV1:
    manager = _manager(request)
    job, run = await _portfolio_run_or_error(manager, job_id)
    assert job.summary is not None and job.summary.portfolio_simulation is not None
    return PortfolioRunMetadataV1(
        schema_version=1,
        engine_version=run.engine_version,
        quote_asset=run.quote_asset,
        summary=job.summary.portfolio_simulation.summary,
        details_status=PortfolioDetailsStatus.COMPLETE,
        order_count=run.order_count,
        execution_count=run.execution_count,
        trade_count=run.trade_count,
        equity_point_count=run.equity_point_count,
        available_after_restart=True,
    )


@router.get("/{job_id}/trades", response_model=PortfolioTradePage)
async def get_portfolio_trades(
    job_id: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> PortfolioTradePage:
    manager = _manager(request)
    await _portfolio_run_or_error(manager, job_id)
    page = await manager.portfolio_repository.list_trades(job_id=job_id, offset=offset, limit=limit)
    return PortfolioTradePage(
        items=[_public_trade(item) for item in page.items],
        total=page.total,
        offset=offset,
        limit=limit,
        has_more=offset + len(page.items) < page.total,
    )


@router.get("/{job_id}/equity", response_model=PortfolioEquityPage)
async def get_portfolio_equity(
    job_id: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1_000),
    mode: Literal["raw", "sampled"] = "raw",
    max_points: int = Query(default=1_000, ge=4, le=2_000),
) -> PortfolioEquityPage:
    manager = _manager(request)
    await _portfolio_run_or_error(manager, job_id)
    if mode == "sampled":
        if offset != 0:
            raise _portfolio_error(
                422,
                "invalid_pagination",
                "offset doit valoir 0 en mode sampled.",
            )
        page = await manager.portfolio_repository.sample_equity_points(
            job_id=job_id, max_points=max_points
        )
        return PortfolioEquityPage(
            items=[_public_equity(item) for item in page.items],
            total=page.total,
            offset=0,
            limit=max_points,
            has_more=False,
            sampled=True,
            source_point_count=page.total,
        )
    page = await manager.portfolio_repository.list_equity_points(
        job_id=job_id, offset=offset, limit=limit
    )
    return PortfolioEquityPage(
        items=[_public_equity(item) for item in page.items],
        total=page.total,
        offset=offset,
        limit=limit,
        has_more=offset + len(page.items) < page.total,
        sampled=False,
        source_point_count=page.total,
    )


@router.get("/{job_id}/trades/export.csv")
async def export_portfolio_trades(job_id: str, request: Request) -> StreamingResponse:
    manager = _manager(request)
    await _portfolio_run_or_error(manager, job_id)
    return StreamingResponse(
        stream_trades_v1(manager.portfolio_repository, job_id),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{job_id}-trades-v1.csv"'},
    )


@router.get("/{job_id}/equity/export.csv")
async def export_portfolio_equity(job_id: str, request: Request) -> StreamingResponse:
    manager = _manager(request)
    await _portfolio_run_or_error(manager, job_id)
    return StreamingResponse(
        stream_equity_v1(manager.portfolio_repository, job_id),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{job_id}-equity-v1.csv"'},
    )


@router.get("/{job_id}/summary.json")
async def export_summary_json(job_id: str, request: Request) -> Response:
    job = await _job_or_404(_manager(request), job_id)
    if job.summary is None:
        raise HTTPException(status_code=409, detail="Résumé indisponible")
    return Response(
        json.dumps(job.summary.public_payload(), ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="backtest-{job_id}-summary.json"'},
    )


@router.get("/{job_id}/observations")
async def get_observations(
    job_id: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1_000),
    accepted: bool | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
    grade: str | None = None,
    rejection_stage: str | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    has_divergence: bool | None = None,
    sort_by: Literal["decision_time", "symbol", "accepted", "confluence_score"] = "decision_time",
    order: Literal["asc", "desc"] = "asc",
) -> dict[str, Any]:
    manager = _manager(request)
    await _job_or_404(manager, job_id)
    items, total = await manager.repository.observations(
        job_id,
        offset=offset,
        limit=limit,
        accepted=accepted,
        symbol=symbol,
        timeframe=timeframe,
        start_ms=start_ms,
        end_ms=end_ms,
        grade=grade,
        rejection_stage=rejection_stage,
        min_score=min_score,
        max_score=max_score,
        has_divergence=has_divergence,
        sort_by=sort_by,
        order=order,
    )
    return {
        "items": [item.model_dump(mode="json") for item in items],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/{job_id}/correlations")
async def get_correlations(job_id: str, request: Request) -> dict[str, Any]:
    job = await _job_or_404(_manager(request), job_id)
    if job.correlations is None:
        raise HTTPException(status_code=409, detail="Corrélations indisponibles")
    return job.correlations


@router.get("/{job_id}/outcomes")
async def get_outcomes(
    job_id: str,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1_000),
    horizon: int | None = Query(default=None, ge=1),
    censored: bool | None = None,
) -> dict[str, Any]:
    manager = _manager(request)
    await _job_or_404(manager, job_id)
    items = await manager.repository.all_outcomes(job_id)
    filtered = [
        item
        for item in items
        if (horizon is None or item.horizon == horizon)
        and (censored is None or item.censored == censored)
    ]
    return {
        "items": [item.model_dump(mode="json") for item in filtered[offset : offset + limit]],
        "total": len(filtered),
        "offset": offset,
        "limit": limit,
    }


@router.get("/{job_id}/segments")
async def get_segments(job_id: str, request: Request) -> Any:
    await _job_or_404(_manager(request), job_id)
    return await _manager(request).repository.get_artifact(job_id, "segments") or {}


@router.get("/{job_id}/funnel")
async def get_funnel(job_id: str, request: Request) -> Any:
    await _job_or_404(_manager(request), job_id)
    return await _manager(request).repository.get_artifact(job_id, "funnel") or []


@router.get("/{job_id}/divergences")
async def get_divergences(job_id: str, request: Request) -> Any:
    await _job_or_404(_manager(request), job_id)
    return await _manager(request).repository.get_artifact(job_id, "divergences") or []


@router.get("/{job_id}/exports")
async def get_exports(job_id: str, request: Request) -> dict[str, str]:
    manager = _manager(request)
    job = await _job_or_404(manager, job_id)
    base = f"/api/backtests/{job_id}"
    exports = {
        "summary": f"{base}/summary.json",
        "observations": f"{base}/export.csv?dataset=observations",
        "outcomes": f"{base}/export.csv?dataset=outcomes",
        "correlations": f"{base}/export.csv?dataset=correlations",
        "ablations": f"{base}/export.csv?dataset=ablations",
    }
    if (
        job.status is BacktestStatus.COMPLETED
        and await manager.portfolio_repository.get_run_metadata(job_id) is not None
    ):
        exports["portfolio_trades_v1"] = f"{base}/trades/export.csv"
        exports["portfolio_equity_v1"] = f"{base}/equity/export.csv"
    return exports


@router.get("/{job_id}/ablations")
async def get_ablations(job_id: str, request: Request) -> dict[str, Any]:
    job = await _job_or_404(_manager(request), job_id)
    if job.ablations is None:
        raise HTTPException(status_code=409, detail="Ablations indisponibles")
    return job.ablations


def _csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    columns = sorted({key for row in rows for key in row})
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                )
                for key, value in row.items()
            }
        )
    return stream.getvalue()


@router.get("/{job_id}/export.csv")
async def export_csv(
    job_id: str,
    request: Request,
    dataset: Literal["observations", "outcomes", "correlations", "ablations"] = "observations",
) -> Response:
    manager = _manager(request)
    job = await _job_or_404(manager, job_id)
    if dataset == "observations":
        rows = [
            item.model_dump(mode="json")
            for item in await manager.repository.all_observations(job_id)
        ]
    elif dataset == "outcomes":
        rows = [
            item.model_dump(mode="json") for item in await manager.repository.all_outcomes(job_id)
        ]
    else:
        source = job.correlations if dataset == "correlations" else job.ablations
        if source is None:
            raise HTTPException(status_code=409, detail=f"{dataset} indisponible")
        rows = [{"section": key, "payload": value} for key, value in source.items()]
    return Response(
        _csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="backtest-{job_id}-{dataset}.csv"'},
    )


@router.websocket("/{job_id}/ws")
async def backtest_websocket(websocket: WebSocket, job_id: str) -> None:
    manager: BacktestManager = websocket.app.state.backtest_manager
    job = await manager.get_job(job_id)
    if job is None:
        await websocket.close(code=4404, reason="Backtest introuvable")
        return
    await websocket.accept()
    version = manager.current_version(job_id)
    try:
        await websocket.send_json(job.public_payload())
        while job.status not in {
            BacktestStatus.COMPLETED,
            BacktestStatus.FAILED,
            BacktestStatus.CANCELLED,
            BacktestStatus.INTERRUPTED,
        }:
            changed = await manager.wait_for_change(job_id, version)
            if changed is None:
                return
            version, job = changed
            await websocket.send_json(job.public_payload())
    except WebSocketDisconnect:
        return
