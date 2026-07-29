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

from app.models.backtest import BacktestConfig, BacktestStatus
from app.services.backtest_manager import BacktestManager

router = APIRouter(prefix="/api/backtests", tags=["backtests"])


def _manager(request: Request) -> BacktestManager:
    return request.app.state.backtest_manager


async def _job_or_404(manager: BacktestManager, job_id: str):
    job = await manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Backtest introuvable")
    return job


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
        "trade_simulation": False,
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
    return job.summary.model_dump(mode="json")


@router.get("/{job_id}/summary.json")
async def export_summary_json(job_id: str, request: Request) -> Response:
    job = await _job_or_404(_manager(request), job_id)
    if job.summary is None:
        raise HTTPException(status_code=409, detail="Résumé indisponible")
    return Response(
        job.summary.model_dump_json(indent=2),
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
    await _job_or_404(_manager(request), job_id)
    base = f"/api/backtests/{job_id}"
    return {
        "summary": f"{base}/summary.json",
        "observations": f"{base}/export.csv?dataset=observations",
        "outcomes": f"{base}/export.csv?dataset=outcomes",
        "correlations": f"{base}/export.csv?dataset=correlations",
        "ablations": f"{base}/export.csv?dataset=ablations",
    }


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
