"""Endpoints en lecture seule de couverture historique et de runs."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request

from app.repositories.backfill_repository import BackfillRepository
from app.repositories.candle_repository import CandleRepository

router = APIRouter(prefix="/api/market/history", tags=["history"])
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]*/[A-Z0-9][A-Z0-9._-]*$")


def _repositories(request: Request) -> tuple[CandleRepository, BackfillRepository]:
    candles = getattr(request.app.state, "candle_repository", None)
    backfills = getattr(request.app.state, "backfill_repository", None)
    if candles is None or backfills is None:
        raise HTTPException(status_code=503, detail="Historique local indisponible")
    return candles, backfills


async def _with_status(
    rows: list[dict[str, object]],
    candles: CandleRepository,
    backfills: BackfillRepository,
    exchange_id: str,
    market_type: str,
) -> list[dict[str, object]]:
    """Ajoute état et trous à une agrégation bornée."""
    now = int(datetime.now(timezone.utc).timestamp() * 1_000)
    result: list[dict[str, object]] = []
    for row in rows:
        symbol = str(row["symbol"])
        timeframe = str(row["timeframe"])
        state = await backfills.get_state(exchange_id, market_type, symbol, timeframe)
        gaps = await candles.find_missing_ranges(
            exchange_id,
            market_type,
            symbol,
            timeframe,
            now_ms=now,
            max_ranges=100,
        )
        result.append(
            {
                **row,
                "status": state.status.value if state else None,
                "gap_count": len(gaps),
            }
        )
    return result


@router.get("/coverage", summary="Lire la couverture OHLCV globale")
async def coverage(
    request: Request,
    exchange_id: str = Query(default="binance", min_length=1, max_length=50),
    market_type: str = Query(default="spot", pattern="^(spot|swap|future)$"),
    limit: int = Query(default=500, ge=1, le=2_000),
) -> dict[str, object]:
    """Retourne une couverture bornée sans exposer le chemin SQLite."""
    candles, backfills = _repositories(request)
    rows = await candles.coverage_summary(
        exchange_id=exchange_id.strip().lower(),
        market_type=market_type,
        limit=limit,
    )
    enriched = await _with_status(
        rows, candles, backfills, exchange_id.strip().lower(), market_type
    )
    return {"count": len(enriched), "coverage": enriched}


@router.get("/coverage/{symbol:path}", summary="Lire la couverture d'un symbole")
async def symbol_coverage(
    request: Request,
    symbol: str,
    exchange_id: str = Query(default="binance", min_length=1, max_length=50),
    market_type: str = Query(default="spot", pattern="^(spot|swap|future)$"),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    """Retourne tous les timeframes locaux d'un symbole validé."""
    symbol = symbol.strip().upper()
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise HTTPException(status_code=422, detail="Symbole invalide")
    candles, backfills = _repositories(request)
    exchange_id = exchange_id.strip().lower()
    rows = await candles.coverage_summary(
        exchange_id=exchange_id,
        market_type=market_type,
        symbol=symbol,
        limit=limit,
    )
    return {
        "symbol": symbol,
        "coverage": await _with_status(rows, candles, backfills, exchange_id, market_type),
    }


@router.get("/runs", summary="Lister les exécutions de backfill")
async def runs(
    request: Request, limit: int = Query(default=50, ge=1, le=200)
) -> list[dict[str, object]]:
    """Retourne les runs les plus récents."""
    _, backfills = _repositories(request)
    return await backfills.list_runs(limit)


@router.get("/runs/{run_id}", summary="Lire une exécution de backfill")
async def run_detail(request: Request, run_id: str) -> dict[str, object]:
    """Retourne un run ou une erreur 404 stable."""
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise HTTPException(status_code=422, detail="Identifiant de run invalide")
    _, backfills = _repositories(request)
    run = await backfills.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Exécution introuvable")
    return run
