from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import ccxt.async_support as ccxt

from app.core.config import AppSettings
from app.database.connection import Database
from app.domain.candles import Candle
from app.repositories.candle_repository import CandleRepository
from app.services.candle_sync import CandleSyncService
from app.services.market_history import MarketHistoryService


class FakeExchange:
    def __init__(self, rows: list[list[float | int]], calls: list[int]) -> None:
        self.rows = rows
        self.calls = calls
        self.markets = {"BTC/USDC": {}}
        self.timeframes = {"1m": "1m"}

    async def load_markets(self):
        return self.markets

    async def fetch_ohlcv(self, _symbol, *, timeframe, since, limit):
        self.calls.append(since)
        return [row for row in self.rows if int(row[0]) >= since][:limit]

    async def close(self):
        return None


class RoutedExchange:
    def __init__(
        self,
        datasets: dict[tuple[str, str], list[list[float | int]]],
        calls: list[tuple[str, str, int]],
        scripted: list[list[list[float | int]] | Exception] | None = None,
    ) -> None:
        self.datasets = datasets
        self.calls = calls
        self.scripted = scripted
        self.markets = {symbol: {} for symbol, _ in datasets}
        self.timeframes = {timeframe: timeframe for _, timeframe in datasets}

    async def load_markets(self):
        return self.markets

    async def fetch_ohlcv(self, symbol, *, timeframe, since, limit):
        self.calls.append((symbol, timeframe, since))
        if self.scripted is not None and self.scripted:
            result = self.scripted.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return [row for row in self.datasets[(symbol, timeframe)] if int(row[0]) >= since][:limit]

    async def close(self):
        return None


def candle(open_time: int) -> Candle:
    return Candle(
        "binance",
        "spot",
        "BTC/USDC",
        "1m",
        open_time,
        1,
        2,
        0.5,
        1.5,
        10,
        open_time + 60_000,
        True,
    )


class MarketHistoryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        database = Database(Path(self.temporary.name) / "history.sqlite3")
        await database.initialize()
        self.database = database
        self.repository = CandleRepository(database)
        self.calls: list[int] = []
        self.rows = [[timestamp, 1, 2, 0.5, 1.5, 10] for timestamp in range(0, 600_000, 60_000)]
        settings = AppSettings(
            database_path=database.path,
            candle_sync_page_limit=2,
            candle_sync_max_pages=20,
        )
        sync = CandleSyncService(
            self.repository,
            settings,
            exchange_factory=lambda _config: FakeExchange(self.rows, self.calls),
        )
        self.service = MarketHistoryService(self.repository, sync)

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temporary.cleanup()

    async def test_local_page_does_not_open_exchange(self) -> None:
        await self.repository.upsert_many([candle(0), candle(60_000), candle(120_000)])
        result = await self.service.get_before(
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1m",
            before=180_000,
            limit=3,
            closed_only=False,
            sync_missing=True,
        )
        self.assertEqual([item.open_time for item in result.candles], [0, 60_000, 120_000])
        self.assertEqual(self.calls, [])

    async def test_missing_page_is_downloaded_persisted_and_reused(self) -> None:
        await self.repository.upsert_many([candle(300_000), candle(360_000)])
        first = await self.service.get_before(
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1m",
            before=300_000,
            limit=3,
            closed_only=False,
            sync_missing=True,
        )
        calls_after_first = len(self.calls)
        second = await self.service.get_before(
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1m",
            before=300_000,
            limit=3,
            closed_only=False,
            sync_missing=True,
        )
        self.assertEqual(
            [item.open_time for item in first.candles],
            [120_000, 180_000, 240_000],
        )
        self.assertEqual(
            [item.open_time for item in second.candles],
            [120_000, 180_000, 240_000],
        )
        self.assertEqual(len(self.calls), calls_after_first)
        self.assertGreater(first.downloaded_from_exchange, 0)

    async def test_window_downloads_only_around_anchor(self) -> None:
        result = await self.service.get_around(
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1m",
            anchor_time=240_000,
            before_count=2,
            after_count=2,
            closed_only=False,
        )
        self.assertEqual(
            [item.open_time for item in result.candles],
            [120_000, 180_000, 240_000, 300_000],
        )
        self.assertGreater(result.downloaded_from_exchange, 0)

    async def test_concurrent_requests_share_one_target_download(self) -> None:
        first, second = await asyncio.gather(
            *[
                self.service.get_before(
                    exchange_id="binance",
                    market_type="spot",
                    symbol="BTC/USDC",
                    timeframe="1m",
                    before=300_000,
                    limit=3,
                    closed_only=False,
                    sync_missing=True,
                )
                for _ in range(2)
            ]
        )
        self.assertEqual(
            [item.open_time for item in first.candles],
            [120_000, 180_000, 240_000],
        )
        self.assertEqual(first.candles, second.candles)
        self.assertEqual(self.calls, [0, 120_000, 240_000])

    async def test_real_beginning_is_persisted_and_stops_older_requests(self) -> None:
        result = await self.service.get_before(
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1m",
            before=120_000,
            limit=3,
            closed_only=False,
            sync_missing=True,
        )
        self.assertEqual([item.open_time for item in result.candles], [0, 60_000])
        self.assertTrue(result.exchange_earliest_verified)
        self.assertFalse(result.has_more_before)
        calls = len(self.calls)
        repeated = await self.service.get_before(
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1m",
            before=60_000,
            limit=3,
            closed_only=False,
            sync_missing=True,
        )
        self.assertEqual(len(self.calls), calls)
        self.assertTrue(repeated.exchange_earliest_verified)
        self.assertFalse(repeated.has_more_before)


class GenericHistoricalBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary.name) / "generic.sqlite3")
        await self.database.initialize()
        self.repository = CandleRepository(self.database)
        self.calls: list[tuple[str, str, int]] = []

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temporary.cleanup()

    def service(
        self,
        datasets: dict[tuple[str, str], list[list[float | int]]],
        *,
        scripted: list[list[list[float | int]] | Exception] | None = None,
        page_limit: int = 2,
    ) -> MarketHistoryService:
        settings = AppSettings(
            database_path=self.database.path,
            candle_sync_page_limit=page_limit,
            candle_sync_max_pages=20,
        )
        sync = CandleSyncService(
            self.repository,
            settings,
            exchange_factory=lambda _config: RoutedExchange(datasets, self.calls, scripted),
        )
        return MarketHistoryService(self.repository, sync)

    @staticmethod
    def rows(interval: int, count: int) -> list[list[float | int]]:
        return [[index * interval, 1, 2, 0.5, 1.5, 10] for index in range(count)]

    @staticmethod
    def target_candle(symbol: str, timeframe: str, open_time: int, interval: int) -> Candle:
        return Candle(
            "binance",
            "spot",
            symbol,
            timeframe,
            open_time,
            1,
            2,
            0.5,
            1.5,
            10,
            open_time + interval,
            True,
        )

    async def test_progressively_recovers_missing_years_until_real_start(self) -> None:
        day = 86_400_000
        symbol = "ETH/USDC"
        service = self.service({(symbol, "1d"): self.rows(day, 7)})
        await self.repository.upsert_many(
            [
                self.target_candle(symbol, "1d", 5 * day, day),
                self.target_candle(symbol, "1d", 6 * day, day),
            ]
        )

        first = await service.get_before(
            exchange_id="binance",
            market_type="spot",
            symbol=symbol,
            timeframe="1d",
            before=5 * day,
            limit=2,
            closed_only=False,
            sync_missing=True,
        )
        second = await service.get_before(
            exchange_id="binance",
            market_type="spot",
            symbol=symbol,
            timeframe="1d",
            before=3 * day,
            limit=2,
            closed_only=False,
            sync_missing=True,
        )
        final = await service.get_before(
            exchange_id="binance",
            market_type="spot",
            symbol=symbol,
            timeframe="1d",
            before=day,
            limit=2,
            closed_only=False,
            sync_missing=True,
        )

        self.assertEqual([item.open_time for item in first.candles], [3 * day, 4 * day])
        self.assertEqual([item.open_time for item in second.candles], [day, 2 * day])
        self.assertEqual([item.open_time for item in final.candles], [0])
        self.assertEqual(final.local_earliest_time, 0)
        self.assertEqual(final.exchange_earliest_time, 0)
        self.assertTrue(final.exchange_earliest_verified)
        self.assertFalse(final.has_more_before)
        self.assertEqual(
            await self.repository.count("binance", "spot", symbol, "1d"),
            7,
        )

    async def test_multiple_symbols_and_timeframes_have_independent_bounds(self) -> None:
        hour = 3_600_000
        day = 86_400_000
        datasets = {
            ("ETH/USDC", "1h"): self.rows(hour, 5),
            ("SOL/USDC", "1d"): self.rows(day, 5),
        }
        service = self.service(datasets)
        for symbol, timeframe, interval in (
            ("ETH/USDC", "1h", hour),
            ("SOL/USDC", "1d", day),
        ):
            await self.repository.upsert_many(
                [self.target_candle(symbol, timeframe, 4 * interval, interval)]
            )
            result = await service.get_before(
                exchange_id="binance",
                market_type="spot",
                symbol=symbol,
                timeframe=timeframe,
                before=4 * interval,
                limit=2,
                closed_only=False,
                sync_missing=True,
            )
            self.assertTrue(result.exchange_earliest_verified)
            self.assertEqual(result.exchange_earliest_time, 0)
            self.assertTrue(result.has_more_before)
        self.assertIn(("ETH/USDC", "1h", 0), self.calls)
        self.assertIn(("SOL/USDC", "1d", 0), self.calls)

    async def test_temporary_empty_page_never_verifies_exchange_start(self) -> None:
        minute = 60_000
        symbol = "ADA/USDC"
        dataset = {(symbol, "1m"): self.rows(minute, 4)}
        scripted: list[list[list[float | int]] | Exception] = [[], []]
        service = self.service(dataset, scripted=scripted)
        await self.repository.upsert_many([self.target_candle(symbol, "1m", 3 * minute, minute)])
        result = await service.get_before(
            exchange_id="binance",
            market_type="spot",
            symbol=symbol,
            timeframe="1m",
            before=3 * minute,
            limit=2,
            closed_only=False,
            sync_missing=True,
        )
        self.assertFalse(result.exchange_earliest_verified)
        self.assertIsNone(result.exchange_earliest_time)
        self.assertTrue(result.has_more_before)

    async def test_network_error_is_recorded_without_verifying_start(self) -> None:
        minute = 60_000
        symbol = "XRP/USDC"
        errors = [ccxt.NetworkError("offline") for _ in range(4)]
        service = self.service(
            {(symbol, "1m"): self.rows(minute, 4)},
            scripted=errors,
        )
        await self.repository.upsert_many([self.target_candle(symbol, "1m", 3 * minute, minute)])
        with patch("app.services.candle_sync.asyncio.sleep", new=AsyncMock()):
            with self.assertRaises(ccxt.NetworkError):
                await service.get_before(
                    exchange_id="binance",
                    market_type="spot",
                    symbol=symbol,
                    timeframe="1m",
                    before=3 * minute,
                    limit=2,
                    closed_only=False,
                    sync_missing=True,
                )
        metadata = await self.repository.get_history_metadata("binance", "spot", symbol, "1m")
        self.assertFalse(metadata.exchange_earliest_verified)
        self.assertTrue(metadata.has_more_before)
        self.assertIn("offline", metadata.last_error or "")

    async def test_stalled_pagination_does_not_claim_local_start(self) -> None:
        minute = 60_000
        symbol = "DOT/USDC"
        row0 = self.rows(minute, 1)
        stalled = self.rows(minute, 5)[3:5]
        service = self.service(
            {(symbol, "1m"): self.rows(minute, 8)},
            scripted=[row0, stalled, stalled],
        )
        await self.repository.upsert_many([self.target_candle(symbol, "1m", 6 * minute, minute)])
        with self.assertRaises(Exception) as raised:
            await service.get_before(
                exchange_id="binance",
                market_type="spot",
                symbol=symbol,
                timeframe="1m",
                before=6 * minute,
                limit=3,
                closed_only=False,
                sync_missing=True,
            )
        self.assertIn("Pagination", str(raised.exception))
        metadata = await self.repository.get_history_metadata("binance", "spot", symbol, "1m")
        self.assertTrue(metadata.has_more_before)
        self.assertIn("Pagination", metadata.last_error or "")

    async def test_resume_upsert_does_not_create_duplicates(self) -> None:
        hour = 3_600_000
        symbol = "LINK/USDC"
        service = self.service({(symbol, "1h"): self.rows(hour, 5)})
        await self.repository.upsert_many([self.target_candle(symbol, "1h", 4 * hour, hour)])
        for _ in range(2):
            await service.get_before(
                exchange_id="binance",
                market_type="spot",
                symbol=symbol,
                timeframe="1h",
                before=4 * hour,
                limit=2,
                closed_only=False,
                sync_missing=True,
            )
        self.assertEqual(
            await self.repository.count("binance", "spot", symbol, "1h"),
            3,
        )


if __name__ == "__main__":
    unittest.main()
