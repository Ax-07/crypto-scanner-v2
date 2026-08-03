"""Routes REST de lecture, synchronisation ciblée et export OHLCV."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.core.exceptions import ScannerError
from app.domain.candles import TIMEFRAME_SECONDS, Candle
from app.repositories.backfill_repository import BackfillRepository
from app.repositories.candle_repository import CandleRepository
from app.services.candle_sync import CandleSyncService
from app.services.market_history import MarketHistoryResult, MarketHistoryService
from app.services.market_stream import (
    build_divergence_markers,
    build_indicator_event_markers,
    bundle_to_chart_data,
    calculate_indicator_bundle,
    calculate_market_snapshots,
    sort_markers,
)
from app.core.settings import MarketIndicatorConfig

router = APIRouter(prefix="/api/market/candles", tags=["candles"])
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]*/[A-Z0-9][A-Z0-9._-]*$")
MARKET_TYPES = {"spot", "swap", "future"}


def _validate_market(symbol: str, timeframe: str, market_type: str) -> tuple[str, str, str]:
    normalized_symbol = symbol.strip().upper()
    normalized_timeframe = timeframe.strip()
    normalized_market_type = market_type.strip().lower()
    if not SYMBOL_PATTERN.fullmatch(normalized_symbol):
        raise HTTPException(status_code=422, detail="Symbole invalide")
    if normalized_timeframe not in TIMEFRAME_SECONDS:
        raise HTTPException(status_code=422, detail="Timeframe non pris en charge")
    if normalized_market_type not in MARKET_TYPES:
        raise HTTPException(status_code=422, detail="Type de marché non pris en charge")
    return normalized_symbol, normalized_timeframe, normalized_market_type


def _dependencies(
    request: Request,
) -> tuple[
    CandleRepository,
    CandleSyncService,
    BackfillRepository,
    MarketHistoryService,
]:
    repository = getattr(request.app.state, "candle_repository", None)
    candle_sync = getattr(request.app.state, "candle_sync", None)
    backfill = getattr(request.app.state, "backfill_repository", None)
    market_history = getattr(request.app.state, "market_history", None)
    if (
        repository is None
        or candle_sync is None
        or backfill is None
        or market_history is None
        or not candle_sync.settings.candle_storage_enabled
    ):
        raise HTTPException(status_code=503, detail="Stockage local des bougies indisponible")
    return repository, candle_sync, backfill, market_history


def _validate_range(from_time: int | None, to_time: int | None) -> None:
    if from_time is not None and to_time is not None and from_time >= to_time:
        raise HTTPException(
            status_code=422,
            detail="from_time doit être strictement inférieur à to_time",
        )


@router.get("/status", summary="Lire l'état local d'un historique OHLCV")
async def candle_status(
    request: Request,
    exchange_id: str = Query(default="binance", min_length=1, max_length=50),
    market_type: str = Query(default="spot"),
    symbol: str = Query(..., min_length=3, max_length=100),
    timeframe: str = Query(default="1h"),
) -> dict[str, object]:
    symbol, timeframe, market_type = _validate_market(symbol, timeframe, market_type)
    repository, _, _, _ = _dependencies(request)
    exchange_id = exchange_id.strip().lower()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1_000)
    gaps = await repository.find_missing_ranges(
        exchange_id,
        market_type,
        symbol,
        timeframe,
        now_ms=now_ms,
        max_ranges=20,
    )
    metadata = await repository.get_history_metadata(exchange_id, market_type, symbol, timeframe)
    local_earliest = await repository.get_first_open_time(
        exchange_id, market_type, symbol, timeframe
    )
    return {
        "first_open_time": await repository.get_first_open_time(
            exchange_id, market_type, symbol, timeframe
        ),
        "last_open_time": await repository.get_last_open_time(
            exchange_id, market_type, symbol, timeframe
        ),
        "last_closed_open_time": await repository.get_last_open_time(
            exchange_id,
            market_type,
            symbol,
            timeframe,
            closed_only=True,
        ),
        "count": await repository.count(exchange_id, market_type, symbol, timeframe),
        "has_gaps": bool(gaps),
        "missing_ranges": [[start, end] for start, end in gaps],
        "local_earliest_time": local_earliest,
        "exchange_earliest_time": metadata.exchange_earliest_time,
        "exchange_earliest_verified": metadata.exchange_earliest_verified,
        "has_more_before": metadata.has_more_before,
        "last_error": metadata.last_error,
    }


@router.get("/export.csv", summary="Exporter les bougies locales au format CSV")
async def export_candles(
    request: Request,
    exchange_id: str = Query(default="binance", min_length=1, max_length=50),
    market_type: str = Query(default="spot"),
    symbol: str = Query(..., min_length=3, max_length=100),
    timeframe: str = Query(default="1h"),
    from_time: int | None = Query(default=None, ge=0),
    to_time: int | None = Query(default=None, ge=0),
    closed_only: bool = Query(default=False),
    limit: int | None = Query(default=None, ge=1),
) -> StreamingResponse:
    symbol, timeframe, market_type = _validate_market(symbol, timeframe, market_type)
    _validate_range(from_time, to_time)
    repository, candle_sync, _, _ = _dependencies(request)
    maximum = candle_sync.settings.candle_max_api_limit
    effective_limit = min(limit or maximum, maximum)
    candles = await repository.get_range(
        exchange_id.strip().lower(),
        market_type,
        symbol,
        timeframe,
        from_time=from_time,
        to_time=to_time,
        limit=effective_limit,
        closed_only=closed_only,
    )
    filename = f"candles-{symbol.replace('/', '-')}-{timeframe}.csv"
    return StreamingResponse(
        _csv_rows(candles),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/window", summary="Lire une fenêtre autour d'une date")
async def get_candle_window(
    request: Request,
    exchange_id: str = Query(default="binance", min_length=1, max_length=50),
    market_type: str = Query(default="spot"),
    symbol: str = Query(..., min_length=3, max_length=100),
    timeframe: str = Query(default="1h"),
    anchor_time: int = Query(..., ge=0),
    before_count: int | None = Query(default=None, ge=1),
    after_count: int | None = Query(default=None, ge=1),
    closed_only: bool = Query(default=False),
    include_indicators: bool = Query(default=True),
    profile: str | None = Query(default=None),
) -> dict[str, object]:
    symbol, timeframe, market_type = _validate_market(symbol, timeframe, market_type)
    repository, candle_sync, _, market_history = _dependencies(request)
    effective_before = before_count or candle_sync.settings.market_history_window_before
    effective_after = after_count or candle_sync.settings.market_history_window_after
    maximum = candle_sync.settings.candle_max_api_limit
    if effective_before + effective_after > maximum:
        raise HTTPException(
            status_code=422,
            detail=f"before_count + after_count ne peut pas dépasser {maximum}",
        )
    exchange_id = exchange_id.strip().lower()
    try:
        indicator_profile = (
            MarketIndicatorConfig.model_validate_json(profile)
            if profile
            else MarketIndicatorConfig()
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Profil d'indicateurs invalide: {exc}"
        ) from exc
    try:
        result = await market_history.get_around(
            exchange_id=exchange_id,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
            anchor_time=anchor_time,
            before_count=effective_before,
            after_count=effective_after,
            closed_only=closed_only,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Synchronisation historique impossible: {exc}",
        ) from exc
    return await _history_response(
        repository,
        candle_sync,
        result,
        exchange_id=exchange_id,
        market_type=market_type,
        symbol=symbol,
        timeframe=timeframe,
        limit=effective_before + effective_after,
        include_indicators=include_indicators,
        anchor_time=anchor_time,
        profile=indicator_profile,
    )


@router.get("", summary="Lire les bougies d'un marché")
async def get_candles(
    request: Request,
    exchange_id: str = Query(default="binance", min_length=1, max_length=50),
    market_type: str = Query(default="spot"),
    symbol: str = Query(..., min_length=3, max_length=100),
    timeframe: str = Query(default="1h"),
    limit: int | None = Query(default=None, ge=1),
    from_time: int | None = Query(default=None, ge=0),
    to_time: int | None = Query(default=None, ge=0),
    before: int | None = Query(default=None, ge=0),
    after: int | None = Query(default=None, ge=0),
    closed_only: bool = Query(default=False),
    include_indicators: bool = Query(default=True),
    sync_if_missing: bool = Query(default=False),
    profile: str | None = Query(default=None),
) -> dict[str, object]:
    symbol, timeframe, market_type = _validate_market(symbol, timeframe, market_type)
    _validate_range(from_time, to_time)
    if before is not None and after is not None:
        raise HTTPException(status_code=422, detail="before et after sont mutuellement exclusifs")
    if (before is not None or after is not None) and (from_time is not None or to_time is not None):
        raise HTTPException(
            status_code=422,
            detail="before/after ne peuvent pas être combinés avec from_time/to_time",
        )
    repository, candle_sync, _, market_history = _dependencies(request)
    try:
        indicator_profile = (
            MarketIndicatorConfig.model_validate_json(profile)
            if profile
            else MarketIndicatorConfig()
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Profil d'indicateurs invalide: {exc}"
        ) from exc
    maximum = candle_sync.settings.candle_max_api_limit
    effective_limit = limit or candle_sync.settings.candle_default_limit
    if effective_limit > maximum:
        raise HTTPException(status_code=422, detail=f"limit ne peut pas dépasser {maximum}")
    exchange_id = exchange_id.strip().lower()
    try:
        if before is not None:
            result = await market_history.get_before(
                exchange_id=exchange_id,
                market_type=market_type,
                symbol=symbol,
                timeframe=timeframe,
                before=before,
                limit=effective_limit,
                closed_only=closed_only,
                sync_missing=sync_if_missing,
            )
        elif after is not None:
            result = await market_history.get_after(
                exchange_id=exchange_id,
                market_type=market_type,
                symbol=symbol,
                timeframe=timeframe,
                after=after,
                limit=effective_limit,
                closed_only=closed_only,
                sync_missing=sync_if_missing,
            )
        elif from_time is not None or to_time is not None:
            candles = await repository.get_range(
                exchange_id,
                market_type,
                symbol,
                timeframe,
                from_time=from_time,
                to_time=to_time,
                limit=effective_limit,
                closed_only=closed_only,
            )
            result = await market_history.from_local(
                exchange_id=exchange_id,
                market_type=market_type,
                symbol=symbol,
                timeframe=timeframe,
                candles=candles,
                closed_only=closed_only,
            )
        else:
            result = await market_history.get_latest(
                exchange_id=exchange_id,
                market_type=market_type,
                symbol=symbol,
                timeframe=timeframe,
                limit=effective_limit,
                closed_only=closed_only,
                sync_missing=sync_if_missing,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ScannerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Synchronisation historique impossible: {exc}",
        ) from exc
    return await _history_response(
        repository,
        candle_sync,
        result,
        exchange_id=exchange_id,
        market_type=market_type,
        symbol=symbol,
        timeframe=timeframe,
        limit=effective_limit,
        include_indicators=include_indicators,
        profile=indicator_profile,
    )


async def _history_response(
    repository: CandleRepository,
    candle_sync: CandleSyncService,
    result: MarketHistoryResult,
    *,
    exchange_id: str,
    market_type: str,
    symbol: str,
    timeframe: str,
    limit: int,
    include_indicators: bool,
    anchor_time: int | None = None,
    profile: MarketIndicatorConfig | None = None,
) -> dict[str, object]:
    profile = profile or MarketIndicatorConfig()
    candles = result.candles
    oldest = candles[0].open_time if candles else None
    newest = candles[-1].open_time if candles else None
    indicators: dict[str, list[dict[str, float | int]]] = {}
    markers: list[dict[str, object]] = []
    snapshot = calculate_market_snapshots(
        [candle.to_ohlcv() for candle in candles],
        timeframe,
        profile,
    )
    if include_indicators and candles:
        indicators, markers, snapshot = await _historical_analysis(
            repository,
            candles,
            exchange_id=exchange_id,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
            warmup_bars=candle_sync.settings.candle_indicator_warmup_bars,
            profile=profile,
        )
    gaps = await repository.find_missing_ranges(
        exchange_id,
        market_type,
        symbol,
        timeframe,
        now_ms=int(datetime.now(timezone.utc).timestamp() * 1_000),
        max_ranges=20,
    )
    has_more_before = result.has_more_before
    has_more_after = bool(
        newest is not None
        and (
            (result.latest_available is not None and newest < result.latest_available)
            or not result.recent_complete
        )
    )
    return {
        "exchange_id": exchange_id,
        "market_type": market_type,
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": [candle.to_chart() for candle in candles],
        "indicators": indicators,
        "markers": markers,
        "snapshot": snapshot,
        "profile": profile.model_dump(mode="json"),
        "page": {
            "limit": limit,
            "count": len(candles),
            "oldest_open_time": oldest,
            "newest_open_time": newest,
            "next_before": oldest,
            "next_after": newest,
            "has_more_before": has_more_before,
            "has_more_after": has_more_after,
        },
        "coverage": {
            "earliest_open_time": result.local_earliest_time,
            "latest_open_time": result.latest_available,
            "available_from": result.local_earliest_time,
            "available_to": result.latest_available,
            "local_earliest_time": result.local_earliest_time,
            "exchange_earliest_time": result.exchange_earliest_time,
            "exchange_earliest_verified": result.exchange_earliest_verified,
            "total_candles": result.local_candle_count,
            "local_candle_count": result.local_candle_count,
            "is_complete": (
                result.exchange_earliest_verified
                and not result.has_more_before
                and result.recent_complete
                and not gaps
            ),
            "is_earliest_known": result.exchange_earliest_verified,
            "is_recent_complete": result.recent_complete,
            "gap_count": len(gaps),
            "history_last_error": result.history_last_error,
        },
        "source": {
            "read_from_sqlite": True,
            "downloaded_from_exchange": result.downloaded_from_exchange,
        },
        "anchor_time": anchor_time,
        "anchor_before_available": result.anchor_before_available,
    }


async def _historical_analysis(
    repository: CandleRepository,
    candles: list[Candle],
    *,
    exchange_id: str,
    market_type: str,
    symbol: str,
    timeframe: str,
    warmup_bars: int,
    profile: MarketIndicatorConfig | None = None,
) -> tuple[
    dict[str, list[dict[str, float | int]]],
    list[dict[str, object]],
    dict[str, Any],
]:
    profile = profile or MarketIndicatorConfig()
    oldest = candles[0].open_time
    warmup = await repository.get_candles_before(
        exchange_id=exchange_id,
        market_type=market_type,
        symbol=symbol,
        timeframe=timeframe,
        before_open_time=oldest,
        limit=warmup_bars,
        closed_only=False,
    )
    combined_by_time = {item.open_time: item for item in (*warmup, *candles)}
    combined = [combined_by_time[key] for key in sorted(combined_by_time)]
    dataframe, bundle = calculate_indicator_bundle([item.to_ohlcv() for item in combined], profile)
    minimum_seconds = oldest // 1_000
    maximum_seconds = candles[-1].open_time // 1_000
    indicator_data = {
        name: [
            point for point in points if minimum_seconds <= int(point["time"]) <= maximum_seconds
        ]
        for name, points in bundle_to_chart_data(dataframe, bundle, limit=None).items()
    }
    closed = [item for item in combined if item.is_closed]
    closed_dataframe, closed_bundle = calculate_indicator_bundle(
        [item.to_ohlcv() for item in closed], profile
        )
    marker_data = sort_markers(
        build_indicator_event_markers(
            closed_dataframe,
            closed_bundle,
            minimum_time=minimum_seconds,
        )
        + build_divergence_markers(
            closed_dataframe,
            closed_bundle,
            minimum_time=minimum_seconds,
        )
    )
    markers = [marker for marker in marker_data if int(marker["time"]) <= maximum_seconds]
    snapshot = calculate_market_snapshots(
        [item.to_ohlcv() for item in combined],
        timeframe,
        profile,
    )
    return indicator_data, markers, snapshot


async def _csv_rows(candles: list[Candle]) -> AsyncIterator[str]:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        ["open_time", "open", "high", "low", "close", "volume", "close_time", "is_closed"]
    )
    yield buffer.getvalue()
    for candle in candles:
        buffer.seek(0)
        buffer.truncate(0)
        writer.writerow(
            [
                candle.open_time,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                candle.close_time,
                int(candle.is_closed),
            ]
        )
        yield buffer.getvalue()
