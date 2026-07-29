"""Synchronisation incrémentale des bougies CCXT vers SQLite."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Any, Callable, Literal, cast

import ccxt.async_support as ccxt

from app.core.config import AppSettings, get_app_settings
from app.core.exceptions import (
    InsufficientHistoryError,
    InvalidOhlcvError,
    PaginationStalledError,
)
from app.core.settings import ScanConfig
from app.domain.candles import Candle, candle_from_ohlcv, timeframe_milliseconds
from app.repositories.candle_repository import CandleRepository
from app.services.exchange import create_exchange

logger = logging.getLogger(__name__)
ExchangeFactory = Callable[[ScanConfig], Any]


class CandleSyncService:
    """Orchestre pagination, retries, UPSERT et réparation des trous."""

    def __init__(
        self,
        repository: CandleRepository,
        settings: AppSettings | None = None,
        exchange_factory: ExchangeFactory = create_exchange,
    ) -> None:
        """Configure le service sans ouvrir d'exchange ni de connexion SQLite."""
        self.repository = repository
        self.settings = settings or get_app_settings()
        self.exchange_factory = exchange_factory

    async def ensure_history(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        required_bars: int,
        closed_only: bool = True,
        exchange: Any | None = None,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> list[Candle]:
        """Garantit un historique minimal, puis le relit depuis SQLite."""
        has_enough = await self.repository.has_sufficient_history(
            exchange_id,
            market_type,
            symbol,
            timeframe,
            required_bars,
            closed_only=closed_only,
        )
        latest = await self.repository.get_last_open_time(
            exchange_id,
            market_type,
            symbol,
            timeframe,
            closed_only=closed_only,
        )
        fresh_after = self._now_ms() - 2 * timeframe_milliseconds(timeframe)
        if has_enough and latest is not None and latest >= fresh_after:
            return await self.repository.get_latest(
                exchange_id,
                market_type,
                symbol,
                timeframe,
                required_bars,
                closed_only=closed_only,
            )

        if not self.settings.candle_sync_enabled:
            raise InsufficientHistoryError(
                f"Historique local insuffisant pour {symbol} {timeframe}"
            )

        owned_exchange = exchange is None
        active_exchange = exchange or self._create_exchange(exchange_id, market_type)
        try:
            await self.sync_latest(
                exchange_id=exchange_id,
                market_type=market_type,
                symbol=symbol,
                timeframe=timeframe,
                required_bars=required_bars,
                exchange=active_exchange,
                max_retries=max_retries,
                retry_delay_seconds=retry_delay_seconds,
            )
            await self.repair_missing(
                exchange_id=exchange_id,
                market_type=market_type,
                symbol=symbol,
                timeframe=timeframe,
                exchange=active_exchange,
            )
        finally:
            if owned_exchange:
                await active_exchange.close()

        candles = await self.repository.get_latest(
            exchange_id,
            market_type,
            symbol,
            timeframe,
            required_bars,
            closed_only=closed_only,
        )
        if len(candles) < required_bars:
            raise InsufficientHistoryError(
                f"{len(candles)}/{required_bars} bougies disponibles pour {symbol} {timeframe}"
            )
        return candles

    async def sync_latest(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        required_bars: int,
        exchange: Any,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> int:
        """Met à jour depuis la dernière bougie connue avec un chevauchement."""
        interval = timeframe_milliseconds(timeframe)
        last = await self.repository.get_last_open_time(exchange_id, market_type, symbol, timeframe)
        now_ms = self._now_ms()
        since = last if last is not None else max(0, now_ms - interval * (required_bars + 2))
        return await self.backfill(
            exchange_id=exchange_id,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
            since=since,
            until=now_ms + interval,
            exchange=exchange,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay_seconds,
        )

    async def backfill(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        since: int,
        until: int | None,
        exchange: Any,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> int:
        """Télécharge explicitement des pages ``since`` croissantes et bornées."""
        interval = timeframe_milliseconds(timeframe)
        cursor = since
        processed = 0
        pages = 0
        previous_last: int | None = None

        while pages < self.settings.candle_sync_max_pages:
            if until is not None and cursor >= until:
                break
            page = await self._fetch_page(
                exchange,
                symbol,
                timeframe,
                cursor,
                self.settings.candle_sync_page_limit,
                max_retries,
                retry_delay_seconds,
            )
            pages += 1
            if not page:
                break

            candles = self._normalize_page(
                page,
                exchange_id=exchange_id,
                market_type=market_type,
                symbol=symbol,
                timeframe=timeframe,
            )
            if until is not None:
                candles = [candle for candle in candles if candle.open_time < until]
            if not candles:
                break

            last = candles[-1].open_time
            if previous_last is not None and last <= previous_last:
                raise PaginationStalledError(
                    f"Pagination bloquée pour {symbol} {timeframe} à {last}"
                )
            previous_last = last
            processed += await self.repository.upsert_many(candles)
            cursor = last + interval
            logger.info(
                "Synchronisation %s %s: page %s, %s bougies traitées",
                symbol,
                timeframe,
                pages,
                len(candles),
            )
            if len(page) < self.settings.candle_sync_page_limit:
                break
        else:
            raise PaginationStalledError(
                f"Limite de {self.settings.candle_sync_max_pages} pages atteinte"
            )

        return processed

    async def repair_range(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        from_time: int,
        to_time: int,
        exchange: Any,
    ) -> int:
        """Répare une plage détectée sans créer de bougies artificielles."""
        return await self.backfill(
            exchange_id=exchange_id,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
            since=from_time,
            until=to_time,
            exchange=exchange,
        )

    async def repair_missing(
        self,
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        exchange: Any,
        max_ranges: int = 5,
    ) -> int:
        """Détecte puis répare au plus ``max_ranges`` trous internes."""
        if not self.settings.candle_gap_repair_enabled:
            return 0
        ranges = await self.repository.find_missing_ranges(
            exchange_id,
            market_type,
            symbol,
            timeframe,
            now_ms=self._now_ms(),
            max_ranges=max_ranges,
        )
        if ranges:
            logger.info("%s trou(s) détecté(s) pour %s %s", len(ranges), symbol, timeframe)
        total = 0
        for start, end in ranges:
            total += await self.repair_range(
                exchange_id=exchange_id,
                market_type=market_type,
                symbol=symbol,
                timeframe=timeframe,
                from_time=start,
                to_time=end,
                exchange=exchange,
            )
        return total

    async def _fetch_page(
        self,
        exchange: Any,
        symbol: str,
        timeframe: str,
        since: int,
        limit: int,
        max_retries: int,
        retry_delay_seconds: float,
    ) -> list[list[Any]]:
        """Récupère une page avec backoff sur les erreurs CCXT transitoires."""
        delay = retry_delay_seconds
        for attempt in range(max_retries + 1):
            try:
                result = await exchange.fetch_ohlcv(
                    symbol,
                    timeframe=timeframe,
                    since=since,
                    limit=limit,
                )
                return list(result or [])
            except asyncio.CancelledError:
                raise
            except (ccxt.RateLimitExceeded, ccxt.NetworkError):
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(min(delay, 30.0) * random.uniform(0.9, 1.1))
                delay = min(delay * 2, 30.0)
        return []

    async def fetch_page(
        self,
        exchange: Any,
        symbol: str,
        timeframe: str,
        since: int,
        limit: int,
        max_retries: int,
        retry_delay_seconds: float,
    ) -> list[list[Any]]:
        """Expose la récupération résiliente d'une page aux orchestrateurs internes."""
        return await self._fetch_page(
            exchange,
            symbol,
            timeframe,
            since,
            limit,
            max_retries,
            retry_delay_seconds,
        )

    def _normalize_page(
        self,
        rows: list[list[Any]],
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
    ) -> list[Candle]:
        """Valide, déduplique et trie une page OHLCV."""
        by_time: dict[int, Candle] = {}
        now_ms = self._now_ms()
        for row in rows:
            try:
                candle = candle_from_ohlcv(
                    row,
                    exchange_id=exchange_id,
                    market_type=market_type,
                    symbol=symbol,
                    timeframe=timeframe,
                    now_ms=now_ms,
                )
            except (TypeError, ValueError, OverflowError) as exc:
                raise InvalidOhlcvError(f"Réponse OHLCV invalide pour {symbol}") from exc
            by_time[candle.open_time] = candle
        return [by_time[key] for key in sorted(by_time)]

    def normalize_page(
        self,
        rows: list[list[Any]],
        *,
        exchange_id: str,
        market_type: str,
        symbol: str,
        timeframe: str,
    ) -> list[Candle]:
        """Expose la validation canonique d'une page aux backfills."""
        return self._normalize_page(
            rows,
            exchange_id=exchange_id,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
        )

    def _create_exchange(self, exchange_id: str, market_type: str) -> Any:
        """Crée un exchange CCXT public pour une synchronisation autonome."""
        config = ScanConfig(
            exchange_id=exchange_id,
            market_type=cast(Literal["spot", "swap", "future"], market_type),
            use_rsi=False,
            use_ma=False,
            use_macd=False,
            use_bollinger=False,
            use_stochastic=False,
            use_confluence_score=False,
        )
        return self.exchange_factory(config)

    def create_market_exchange(self, exchange_id: str, market_type: str) -> Any:
        """Expose une instance publique bornée à une synchronisation ciblée."""
        return self._create_exchange(exchange_id, market_type)

    @staticmethod
    def _now_ms() -> int:
        """Retourne l'heure UTC courante en millisecondes Unix."""
        return int(datetime.now(timezone.utc).timestamp() * 1_000)
