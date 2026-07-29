"""Historique de marché SQLite complété à la demande, cible par cible."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import AsyncIterator

from app.domain.candles import Candle, timeframe_milliseconds
from app.repositories.candle_repository import CandleRepository
from app.services.candle_sync import CandleSyncService


@dataclass(frozen=True, slots=True)
class MarketHistoryResult:
    """Résultat relu depuis SQLite après une éventuelle synchronisation."""

    candles: list[Candle]
    downloaded_from_exchange: int
    local_earliest_time: int | None
    exchange_earliest_time: int | None
    exchange_earliest_verified: bool
    has_more_before: bool
    history_last_error: str | None
    latest_available: int | None
    local_candle_count: int
    recent_complete: bool
    anchor_before_available: bool = False


@dataclass(slots=True)
class _LockEntry:
    lock: asyncio.Lock
    users: int = 0


class MarketHistoryService:
    """Télécharge seulement les plages demandées et les persiste avant lecture."""

    def __init__(
        self,
        repository: CandleRepository,
        candle_sync: CandleSyncService,
    ) -> None:
        self.repository = repository
        self.candle_sync = candle_sync
        self._locks: dict[tuple[str, str, str, str], _LockEntry] = {}
        self._locks_guard = asyncio.Lock()

    async def get_latest(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        limit: int,
        closed_only: bool,
        sync_missing: bool,
    ) -> MarketHistoryResult:
        downloaded = 0
        if sync_missing:
            async with self._target_lock(exchange_id, market_type, symbol, timeframe):
                exchange = self.candle_sync.create_market_exchange(exchange_id, market_type)
                try:
                    await exchange.load_markets()
                    self._validate_exchange(exchange, symbol, timeframe)
                    downloaded = await self.candle_sync.sync_latest(
                        exchange_id=exchange_id,
                        market_type=market_type,
                        symbol=symbol,
                        timeframe=timeframe,
                        required_bars=limit,
                        exchange=exchange,
                    )
                finally:
                    await exchange.close()
        candles = await self.repository.get_latest(
            exchange_id,
            market_type,
            symbol,
            timeframe,
            limit,
            closed_only=closed_only,
        )
        return await self._result(
            candles,
            downloaded,
            exchange_id,
            market_type,
            symbol,
            timeframe,
            closed_only,
        )

    async def get_before(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        before: int,
        limit: int,
        closed_only: bool,
        sync_missing: bool,
    ) -> MarketHistoryResult:
        downloaded = 0
        if sync_missing:
            async with self._target_lock(exchange_id, market_type, symbol, timeframe):
                metadata = await self.repository.refresh_history_metadata(
                    exchange_id, market_type, symbol, timeframe
                )
                local_page = await self.repository.get_candles_before(
                    exchange_id=exchange_id,
                    market_type=market_type,
                    symbol=symbol,
                    timeframe=timeframe,
                    before_open_time=before,
                    limit=limit,
                    closed_only=closed_only,
                )
                if len(local_page) < limit and metadata.has_more_before:
                    local_earliest = await self.repository.get_first_open_time(
                        exchange_id,
                        market_type,
                        symbol,
                        timeframe,
                        closed_only=closed_only,
                    )
                    page_end = min(before, local_earliest) if local_earliest is not None else before
                    try:
                        downloaded = await self._download_older_range(
                            exchange_id,
                            market_type,
                            symbol,
                            timeframe,
                            page_end=page_end,
                            limit=limit,
                        )
                        await self.repository.clear_history_error(
                            exchange_id, market_type, symbol, timeframe
                        )
                    except Exception as exc:
                        await self.repository.set_history_error(
                            exchange_id,
                            market_type,
                            symbol,
                            timeframe,
                            str(exc),
                        )
                        raise
                    await self.repository.refresh_history_metadata(
                        exchange_id, market_type, symbol, timeframe
                    )
        candles = await self.repository.get_candles_before(
            exchange_id=exchange_id,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
            before_open_time=before,
            limit=limit,
            closed_only=closed_only,
        )
        return await self._result(
            candles,
            downloaded,
            exchange_id,
            market_type,
            symbol,
            timeframe,
            closed_only,
        )

    async def get_after(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        after: int,
        limit: int,
        closed_only: bool,
        sync_missing: bool,
    ) -> MarketHistoryResult:
        downloaded = 0
        if sync_missing:
            async with self._target_lock(exchange_id, market_type, symbol, timeframe):
                local = await self.repository.get_candles_after(
                    exchange_id=exchange_id,
                    market_type=market_type,
                    symbol=symbol,
                    timeframe=timeframe,
                    after_open_time=after,
                    limit=limit,
                    closed_only=closed_only,
                )
                if len(local) < limit:
                    interval = timeframe_milliseconds(timeframe)
                    end = min(self._now_ms() + interval, after + (limit + 1) * interval)
                    downloaded = await self._download_range(
                        exchange_id,
                        market_type,
                        symbol,
                        timeframe,
                        after + interval,
                        end,
                    )
        candles = await self.repository.get_candles_after(
            exchange_id=exchange_id,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
            after_open_time=after,
            limit=limit,
            closed_only=closed_only,
        )
        return await self._result(
            candles,
            downloaded,
            exchange_id,
            market_type,
            symbol,
            timeframe,
            closed_only,
        )

    async def get_around(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        anchor_time: int,
        before_count: int,
        after_count: int,
        closed_only: bool,
    ) -> MarketHistoryResult:
        interval = timeframe_milliseconds(timeframe)
        anchor = anchor_time - anchor_time % interval
        start = max(0, anchor - before_count * interval)
        end = min(self._now_ms() + interval, anchor + after_count * interval)
        downloaded = 0
        async with self._target_lock(exchange_id, market_type, symbol, timeframe):
            complete = await self.repository.has_complete_range(
                exchange_id=exchange_id,
                market_type=market_type,
                symbol=symbol,
                timeframe=timeframe,
                start_time=start,
                end_time=end,
                closed_only=closed_only,
            )
            if not complete:
                downloaded = await self._download_range(
                    exchange_id,
                    market_type,
                    symbol,
                    timeframe,
                    start,
                    end,
                )
        candles = await self.repository.get_window(
            exchange_id=exchange_id,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
            anchor_open_time=anchor,
            before_count=before_count,
            after_count=after_count,
            closed_only=closed_only,
        )
        result = await self._result(
            candles,
            downloaded,
            exchange_id,
            market_type,
            symbol,
            timeframe,
            closed_only,
        )
        return replace(
            result,
            anchor_before_available=bool(
                not candles
                and result.exchange_earliest_verified
                and result.exchange_earliest_time is not None
                and anchor < result.exchange_earliest_time
            ),
        )

    async def from_local(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        candles: list[Candle],
        closed_only: bool,
    ) -> MarketHistoryResult:
        """Construit les métadonnées d'une lecture locale historique compatible."""
        return await self._result(
            candles,
            0,
            exchange_id,
            market_type,
            symbol,
            timeframe,
            closed_only,
        )

    async def _download_range(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
    ) -> int:
        if start >= end or not self.candle_sync.settings.candle_sync_enabled:
            return 0
        exchange = self.candle_sync.create_market_exchange(exchange_id, market_type)
        try:
            await exchange.load_markets()
            self._validate_exchange(exchange, symbol, timeframe)
            return await self.candle_sync.backfill(
                exchange_id=exchange_id,
                market_type=market_type,
                symbol=symbol,
                timeframe=timeframe,
                since=start,
                until=end,
                exchange=exchange,
            )
        finally:
            await exchange.close()

    async def _download_older_range(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        *,
        page_end: int,
        limit: int,
    ) -> int:
        """Vérifie la borne exchange puis télécharge uniquement la page précédente."""
        if not self.candle_sync.settings.candle_sync_enabled:
            return 0
        interval = timeframe_milliseconds(timeframe)
        exchange = self.candle_sync.create_market_exchange(exchange_id, market_type)
        try:
            await exchange.load_markets()
            self._validate_exchange(exchange, symbol, timeframe)
            metadata = await self.repository.get_history_metadata(
                exchange_id, market_type, symbol, timeframe
            )
            if not metadata.exchange_earliest_verified:
                discovery_rows = await self.candle_sync.fetch_page(
                    exchange,
                    symbol,
                    timeframe,
                    0,
                    min(10, self.candle_sync.settings.candle_sync_page_limit),
                    3,
                    1.0,
                )
                if discovery_rows:
                    discovery = self.candle_sync.normalize_page(
                        discovery_rows,
                        exchange_id=exchange_id,
                        market_type=market_type,
                        symbol=symbol,
                        timeframe=timeframe,
                    )
                    if discovery:
                        await self.repository.set_exchange_earliest_verified(
                            exchange_id,
                            market_type,
                            symbol,
                            timeframe,
                            discovery[0].open_time,
                        )
                        metadata = await self.repository.get_history_metadata(
                            exchange_id, market_type, symbol, timeframe
                        )
            start = max(0, page_end - limit * interval)
            if metadata.exchange_earliest_verified and metadata.exchange_earliest_time is not None:
                start = max(start, metadata.exchange_earliest_time)
            if start >= page_end:
                return 0
            return await self.candle_sync.backfill(
                exchange_id=exchange_id,
                market_type=market_type,
                symbol=symbol,
                timeframe=timeframe,
                since=start,
                until=page_end,
                exchange=exchange,
            )
        finally:
            await exchange.close()

    async def _result(
        self,
        candles: list[Candle],
        downloaded: int,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        closed_only: bool,
    ) -> MarketHistoryResult:
        local_earliest, latest, count, metadata = await asyncio.gather(
            self.repository.get_first_open_time(
                exchange_id,
                market_type,
                symbol,
                timeframe,
                closed_only=closed_only,
            ),
            self.repository.get_last_open_time(
                exchange_id,
                market_type,
                symbol,
                timeframe,
                closed_only=closed_only,
            ),
            self.repository.count(
                exchange_id,
                market_type,
                symbol,
                timeframe,
                closed_only=closed_only,
            ),
            self.repository.get_history_metadata(exchange_id, market_type, symbol, timeframe),
        )
        interval = timeframe_milliseconds(timeframe)
        return MarketHistoryResult(
            candles=candles,
            downloaded_from_exchange=downloaded,
            local_earliest_time=local_earliest,
            exchange_earliest_time=metadata.exchange_earliest_time,
            exchange_earliest_verified=metadata.exchange_earliest_verified,
            has_more_before=metadata.has_more_before,
            history_last_error=metadata.last_error,
            latest_available=latest,
            local_candle_count=count,
            recent_complete=bool(latest is not None and latest >= self._now_ms() - 2 * interval),
        )

    @asynccontextmanager
    async def _target_lock(
        self,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
    ) -> AsyncIterator[None]:
        key = (exchange_id, market_type, symbol, timeframe)
        async with self._locks_guard:
            entry = self._locks.setdefault(key, _LockEntry(asyncio.Lock()))
            entry.users += 1
        await entry.lock.acquire()
        try:
            yield
        finally:
            entry.lock.release()
            async with self._locks_guard:
                entry.users -= 1
                if entry.users == 0 and not entry.lock.locked():
                    self._locks.pop(key, None)

    @staticmethod
    def _validate_exchange(exchange: object, symbol: str, timeframe: str) -> None:
        markets = getattr(exchange, "markets", {})
        if symbol not in markets:
            raise ValueError(f"Symbole inconnu sur l'exchange : {symbol}")
        timeframes = getattr(exchange, "timeframes", {})
        if timeframes and timeframe not in timeframes:
            raise ValueError(f"Timeframe indisponible sur l'exchange : {timeframe}")

    @staticmethod
    def _now_ms() -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1_000)
