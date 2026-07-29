from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import ccxt.async_support as ccxt

from app.core.config import AppSettings
from app.core.exceptions import InvalidOhlcvError, PaginationStalledError
from app.database.connection import Database
from app.domain.candles import Candle
from app.repositories.candle_repository import CandleRepository
from app.services.candle_sync import CandleSyncService
from app.core.settings import ScanConfig
from app.services.scanner import ScannerService


class FakeExchange:
    def __init__(self, rows: list[list[float]], page_size: int = 2) -> None:
        self.rows = rows
        self.page_size = page_size
        self.calls: list[int] = []
        self.closed = False

    async def fetch_ohlcv(
        self, _symbol: str, *, timeframe: str, since: int, limit: int
    ) -> list[list[float]]:
        self.calls.append(since)
        return [row for row in self.rows if row[0] >= since][: min(limit, self.page_size)]

    async def close(self) -> None:
        self.closed = True


def row(timestamp: int, close: float = 1.5) -> list[float]:
    return [timestamp, 1, 2, 0.5, close, 10]


class CandleSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary.name) / "sync.sqlite3")
        await self.database.initialize()
        self.repository = CandleRepository(self.database)
        self.settings = AppSettings(
            database_path=self.database.path,
            candle_sync_page_limit=2,
            candle_sync_max_pages=10,
        )
        self.service = CandleSyncService(self.repository, self.settings)
        self.now = int(datetime.now(timezone.utc).timestamp() * 1_000)
        self.base = self.now - 5 * 60_000

    async def asyncTearDown(self) -> None:
        await self.database.close()
        self.temporary.cleanup()

    async def test_sufficient_fresh_history_skips_exchange(self) -> None:
        candles = [
            Candle(
                "binance",
                "spot",
                "BTC/USDC",
                "1m",
                self.now - (index + 1) * 60_000,
                1,
                2,
                0.5,
                1.5,
                10,
                self.now - index * 60_000,
                True,
            )
            for index in range(3)
        ]
        await self.repository.upsert_many(candles)
        exchange = AsyncMock()
        result = await self.service.ensure_history(
            exchange_id="binance",
            market_type="spot",
            symbol="BTC/USDC",
            timeframe="1m",
            required_bars=3,
            exchange=exchange,
        )
        self.assertEqual(len(result), 3)
        exchange.fetch_ohlcv.assert_not_awaited()

    async def test_multi_page_resume_overlap_and_open_update(self) -> None:
        rows = [row(self.base + index * 60_000) for index in range(6)]
        exchange = FakeExchange(rows)
        with patch.object(self.service, "_now_ms", return_value=self.now):
            processed = await self.service.sync_latest(
                exchange_id="binance",
                market_type="spot",
                symbol="BTC/USDC",
                timeframe="1m",
                required_bars=5,
                exchange=exchange,
            )
        self.assertEqual(processed, 6)
        self.assertGreaterEqual(len(exchange.calls), 3)

        rows[-1][4] = 9
        second = FakeExchange(rows)
        with patch.object(self.service, "_now_ms", return_value=self.now):
            await self.service.sync_latest(
                exchange_id="binance",
                market_type="spot",
                symbol="BTC/USDC",
                timeframe="1m",
                required_bars=5,
                exchange=second,
            )
        self.assertEqual(second.calls[0], int(rows[-1][0]))
        latest = await self.repository.get_latest("binance", "spot", "BTC/USDC", "1m", 1)
        self.assertEqual(latest[0].close, 9)

    async def test_empty_page_stalled_page_invalid_data_and_retry(self) -> None:
        empty = FakeExchange([])
        self.assertEqual(
            await self.service.backfill(
                exchange_id="binance",
                market_type="spot",
                symbol="BTC/USDC",
                timeframe="1m",
                since=0,
                until=120_000,
                exchange=empty,
            ),
            0,
        )

        stalled = AsyncMock()
        stalled.fetch_ohlcv.return_value = [row(0), row(60_000)]
        with self.assertRaises(PaginationStalledError):
            await self.service.backfill(
                exchange_id="binance",
                market_type="spot",
                symbol="BTC/USDC",
                timeframe="1m",
                since=0,
                until=300_000,
                exchange=stalled,
            )

        invalid = FakeExchange([[0, 1]])
        with self.assertRaises(InvalidOhlcvError):
            await self.service.backfill(
                exchange_id="binance",
                market_type="spot",
                symbol="BTC/USDC",
                timeframe="1m",
                since=0,
                until=60_000,
                exchange=invalid,
            )

        retry = AsyncMock()
        retry.fetch_ohlcv.side_effect = [ccxt.NetworkError("offline"), []]
        with patch("app.services.candle_sync.asyncio.sleep", new=AsyncMock()) as sleep:
            await self.service.backfill(
                exchange_id="binance",
                market_type="spot",
                symbol="BTC/USDC",
                timeframe="1m",
                since=0,
                until=60_000,
                exchange=retry,
            )
        sleep.assert_awaited_once()

    async def test_repair_only_requests_detected_gap_and_cancellation_propagates(self) -> None:
        await self.repository.upsert_many(
            [
                Candle(
                    "binance",
                    "spot",
                    "BTC/USDC",
                    "1m",
                    timestamp,
                    1,
                    2,
                    0.5,
                    1.5,
                    10,
                    timestamp + 60_000,
                    True,
                )
                for timestamp in (0, 120_000)
            ]
        )
        exchange = FakeExchange([row(60_000)])
        with patch.object(self.service, "_now_ms", return_value=180_000):
            repaired = await self.service.repair_missing(
                exchange_id="binance",
                market_type="spot",
                symbol="BTC/USDC",
                timeframe="1m",
                exchange=exchange,
            )
        self.assertEqual(repaired, 1)
        self.assertEqual(exchange.calls, [60_000])

        blocking = AsyncMock()
        blocking.fetch_ohlcv.side_effect = asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await self.service.backfill(
                exchange_id="binance",
                market_type="spot",
                symbol="BTC/USDC",
                timeframe="1m",
                since=0,
                until=60_000,
                exchange=blocking,
            )

    async def test_scanner_reads_fresh_sqlite_without_exchange_call(self) -> None:
        candles = [
            Candle(
                "binance",
                "spot",
                "BTC/USDC",
                "1m",
                self.now - (60 - index) * 60_000,
                1,
                2,
                0.5,
                1.5,
                10,
                self.now - (59 - index) * 60_000,
                True,
            )
            for index in range(60)
        ]
        await self.repository.upsert_many(candles)
        exchange = AsyncMock()
        config = ScanConfig(
            timeframe="1m",
            min_ohlcv_bars=60,
            use_rsi=False,
            use_ma=False,
            use_macd=False,
            use_bollinger=False,
            use_stochastic=False,
            use_confluence_score=False,
        )
        scanner = ScannerService(config, candle_sync=self.service)
        status, result = await scanner.analyze_symbol(exchange, "BTC/USDC")
        self.assertEqual(status, "success")
        self.assertIsNotNone(result)
        exchange.fetch_ohlcv.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
